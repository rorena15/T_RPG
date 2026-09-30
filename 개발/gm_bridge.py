"""탐색 중 랜덤 이벤트와 빈 탐색을 로컬 GM(stigma-gm)이 판정·서술하도록 잇는다.

생성 서버: 게임에 동봉한 llama-server (gm_server.py). 개발 환경에서 그게 없으면 Ollama를 대신 쓴다.

화면에는 GM도 주사위도 드러내지 않는다(사용자 결정). 플레이어는 행동과 그 결과(서술, 수치 변화)만 본다.
규칙
- 대본 선택지: 주사위는 반드시 굴린다(숨김). 성공(또는 판정 없음)일 때만 대본 보상, 대성공이면 고철 1.5배.
  대가(HP 손실, 고철 지불 등)는 항상 치르고, 피해는 대본 대가와 GM 피해 중 큰 쪽. 성향은 대본 값 +1(대성공 +2).
  보상과 대가를 LORE로 알려 서술이 결과와 맞게 한다. GM이 준 고철·아이템·성향은 쓰지 않는다(이중 보상 방지).
- 직접 행동과 이어서 한 행동: GM의 수치를 그대로 반영한다 (guard가 상한을 막는다).
- 결과 뒤 같은 장면에서 최대 MAX_FOLLOWUPS번 더 행동할 수 있다. 매번 턴이 흐른다(허기·갈증 소모).
- 게임에 없는 수치(오염, RAM)는 버린다. 첫 행동의 턴 비용은 탐색이 이미 치렀으므로 허기·갈증은 회복분만.
- GM을 못 쓰면(모드 끄기, 추가 데이터 없음, 서버 준비 중·실패, 영어 모드, 화면 없음) False를 돌려주고 호출한 쪽이 대본으로 진행한다.
  이벤트 도중 GM이 실패하면 같은 화면에서 조용히 대체한다: 대본 선택지는 대본 결과, 직접 행동은 담담한 한 줄.
GM 런타임(gm/)의 원본은 E:/Git_Project/T_RPG/stigma-gm/engine 이다.
"""
import json
import random
import re
import sqlite3
import time
import urllib.request

import constants
import gm_server
import i18n
from core import get_equipment_data
from event_view import EventView
from gui import get_terminal
from i18n import db_t, t
from quest import advance_quest
from ui import log_diary
from gm.guard import sanitize_player_input
from gm.lore import LoreIndex
from gm.prompt import system_prompt
from gm.runtime import configure as configure_backend
from gm.runtime import generate_turn

# 설정의 "로컬 GM" 항목 (settings.json gm_mode). off면 GM을 쓰지 않고 대본으로 진행한다.
MODES = ["full", "lite", "off"]
MODELS = {"full": "stigma-gm", "lite": "stigma-gm-lite"}  # 고품질 8B / 가벼움 2.1B
TAGS_URL = "http://127.0.0.1:11434/api/tags"
RECHECK_SEC = 60
MAX_FOLLOWUPS = 2
HISTORY_TURNS = 3  # 문맥(4096)에 넣을 이전 턴 수
CRIT_SCRAP_MULT = 1.5
# stigma-gm 학습 데이터(data/_common.py)와 같은 LORE. 1막 맵은 폐기물 처리장이고 목표 칸이 방공호다.
LORE_JUNKYARD = ("폐기물 처리장: 데드존 최외각. 수십 미터 높이로 쌓인 구형 드론 사체와 탄 메인보드 파편의 바다. "
                 "녹슨 기름 냄새와 수은 안개가 생체 지표를 압박한다. 무작위 인카운터: 경비 드론, 오염된 들개.")
LORE_BUNKER = ("구시대 지하 방공호: 쓰레기 바다 안쪽에 묻힌 녹슨 무쇠 문 벙커. 1막의 첫 거점 후보. "
               "스캐브 컬렉터: 총괄국의 자동화 청소기계. 궤도 바퀴와 유압 분쇄 칼날, 잔해와 불량 코드(인간)를 일괄 분쇄한다.")
SYSTEM_LINE = re.compile(r"^\[(경고|SYSTEM|ERROR)\]\s*(.*)$")
SCRIPT_TAG = re.compile(r"^\[[^\]]+\]\s*")  # 대본 결과 문장 앞의 [처리] 같은 표식
SUCCESS = (None, "success", "crit_success")

