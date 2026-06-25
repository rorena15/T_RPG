# core.py — DB 로드, 장비 조회, 파일 경로, 저장/로드
# 의존성: constants, db_init, sys_log, ui

import os
import sys
import json
import sqlite3
import time
import db_init
import constants
from i18n import t
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


@track
def get_equipment_data(item_id):
    """장비 데이터는 세션 내 캐시 우선, 미등록 시 SQLite 쿼리."""
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
    cursor.execute("SELECT name, power, type, tier, slot, slot_weight, description FROM equipment WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        result = {"name": row[0], "power": row[1], "type": row[2], "tier": row[3],
                  "slot": row[4], "slot_weight": row[5], "desc": row[6]}
    else:
        result = {"name": t('equip_unidentified_scrap'), "power": 5, "type": "kinetic", "tier": 4,
                  "slot": "main_weapon", "slot_weight": 1.5, "desc": t('equip_desc_unregistered')}
    _eq_cache[item_id] = result
    return result


def save_data(player, grid):
    from ui import wait_for_keypress  # 지연 임포트로 순환 참조 방지
    save_file = {"player": player.to_dict(), "grid": grid.to_dict()}
    try:
        with open(get_save_path(), "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        print(t('save_success'))
    except Exception as e:
        print(t('save_fail', e=e))
    wait_for_keypress()
