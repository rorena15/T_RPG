# core.py — DB 로드, 장비 조회, 파일 경로, 저장/로드
# 의존성: constants, db_init, sys_log, ui

import os
import sys
import json
import sqlite3
import time
import db_init
import constants
from i18n import t, db_t
from sys_log import sys_log, track

_eq_cache: dict = {}

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_save_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "stigma_save.json")
    return os.path.join(os.path.abspath("."), "stigma_save.json")


def get_settings_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "settings.json")
    return os.path.join(os.path.abspath("."), "settings.json")


def load_settings() -> dict:
    defaults = {"master_volume": 1.0, "bgm_volume": 0.5, "amb_volume": 0.5, "sfx_volume": 0.5, "vol_curve": 2,
                "mute": False, "text_speed": 1.0, "gm_mode": "full", "combat_speed": 1.0, "font_scale": 1.0,
                "screen_shake": True, "reduce_motion": False, "fullscreen": False, "autosave": 10}
    try:
        with open(get_settings_path(), encoding="utf-8") as f:
            saved = json.load(f)
    except Exception:
        return defaults
    if "vol_curve" not in saved:
        # 예전 음량 값(실제 크기 = min(1, 값 × 2))을 새 곡선(sound.VOL_CURVE)에서 같은 크기가 되는 값으로 옮긴다 (5% 단위)
        for k in ("bgm_volume", "sfx_volume"):
            if k in saved:
                saved[k] = round(min(1.0, saved[k] * 2) ** (1 / 1.7) * 20) / 20
        if "bgm_volume" in saved:
            saved["amb_volume"] = saved["bgm_volume"]   # 환경음은 예전에 음악 음량을 따랐다
    return {**defaults, **saved}


def save_settings(d: dict):
    try:
        with open(get_settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@track
def init_and_load_db():
    """게임 부팅 시 DB 및 master_formulas.json 무결성을 검증하고 메모리에 로드합니다."""
    sys_log(" [SYSTEM BOOT] Starting SSOT, memory integrity check...", level="INFO")
    time.sleep(0.4)

    formula_real_path = resource_path("master_formulas.json")
    if os.path.exists(formula_real_path):
        try:
            with open(formula_real_path, "r", encoding="utf-8") as f:
                constants.MASTER_FORMULAS = json.load(f)
            sys_log(" [SYSTEM LOG] Synchronization complete. Integrity check passed.", level="INFO")
        except Exception as e:
            sys_log(f" [SYSTEM WARN] Failed to load SSOT. Activating fallback engine ({e})", level="WARN")

    if not constants.MASTER_FORMULAS:
        constants.MASTER_FORMULAS = {
            "formulas": {
                "reputation_multiplier": {"divisor": 2000.0},
                "max_level": {"base": 15, "growth": 0.93}
            }
        }

    if db_init.init_database():
        sys_log(" [SYSTEM LOG] Hardware device computation database setup complete.", level="INFO")
    else:
        sys_log(" [SYSTEM LOG] Local device database integrity check complete.", level="INFO", show=False)

    json_file_path = resource_path("database.json")
    if not os.path.exists(json_file_path):
        sys_log(f" [SYSTEM FATAL] Narrative file '{json_file_path}' is missing. Cannot start entry.", level="FATAL")
        sys.exit()

    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            db_data = json.load(f)
            constants.AMBIENT_LORE    = db_data.get("AMBIENT_LORE", [])
            constants.AMBIENT_LORE_EN = db_data.get("AMBIENT_LORE_EN", [])
            constants.CONSUMABLES_DB  = db_data.get("CONSUMABLES_DB", {})
            constants.SESSIONS_DB     = db_data.get("SESSIONS_DB", [])
            constants.RANDOM_EVENTS   = db_data.get("RANDOM_EVENTS", [])
            constants.TRADER_ITEMS    = db_data.get("TRADER_ITEMS", [])
        sys_log(" [SYSTEM LOG] Parsing completed for structured narrative and biometric consumables data.", level="INFO")
        time.sleep(0.6)
    except Exception as e:
        sys_log(f" [SYSTEM FATAL] Failed to parse JSON database: {e}", level="FATAL")
        sys.exit()


def roll_equipment(tier_weights=None):
    """드롭 장비 하나를 고른다: 등급은 tier_weights(기본 GEAR_DROP_TIER_WEIGHTS) 비율, 그 등급 안에서는 무작위. 없으면 None."""
    import random
    tw = tier_weights or constants.GEAR_DROP_TIER_WEIGHTS
    tiers = list(tw)
    tier = random.choices(tiers, weights=[tw[x] for x in tiers], k=1)[0]
    try:
        with sqlite3.connect("stigma_data.db") as conn:
            rows = conn.execute("SELECT item_id FROM equipment WHERE tier = ? AND item_id != 'WEAPON_NONE'", (tier,)).fetchall()
    except sqlite3.Error:
        return None
    return random.choice(rows)[0] if rows else None



def grant_gear_drop(player, tier_weights=None):
    """장비 하나를 굴려 가방에 넣고 알림 문구를 돌려준다. 못 골랐으면 None."""
    iid = roll_equipment(tier_weights)
    if not iid:
        return None
    player.inventory.append(iid)
    d = get_equipment_data(iid)
    import sound
    sound.sfx("gear")
    return t('loot_gear', name=db_t(d, 'name'), tier=constants.tier_tag(d.get('tier', 4)))


def get_equipment_data(item_id):
    """장비 데이터는 세션 내 캐시 우선, 미등록 시 SQLite 쿼리.
    호출 기록(@track)은 붙이지 않는다: 화면이 매 프레임 부르는 단순 조회라 events 기록의 87%를 차지했다.
    여기서 난 예외는 부른 쪽(기록되는 함수)이나 전역 예외 기록에 그대로 남는다."""
    if item_id in _eq_cache:
        return _eq_cache[item_id]
    if item_id in constants.SPECIAL_ITEMS:
        result = constants.SPECIAL_ITEMS[item_id]
        _eq_cache[item_id] = result
        return result
    db_path = "stigma_data.db"
    if not os.path.exists(db_path):
        result = {"name": t('equip_damaged_scrap'), "power": 5, "type": "kinetic", "tier": 4, "desc": t('equip_desc_db_missing')}
        _eq_cache[item_id] = result
        return result

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, power, type, tier, slot, slot_weight, description, name_en, description_en "
                   "FROM equipment WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        result = {"name": row[0], "power": row[1], "type": row[2], "tier": row[3],
                  "slot": row[4], "slot_weight": row[5], "desc": row[6],
                  "name_en": row[7], "desc_en": row[8]}
    else:
        result = {"name": t('equip_unidentified_scrap'), "power": 5, "type": "kinetic", "tier": 4,
                  "slot": "main_weapon", "slot_weight": 1.5, "desc": t('equip_desc_unregistered')}
    _eq_cache[item_id] = result
    return result


def save_data(player, grid, wait=True):
    """저장하고 결과 문장을 돌려준다. wait=False면 찍지도 기다리지도 않는다 (그림 화면이 그 문장을 직접 보여 준다)."""
    from ui import wait_for_keypress  # 지연 임포트로 순환 참조 방지
    import playtime
    playtime.mark(player)   # 저장 직전까지의 플레이 시간
    save_file = {"player": player.to_dict(), "grid": grid.to_dict()}
    try:
        with open(get_save_path(), "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        import sound
        sound.sfx("save")
        msg = t('save_success')
    except Exception as e:
        msg = t('save_fail', e=e)
    if wait:
        print(msg)
        wait_for_keypress()
    return msg