# 장비·NPC 이름에서 외부 게임 브랜드명을 자체 이름으로 바꿨다. 지금 GM 모델은 예전 이름으로 학습돼 있어,
# 응답에 예전 이름이 나오면 새 이름으로 고친다 (서술이 어긋나지 않고, 이름으로 찾는 아이템 지급이 빠지지 않게).
# 학습 데이터를 바꿔 다시 학습한 뒤에도 안전장치로 남겨 둔다.
RENAMED = [("오비탈 에어", "스트라토"), ("오비탈", "스트라토"), ("아라사카", "아마기리"), ("밀리테크", "스틸게이트"),
           ("바이오테크니카", "셀리온"), ("캉타오", "란위"), ("트라우마 팀", "레드라인"), ("마이크로테크", "비트레일"),
           ("리퍼닥", "봉합꾼")]
_JOSA_PAIRS = {"이": ("이", "가"), "가": ("이", "가"), "을": ("을", "를"), "를": ("을", "를"),
               "은": ("은", "는"), "는": ("은", "는"), "과": ("과", "와"), "와": ("과", "와"),
               "으로": ("으로", "로"), "로": ("으로", "로")}
# 띄어쓰기가 달라도 잡는다 ("리퍼 닥", "트라우마팀": 가벼움 모델이 실제로 띄어 썼다). 영문 표기는 플레이어 입력용
RENAMED_EN = [("orbital air", "스트라토"), ("arasaka", "아마기리"), ("militech", "스틸게이트"), ("biotechnica", "셀리온"),
              ("kang tao", "란위"), ("trauma team", "레드라인"), ("microtech", "비트레일"), ("ripperdoc", "봉합꾼")]
_RENAMED_RE = re.compile("(" + "|".join(r"\s?".join(re.escape(ch) for ch in a.replace(" ", "")) for a, _ in RENAMED + RENAMED_EN)
                         + ")(?:(으로|로|이|가|을|를|은|는|과|와)(?![가-힣]))?", re.IGNORECASE)
_RENAMED_MAP = {a.replace(" ", ""): b for a, b in RENAMED + RENAMED_EN}


def _renamed(text):
    """예전 브랜드명을 새 이름으로. 바로 뒤 조사는 새 이름의 받침에 맞춘다."""
    if not isinstance(text, str) or not text:
        return text

    def sub(m):
        new, josa = _RENAMED_MAP["".join(m.group(1).split()).lower()], m.group(2)
        if not josa:
            return new
        jong = (ord(new[-1]) - 0xAC00) % 28 if "가" <= new[-1] <= "힣" else 0
        with_b, without_b = _JOSA_PAIRS[josa]
        if josa in ("으로", "로"):
            return new + ("로" if jong in (0, 8) else "으로")   # 받침 없음·ㄹ → 로
        return new + (with_b if jong else without_b)
    return _RENAMED_RE.sub(sub, text)


def _renamed_out(out):
    items = out.get("items") if isinstance(out, dict) else None
    if isinstance(items, dict):
        for k in ("add", "remove"):
            if isinstance(items.get(k), list):
                items[k] = [_renamed(n) for n in items[k]]
    return out


_status = {"models": None, "checked": 0.0}  # Ollama에 설치된 모델 이름 (캐시)
_mode = "full"
_name_to_id = None
_lore = None


def _lore_index():
    global _lore
    if _lore is None:
        _lore = LoreIndex()  # gm/lore_snippets.json
    return _lore


def set_mode(mode):
    """설정에서 고른 모드를 적용하고, 그 모드의 동봉 서버를 백그라운드로 띄운다 (full / lite / off)."""
    global _mode
    _mode = mode if mode in MODES else "full"
    gm_server.server.start(_mode)


def get_mode():
    return _mode


def _ollama_models(refresh=False):
    """개발용 대체 경로: Ollama에 설치된 모델 이름 집합. 꺼져 있으면 빈 집합. RECHECK_SEC마다 다시 확인한다."""
    now = time.time()
    if refresh or _status["models"] is None or (not _status["models"] and now - _status["checked"] > RECHECK_SEC):
        try:
            with urllib.request.urlopen(TAGS_URL, timeout=1.5) as r:
                _status["models"] = {m["name"].split(":")[0] for m in json.loads(r.read()).get("models", [])}
        except OSError:
            _status["models"] = set()
        _status["checked"] = now
    return _status["models"]


def mode_installed(mode):
    """설정 화면 표시용: 이 모드의 추가 데이터가 있는지 (off는 항상 True)."""
    if mode == "off" or gm_server.model_installed(mode):
        return True
    return MODELS.get(mode) in _ollama_models(refresh=True)  # 개발 환경


def available():
    """지금 동적 서사를 쓸 수 있는지. 동봉 서버가 준비됐으면 그걸, 아니면 (개발 환경의) Ollama를 쓴다."""
    if _mode == "off" or i18n.LANG != "ko" or get_terminal() is None:
        return False
    srv = gm_server.server
    if srv.state == "ready" and srv.proc is not None and srv.proc.poll() is not None:
        srv.start(_mode)  # 서버가 도중에 죽었다: 다시 띄우고 이번 이벤트는 대본으로
        return False
    if srv.state == "ready" and srv.mode == _mode:
        configure_backend("llamacpp", srv.url, srv.api_key)
        return True
    if srv.state == "starting":  # 첫 실행 셰이더 컴파일 중에는 이번 이벤트만 대본으로
        return False
    if MODELS[_mode] in _ollama_models():
        configure_backend("ollama", "http://127.0.0.1:11434")
        return True
    return False


def _item_id(name):
    global _name_to_id
    if _name_to_id is None:
        _name_to_id = {}
        try:
            with sqlite3.connect("stigma_data.db") as c:
                for iid, n in c.execute("SELECT item_id, name FROM equipment ORDER BY rowid"):
                    _name_to_id.setdefault(n, iid)
        except sqlite3.Error:
            pass
        for iid, d in constants.SPECIAL_ITEMS.items():
            _name_to_id.setdefault(d["name"], iid)
    return _name_to_id.get(_renamed(name))


def _build_state(player, grid):
    at_bunker = list(grid.player_pos) == list(grid.bunker_pos)
    ids = list(player.inventory) + [v for v in player.equipment.values() if v and v != "WEAPON_NONE"]
    names = []
    for iid in ids:
        n = get_equipment_data(iid).get("name")
        if n and n not in names:
            names.append(n)
    state = {
        "location": "구시대 지하 방공호" if at_bunker else "폐기물 처리장",
        "turn": player.turn_count, "hp": player.hp, "max_hp": player.max_hp,
        "hunger": player.hunger, "thirst": player.thirst, "contamination": 5,
        "ram": player.max_ram, "max_ram": player.max_ram,
        "stats": {"VIT": player.vit, "INT": player.int_s, "DEX": player.dex},
        "inventory": names,
    }
    return state, (LORE_BUNKER if at_bunker else LORE_JUNKYARD)


# ── 대본 보상 ────────────────────────────────────────────────────────────

def _consumable_name(key):
    return db_t(constants.CONSUMABLES_DB[key], 'name') if key in constants.CONSUMABLES_DB else key


def _script_hint(src):
    """대본 선택지의 보상과 대가를 GM에게 알려 줄 LORE 문장. 서술이 결과와 어긋나지 않게 한다."""
    gains, costs = [], []
    if src.get("consumable"):
        gains.append(f"{_consumable_name(src['consumable'])} 1개")
    mat = src.get("materials", 0)
    if mat > 0:
        gains.append(f"고철 {mat}개")
    elif mat < 0:
        costs.append(f"고철 {-mat}개 지불")
    for key, label in (("hunger", "허기"), ("thirst", "갈증")):
        v = src.get(key, 0)
        if v > 0:
            gains.append(f"{label} 회복")
        elif v < 0:
            costs.append(f"{label} 악화")
    if src.get("ram_bonus", 0) > 0:
        gains.append(f"최대 RAM +{src['ram_bonus']}")
    if src.get("hp_loss", 0) > 0:
        costs.append(f"체력 손실 약 {src['hp_loss']}")
    parts = []
    if gains:
        parts.append("이 행동이 성공하면 얻는 것: " + ", ".join(gains) + ".")
    if costs:
        parts.append("이 행동의 대가: " + ", ".join(costs) + ".")
    return " ".join(parts)


def _sign(v):
    return "+" if v > 0 else "−"


def _apply_script(player, src, weight, out):
    """대본 선택지의 결과를 반영하고 화면에 보일 변화 목록을 돌려준다."""
    tokens = []
    c = out["check"]
    outcome = c["outcome"] if c else None
    success = outcome in SUCCESS
    damage = max(-min(out["delta"].get("hp", 0), 0), src.get("hp_loss", 0))
    if damage:
        player.hp = max(1, player.hp - damage)
        tokens.append((t('gm_tok_hp', sign="−", val=damage), "hp_loss"))
    alert = out["delta"].get("alert", 0)
    if alert:
        player.alert_level = max(0, player.alert_level + alert)
        tokens.append((t('gm_tok_alert', sign=_sign(alert), val=abs(alert)), "info"))
    mat = src.get("materials", 0)
    if mat < 0:
        player.materials = max(0, player.materials + mat)
        tokens.append((t('gm_tok_scrap', sign="−", val=-mat), "scrap"))
    for key in ("hunger", "thirst"):
        if src.get(key, 0) < 0:
            setattr(player, key, max(0, getattr(player, key) + src[key]))

    has_gain = mat > 0 or src.get("consumable") or src.get("ram_bonus", 0) > 0 or \
        src.get("hunger", 0) > 0 or src.get("thirst", 0) > 0
    if success:
        if mat > 0:
            gain = int(mat * CRIT_SCRAP_MULT) if outcome == "crit_success" else mat
            player.materials += gain
            tokens.append((t('gm_tok_scrap', sign="+", val=gain), "scrap"))
            advance_quest(player, "scrap", gain)
        for key, label in (("hunger", 'gm_tok_hunger'), ("thirst", 'gm_tok_thirst')):
            if src.get(key, 0) > 0:
                before = getattr(player, key)
                setattr(player, key, min(100, before + src[key]))
                if getattr(player, key) > before:
                    tokens.append((t(label, val=getattr(player, key) - before), "gain"))
        if src.get("ram_bonus", 0) > 0:
            player.max_ram += src["ram_bonus"]
            tokens.append((t('gm_tok_ram', val=src['ram_bonus']), "gain"))
        key = src.get("consumable")
        if key and key in player.consumables:
            player.consumables[key] += 1
            tokens.append((_consumable_name(key), "item"))
    elif has_gain:
        tokens.append((t('gm_tok_nothing'), "info"))
    if weight and weight in player.weights:
        w = 2 if outcome == "crit_success" else 1
        player.weights[weight] += w
        tokens.append((t('gm_tok_weight', label=t(f'weight_label_{weight}'), val=w), "weight"))
    return tokens


def _apply_gm(player, out):
    """직접 행동의 결과. GM 출력 중 게임에 있는 수치만 반영하고 변화 목록을 돌려준다."""
    tokens = []
    d = out["delta"]
    hp = d.get("hp", 0)
    if hp:
        before = player.hp
        player.hp = max(1, min(player.max_hp, player.hp + hp))
        diff = player.hp - before
        if diff:
            tokens.append((t('gm_tok_hp', sign=_sign(diff), val=abs(diff)), "hp_loss" if diff < 0 else "gain"))
    for key, label in (("hunger", 'gm_tok_hunger'), ("thirst", 'gm_tok_thirst')):
        v = d.get(key, 0)
        if v > 0:
            before = getattr(player, key)
            setattr(player, key, min(100, before + v))
            if getattr(player, key) > before:
                tokens.append((t(label, val=getattr(player, key) - before), "gain"))
    alert = d.get("alert", 0)
    if alert:
        player.alert_level = max(0, player.alert_level + alert)
        tokens.append((t('gm_tok_alert', sign=_sign(alert), val=abs(alert)), "info"))
    scrap = d.get("scrap", 0)
    if scrap:
        before = player.materials
        player.materials = max(0, player.materials + scrap)
        diff = player.materials - before
        if diff:
            tokens.append((t('gm_tok_scrap', sign=_sign(diff), val=abs(diff)), "scrap"))
        if diff > 0:
            advance_quest(player, "scrap", diff)
    for k, v in out["weights"].items():
        if v and k in player.weights:
            player.weights[k] += v
            tokens.append((t('gm_tok_weight', label=t(f'weight_label_{k}'), val=v), "weight"))
    for name in out["items"].get("add", []):
        iid = _item_id(name)
        # T0 유물·T1 기업제는 보상으로 주지 않는다 (stigma-gm 학습 규칙과 같음)
        if iid and iid not in player.inventory and get_equipment_data(iid).get("tier", 4) > 1:
            player.inventory.append(iid)
            tokens.append((name, "item"))
    for name in out["items"].get("remove", []):
        iid = _item_id(name)
        if iid in player.inventory:  # 장착 중인 장비는 건드리지 않는다
            player.inventory.remove(iid)
            tokens.append((f"−{name}", "info"))
    return tokens


# ── 화면에서 한 턴 진행 ───────────────────────────────────────────────────

def _call(view, player, grid, action, history, hint="", force_check=False):
    """GM 한 턴을 백그라운드에서 돌린다(화면은 계속 움직임). 성공하면 (서술, 출력, 원문), 실패하면 None."""
    state, lore = _build_state(player, grid)
    base = lore
    action = _renamed(action)   # 플레이어가 예전 이름을 직접 쓰면 모델이 그대로 따라 쓴다 (8B 12번 중 9번): 넘기기 전에 바꾼다
    if hint:
        lore = f"{lore} {hint}"
    # 장면·행동·소지품과 맞는 원작 설정 조각을 덧붙인다 (없는 설정을 지어내지 않게)
    extra = _lore_index().extra_lore(f"{action} {hint} {base}", state["inventory"], base)
    if extra:
        lore = f"{lore} {extra}"
    roll = random.randint(1, 100)
    system = system_prompt(state, lore, roll)
    view.hud_hold = True  # 결과를 반영해도 HUD는 서술이 끝나고 결과가 뜰 때 움직인다 (_show가 푼다)
    try:
        narration, out, text, _ = view.run_task(lambda: generate_turn(
            system, history[-HISTORY_TURNS:], action, roll, MODELS[_mode], force_check=force_check), action)
        return _renamed(narration), _renamed_out(out), _renamed(text)
    except OSError:  # 서버가 꺼졌다: 한동안 GM 없이 진행하고 RECHECK_SEC 뒤 다시 확인
        _status["models"] = set()
        _status["checked"] = time.time()
        return None
    except (RuntimeError, ValueError, KeyError, TypeError, AttributeError):  # 이번 턴만 검증 실패 (응답 모양이 틀려도 게임은 대본으로)
        return None


def _show(view, narration, tokens, out=None):
    """서술을 타자 치듯 드러내고, 시스템 줄은 HUD 경고로, 마지막에 변화 목록을 붙인다.
    결과가 뜨는 순간 HUD가 움직이고, 대실패나 큰 피해면 화면이 흔들린다 (판정 수치는 보이지 않는다)."""
    buf = []

    def flush():
        if buf:
            entry = view.add("narr", lines=list(buf))
            view.type_out(entry)
            buf.clear()
    for line in (x.strip() for x in narration.splitlines()):
        if not line:
            continue
        m = SYSTEM_LINE.match(line)
        if m:
            flush()
            view.add("sys", label=m.group(1), text=m.group(2))
            view.pause(220)
        else:
            buf.append(line)
    flush()
    view.pause(150)
    view.hud_hold = False
    check = (out or {}).get("check") or {}
    big_hit = any(kind == "hp_loss" for _, kind in tokens) and         view.player.max_hp and (view._hud.get("hp", view.player.hp) - view.player.hp) >= view.player.max_hp * 0.05
    outcome = check.get("outcome")
    if outcome:
        import sound
        sound.sfx({"crit_success": "evt_great", "success": "evt_good", "partial": "evt_good"}.get(outcome, "evt_bad"))
    if check.get("outcome") == "crit_fail" or big_hit:
        view.shake(9 if check.get("outcome") == "crit_fail" else 6)
    if tokens:
        view.add("result", tokens=tokens, sfx=_result_sfx(tokens))


def _result_sfx(tokens):
    """결과 표시(글자, 종류)를 결과 효과음 종류로 (sound.results)."""
    hp_up = t('gm_tok_hp', sign="+", val=0)[:-1]
    alert_up = t('gm_tok_alert', sign="+", val=0)[:-1]
    kinds = []
    for text, kind in tokens:
        if kind == "hp_loss":
            kinds.append("hp_loss")
        elif kind == "scrap":
            kinds.append("scrap+" if "+" in text else "scrap-")
        elif kind == "gain":
            kinds.append("hp_gain" if text.startswith(hp_up) else "gain")
        elif kind in ("item", "weight"):
            kinds.append(kind)
        elif kind == "info" and text.startswith(alert_up):
            kinds.append("alert")
        else:
            kinds.append(None)   # 소리 없이 간격만
    return kinds


def _followups(view, player, grid, history, scene=""):
    """같은 장면에서 이어서 행동한다. 매번 턴이 흐르고, GM의 수치를 그대로 반영한다."""
    left = MAX_FOLLOWUPS
    while left > 0:
        view.footer = [("0", t('gm_foot_more', left=left)), ("Enter", t('gm_foot_leave'))]
        if view.wait_key({"0", "ENTER", "ESC"}) != "0":
            return
        view.footer = [("Enter", t('gm_foot_submit')), (t('ui_key_empty_enter'), t('gm_foot_cancel'))]
        action = view.read_line()
        if action is None:
            continue
        action = sanitize_player_input(action)
        left -= 1
        player.consume_resources()
        view.add("sep")
        view.add("you", text=action, custom=True)
        view.footer = []
        result = _call(view, player, grid, action, history, scene)
        if result is None:
            _show(view, t('gm_fallback_custom'), [])
            break
        narration, out, text = result
        _show(view, narration, _apply_gm(player, out), out)
        history.append((action, text))
    view.footer = [("Enter", t('gm_foot_leave'))]
    view.wait_key({"ENTER", "ESC", " "})


def _scene_lore(event):
    """대본의 도입 상황을 LORE의 '현재 장면'으로 넘긴다.
    history(GM의 직전 서술)로 넘기면 대본의 합니다체를 GM이 따라 써서 문체가 섞인다."""
    return "현재 장면: " + " ".join(db_t(event, 'text').split())


def run_event(player, grid, event):
    """랜덤 이벤트를 GM으로 진행한다. 진행했으면 True, 대본으로 넘겨야 하면 False."""
    if event["type"] == "weapon_item" or not available():
        return False  # 무기 이벤트는 임시 무기 사용 횟수 같은 게임 전용 규칙이 있어 대본 유지

    state, _ = _build_state(player, grid)
    # 그림 고르기: 이벤트 전용 그림 -> 이벤트 문장에 나온 말 -> 장소 (scene_art.choose)
    view = EventView(get_terminal(), player, grid, state["location"], event_id=event.get("id"),
                     context=f"{event.get('title', '')} {event.get('text', '')}")
    view.add("title", tag=t('gm_tag_event'), title=db_t(event, 'title'))
    view.add("prose", lines=[" ".join(db_t(event, 'text').split())])
    if event["type"] == "choice":
        options = [(db_t(c, 'text'), c, c.get("weight")) for c in event["choices"]]
    else:
        options = [(t('gm_simple_inspect'), event["result"], None), (t('gm_simple_pass'), None, None)]
    view.open()
    try:
        while True:
            menu = view.add("choices", items=[(str(i + 1), o[0]) for i, o in enumerate(options)]
                            + [("0", t('gm_custom_choice'))])
            view.footer = [("↑↓", t('ui_select')), ("Enter", t('ui_confirm'))]
            key = view.choose(menu, len(options))
            view.log.remove(menu)
            if key == "0":
                view.footer = [("Enter", t('gm_foot_submit')), (t('ui_key_empty_enter'), t('gm_foot_cancel'))]
                action = view.read_line()
                if action is None:
                    continue
                action, src, weight = sanitize_player_input(action), None, None
            else:
                action, src, weight = options[int(key) - 1]
            break

        view.add("you", text=action, custom=src is None)
        view.footer = []
        if event["type"] != "choice" and src is None and key != "0":  # 단순 이벤트에서 지나치기
            _show(view, t('gm_pass_log'), [])
            view.footer = [("Enter", t('gm_foot_leave'))]
            view.wait_key({"ENTER", "ESC", " "})
            return True

        scene = _scene_lore(event)
        hint = f"{scene} {_script_hint(src)}" if src else scene
        # 대본 선택지는 보상이 걸린 행동이라 반드시 주사위를 굴린다. 직접 행동은 판정 여부도 GM이 정한다.
        result = _call(view, player, grid, action, [], hint, force_check=src is not None)
        log_diary(player, t('event_log_simple', title=db_t(event, 'title')))
        if result is None:  # GM 실패: 같은 화면에서 조용히 대체
            if src is not None:
                # 대본 결과 그대로: 대본 모드처럼 보상을 준다 (check가 None이면 실패로 쳐서 "얻은 것 없음"이 떴다)
                empty = {"check": {"outcome": "success"}, "delta": {}, "weights": {}, "items": {"add": [], "remove": []}}
                _show(view, SCRIPT_TAG.sub("", db_t(src, 'log').split("\n")[0]), _apply_script(player, src, weight, empty))
            else:
                _show(view, t('gm_fallback_custom'), [])
            view.footer = [("Enter", t('gm_foot_leave'))]
            view.wait_key({"ENTER", "ESC", " "})
            return True
        narration, out, text = result
        tokens = _apply_script(player, src, weight, out) if src is not None else _apply_gm(player, out)
        _show(view, narration, tokens, out)
        _followups(view, player, grid, [(action, text)], scene)
        return True
    finally:
        view.close()


def run_event_script(player, grid, event):
    """GM 없이 대본 이벤트를 그림 화면으로 진행한다 (동적 서사 끔·미설치·영어). 진행했으면 True.
    규칙은 quest.handle_random_event(터미널 판)와 같다: 단순 이벤트는 바로 결과, 선택 이벤트는 고른 대로."""
    if get_terminal() is None:
        return False
    state, _ = _build_state(player, grid)
    view = EventView(get_terminal(), player, grid, state["location"], event_id=event.get("id"),
                     context=f"{event.get('title', '')} {event.get('text', '')}")
    view.add("title", tag=t('gm_tag_event'), title=db_t(event, 'title'))
    view.add("prose", lines=[" ".join(db_t(event, 'text').split())])
    empty = {"check": {"outcome": "success"}, "delta": {}, "weights": {}, "items": {"add": [], "remove": []}}
    view.open()
    try:
        if event["type"] == "choice":
            items = [(str(i + 1), db_t(c, 'text')) for i, c in enumerate(event["choices"])]
            menu = view.add("choices", items=items)
            view.footer = [("↑↓", t('ui_select')), ("Enter", t('ui_confirm'))]
            src = event["choices"][int(view.choose(menu, len(items))) - 1]
            view.log.remove(menu)
            view.add("you", text=db_t(src, 'text'))
            tokens = _apply_script(player, src, src.get("weight"), empty)
            label = t(f"weight_label_{src['weight']}") if src.get("weight") in player.weights else t('weight_label_default')
            diary = t('event_log_choice', title=db_t(event, 'title'), label=label)
        elif event["type"] == "weapon_item":
            src = event["result"]
            tokens = _apply_script(player, src, None, empty)
            wid, uses = src["weapon_id"], src.get("weapon_uses", 2)
            if wid not in player.inventory:
                player.inventory.append(wid)
                player.temp_weapon_uses[wid] = uses
                tokens.append((" ".join(t('event_weapon_gain', uses=uses).split()), "item"))
            else:
                tokens.append((" ".join(t('event_weapon_dup').split()), "info"))
            diary = t('event_log_weapon', title=db_t(event, 'title'))
        else:
            src = event["result"]
            tokens = _apply_script(player, src, None, empty)
            diary = t('event_log_simple', title=db_t(event, 'title'))
        view.footer = []
        _show(view, "\n".join(SCRIPT_TAG.sub("", x.strip()) for x in db_t(src, 'log').splitlines()), tokens)
        log_diary(player, diary)
        view.footer = [("Enter", t('gm_foot_leave'))]
        view.wait_key({"ENTER", "ESC", " "})
        return True
    finally:
        view.close()


def run_search(player, grid):
    """아무 일도 없던 탐색 결과를 서술한다. 묘사된 것에 이어서 행동할 수 있다. 진행했으면 True."""
    if not available():
        return False
    state, _ = _build_state(player, grid)
    view = EventView(get_terminal(), player, grid, state["location"], search=True)  # 빈 탐색: 못 본 랜드마크 우선
    view.add("title", tag=t('gm_tag_search'), title=t('gm_search_title'))
    view.open()
    try:
        action = t('gm_search_action')
        result = _call(view, player, grid, action, [])
        if result is None:
            return False
        narration, out, text = result
        _show(view, narration, _apply_gm(player, out), out)
        _followups(view, player, grid, [(action, text)])
        return True
    finally:
        view.close()
