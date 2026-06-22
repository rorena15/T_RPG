import math
import random
import sys
import time
import os
import json
import sqlite3
import db_init
from sys_log import sys_log, track, track_event
from colorama import Fore, Back, Style, init as colorama_init
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.columns import Columns
from rich import box as rich_box

_console = Console(highlight=False)

# ====================================================================
# [0] 경로
# ====================================================================
def resource_path(relative_path):
    #PyInstaller로 패키징된 경우 임시 폴더 경로를, 그렇지 않으면 절대 경로를 반환합니다.
    try:
        # PyInstaller로 패키징되어 실행될 때 임시 폴더 경로
        base_path = sys._MEIPASS
    except Exception:
        # 일반 파이썬 스크립트로 실행될 때의 절대 경로
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_save_path():
    # EXE 모드: exe 파일 옆에 저장 (sys._MEIPASS 임시폴더 X)
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "stigma_save.json")
    return os.path.join(os.path.abspath("."), "stigma_save.json")

# ====================================================================
# [0.5] 전체 로깅
# ====================================================================
# track / track_event 는 sys_log.py에서 가져온다 (SQLite events 테이블에 적재되는 버전).

# ====================================================================
# [1] 데이터베이스 및 단일 진실 공급원(SSOT) 연산 코어 로더
# ====================================================================
AMBIENT_LORE = []
CONSUMABLES_DB = {}
SESSIONS_DB = []
RANDOM_EVENTS = []
TRADER_ITEMS = []
MASTER_FORMULAS = {}

# 11개 장비 슬롯 정의 — DB slot 컬럼 키와 1:1 대응
SLOT_DISPLAY = {
    "main_weapon":      "주무기",
    "cyberdeck":        "사이버덱",
    "cybernetic_parts": "의체부품",
    "back_gear":        "등 장비",
    "face":             "얼굴",
    "top":              "상의",
    "bottom":           "하의",
    "footwear":         "신발",
    "necklace":         "목걸이",
    "ring":             "반지",
    "custom_part":      "특화부품",
}
SLOT_DEFAULTS = {
    "main_weapon": "WEAPON_NONE",
    "cyberdeck": None, "cybernetic_parts": None, "back_gear": None,
    "face": None, "top": None, "bottom": None, "footwear": None,
    "necklace": None, "ring": None, "custom_part": None,
}
TIER_TAGS = {4: "T4 급조", 3: "T3 규격", 2: "T2 정제", 1: "T1 기업", 0: "T0 유물"}

_eq_cache: dict = {}

SUDDEN_QUESTS = [
    {"id": "SQ_SCRAP_A", "title": "잔해 자원 긴급 확보",
     "desc": "산개한 고철 잔해에서 자원을 집중적으로 확보하십시오.",
     "detail": "고철 +50개 수집", "type": "scrap", "target": 50, "turns": 10,
     "reward_type": "consumable", "reward_id": "MED_FIX_300", "reward_desc": "군용 지혈제 1개"},
    {"id": "SQ_SCRAP_B", "title": "집중 파밍 프로토콜",
     "desc": "이 구역 전체에 회수 가능한 잔해가 산재합니다. 최대한 확보하십시오.",
     "detail": "고철 +80개 수집", "type": "scrap", "target": 80, "turns": 14,
     "reward_type": "materials", "reward_amount": 50, "reward_desc": "고철 50개 추가"},
    {"id": "SQ_COMBAT_A", "title": "구역 정화",
     "desc": "이 구역의 기계 밀도가 비정상입니다. 적 일부를 제압하여 경로를 확보하십시오.",
     "detail": "전투 2회 승리", "type": "combat", "target": 2, "turns": 12,
     "reward_type": "consumable", "reward_id": "MED_PER_50", "reward_desc": "응급 지혈대 1개"},
    {"id": "SQ_COMBAT_B", "title": "데드존 청소부",
     "desc": "총괄국이 자동화 기계 포대를 증파했습니다. 전투 역량을 검증하십시오.",
     "detail": "전투 3회 승리", "type": "combat", "target": 3, "turns": 18,
     "reward_type": "consumable", "reward_id": "MED_FIX_500", "reward_desc": "합성 바이오 젤 1개"},
    {"id": "SQ_SEARCH_A", "title": "지형 데이터 스캔",
     "desc": "사이버덱이 불완전한 지형 정보를 감지했습니다. 추가 스캔이 필요합니다.",
     "detail": "탐색 3회", "type": "search", "target": 3, "turns": 7,
     "reward_type": "ram", "reward_amount": 1, "reward_desc": "RAM +1"},
    {"id": "SQ_SEARCH_B", "title": "광역 환경 스캐닝",
     "desc": "광범위한 지형 정보 수집이 요청됩니다. 반복 스캔을 실시하십시오.",
     "detail": "탐색 5회", "type": "search", "target": 5, "turns": 12,
     "reward_type": "consumable", "reward_id": "FOOD_BOTH", "reward_desc": "수분 함유 전투식량 1개"},
]

@track
def init_and_load_db():
    """게임 부팅 시 DB 및 master_formulas.json 무결성을 검증하고 메모리에 로드합니다."""
    global AMBIENT_LORE, CONSUMABLES_DB, SESSIONS_DB, MASTER_FORMULAS
    
    # clear_screen()
    sys_log(" [SYSTEM BOOT] 마스터 공급원 및 메모리 무결성 검증 중...", level="INFO")
    time.sleep(0.4)
    
    # 1. master_formulas.json 로드 (SSOT 최우선 적용, 경로 검증 정정 완료)
    formula_real_path = resource_path("master_formulas.json")
    if os.path.exists(formula_real_path):
        try:
            with open(formula_real_path, "r", encoding="utf-8") as f:
                MASTER_FORMULAS = json.load(f)
            sys_log(" [SYSTEM LOG] 단일 진실 공급원(master_formulas.json) 동기화 완료.", level="INFO")
        except Exception as e:
            sys_log(f" [SYSTEM WARN] 마스터 수식 로드 실패, 폴백 엔진 가동 ({e})", level="WARN")
    
    # 폴백 안전장치 (파일이 없거나 손상 시 기획서 정식 공식 기본 내장)
    if not MASTER_FORMULAS:
        MASTER_FORMULAS = {
            "formulas": {
                "reputation_multiplier": {"divisor": 2000.0},
                "max_level": {"base": 15, "growth": 0.93}
            }
        }

    # 2. SQLite DB 자동 생성 (Failsafe)
    if db_init.init_database():
        sys_log(" [SYSTEM LOG] 하드웨어 장비 연산 데이터베이스(SQLite) 구축 완료.", level="INFO")
    else:
        sys_log(" [SYSTEM LOG] 로컬 장비 데이터베이스 무결성 확인 완료.", level="INFO", show=False)
        
    # 3. JSON 서사/환경 데이터 로드 (이중 resource_path 제거 완료)
    json_file_path = resource_path("database.json")
    if not os.path.exists(json_file_path):
        sys_log(f" [SYSTEM FATAL] 서사 파일 '{json_file_path}' 누락. 엔트리를 시작할 수 없습니다.", level="FATAL")
        sys.exit()
        
    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            db_data = json.load(f)
            AMBIENT_LORE = db_data.get("AMBIENT_LORE", [])
            CONSUMABLES_DB = db_data.get("CONSUMABLES_DB", {})
            SESSIONS_DB = db_data.get("SESSIONS_DB", [])
            RANDOM_EVENTS = db_data.get("RANDOM_EVENTS", [])
            TRADER_ITEMS = db_data.get("TRADER_ITEMS", [])
        sys_log(" [SYSTEM LOG] 서사 및 생체 소모품 데이터 구조화 파싱 완료.", level="INFO")
        time.sleep(0.6)
    except Exception as e:
        sys_log(f" [SYSTEM FATAL] JSON 데이터베이스 파싱 오류: {e}", level="FATAL")
        wait_for_keypress()
        sys.exit()

@track
def get_equipment_data(item_id):
    """장비 데이터는 세션 내 캐시 우선, 미등록 시 SQLite 쿼리."""
    if item_id in _eq_cache:
        return _eq_cache[item_id]
    db_path = "stigma_data.db"
    if not os.path.exists(db_path):
        result = {"name": "손상된 고철", "power": 5, "type": "kinetic", "tier": 4, "desc": "DB 파일 누락."}
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
        result = {"name": "미식별 고철", "power": 5, "type": "kinetic", "tier": 4,
                  "slot": "main_weapon", "slot_weight": 1.5, "desc": "DB 미등록 부품."}
    _eq_cache[item_id] = result
    return result

# ====================================================================
# [2] 하드웨어 수준 입력 버퍼 및 키 입력 제어
# ====================================================================
def flush_input():
    """타이핑 연출 중 유저가 미리 입력한 키를 강제로 날려 무차별 오작동을 차단합니다."""
    if os.name == 'nt':
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    else:
        import termios
        termios.tcflush(sys.stdin, termios.TCIOFLUSH)

@track
def safe_input(prompt):
    """버퍼 청소 후 명령코드를 온전히 입력받는 래퍼"""
    time.sleep(0.05)
    flush_input()
    return input(prompt)

@track
def wait_for_keypress():
    """엔터 입력 불필요 아무 키나 누르는 즉시 화면 템포가 연출 모드로 진행"""
    flush_input()
    print("\n[아무 키나 누르면 진행됩니다...]")
    if os.name == 'nt':
        import msvcrt
        msvcrt.getch()
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def read_key():
    """엔터 없이 단일 키를 즉시 감지해 대문자 문자열로 반환합니다."""
    flush_input()
    if os.name == 'nt':
        import msvcrt
        ch = msvcrt.getch()
        if ch == b'\x03':
            sys.exit()
        if ch in (b'\xe0', b'\x00'):  # 방향키 등 특수 키 — 두 번째 바이트 소비 후 무시
            msvcrt.getch()
            return ''
        try:
            return ch.decode('cp949').upper()
        except Exception:
            return ''
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x03':
                sys.exit()
            return ch.upper()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

# 구동 프로토콜 가동
init_and_load_db()

# ====================================================================
# [3] 아스키 아트 및 주 기믹 연산
# ====================================================================
ENEMY_ART = {
    "NORMAL": """
       .---.
      /     \\
     | () () |  <-- [ERROR: 광학 센서 오염]
      \\  ^  /
       |||||    <-- [노출된 서보 모터 축]
      /|||||\\
     |||||||||
     '---^---'
    //       \\\\  <-- [급조된 가시철사 링크]
   //         \\\\
    """,
    "BOSS": """
          _ . - - - . _
      _ -             - _
    -       [WARNING]       -
  -     숙청 시퀀스 가동     -
 -                           -
:      <[E]> : <[E]> : <[E]>   : <-- [딥러닝 카운터 패널]
:       | | :   | | :   | |    :
 -                           -
  -  _ - - - _     _ - - - _  -
    |#########|---|#########|
    |#########|---|#########|
     - - - - -     - - - - -
     /  | |  \\     /  | |  \\  <-- [분쇄용 커터 날]
    /   | |   \\   /   | |   \\
   /____|_|____\\ /____|_|____\\
    """,
    "BIOHOUND": """
       _____     _____
      /  X  \\---/  X  \\   <-- [변이 광학 세포 — 무작위 조준]
     |  ___  | |  ___  |
      \\ \\_/ /   \\ \\_/ /
       |   |     |   |
     __|___|_____|___|__
    /  [BIO:FUSED SPINE]  \\  <-- [유기-기계 융합 척추]
   /   :::::::::::::::   \\
  /   /               \\   \\
 |===<  CLAW   CLAW  >===|  <-- [바이오 적출 집게발]
  \\   \\___________/   /
   \\_________________/
    """
}

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def type_text(text, speed=0.015):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    print()

def apply_dynamic_scaling(raw_dmg, raw_hp, highest_equip_tier):
    if highest_equip_tier >= 4:
        return int(raw_dmg), int(raw_hp), ""
    elif highest_equip_tier in [2, 3]:
        return int(raw_dmg * 100), int(raw_hp * 10), "[SYSTEM: 전술 동기화 가동] 시각 피질의 정보 처리량이 가속됩니다."
    else: 
        return int(raw_dmg * 100000), int(raw_hp * 100), "[WARNING: HUD 글리치 발생] 시스템 연산 한계 돌파. 신격 스케일링 개방."

def _ea_width(s):
    """CJK 문자를 포함한 문자열의 터미널 표시 너비를 반환합니다 (한글·한자 = 2칸)."""
    w = 0
    for c in s:
        cp = ord(c)
        if (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF or
                0xA960 <= cp <= 0xA97F or 0xAC00 <= cp <= 0xD7FF or
                0xF900 <= cp <= 0xFAFF or 0xFE10 <= cp <= 0xFE1F or
                0xFE30 <= cp <= 0xFE6F or 0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6):
            w += 2
        else:
            w += 1
    return w

def ea_center(s, width):
    """CJK 표시 너비 기준 center."""
    pad = max(0, width - _ea_width(s))
    return " " * (pad // 2) + s + " " * (pad - pad // 2)

def ea_rpad(s, width):
    """CJK 표시 너비 기준 ljust (오른쪽 공백 패딩)."""
    return s + " " * max(0, width - _ea_width(s))

def print_header(title):
    _console.print()
    _console.print(Panel(
        f"[bold white]{title}[/bold white]",
        border_style="bright_cyan",
        padding=(0, 2),
        expand=True,
    ))
    _console.print()

def print_divider():
    _console.rule(style="cyan dim")

def _log_color(log):
    """전투 로그 항목의 색상을 반환합니다."""
    if any(log.startswith(p) for p in ("[타격]", "[회복]", "[파밍]", "[수집]", "[승리]")):
        return Fore.GREEN + Style.BRIGHT
    if any(log.startswith(p) for p in ("[피격]", "[페이즈 전환]")):
        return Fore.RED + Style.BRIGHT
    if any(log.startswith(p) for p in ("[경고]", "[탈출]", "[탈출 참사]", "[기적적 탈출]", "[경보]")):
        return Fore.YELLOW + Style.BRIGHT
    if any(log.startswith(p) for p in ("[해킹]", "[방어]")):
        return Fore.CYAN + Style.BRIGHT
    return ""

def log_diary(player, entry):
    player.diary.append(f"[턴 {player.turn_count:>4d}]  {entry}")

def show_diary(player):
    entries = player.diary
    if not entries:
        clear_screen()
        print_header("항법 일지 — N-404 행동 코드 누적 로그")
        print()
        print("  기록 없음. 아직 어떤 선택도 누적되지 않았습니다.")
        print()
        wait_for_keypress()
        return

    page_size = 18
    total = len(entries)
    pages = max(1, (total + page_size - 1) // page_size)
    page = pages - 1  # 최신 페이지부터

    while True:
        clear_screen()
        print_header(f"항법 일지 — N-404 행동 코드 누적 로그  [{page + 1} / {pages}]")
        start = page * page_size
        end = min(start + page_size, total)
        for e in entries[start:end]:
            print(f"  {e}")
        print()
        print_divider()
        nav = []
        if page > 0:
            nav.append("P: 이전")
        if page < pages - 1:
            nav.append("N: 다음")
        nav.append("0: 복귀")
        print(f"  {' | '.join(nav)}")
        cmd = read_key()
        if cmd == "0":
            break
        elif cmd == "N" and page < pages - 1:
            page += 1
        elif cmd == "P" and page > 0:
            page -= 1

def print_ambient_lore():
    if AMBIENT_LORE:
        lore = random.choice(AMBIENT_LORE)
        print()
        print("  " + "─" * 70)
        type_text(f"  {lore}", 0.018)
        print("  " + "─" * 70)
        wait_for_keypress()

def roll_medkit():
    r = random.randint(1, 100)
    if r <= 40: return "MED_PER_10"       
    elif r <= 60: return "MED_FIX_100"    
    elif r <= 75: return "MED_PER_50"     
    elif r <= 85: return "MED_FIX_300"    
    elif r <= 93: return "MED_FIX_500"    
    elif r <= 98: return "MED_PER_100"    
    else: return "MED_FIX_1000"           

def roll_food():
    return "FOOD_BOTH" if random.random() < 0.3 else "FOOD_ONLY"

def roll_water():
    return "WATER_BOTH" if random.random() < 0.3 else "WATER_ONLY"

# ====================================================================
# [4] 게임 코어 (Player, Map & Save/Load)
# ====================================================================
class Player:
    def __init__(self):
        self.hp = 1500
        self.max_hp = 1500
        self.hunger = 100
        self.thirst = 100
        self.max_ram = 4
        self.dex = 10  
        self.materials = 0
        self.reputation = 0 # 정식 공식 적용을 위한 밸런스 인자 기본 동기화
        
        self.consumables = {k: 0 for k in CONSUMABLES_DB.keys()}
        if "FOOD_ONLY" in self.consumables: self.consumables["FOOD_ONLY"] = 2
        if "WATER_ONLY" in self.consumables: self.consumables["WATER_ONLY"] = 2
        if "MED_FIX_100" in self.consumables: self.consumables["MED_FIX_100"] = 1
        
        self.weights = {"kinetic": 0, "scrap": 0, "cyber": 0}
        self.enemies_defeated = 0

        # --- 진행 턴 기반 적 스케일링용 상태 ---
        # turn_count : 이동/탐색(consume_resources 호출) 1회당 1씩 누적되는 전체 진행 턴.
        #              파밍 없이 시간만 흘려보내는 플레이를 막기 위한 적 강화의 메인 기준이다.
        # difficulty : 게임 시작 시 선택한 난이도에 따른 턴당 증가율 배율 (이지/노멀/하드).
        self.turn_count = 0
        self.difficulty = "normal"

        # 정식 빌드 시작 인벤토리: 유물(T=0) 장비는 더 이상 기본 지급하지 않는다.
        # 0등급 유물은 본편 설계상 3막 이후 정제로 획득해야 하는 최종 등급 자산이므로,
        # 데모(1막) 단계에서 자동 지급되면 밸런스와 진행 동기를 해친다.
        # 개발자 검증용 유물 지급은 DEV_GRANT_LEGACY 히든 커맨드(아래)로만 가능하다.
        self.inventory = []
        self.equipment = {k: v for k, v in SLOT_DEFAULTS.items()}
        self.diary = []
        self.active_quest = None

    def get_highest_tier(self):
        item_data = get_equipment_data(self.equipment["main_weapon"])
        return item_data.get("tier", 4)

    def to_dict(self):
        return {
            "hp": self.hp, "hunger": self.hunger, "thirst": self.thirst,
            "max_ram": self.max_ram, "dex": self.dex, "materials": self.materials,
            "consumables": self.consumables, "weights": self.weights,
            "inventory": self.inventory, "equipment": self.equipment, "reputation": self.reputation,
            "turn_count": self.turn_count, "difficulty": self.difficulty,
            "enemies_defeated": self.enemies_defeated, "diary": self.diary,
            "active_quest": self.active_quest,
        }

    def from_dict(self, data):
        self.hp = data.get("hp", 1500)
        self.hunger = data.get("hunger", 100)
        self.thirst = data.get("thirst", 100)
        self.max_ram = data.get("max_ram", 4)
        self.dex = data.get("dex", 10)
        self.materials = data.get("materials", 0)
        self.reputation = data.get("reputation", 0)
        self.consumables = data.get("consumables", {k: 0 for k in CONSUMABLES_DB.keys()})
        self.weights = data.get("weights", {"kinetic": 0, "scrap": 0, "cyber": 0})
        self.inventory = data.get("inventory", [])
        raw_eq = data.get("equipment", {})
        if "weapon" in raw_eq and "main_weapon" not in raw_eq:
            raw_eq["main_weapon"] = raw_eq.pop("weapon")
        self.equipment = {k: raw_eq.get(k, v) for k, v in SLOT_DEFAULTS.items()}
        self.turn_count = data.get("turn_count", 0)
        self.difficulty = data.get("difficulty", "normal")
        self.enemies_defeated = data.get("enemies_defeated", 0)
        self.diary = data.get("diary", [])
        self.active_quest = data.get("active_quest", None)

    def get_attack_power(self):
        item_data = get_equipment_data(self.equipment["main_weapon"])
        return item_data.get("power", 10)

    def get_armor_bonus(self):
        """상의+하의 → (HP 보너스, 방어력 보너스)
        미장착 슬롯은 T4 기본 수준 가상값 (HP +80, DEF +1) 부여"""
        hp_b = 0; def_b = 0
        for slot in ("top", "bottom"):
            eid = self.equipment.get(slot)
            if eid:
                d = get_equipment_data(eid)
                hp_b  += d.get("power", 0) * 8
                def_b += d.get("power", 0) // 8
            else:
                hp_b  += 80  # T4 기본 장비 가상값
                def_b += 1   # T4 기본 장비 가상값
        return hp_b, def_b

    def get_gear_atk_bonus(self):
        """비무기·비방어구 8슬롯 → 추가 공격력
        장착 시 power × 0.4 / 미장착(빈 슬롯)은 T4 기본 장비 수준 +5 가상 부여"""
        ATKSLT = {"cyberdeck","cybernetic_parts","back_gear","face",
                  "footwear","necklace","ring","custom_part"}
        bonus = 0.0
        for sl in ATKSLT:
            eid = self.equipment.get(sl)
            if eid:
                d = get_equipment_data(eid)
                bonus += d.get("power", 0) * 0.4
            else:
                bonus += 5  # T4 기본 장비 가상값
        return int(bonus)

    def get_cyberdeck_e_suppress(self):
        """사이버덱 장착 시 연속 공격 E 증가 억제량"""
        eid = self.equipment.get("cyberdeck")
        if eid:
            d = get_equipment_data(eid)
            return min(2, d.get("power", 0) // 25)
        return 0

    def get_cyber_regen(self):
        """의체부품 장착 시 전투 턴당 HP 재생량"""
        eid = self.equipment.get("cybernetic_parts")
        if eid:
            d = get_equipment_data(eid)
            return d.get("power", 0) // 20
        return 0

    @track
    def consume_resources(self):
        self.turn_count += 1
        self.hunger = max(0, self.hunger - 5)
        self.thirst = max(0, self.thirst - 6)
        
        if self.hunger == 0 or self.thirst == 0:
            self.hp -= 50
            print(f"\n{Fore.YELLOW + Style.BRIGHT}[SYSTEM WARN]{Style.RESET_ALL} 신체 연료 고갈. 바이오 조직 괴사가 시작됩니다. (HP -50)")
            wait_for_keypress()
            if self.hp <= 0:
                print(f"\n{Fore.RED + Style.BRIGHT}[SYSTEM FATAL] 신체 손상 100%. 불량 코드가 완전히 소거되었습니다.")
                sys.exit()

    def show_status(self):
        tier = self.get_highest_tier()
        _, display_hp, scale_log = apply_dynamic_scaling(0, self.hp, tier)
        _, display_max_hp, _ = apply_dynamic_scaling(0, self.max_hp, tier)

        hp_ratio = self.hp / self.max_hp if self.max_hp > 0 else 1.0
        hp_color = "bold green" if hp_ratio > 0.6 else ("bold yellow" if hp_ratio > 0.3 else "bold red")

        # HP 바
        bar_len = 20
        filled = int(bar_len * hp_ratio)
        hp_bar = f"[{hp_color}]{'█' * filled}[/][dim]{'░' * (bar_len - filled)}[/]"

        # 허기/갈증 색
        hun_col = "green" if self.hunger > 40 else ("yellow" if self.hunger > 15 else "red")
        thr_col = "cyan"  if self.thirst > 40 else ("yellow" if self.thirst > 15 else "red")

        item_data = get_equipment_data(self.equipment['main_weapon'])
        wpn_name  = item_data['name']
        wpn_pwr   = self.get_attack_power()
        gear_atk  = self.get_gear_atk_bonus()
        hp_b, def_b = self.get_armor_bonus()
        threat_mult = get_turn_scale_multiplier(self)
        diff_label  = {"easy": "이지", "normal": "노멀", "hard": "하드"}.get(self.difficulty, self.difficulty)

        food_cnt  = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k,{}).get("type")=="food")
        water_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k,{}).get("type")=="water")
        med_cnt   = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k,{}).get("type")=="hp")

        # 상태 테이블 — 2컬럼(라벨|값) 구조
        tbl = Table(box=rich_box.SIMPLE, show_header=False, padding=(0,2), expand=True)
        tbl.add_column("label", style="dim cyan", min_width=12, no_wrap=True)
        tbl.add_column("value", no_wrap=False)

        if scale_log:
            tbl.add_row("⚠ 스케일링", f"[bold yellow]{scale_log}[/]")

        tbl.add_row(
            "생명력",
            f"[{hp_color}]{display_hp:,}[/]  /  {display_max_hp:,}    {hp_bar}",
        )
        tbl.add_row(
            "허기 / 갈증",
            f"[{hun_col}]{self.hunger:3d}[/] / 100    [{thr_col}]{self.thirst:3d}[/] / 100",
        )
        tbl.add_row(
            "장착 무기",
            f"[bold white]{wpn_name}[/]  [dim](T={tier} | 위력 {wpn_pwr})[/]",
        )

        bonus_parts = []
        if gear_atk > 0: bonus_parts.append(f"공격 [green]+{gear_atk}[/green]")
        if hp_b > 0:     bonus_parts.append(f"HP [green]+{hp_b}[/green]")
        if def_b > 0:    bonus_parts.append(f"방어 [cyan]-{def_b}[/cyan]")
        bonus_str = "  |  ".join(bonus_parts) if bonus_parts else "[dim]없음[/dim]"
        tbl.add_row("장비 보너스", bonus_str)

        threat_col = "red" if threat_mult > 2 else "yellow"
        tbl.add_row(
            "전황 정보",
            f"진행 [white]{self.turn_count}턴[/white]   "
            f"난이도 [dim]{diff_label}[/dim]   "
            f"위협 배율 [{threat_col}]x{threat_mult:.2f}[/{threat_col}]   "
            f"평판 [cyan]{self.reputation:+d}[/cyan]   "
            f"RAM [magenta]{self.max_ram}[/magenta]",
        )
        tbl.add_row(
            "소지품",
            f"회복약 [bold]{med_cnt}[/bold]    "
            f"식량 [bold]{food_cnt}[/bold]    "
            f"식수 [bold]{water_cnt}[/bold]    "
            f"고철 [bold yellow]{self.materials}[/bold yellow]",
        )

        _console.print(Panel(tbl, title="[bold cyan]▌ 내 의체 시스템 상태창[/]", border_style="cyan"))

        if self.active_quest:
            q = self.active_quest
            turns_left = max(0, q["deadline"] - self.turn_count)
            quest_col = "yellow" if turns_left > 3 else "bold red"
            _console.print(Panel(
                f"[bold yellow]▶ {q['title']}[/bold yellow]   "
                f"[dim]진행[/dim] [white]{q['progress']}/{q['target']}[/white]   "
                f"[dim]기한[/dim] [{quest_col}]{turns_left}턴 남음[/{quest_col}]",
                border_style="yellow" if turns_left > 3 else "red",
                title="[yellow]▌ 돌발 퀘스트[/yellow]",
                padding=(0, 2),
            ))
        _console.print()

    def manage_inventory(self):
        slot_keys = list(SLOT_DISPLAY.keys())

        while True:
            clear_screen()
            print_header("시스템 인벤토리 및 정비")

            # ── 장착 슬롯 현황 패널 ───────────────────────────────────────────
            print("  ▌ 장착 슬롯 현황")
            print_divider()
            for si, sk in enumerate(slot_keys, 1):
                label = ea_rpad(SLOT_DISPLAY[sk], 8)
                eid = self.equipment.get(sk)
                if eid and eid != "WEAPON_NONE":
                    d = get_equipment_data(eid)
                    tag = TIER_TAGS.get(d.get("tier", 4), "T?    ")
                    print(f"   [{si:2d}] {label}  │  ★  {d['name'][:22]}    {tag}  위력:{d['power']:>4}")
                else:
                    print(f"   [{si:2d}] {label}  │  ─  미장착")
            print()

            # ── 보유 장비 목록 (슬롯별 그룹) ────────────────────────────────────
            print(f"  ▌ 보유 장비 목록  (총 {len(self.inventory)}종  /  고철: {self.materials}개)")
            print_divider()
            if not self.inventory:
                print("  데이터 없음 (인벤토리가 비어있습니다)")
            else:
                groups = {sk: [] for sk in slot_keys}
                groups["기타"] = []
                num = 1
                for item_id in self.inventory:
                    d = get_equipment_data(item_id)
                    sk = d.get("slot", "기타")
                    if sk not in groups:
                        sk = "기타"
                    groups[sk].append((num, item_id, d))
                    num += 1

                for sk in slot_keys + ["기타"]:
                    items = groups[sk]
                    if not items:
                        continue
                    label = SLOT_DISPLAY.get(sk, sk)
                    print(f"   ── {label} {'─' * max(2, 56 - len(label) * 2)}")
                    for n, iid, d in items:
                        equipped = (self.equipment.get(sk) == iid)
                        mark = "★" if equipped else " "
                        tag = TIER_TAGS.get(d.get("tier", 4), "T?    ")
                        w = d.get("slot_weight", 1.0)
                        print(f"   [{n:2d}] {mark}  {d['name'][:26]:<26}  {tag}  위력:{d['power']:>4}  W:{w:.1f}")
            print_divider()

            # ── 명령 ────────────────────────────────────────────────────────────
            print("  [ 명령 ]")
            print("   E <번호>     : 장착 (슬롯 자동 인식)     U <슬롯번호>  : 슬롯 해제")
            print("   C            : 소모품 사용                D <번호>      : 분해 (고철 추출)")
            print("   0            : 탐색망으로 복귀")
            print_divider()
            try:
                cmd = safe_input("\n  명령어 입력: ").strip().upper()
            except:
                sys.exit()

            # 장착: E <번호>
            if cmd.startswith("E "):
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    n = int(parts[1])
                    if 1 <= n <= len(self.inventory):
                        item_id = self.inventory[n - 1]
                        d = get_equipment_data(item_id)
                        sk = d.get("slot", "main_weapon")
                        prev = self.equipment.get(sk)
                        self.equipment[sk] = item_id
                        print(f"\n  [결속] '{d['name']}' → {SLOT_DISPLAY.get(sk, sk)} 슬롯에 장착되었습니다.")
                        if prev and prev != "WEAPON_NONE":
                            pd = get_equipment_data(prev)
                            print(f"  [교체] 기존 '{pd['name']}' 해제 — 인벤토리에 보관됩니다.")
                    else:
                        print("\n  [오류] 유효하지 않은 번호입니다.")
                else:
                    print("\n  [오류] 사용법: E <번호>  예) E 2")
                wait_for_keypress()

            # 해제: U <슬롯번호>
            elif cmd.startswith("U "):
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    si = int(parts[1])
                    if 1 <= si <= len(slot_keys):
                        sk = slot_keys[si - 1]
                        eid = self.equipment.get(sk)
                        if eid and eid != "WEAPON_NONE":
                            d = get_equipment_data(eid)
                            self.equipment[sk] = SLOT_DEFAULTS[sk]
                            print(f"\n  [해제] '{d['name']}' — {SLOT_DISPLAY[sk]} 슬롯 결속 해제되었습니다.")
                        else:
                            print(f"\n  [알림] {SLOT_DISPLAY[sk]} 슬롯은 이미 비어 있습니다.")
                    else:
                        print(f"\n  [오류] 슬롯 번호는 1~{len(slot_keys)} 범위입니다.")
                else:
                    print("\n  [오류] 사용법: U <슬롯번호>  예) U 1 = 주무기 해제")
                wait_for_keypress()

            # 소모품
            elif cmd == "C":
                self.use_consumable_menu()

            # 분해: D <번호>
            elif cmd.startswith("D "):
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    n = int(parts[1])
                    if 1 <= n <= len(self.inventory):
                        item_id = self.inventory[n - 1]
                        if any(v == item_id for v in self.equipment.values()):
                            print("\n  [거부] 장착 중인 장비는 분해할 수 없습니다. 먼저 슬롯에서 해제하십시오.")
                        else:
                            self.inventory.pop(n - 1)
                            gained = random.randint(15, 30)
                            self.materials += gained
                            advance_quest(self, "scrap", gained)
                            d = get_equipment_data(item_id)
                            print(f"\n  [처리] '{d['name']}' 분쇄 완료 — 일반 고철 {gained}개 추출했습니다.")
                    else:
                        print("\n  [오류] 유효하지 않은 번호입니다.")
                else:
                    print("\n  [오류] 사용법: D <번호>  예) D 3")
                wait_for_keypress()

            elif cmd == "0":
                break

            # DEV 히든 커맨드 — 메뉴에 노출 안 됨
            elif cmd == "DEV_GRANT_LEGACY":
                conn = sqlite3.connect("stigma_data.db")
                cursor = conn.cursor()
                cursor.execute("SELECT item_id, name FROM equipment WHERE tier = 0")
                legacy_items = cursor.fetchall()
                conn.close()
                granted = 0
                for iid, _ in legacy_items:
                    if iid not in self.inventory:
                        self.inventory.append(iid)
                        granted += 1
                sys_log(f"[DEV] 히든 커맨드 사용: 유물 장비 {granted}종 지급", level="DEV")
                print(f"\n  [DEV MODE] 0등급 유물 장비 {granted}종을 인벤토리에 지급했습니다.")
                wait_for_keypress()

    def use_consumable_menu(self):
        clear_screen()
        print_header("소모품 시스템 관리")
        
        avail = [k for k, v in self.consumables.items() if v > 0]
        if not avail:
            print("[알림] 현재 사용 가능한 소모품이 인벤토리에 없습니다.")
            wait_for_keypress()
            return

        for i, key in enumerate(avail):
            item = CONSUMABLES_DB[key]
            desc = ""
            if item["type"] == "hp":
                if item["is_percent"]: desc = f"HP {int(item['val']*100)}% 회복"
                else: desc = f"HP {item['val']} 고정 회복"
            elif item["type"] in ["food", "water"]:
                h_val = f"허기 +{item['hunger']} " if item['hunger'] > 0 else ""
                t_val = f"갈증 +{item['thirst']}" if item['thirst'] > 0 else ""
                desc = h_val + t_val
            
            print(f"  [{i+1}] {item['name']} (보유: {self.consumables[key]}개) - [{desc}]")
        
        print_divider()
        print("  [0] 이전 메뉴로 복귀")
        cmd = read_key()
        
        if cmd.isdigit() and 0 < int(cmd) <= len(avail):
            key = avail[int(cmd)-1]
            item = CONSUMABLES_DB[key]
            self.consumables[key] -= 1
            
            if item["type"] == "hp":
                heal_amt = int(self.max_hp * item["val"]) if item["is_percent"] else item["val"]
                self.hp = min(self.max_hp, self.hp + heal_amt)
                print(f"\n[치료] '{item['name']}' 주입 완료. 생체 신호가 안정화됩니다. (HP +{heal_amt})")
            else:
                self.hunger = min(100, self.hunger + item["hunger"])
                self.thirst = min(100, self.thirst + item["thirst"])
                print(f"\n[섭취] '{item['name']}' 섭취 완료. 바이오 연료가 보충되었습니다.")
            wait_for_keypress()

class GameMap:
    def __init__(self):
        self.size = 5
        self.player_pos = [0, 0]
        self.bunker_pos = [4, 4]
        self.visited_tiles: set = {(0, 0)}
        self.session_index = 0
        self.escaped_enemy_hp = None
        self.escaped_enemy_type = None

    def to_dict(self):
        return {
            "player_pos": self.player_pos, "visited_tiles": list(self.visited_tiles),
            "session_index": self.session_index, "escaped_enemy_hp": self.escaped_enemy_hp,
            "escaped_enemy_type": self.escaped_enemy_type,
        }

    def from_dict(self, data):
        self.player_pos = data.get("player_pos", [0, 0])
        self.visited_tiles = {tuple(x) for x in data.get("visited_tiles", [(0, 0)])}
        self.session_index = data.get("session_index", 0)
        self.escaped_enemy_hp = data.get("escaped_enemy_hp", None)
        self.escaped_enemy_type = data.get("escaped_enemy_type", None)

    def draw(self):
        grid = Text()
        for y in range(self.size - 1, -1, -1):
            grid.append("  ")
            for x in range(self.size):
                if [x, y] == self.player_pos:
                    grid.append("◈ N404 ", style="bold yellow")
                elif [x, y] == self.bunker_pos:
                    grid.append("◉ BUNK ", style="bold green")
                elif (x, y) in self.visited_tiles:
                    grid.append("· ···  ", style="dim white")
                else:
                    grid.append("░ ░░░  ", style="bright_black")
            grid.append("\n")
        _console.print(Panel(
            grid,
            title="[bold cyan]▌ 데드존 섹터 그리드 스캐너[/bold cyan]",
            subtitle="[yellow]◈[/yellow] 현재위치  [green]◉[/green] 방공호  [white]·[/white] 방문완료  [bright_black]░[/bright_black] 미탐색",
            border_style="cyan",
            expand=False,
        ))
        _console.print()

def save_data(player, grid):
    save_file = {"player": player.to_dict(), "grid": grid.to_dict()}
    try:
        with open(get_save_path(), "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        print("\n[SYSTEM] 현재 동기화 로그가 로컬 환경에 안전하게 백업되었습니다.")
    except Exception as e:
        print(f"\n[SYSTEM ERR] 백업 실패: {e}")
        
    wait_for_keypress() # 메시지 확인 후 다음으로 넘어가도록 대기

# ====================================================================
# [5] 전투 시스템 (master_formulas.json 정합 수식 적용 및 UX 대기 제어)
# ====================================================================
# ====================================================================
# 진행 턴 기반 적 스케일링
# ====================================================================
# 난이도별 턴당 증가율. 적 hp/atk = base * (1 + turn_count * rate), 선형 상승.
# normal 기준 약 50턴 경과 시 +100%(2배), hard는 약 28턴, easy는 약 100턴.
DIFFICULTY_SCALING_RATE = {"easy": 0.01, "normal": 0.02, "hard": 0.035}

# 전투 시작 시점 플레이어 체력 비율이 이 값 미만이면, '위험 상태 완화'가 적용되어
# 그 전투에 한해 턴수 증가분의 절반만 반영한다. 장비가 좋아졌다고 적이 강해지는
# 역설계가 아니라, 순수하게 플레이어가 죽기 직전인 상황을 구제하는 안전핀이다.
LOW_HP_RELIEF_THRESHOLD = 0.3
LOW_HP_RELIEF_FACTOR = 0.5


def get_turn_scale_multiplier(player):
    """진행 턴수와 난이도에 따른 적 스탯 배율을 계산한다. 플레이어 체력이 위험 수준이면 완화한다."""
    rate = DIFFICULTY_SCALING_RATE.get(player.difficulty, DIFFICULTY_SCALING_RATE["normal"])
    growth = player.turn_count * rate

    hp_ratio = player.hp / player.max_hp if player.max_hp > 0 else 1.0
    if hp_ratio < LOW_HP_RELIEF_THRESHOLD:
        growth *= LOW_HP_RELIEF_FACTOR

    return 1.0 + growth


@track
def combat_loop(player, is_boss=False, current_hp=None, enemy_type="drone"):
    scale_mult = get_turn_scale_multiplier(player)
    boss_max_hp = 0
    phase2_triggered = False

    if is_boss:
        name, e_def, base_atk, hp = "스캐브 컬렉터 [BOSS]", 45, 180, 35000
        art, header_title = ENEMY_ART["BOSS"], "SYSTEM ALERT: 숙청 시퀀스 가동"
        base_atk = int(base_atk * scale_mult)
        hp = int(hp * scale_mult)
        boss_max_hp = hp
        atk = base_atk
    elif enemy_type == "bio_hound":
        name, e_def, base_atk, hp = "바이오 하운드 [변이체]", 15, 110, 10000
        art, header_title = ENEMY_ART["BIOHOUND"], "ENCOUNTER: 생물형 기계 괴수"
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp = current_hp
            name = "상처입은 바이오 하운드"
            header_title = "ENCOUNTER: 추적된 변이체"
        else:
            hp = int(hp * scale_mult)
        atk = base_atk
    else:
        name, e_def, base_atk, hp = "오염된 스캐브 드론", 5, 80, 8000
        art, header_title = ENEMY_ART["NORMAL"], "ENCOUNTER: 포식자 조우"
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp = current_hp
            name = "상처입은 스캐브 드론"
            header_title = "ENCOUNTER: 추적된 개체"
        else:
            hp = int(hp * scale_mult)
        atk = base_atk

    turn = 1
    learning_index = 0
    consecutive_attacks = 0
    escaped = False
    escape_log = ""
    action_logs = [f"[경보] 안개 속에서 {name}이(가) 나타났습니다!"]

    hp_bonus, def_bonus = player.get_armor_bonus()
    gear_atk     = player.get_gear_atk_bonus()
    e_suppress   = player.get_cyberdeck_e_suppress()
    cyber_regen  = player.get_cyber_regen()
    if hp_bonus > 0:
        player.max_hp += hp_bonus
        player.hp = min(player.hp + hp_bonus, player.max_hp)

    while hp > 0 and player.hp > 0:
        if is_boss and turn > 15:
            clear_screen()
            type_text(Fore.RED + Style.BRIGHT + "\n[SYSTEM FATAL] 15턴 임계점 초과. 거점이 고철 분진으로 분쇄되었습니다. GAME OVER.")
            sys.exit()

        # 보스 페이즈 2 전환 (HP 50% 이하)
        if is_boss and not phase2_triggered and hp <= boss_max_hp * 0.5:
            phase2_triggered = True
            atk = int(base_atk * 1.6)
            learning_index += 5
            clear_screen()
            print_header("!! PHASE 2 — 핵심 코어 오버클럭 !!")
            type_text(Fore.RED + Style.BRIGHT + "  [경보] 스캐브 컬렉터의 핵심 코어가 과부하 상태로 돌입합니다.", 0.03)
            type_text(Fore.RED + Style.BRIGHT + "  [경보] 공격 출력 160% 강제 증폭. 패턴 분석 속도 가속.", 0.03)
            type_text(Fore.YELLOW + Style.BRIGHT + "  [경보] 딥러닝 카운터 패널 전 채널 개방.", 0.03)
            time.sleep(1.5)
            action_logs.append("[페이즈 전환] 보스가 한계를 돌파했습니다! 공격력 대폭 상승!")

        clear_screen()
        tier = player.get_highest_tier()

        _, disp_ehp, scale_log = apply_dynamic_scaling(0, hp, tier)
        _, disp_php, _ = apply_dynamic_scaling(0, player.hp, tier)
        _, disp_pmaxhp, _ = apply_dynamic_scaling(0, player.max_hp, tier)

        # 보스 체력바 시각화
        if is_boss:
            hp_pct = hp / boss_max_hp if boss_max_hp > 0 else 0
            bar_len = 40
            filled = int(bar_len * hp_pct)
            phase_tag = " [!! PHASE 2 !!]" if phase2_triggered else ""
            bar_col = (Fore.GREEN + Style.BRIGHT) if hp_pct > 0.5 else ((Fore.YELLOW + Style.BRIGHT) if hp_pct > 0.25 else (Fore.RED + Style.BRIGHT))
            hp_bar = f"  {bar_col}[{('█' * filled) + ('░' * (bar_len - filled))}] {hp_pct*100:.1f}%{phase_tag}"

        print_header(header_title)
        if scale_log:
            print(f"  {scale_log}")
            print_divider()

        print(art)
        if is_boss:
            print(hp_bar)
        print(f"  ─── 전투 턴 [{turn}] │ {name} HP: {disp_ehp:,}")
        print(f"  [내 의체] HP: {disp_php:,}/{disp_pmaxhp:,} │ 가용 RAM: {player.max_ram}")
        if is_boss:
            print(f"  [적 상태] 패턴 분석 지수 (E): {learning_index}/10")

        print("\n  [ 전투 로그 ]")
        for log in action_logs: print(f"    {_log_color(log)}{log}")
        print_divider()
        print()
        action_logs.clear()

        has_consumable = any(v > 0 for v in player.consumables.values())
        print("  1. 주무기 물리 타격 (ATTACK)")
        print("  2. 급조 바리케이드 전개 (DEFENSE - 피격 반감 및 적 분석 지수 차감)")
        print("  3. 패킷 우회 교란 (HACK - RAM 2 소모, 적 분석 지수 초기화)")
        print("  4. 전술적 후퇴 (ESCAPE - 민첩 비례 탈출 및 확률적 파밍)")
        if has_consumable:
            print("  5. 소모품 사용 (USE ITEM - 전투 중 회복, 적 반격 있음)")

        cmd = read_key()

        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                e_gain = max(0, 3 - e_suppress)
                learning_index += e_gain
                if e_suppress > 0:
                    action_logs.append(f"[경고] 동일 공격 반복 감지. 사이버덱이 학습 신호를 교란합니다. (E +{e_gain})")
                else:
                    action_logs.append(f"[경고] 동일 공격 반복 감지. 보스가 궤적을 딥러닝 중입니다. (E +{e_gain})")

            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            f_multiplier = 1.0 + (player.reputation / 2000) * 1
            effective_power = player.get_attack_power() + gear_atk

            dmg = max(100, math.floor(effective_power * f_multiplier * penalty * 100) - e_def + random.randint(-50, 50))
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)

            print(f"\n  {Fore.GREEN + Style.BRIGHT}콰아앙! 무기가 적의 장갑판을 관통했습니다! (피해량: {disp_dmg:,})")
            time.sleep(1)
            hp = max(0, hp - dmg)
            _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
            print(f"  [시스템 갱신] {name}의 잔여 체력: {disp_ehp_new:,}")
            time.sleep(1)
            action_logs.append(f"[타격] 적에게 {disp_dmg:,}의 피해를 입혔습니다.")
            time.sleep(1)

        elif cmd == "2":
            consecutive_attacks = 0
            learning_index = max(0, learning_index - 4)
            atk = int(atk * 0.5)

            print("\n  급조 바리케이드 전개! 적의 분석 궤적을 방해합니다.")
            time.sleep(1)
            action_logs.append("[방어] 바리케이드 전개. 다음 공격의 피해를 반감시킵니다.")
            time.sleep(2)

        elif cmd == "3":
            if player.max_ram >= 2:
                consecutive_attacks = 0
                learning_index = 0
                player.max_ram -= 2

                print("\n  교란 신호 방출! 적의 센서 데이터가 초기화됩니다. (RAM -2)")
                time.sleep(1)
                action_logs.append("[해킹] 교란 신호 성공. 적 분석 지수를 초기화했습니다.")
            else:
                print("\n  [오류] 시스템 RAM 가용량이 부족합니다.")
                time.sleep(0.5)
                action_logs.append("[오류] RAM 부족으로 해킹에 실패했습니다.")

        elif cmd == "4":
            if is_boss:
                print("\n  [거부] 보스전에서는 후퇴할 수 없습니다. 거점을 사수하십시오.")
                time.sleep(0.5)
                action_logs.append("[거부] 탈출 실패. 적이 퇴로를 차단했습니다.")
                time.sleep(1)
            else:
                dex_bonus = max(0, player.dex - 10) * 2
                weights = [60 + dex_bonus, max(0, 20 - dex_bonus/2), max(0, 10 - dex_bonus/4), max(0, 5 - dex_bonus/4), 5 + dex_bonus/2]
                res = random.choices(["SAFE", "NORMAL", "1.5X", "2.0X", "LUCKY"], weights=weights, k=1)[0]

                escaped = True
                if res == "SAFE":
                    escape_log = "[탈출] 적의 사각을 파고들어 피해 없이 안전하게 이탈했습니다."
                elif res in ["NORMAL", "1.5X", "2.0X"]:
                    dmg_calc = atk if res == "NORMAL" else int(atk * 1.5) if res == "1.5X" else int(atk * 2.0)

                    print(f"\n  후퇴 중 적에게 공격을 허용했습니다! (피해량: {dmg_calc:,})")
                    time.sleep(1)
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(f"  [시스템 갱신] 내 체력이 {disp_php_new:,}(으)로 감소했습니다.")
                    time.sleep(1)

                    if res == "NORMAL": escape_log = f"[탈출] 후퇴 중 적의 공격에 노출되었습니다. (피해: {dmg_calc:,})"
                    elif res == "1.5X": escape_log = f"[탈출] 치명적인 손상을 입으며 이탈했습니다. (피해: {dmg_calc:,})"
                    else: escape_log = f"[탈출 참사] 도주 중 의체 중심부가 관통당했습니다! (피해: {dmg_calc:,})"
                elif res == "LUCKY":
                    escape_log = "[기적적 탈출] 무사히 이탈하며 적 주변의 잔해에서 쓸만한 물자를 챙겼습니다."
                break

        elif cmd == "5" and has_consumable:
            consecutive_attacks = 0
            avail = [k for k, v in player.consumables.items() if v > 0]
            print("\n[ 소모품 목록 ]")
            for i, key in enumerate(avail):
                item = CONSUMABLES_DB[key]
                if item["type"] == "hp":
                    desc = f"HP {int(item['val']*100)}% 회복" if item["is_percent"] else f"HP {item['val']} 회복"
                else:
                    h_val = f"허기 +{item['hunger']} " if item['hunger'] > 0 else ""
                    t_val = f"갈증 +{item['thirst']}" if item['thirst'] > 0 else ""
                    desc = h_val + t_val
                print(f"  [{i+1}] {item['name']} x{player.consumables[key]} — {desc}")
            print("  [0] 취소")
            item_cmd = read_key()
            if item_cmd.isdigit() and 0 < int(item_cmd) <= len(avail):
                key = avail[int(item_cmd) - 1]
                item = CONSUMABLES_DB[key]
                player.consumables[key] -= 1
                if item["type"] == "hp":
                    heal = int(player.max_hp * item["val"]) if item["is_percent"] else item["val"]
                    player.hp = min(player.max_hp, player.hp + heal)
                    _, disp_heal, _ = apply_dynamic_scaling(heal, 0, tier)
                    action_logs.append(f"[회복] '{item['name']}' 사용. HP +{disp_heal:,}")
                else:
                    player.hunger = min(100, player.hunger + item["hunger"])
                    player.thirst = min(100, player.thirst + item["thirst"])
                    action_logs.append(f"[섭취] '{item['name']}' 사용. 바이오 연료 보충.")
            else:
                action_logs.append("[취소] 소모품 사용을 중단했습니다.")

        else:
            print("\n  [오류] 인식할 수 없는 명령 프로토콜입니다.")
            time.sleep(1)
            action_logs.append("[오류] 잘못된 명령어 입력.")

        # --- 적의 반격 ---
        if hp > 0 and not escaped:
            # 페이즈 2 전환 후 방어가 풀리지 않도록 atk 재복구
            if cmd == "2":
                atk = int(base_atk * (1.6 if phase2_triggered else 1.0))

            dmg_taken = max(1, atk - def_bonus)
            print(f"\n  {Fore.RED + Style.BRIGHT}{name}의 무자비한 공격! (피해량: {dmg_taken:,})")
            time.sleep(1)
            player.hp -= dmg_taken
            if cyber_regen > 0 and player.hp > 0:
                player.hp = min(player.max_hp, player.hp + cyber_regen)
            _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
            print(f"  [시스템 갱신] 내 잔여 체력: {disp_php_new:,} / {disp_pmaxhp:,}")
            time.sleep(1)
            def_note = f" (방어 -{def_bonus})" if def_bonus > 0 else ""
            action_logs.append(f"[피격] 적의 공격으로 {dmg_taken:,}의 손상을 입었습니다.{def_note}")
            time.sleep(1)

        turn += 1

    if player.hp <= 0:
        clear_screen()
        if escape_log: type_text(escape_log, 0.02)
        type_text(Fore.RED + Style.BRIGHT + "\n[SYSTEM FATAL] 신체 손상 100%. 의체 붕괴. GAME OVER.", 0.03)
        wait_for_keypress()
        sys.exit()

    if escaped:
        clear_screen()
        print_header("COMBAT ESCAPE (전술적 후퇴)")
        print(f"\n{escape_log}")
        if res == "LUCKY":
            loot_types = ["MEDKIT", "MATERIAL", "PART", "WATER", "FOOD"]
            loot_weights = [10, 10, 10, 35, 35]
            loot_res = random.choices(loot_types, weights=loot_weights, k=1)[0]

            if loot_res == "MEDKIT":
                it = roll_medkit()
                player.consumables[it] += 1
                print(f"  [수집] {CONSUMABLES_DB[it]['name']} 1개 획득")
            elif loot_res == "MATERIAL":
                player.materials += 15
                advance_quest(player, "scrap", 15)
                print("  [수집] 일반 고철 15개 획득")
            elif loot_res == "PART":
                part = random.choice(["PART_SCRAP_01", "PART_SCRAP_02", "PART_SCRAP_03"])
                player.inventory.append(part)
                item_data = get_equipment_data(part)
                print(f"  [수집] 부품 '{item_data['name']}' 획득")
            elif loot_res == "WATER":
                it = roll_water()
                player.consumables[it] += 1
                print(f"  [수집] {CONSUMABLES_DB[it]['name']} 1개 획득")
            elif loot_res == "FOOD":
                it = roll_food()
                player.consumables[it] += 1
                print(f"  [수집] {CONSUMABLES_DB[it]['name']} 1개 획득")

        log_diary(player, f"[전투] {name} — 전술적 후퇴")
        wait_for_keypress()
        if hp_bonus > 0:
            player.max_hp -= hp_bonus
            player.hp = min(player.hp, player.max_hp)
        return hp, enemy_type

    clear_screen()
    print_header("TARGET ELIMINATED (적 제압 완료)")
    print(f"\n{Fore.GREEN + Style.BRIGHT}[승리]{Style.RESET_ALL} {name}의 시스템 가동이 중지되었습니다.")
    player.enemies_defeated += 1

    if not is_boss:
        drop_roll = random.random()
        if drop_roll < 0.25:
            it = roll_food()
            player.consumables[it] += 1
            print(f"  [파밍] 적의 파편에서 '{CONSUMABLES_DB[it]['name']}' 1개를 적출했습니다.")
        elif drop_roll < 0.50:
            it = roll_water()
            player.consumables[it] += 1
            print(f"  [파밍] 적의 냉각 기관에서 '{CONSUMABLES_DB[it]['name']}' 1개를 추출했습니다.")
        elif drop_roll < 0.60:
            it = roll_medkit()
            player.consumables[it] += 1
            print(f"  [파밍] 기적적으로 온전한 '{CONSUMABLES_DB[it]['name']}' 1개를 회수했습니다.")
        else:
            player.materials += 20
            advance_quest(player, "scrap", 20)
            print("  [파밍] 고가치 일반 고철 20개를 회수했습니다.")

    advance_quest(player, "combat")
    log_diary(player, f"[전투] {name} — 제압 완료 (총 {player.enemies_defeated}기)")
    wait_for_keypress()
    if hp_bonus > 0:
        player.max_hp -= hp_bonus
        player.hp = min(player.hp, player.max_hp)
    return None, None

# ====================================================================
# [6] 메인 구동 루프 망 명세
# ====================================================================
def get_encounter_chance(player):
    hp_ratio = player.hp / player.max_hp
    base_chance = 0.10
    return base_chance + (0.25 * hp_ratio)

@track
def run_game():
    if os.name == 'nt':
        os.system('title PROTOCOL: STIGMA — 1막: 낙인')
    colorama_init(autoreset=True)
    player = Player()
    grid = GameMap()

    while True:  # 타이틀 ~ 설정 루프
        clear_screen()

        title_text = Text(justify="center")
        title_text.append("\n")
        title_text.append("P  R  O  T  O  C  O  L  :  S  T  I  G  M  A\n", style="bold white")
        title_text.append("\n")
        title_text.append("1막: 낙인  —  시스템이 폐기한 불량 코드\n", style="bold cyan")
        title_text.append("\n")
        title_text.append("─" * 54 + "\n", style="dim cyan")
        title_text.append("\n")
        title_text.append('"세상이 당신을 거부했다면,\n', style="italic cyan")
        title_text.append(' 당신은 세상의 규칙 밖에서 숨 쉬는 법을 배워야 한다."\n', style="italic cyan")
        title_text.append("\n")
        _console.print(Panel(title_text, border_style="bright_cyan", padding=(1, 4)))
        _console.print()

        has_save = os.path.exists(get_save_path())
        print_divider()
        print("  1. 새로운 게임 (New Game)")
        if has_save:
            print("  2. 동기화 복구 (Load Game)")
        exit_key = "3" if has_save else "2"
        print(f"  {exit_key}. 시스템 종료 (Exit)")
        print_divider()

        ans = read_key()

        # ── 종료 ──────────────────────────────────────────────────────────
        if ans == exit_key:
            clear_screen()
            type_text("  [SYSTEM] 그리드 접속을 종료합니다.", 0.025)
            time.sleep(0.5)
            sys.exit()

        # ── 세이브 로드 ───────────────────────────────────────────────────
        if ans == "2" and has_save:
            player = Player()
            grid = GameMap()
            try:
                with open(get_save_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                player.from_dict(data["player"])
                grid.from_dict(data["grid"])
                clear_screen()
                type_text("  [SYSTEM] 로컬 백업소에서 생체 신호를 성공적으로 복구했습니다.", 0.02)
            except Exception as e:
                type_text(f"  [ERROR] 데이터 파일 손상 ({e}). 초기화 프로토콜을 가동합니다.", 0.02)
            wait_for_keypress()
            break  # 게임 루프 진입

        # ── 새로운 게임 ───────────────────────────────────────────────────
        if ans == "1":
            player = Player()
            grid = GameMap()
            go_back = False

            while True:  # 난이도 선택 루프
                clear_screen()
                print_header("난이도 선택 (DIFFICULTY PROTOCOL)")
                print("  진행 턴이 누적될수록 적의 체력과 공격력이 함께 상승합니다.")
                print("  상승 속도는 난이도에 따라 달라집니다.\n")
                print("  1. 이지   (EASY)   — 세상은 당신을 환영하며 따뜻하게 맞이 할 것 입니다")
                print("  2. 노멀   (NORMAL) — 아직 세상은 따듯할 수도 있습니다")
                print("  3. 하드   (HARD)   — 세상은 당신을 증오 합니다, 살아 남을 수 있을 까요?")
                print_divider()
                print("  0. 메인 화면으로 돌아가기")
                print_divider()

                diff_map = {"1": "easy", "2": "normal", "3": "hard"}
                diff_ans = read_key()

                if diff_ans == "0":
                    go_back = True
                    break

                if diff_ans in diff_map:
                    player.difficulty = diff_map[diff_ans]
                    run_prologue()
                    log_diary(player, "[시작] 생존 프로토콜 개시 — N-404, 데드존 투입")
                    break

                print("\n  [오류] 1, 2, 3 중에서 선택하십시오.")
                time.sleep(0.8)

            if go_back:
                continue  # 타이틀 루프 재시작
            break  # 게임 루프 진입

        # 잘못된 입력 → 타이틀 재표시

    while True:
        clear_screen()
        if player.active_quest and player.turn_count > player.active_quest["deadline"]:
            q = player.active_quest
            print(f"\n  [퀘스트 실패] '{q['title']}' — 제한 턴 초과")
            log_diary(player, f"[퀘스트 실패] {q['title']}")
            player.active_quest = None
            time.sleep(1.5)
            clear_screen()
        grid.draw()
        player.show_status()
        
        cmd_tbl = Table(box=rich_box.SIMPLE, show_header=False, padding=(0,2), expand=True)
        cmd_tbl.add_column("key", style="bold yellow", min_width=14)
        cmd_tbl.add_column("desc", style="white")
        cmd_tbl.add_row("[W/A/S/D]", "그리드 이동  (허기·갈증 소모)")
        cmd_tbl.add_row("[F]",       "현재 타일 탐색  (전투·이벤트·자원)")
        cmd_tbl.add_row("[I]",       "인벤토리  (장비 장착 / 소모품 / 분해)")
        cmd_tbl.add_row("[J]",       "항법 일지 열람")
        cmd_tbl.add_row("[C]",       "현재 상태 저장")
        cmd_tbl.add_row("[Q]",       "시스템 접속 종료")
        _console.print(Panel(cmd_tbl, title="[bold cyan]▌ 명령 프로토콜[/]", border_style="cyan"))
        
        move = read_key()

        if move == "I":
            player.manage_inventory()
            continue
        elif move == "J":
            show_diary(player)
            continue
        elif move == "C":
            save_data(player, grid)
            continue
            
        if move == "F":
            player.consume_resources()
            print("\n[행동] 주변의 고철 더미를 뒤지기 시작합니다...")
            time.sleep(0.5)

            encounter_chance = get_encounter_chance(player)
            roll = random.random()

            if roll < 0.08 and TRADER_ITEMS:
                # 행상인 NPC 조우 (8%)
                handle_trader(player)
            elif roll < 0.08 + encounter_chance:
                # 전투 조우 (encounter_chance%)
                print("\n[경고] 탐색 중 발생한 소음이 기계 괴수를 끌어들였습니다!")
                wait_for_keypress()
                # 바이오 하운드 20% 확률 등장 (재조우 시 이전 타입 유지)
                if grid.escaped_enemy_hp is not None:
                    etype = grid.escaped_enemy_type or "drone"
                else:
                    etype = "bio_hound" if random.random() < 0.20 else "drone"
                result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                grid.escaped_enemy_hp = result_hp
                grid.escaped_enemy_type = result_type
            elif roll < 0.08 + encounter_chance + 0.20 and RANDOM_EVENTS:
                # 랜덤 서사 이벤트 (20%)
                event = random.choice(RANDOM_EVENTS)
                handle_random_event(player, event)
            elif roll < 0.08 + encounter_chance + 0.20 + 0.30:
                # 공탐색 — 분위기 로그 (30%)
                _empty = random.choice([
                    "적막만이 돌아옵니다. 이 구역은 이미 누군가 쓸고 간 흔적입니다.",
                    "먼지와 녹슨 고철 외에는 쓸만한 게 없습니다.",
                    "바람 소리와 정적뿐. 오늘은 운이 따르지 않습니다.",
                    "탐색에 성과가 없었습니다. 허기와 갈증만 소모됩니다.",
                    "이 구역은 완전히 비어 있습니다. 다른 스캐벤저가 먼저였을 겁니다.",
                    "콘크리트 파편과 연소된 배선만 남아 있습니다.",
                ])
                print(f"\n  {_empty}")
                print_ambient_lore()
            else:
                # 자원 파밍 (나머지 ~22%)
                item_roll = random.random()
                if item_roll <= 0.25:
                    gained = random.randint(10, 25)
                    player.materials += gained
                    advance_quest(player, "scrap", gained)
                    print(f"\n[획득] 엉켜있는 배선에서 일반 고철 {gained}개를 주웠습니다.")
                elif item_roll <= 0.60:
                    if random.random() < 0.5:
                        it = roll_food()
                        player.consumables[it] += 1
                        print(f"\n[획득] 낡은 컨테이너에서 '{CONSUMABLES_DB[it]['name']}' 1개를 발견했습니다.")
                    else:
                        it = roll_water()
                        player.consumables[it] += 1
                        print(f"\n[획득] 끊어진 냉각 파이프에서 '{CONSUMABLES_DB[it]['name']}' 1개를 추출했습니다.")
                else:
                    it = roll_medkit()
                    player.consumables[it] += 1
                    print(f"\n[획득] 구석의 구급 상자에서 희귀한 '{CONSUMABLES_DB[it]['name']}' 1개를 획득했습니다.")
                wait_for_keypress()
            # 탐색 퀘스트 진행 및 돌발 퀘스트 (전투 미조우 시)
            if not (0.08 <= roll < 0.08 + encounter_chance):
                advance_quest(player, "search")
                if roll >= 0.08 + encounter_chance + 0.20:
                    trigger_sudden_quest(player)
            continue
        elif move == "Q":
            clear_screen()
            print_header("생체 접속 종료 — 그리드 이탈")
            print()
            type_text("  현재까지의 당신의 흔적을 세상에 남겨 두시겠습니까?", 0.02)
            print()
            print("  저장 후 종료하시겠습니까? (Y/N): ", end="", flush=True)
            save_choice = read_key()
            if save_choice == 'Y':
                save_data(player, grid)
                print("\n  [SYSTEM] 데이터 동기화 완료. 그리드 접속을 종료합니다.")
            else:
                print("\n  [SYSTEM] 저장 없이 이탈합니다. 진행 기록은 소실됩니다.")
            print()
            print("  ╔" + "═" * 74 + "╗")
            print("  ║  " + ea_rpad("생체 접속 종료. 그리드망에서 이탈합니다.", 72) + "║")
            print("  ╚" + "═" * 74 + "╝")
            print()
            time.sleep(0.8)
            sys.exit()
        
        px, py = grid.player_pos[0], grid.player_pos[1]
        valid_move = False
        if move == "W" and py < grid.size - 1: py += 1; valid_move = True
        elif move == "S" and py > 0: py -= 1; valid_move = True
        elif move == "A" and px > 0: px -= 1; valid_move = True
        elif move == "D" and px < grid.size - 1: px += 1; valid_move = True
        else:
            print("\n[거부] 이동 불가능한 폐기물 장벽입니다.")
            time.sleep(0.5)
            continue

        if valid_move:
            grid.player_pos = [px, py]
            player.consume_resources()

            current_loc = tuple(grid.player_pos)
            is_new_tile = current_loc not in grid.visited_tiles
            grid.visited_tiles.add(current_loc)

            if current_loc == tuple(grid.bunker_pos):
                if SESSIONS_DB and len(SESSIONS_DB) > 6:
                    handle_session(player, SESSIONS_DB[6])
                # 보스전 준비 화면
                log_diary(player, "[보스] 스캐브 컬렉터 추적 확인 — 최종 전투 준비")
                clear_screen()
                print_header("!! CRITICAL ALERT — 스캐브 컬렉터 접근 중 !!")
                type_text("  지면이 거대하게 진동하기 시작합니다.", 0.025)
                type_text("  수십 개의 유압 분쇄 칼날과 회수 집게를 펼치며,", 0.025)
                type_text("  총괄국의 자동화 청소기계 '스캐브 컬렉터'가 벙커를 향해 돌진해 옵니다.", 0.025)
                print()
                type_text("  사이버덱에 경보가 떴습니다 ─ [추적 목표: N-404 / 회수 우선순위: 최고 등급]", 0.025)
                type_text("  이 기계는 처음부터 당신을 추적하고 있었습니다.", 0.025)
                print()
                type_text("  이 문이 부서지면 내일은 없습니다. 마지막 준비를 완료하십시오.\n", 0.025)
                while True:
                    print_divider()
                    tier_now = player.get_highest_tier()
                    _, disp_hp_now, _ = apply_dynamic_scaling(0, player.hp, tier_now)
                    _, disp_maxhp_now, _ = apply_dynamic_scaling(0, player.max_hp, tier_now)
                    print(f"  [현재 상태] HP: {disp_hp_now:,}/{disp_maxhp_now:,}  허기: {player.hunger}  갈증: {player.thirst}  고철: {player.materials}")
                    print_divider()
                    print("  1. 소모품 사용")
                    print("  2. 현재 상태 저장")
                    print("  3. 보스전 돌입 (ENTER COMBAT)")
                    prep_cmd = read_key()
                    if prep_cmd == "1":
                        player.use_consumable_menu()
                    elif prep_cmd == "2":
                        save_data(player, grid)
                    elif prep_cmd == "3":
                        break
                combat_loop(player, is_boss=True)
                run_boss_core_choice(player)
                run_ending(player)
                break
            else:
                session_triggered = False
                if is_new_tile and SESSIONS_DB and grid.session_index < len(SESSIONS_DB) - 1:
                    _s_base = 0.40 if grid.session_index < 3 else 0.10
                    _s_prob = max(0.05, _s_base * (1.0 - player.turn_count / 100.0))
                    if random.random() < _s_prob:
                        print("\n  [스캔] 이 구역에서 특이한 반응이 감지됩니다...")
                        time.sleep(1.2)
                        handle_session(player, SESSIONS_DB[grid.session_index])
                        grid.session_index += 1
                        session_triggered = True

                if not session_triggered:
                    if random.random() < get_encounter_chance(player):
                        print("\n[경보] 안개 속에서 기계 괴수의 광학 센서가 번뜩입니다!")
                        wait_for_keypress()
                        if grid.escaped_enemy_hp is not None:
                            etype = grid.escaped_enemy_type or "drone"
                        else:
                            etype = "bio_hound" if random.random() < 0.20 else "drone"
                        result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                        grid.escaped_enemy_hp = result_hp
                        grid.escaped_enemy_type = result_type
                    else:
                        if random.random() < 0.2:
                            print_ambient_lore()

def handle_session(player, session):
    clear_screen()
    print_header(session['title'])
    type_text(session['text'], 0.02)
    print()
    for i, choice in enumerate(session['choices']):
        print(f"  [{i+1}] {choice['text']}")
    time.sleep(1)
    while True:
        ans = read_key()
        if ans in ["1", "2", "3"]:
            choice_data = session['choices'][int(ans) - 1]
            choice_weight = choice_data.get('weight')
            if choice_weight:
                player.weights[choice_weight] += 1

            # 장비 / 고철 보상
            if choice_data.get("reward"):
                if choice_data["reward"] == "SCRAP_MAT":
                    mat_gain = choice_data.get("materials", 30)
                    player.materials += mat_gain
                    advance_quest(player, "scrap", mat_gain)
                    print(f"\n[획득] 일반 고철 {mat_gain}개를 회수했습니다.")
                else:
                    player.inventory.append(choice_data["reward"])
                    item_data = get_equipment_data(choice_data["reward"])
                    print(f"\n[보상] 소켓 파싱 완료: 장비 '{item_data['name']}' 코드를 획득했습니다.")

            # 소모품 보상
            if choice_data.get("consumable"):
                key = choice_data["consumable"]
                if key in player.consumables:
                    player.consumables[key] += 1
                    print(f"\n[보상] {CONSUMABLES_DB.get(key, {}).get('name', key)} 1개를 획득했습니다.")

            # 고철 직접 지급 (SCRAP_MAT 없이)
            raw_mat = choice_data.get("materials", 0)
            if raw_mat != 0 and not choice_data.get("reward") == "SCRAP_MAT":
                player.materials = max(0, player.materials + raw_mat)
                if raw_mat > 0:
                    advance_quest(player, "scrap", raw_mat)
                    print(f"\n[획득] 고철 +{raw_mat}개")
                else:
                    print(f"\n[소비] 고철 {raw_mat}개")

            # 생체 상태 변화
            if choice_data.get("hp_loss", 0):
                player.hp = max(1, player.hp - choice_data["hp_loss"])
                print(f"\n[피해] HP -{choice_data['hp_loss']}")
            if choice_data.get("thirst", 0):
                player.thirst = min(100, player.thirst + choice_data["thirst"])
            if choice_data.get("hunger", 0):
                player.hunger = min(100, player.hunger + choice_data["hunger"])
            if choice_data.get("ram_bonus", 0):
                player.max_ram += choice_data["ram_bonus"]
                print(f"\n[시스템] 가용 RAM +{choice_data['ram_bonus']}")

            time.sleep(0.6)
            type_text(f"\n  {choice_data['log']}", 0.025)

            _w_label = {"kinetic": "완력", "scrap": "해체", "cyber": "해킹"}.get(choice_weight, "선택")
            _reward_note = ""
            if choice_data.get("reward") and choice_data["reward"] != "SCRAP_MAT":
                _rd = get_equipment_data(choice_data["reward"])
                _reward_note = f" → {_rd['name']} 획득"
            elif choice_data.get("reward") == "SCRAP_MAT":
                _reward_note = f" → 고철 +{choice_data.get('materials', 30)}"
            if choice_data.get("ram_bonus"):
                _reward_note += f" (RAM +{choice_data['ram_bonus']})"
            log_diary(player, f"[세션] {session['title']} — {_w_label}{_reward_note}")

            if choice_weight and player.weights[choice_weight] >= 3:
                _wcb = {
                    "kinetic": "\n  [행동 패턴 고착화] 물리적 집행이 N-404의 1순위 프로토콜로 등록됩니다.",
                    "scrap":   "\n  [행동 패턴 고착화] 정밀 분해가 N-404의 1순위 프로토콜로 등록됩니다.",
                    "cyber":   "\n  [행동 패턴 고착화] 코드 침투가 N-404의 1순위 프로토콜로 등록됩니다.",
                }
                time.sleep(0.3)
                type_text(_wcb[choice_weight], 0.022)

            wait_for_keypress()
            break

def trigger_sudden_quest(player):
    """12% 확률로 돌발 퀘스트 발생. 기존 활성 퀘스트가 있으면 무시."""
    if player.active_quest is not None or not SUDDEN_QUESTS:
        return
    if random.random() > 0.12:
        return
    tpl = random.choice(SUDDEN_QUESTS)
    deadline = player.turn_count + tpl["turns"]
    q: dict = {
        "id":          tpl["id"],
        "title":       tpl["title"],
        "type":        tpl["type"],
        "target":      tpl["target"],
        "progress":    0,
        "deadline":    deadline,
        "reward_type": tpl["reward_type"],
        "reward_desc": tpl["reward_desc"],
    }
    if "reward_id"     in tpl: q["reward_id"]     = tpl["reward_id"]
    if "reward_amount" in tpl: q["reward_amount"] = tpl["reward_amount"]
    player.active_quest = q
    clear_screen()
    print_header(f"!! 돌발 퀘스트 — {tpl['title']}")
    type_text(f"  {tpl['desc']}", 0.022)
    print()
    print(f"  [목표]  {tpl['detail']}")
    print(f"  [기한]  {tpl['turns']}턴 이내  (현재 {player.turn_count}턴 → 기한 {deadline}턴)")
    print(f"  [보상]  {tpl['reward_desc']}")
    print()
    log_diary(player, f"[퀘스트] {tpl['title']} 발생 (기한: {deadline}턴)")
    wait_for_keypress()


def _complete_quest(player):
    """퀘스트 완료 처리: 보상 지급 후 active_quest 초기화."""
    q = player.active_quest
    if q is None:
        return
    clear_screen()
    print_header(f"!! 돌발 퀘스트 완료 — {q['title']}")
    print()
    print(f"  [보상 지급]  {q['reward_desc']}")
    rtype = q["reward_type"]
    if rtype == "consumable":
        rid = q["reward_id"]
        player.consumables[rid] = player.consumables.get(rid, 0) + 1
        print(f"  {CONSUMABLES_DB.get(rid, {}).get('name', rid)} 소지품에 추가됨.")
    elif rtype == "materials":
        amt = q.get("reward_amount", 30)
        player.materials += amt
        print(f"  잔여 고철: {player.materials}개")
    elif rtype == "ram":
        amt = q.get("reward_amount", 1)
        player.max_ram += amt
        print(f"  가용 RAM: {player.max_ram}")
    print()
    log_diary(player, f"[퀘스트 완료] {q['title']} → {q['reward_desc']}")
    player.active_quest = None
    wait_for_keypress()


def advance_quest(player, qtype, amount=1):
    """퀘스트 진행 갱신. qtype이 일치할 때만 progress 누적 후 완료 판정."""
    q = player.active_quest
    if q is None or q["type"] != qtype:
        return
    q["progress"] = min(q["target"], q["progress"] + amount)
    if q["progress"] >= q["target"]:
        _complete_quest(player)


def handle_random_event(player, event):
    """RANDOM_EVENTS DB에서 뽑힌 미니 이벤트를 처리합니다."""
    clear_screen()
    print_header(f"[탐색 이벤트] {event['title']}")
    type_text(event["text"], 0.02)
    print()

    if event["type"] == "simple":
        result = event["result"]
        time.sleep(0.5)
        type_text(result["log"], 0.02)
        if result.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - result["hp_loss"])
            print(f"  [피해] HP -{result['hp_loss']}")
        if result.get("materials", 0) != 0:
            player.materials = max(0, player.materials + result["materials"])
            sign = "+" if result["materials"] > 0 else ""
            print(f"  [자원] 고철 {sign}{result['materials']}개")
            if result["materials"] > 0:
                advance_quest(player, "scrap", result["materials"])
        if result.get("hunger", 0) < 0:
            player.hunger = max(0, player.hunger + result["hunger"])
        if result.get("thirst", 0) < 0:
            player.thirst = max(0, player.thirst + result["thirst"])
        if result.get("consumable"):
            key = result["consumable"]
            if key in player.consumables:
                player.consumables[key] += 1
                print(f"  [획득] {CONSUMABLES_DB[key]['name']} 1개")
        log_diary(player, f"[이벤트] {event['title']}")
        wait_for_keypress()

    elif event["type"] == "choice":
        choices = event["choices"]
        for i, c in enumerate(choices):
            print(f"  [{i+1}] {c['text']}")
        time.sleep(0.5)
        while True:
            ans = read_key()
            if ans.isdigit() and 1 <= int(ans) <= len(choices):
                c = choices[int(ans) - 1]
                break

        if c.get("weight"):
            player.weights[c["weight"]] += 1

        print()
        type_text(c["log"], 0.02)
        time.sleep(0.5)

        if c.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - c["hp_loss"])
            print(f"  [피해] HP -{c['hp_loss']}")
        mat = c.get("materials", 0)
        if mat != 0:
            player.materials = max(0, player.materials + mat)
            sign = "+" if mat > 0 else ""
            print(f"  [자원] 고철 {sign}{mat}개")
            if mat > 0:
                advance_quest(player, "scrap", mat)
        if c.get("hunger", 0) > 0:
            player.hunger = min(100, player.hunger + c["hunger"])
        if c.get("thirst", 0) > 0:
            player.thirst = min(100, player.thirst + c["thirst"])
        if c.get("ram_bonus", 0) > 0:
            player.max_ram += c["ram_bonus"]
            print(f"  [RAM] 가용 RAM +{c['ram_bonus']}")
        if c.get("consumable"):
            key = c["consumable"]
            if key in player.consumables:
                player.consumables[key] += 1
                print(f"  [획득] {CONSUMABLES_DB[key]['name']} 1개")
        _ew_label = {"kinetic": "완력", "scrap": "해체", "cyber": "해킹"}.get(c.get("weight"), "선택")
        log_diary(player, f"[이벤트] {event['title']} — {_ew_label}")
        wait_for_keypress()


def handle_trader(player):
    """행상인 NPC 조우 — 고철로 소모품을 구매합니다."""
    clear_screen()
    print_header("ENCOUNTER: 유랑 행상인 조우")
    type_text("  낡은 카트를 밀며 나타난 수상한 인물이 당신을 보고 멈춥니다.", 0.02)
    type_text("  '살아있는 녀석이라니... 운이 좋군. 뭐라도 사갈 텐가?'", 0.02)
    print()

    while True:
        print_divider()
        print(f"  [보유 고철: {player.materials}개]\n")
        print("  [ 판매 목록 ]")
        for i, item in enumerate(TRADER_ITEMS):
            stock_key = item["id"]
            owned = player.consumables.get(stock_key, 0)
            print(f"  [{i+1}] {item['name']:<20} — {item['cost']:>3}개  (보유: {owned}개)")
        print_divider()
        print("  [0] 거래 종료")

        cmd = read_key()

        if cmd == "0":
            type_text("  '또 보자고.' 행상인이 카트를 밀며 안개 속으로 사라집니다.", 0.02)
            wait_for_keypress()
            break

        if cmd.isdigit() and 1 <= int(cmd) <= len(TRADER_ITEMS):
            chosen = TRADER_ITEMS[int(cmd) - 1]
            if player.materials >= chosen["cost"]:
                player.materials -= chosen["cost"]
                key = chosen["id"]
                player.consumables[key] += 1
                print(f"\n  [거래 완료] '{chosen['name']}' 구매. 잔여 고철: {player.materials}개")
                log_diary(player, f"[거래] {chosen['name']} 구매 (-{chosen['cost']} 고철)")
                time.sleep(1)
            else:
                print(f"\n  [거부] 고철이 부족합니다. ({player.materials}/{chosen['cost']}개)")
                time.sleep(1)
        else:
            print("\n  [오류] 올바른 번호를 입력하세요.")
            time.sleep(0.5)


def run_prologue():
    """신규 게임 시작 시 전체 프롤로그 시퀀스를 재생합니다."""
    clear_screen()
    print_header("프로토콜: 낙인 — 시퀀스 초기화")
    print()
    print("  [SYSTEM] 서사 시퀀스 로드 완료.")
    print()
    print("  1. 프롤로그 재생  (부팅 시퀀스 → 도입 서사 → 세계관 → 조작법)")
    print("  0. 스킵           (즉시 게임 시작)")
    print()
    skip_ans = read_key()
    if skip_ans == "0":
        clear_screen()
        type_text("[SYSTEM] 서사 시퀀스 스킵. 생존 인터페이스 가동.", 0.022)
        time.sleep(0.6)
        return

    clear_screen()

    # ── 단계 1: 부팅 시퀀스 ──────────────────────────────────────────────
    boot_log = [
        ("  [SYSTEM BOOT]   시각 센서 복구 중...   0%", 0.04),
        ("  [SYSTEM BOOT]   시각 센서 복구 중...  12%", 0.04),
        ("  [SYSTEM BOOT]   시각 센서 복구 중...  45%", 0.03),
        ("  [SYSTEM BOOT]   시각 센서 복구 중... 100%", 0.03),
        ("", 0.1),
        ("  [SYSTEM LOG]    바이오 링크 프로토콜 체크 중...", 0.03),
        ("  [ERROR  ]       중앙 서버 핸드셰이크 실패 — 접속 불가.", 0.03),
        ("  [SYSTEM LOG]    유기체 일련번호 조회 중... 'N-404'", 0.03),
        ("  [ERROR  ]       등록되지 않은 코드. 승인 거부.", 0.04),
        ("  [WARNING]       분류: 무국적 불량 코드 (Civilian).", 0.04),
        ("  [SYSTEM ]       시스템 조치: 추적 후 영구 폐기.", 0.04),
    ]
    for line, spd in boot_log:
        type_text(line, spd)
        time.sleep(0.08)

    time.sleep(1.2)
    clear_screen()

    # ── 단계 2: 도입 서사 ────────────────────────────────────────────────
    print_header("1막: 낙인 (Stigma) — 시스템이 폐기한 불량 ***")
    time.sleep(0.5)

    narr = [
        "눈을 뜨자마자 온몸의 감각을 찌르는 것은 지독한 녹슨 기름 냄새와 차가운 빗방울이었다.",
        "고개를 들자 수십 미터 높이의 거대한 강철 무덤이 하늘을 완전히 가로막고 있다.",
        "네오 아크 상층민들이 쓰다 버린 드론의 사체, 마모된 메인보드 파편이 끝없는 산을 이룬 곳.",
        "이곳은 시스템이 당신을 쓰레기처럼 내던진 '폐기물 처리장' — 데드존의 외각이다.",
        "",
        "배 속에서 내장 조직이 꼬이는 듯한 강렬한 통증이 느껴진다.",
        "목 뒤의 소켓이 차갑게 식어가며, 단 하나의 메시지가 눈 앞을 아득히 채웁니다:",
        "",
        "  \"당신은 폐기된 ***입니다. 회수 또는 소거.\"",
    ]
    for line in narr:
        type_text(f"  {line}", 0.022) if line else print()
        time.sleep(0.1)

    time.sleep(1.0)
    wait_for_keypress()
    clear_screen()

    # ── 단계 3: 세계관 브리핑 ────────────────────────────────────────────
    print_header("세계관 브리핑 — 당신이 버려진 이유")
    world_log = [
        ("[1주기]  지구 천연자원이 완전히 고갈되었습니다."),
        ("         국제 연합이 대기업 연합의 마스터 AI 기동을 승인 하였습니다."),
        ("         대기업 연합의 마스터 AI가 연산을 실행했습니다."),
        ("         연산 결과: '인류의 95%를 격리해야 인류 존속 가능'. 대붕괴 시작."),
        ("         총괄국을 조직하여 인류의 95%를 격리,처단 권한 위임 하였습니다"),
        (""),
        ("[2주기]  총괄국이 남은 자원 영역에 가상현실 차단막 '네오 아크'를 건설."),
        ("         차단막 밖의 95% 영토는 방사능과 폐기된 기계의 황무지 — '데드존'이 됐다."),
        ("         총괄국 수장 주디스 케인이 네오 아크를 완전 통제하고 있다."),
        (""),
        ("[현재]   데드존의 스캐벤저들이 구시대 유물을 발굴하며 총괄국에 균열을 내고 있다."),
        ("         당신은 네오 아크 실험실에서 '불량 ***'로 낙인찍혀 이곳에 폐기됐다."),
        ("         살아있는 불법 ***는 총괄국 AI에 의해 회수 또는 소거 대상이다."),
    ]
    for line in world_log:
        type_text(f"  {line}", 0.02) if line else print()
        time.sleep(0.05)

    time.sleep(0.8)
    print()
    print_divider()
    type_text("  당신의 목표: 쓰레기 바다를 탐색해 방공호 벙커를 장악하라.", 0.025)
    type_text("  당신의 행동 방식이 당신의 삶을 결정할 것이다.", 0.025)
    print_divider()

    wait_for_keypress()
    clear_screen()

    # ── 단계 4: 조작법 안내 ──────────────────────────────────────────────
    print_header("생존 프로토콜 안내 — 운용 매뉴얼")
    guide = [
        ("W / A / S / D", "그리드 이동. 1타일 이동 시 허기/갈증이 소모됩니다."),
        ("F             ", "현재 위치 탐색. 전투·이벤트·자원 획득이 발생합니다."),
        ("I             ", "인벤토리. 장비 장착, 소모품 사용, 분해 가능."),
        ("C             ", "현재 상태 저장 (stigma_save.json 동기화)."),
        ("Q             ", "게임 종료. 저장 여부 선택 가능."),
    ]
    for key, desc in guide:
        print(f"  [{key}]  {desc}")

    print()
    print_divider()
    type_text("  [경고] 허기/갈증이 0이 되면 매 턴 HP가 감소합니다.", 0.022)
    type_text("  [경고] 이동·탐색 중 기계 괴수와의 전투가 발생할 수 있습니다.", 0.022)
    type_text("  [경보] 당신의 선택은 데이터로 기록됩니다. 선택이 곧 당신입니다.", 0.025)
    print_divider()
    print()
    type_text("  목표 좌표: (4, 4) — 방공호 벙커 [B]. 지역 우상단.", 0.022)
    type_text("  이동하며 탐색하라. 허기와 갈증을 관리하라. 살아남아라.", 0.022)

    wait_for_keypress()
    clear_screen()
    type_text("[SYSTEM] 생존 인터페이스 가동. 그리드 스캐너 활성화.", 0.022)
    time.sleep(0.6)


def run_boss_core_choice(player):
    """보스 격파 후 코어 처분 선택 — 최종 직업 가중치에 영향을 미칩니다."""
    clear_screen()
    print_header("BOSS GLITCH LOG — 핵심 코어 노출")
    type_text("  거대한 기계 괴수가 스파크를 뿜으며 무릎을 꿇습니다.", 0.03)
    type_text("  중앙 제어선이 마비되며 파랗게 요동치는 동력 코어가 노출됩니다.", 0.03)
    type_text("  이 코어를 아지트 터미널에 꽂는 순간, 거점이 완성된다.", 0.03)
    print()
    time.sleep(1.0)
    type_text("  [SYSTEM] 경고. 코어 처분 방식이 행동 코드에 영구 기록됩니다.", 0.03)
    type_text("           이 선택이 당신의 각성 경로를 확정합니다.", 0.03)
    print()
    print_divider()
    print("  1. 코어를 과부하 시켜 의체에 직접 이식한다.")
    print("     ➔ 물리 격돌 W_kinetic 대폭 상승")
    print()
    print("  2. 코어의 희귀 희토류를 분해해 방공호 발전기에 직결한다.")
    print("     ➔ 자원 정제 W_scrap 대폭 상승")
    print()
    print("  3. 코어 내부의 네오 아크 암호화 칩을 사이버덱에 강제 포팅한다.")
    print("     ➔ 연산 침투 W_cyber 대폭 상승")
    print_divider()

    while True:
        ans = read_key()
        if ans == "1":
            player.weights["kinetic"] += 3
            print()
            type_text("  신경망 리미터가 과부하 상태로 돌입합니다. 의체 전역에 금속음이 울립니다.", 0.03)
            type_text("  폭발적인 에너지가 근육 신경망을 재배선합니다. 강해집니다.", 0.03)
            break
        elif ans == "2":
            player.weights["scrap"] += 3
            print()
            type_text("  코어를 정밀 분해합니다. 방공호 발전기가 오렌지빛으로 점화됩니다.", 0.03)
            type_text("  터미널 화면에 '장인 인증 코드'가 파싱됩니다. 기술이 각인됩니다.", 0.03)
            break
        elif ans == "3":
            player.weights["cyber"] += 3
            print()
            type_text("  사이버덱이 달아오르며 암호화 칩이 신경망 내부에 포팅됩니다.", 0.03)
            type_text("  총괄국 군사 기밀 코드가 덱에 박혀 흐릅니다. 세계가 코드로 보입니다.", 0.03)
            break

    time.sleep(1.5)
    wait_for_keypress()


def run_ending(player):
    clear_screen()
    print_header("PIONEER PROTOCOL: NORMALIZATION EXECUTION")
    type_text("  코어가 아지트 터미널에 꽂히는 순간 —", 0.03)
    type_text("  암흑천지였던 지하 방공호에 오렌지색 비상등이 켜지며 아날로그 진동음이 바닥을 울립니다.", 0.03)
    type_text("  총괄국의 마스터 AI 감시망을 차단한 첫 번째 디지털 은신처가 완성됩니다.", 0.03)
    type_text("  눈부신 경고창과 함께 당신의 행위 로그 전체가 스캔되기 시작합니다.\n", 0.03)

    total = sum(player.weights.values()) or 1
    w_k, w_s, w_c = player.weights['kinetic'], player.weights['scrap'], player.weights['cyber']

    time.sleep(1)
    print_divider()
    print("  [ 행위 로그 분석 — 의식 코드 동기화율 ]")
    print_divider()

    bar_len = 30
    def make_bar(val, tot):
        filled = int(bar_len * val / tot) if tot else 0
        return f"[{'█' * filled}{'░' * (bar_len - filled)}] {val/tot*100:.1f}%"

    print(f"  컴뱃 포스     (kinetic) : {make_bar(w_k, total)}  ({w_k}회)")
    print(f"  메카니컬 테크 (scrap)   : {make_bar(w_s, total)}  ({w_s}회)")
    print(f"  넷 포스       (cyber)   : {make_bar(w_c, total)}  ({w_c}회)")
    print()
    time.sleep(1.5)

    print_divider()
    if w_k == w_s == w_c:
        type_text("  [HIDDEN PROTOCOL] tri_balance_awakening — 황금의 조율사 해제", 0.035)
        print()
        type_text("  경고. 모든 가중치 배열이 완벽한 데드락 균형을 이루었습니다.", 0.03)
        type_text("  시스템이 당신의 성향을 단일 코드로 정의하지 못해 히든 개척자 프로토콜을 개방합니다.", 0.03)
        type_text("  모든 역할군의 기본 노드가 동시에 교차 활성화됩니다.", 0.03)
        type_text("  당신은 어느 한 쪽의 논리에도 귀속되지 않는 유일한 존재입니다.", 0.03)
    elif w_k >= w_s and w_k >= w_c:
        type_text("  [각성] 컴뱃 포스 (Combat Force) 코드 직결.", 0.035)
        print()
        type_text("  당신의 육체적 집행 기록이 정량화되었습니다.", 0.03)
        type_text("  찢어발긴 기계들의 강화 장갑 프로토콜이 신경망 리미터를 영구 해제합니다.", 0.03)
        type_text("  뼈를 깎는 무력의 집행자 — [컴뱃 포스]가 당신의 척수에 직결됩니다.", 0.03)
        type_text("  강한 자가 살아남는다. 당신은 이제 데드존의 법칙 그 자체입니다.", 0.03)
    elif w_s >= w_k and w_s >= w_c:
        type_text("  [각성] 메카니컬 테크 (Mechanical Tech) 인덱스 전이.", 0.035)
        print()
        type_text("  그리드 화면에 고철 분해 및 유물 제어 시퀀스가 파싱됩니다.", 0.03)
        type_text("  녹슨 발전기가 복구되자, 고대 설계도가 당신을 장인으로 인정합니다.", 0.03)
        type_text("  고철의 연금술사 — [메카니컬 테크] 자격이 부여됩니다.", 0.03)
        type_text("  폐철 하나도 낭비하지 않는다. 당신의 손 끝에서 데드존이 재건됩니다.", 0.03)
    else:
        type_text("  [각성] 넷 포스 (Net Force) 아나키스트 패킷 주입.", 0.035)
        print()
        type_text("  마스터 AI 감시망 '그리드'에 당신이 새겨넣은 유령 백도어가 고정 노드로 승인됩니다.", 0.03)
        type_text("  가상현실 프로토콜을 왜곡하는 아나키스트 — [넷 포스]의 코드가 주입됩니다.", 0.03)
        type_text("  코드는 현실보다 강하다. 당신은 시스템의 균열을 타고 흐릅니다.", 0.03)
        type_text("  총괄국 AI가 당신을 단 한 번도 예측하지 못했습니다.", 0.03)
    print_divider()

    print()
    time.sleep(1)

    # 플레이 통계
    print_divider()
    print("  [ 1막 클리어 통계 ]")
    print_divider()
    tier_final = player.get_highest_tier()
    tier_names = {4: "급조 (T4)", 3: "규격 (T3)", 2: "정제 (T2)", 1: "기업제 (T1)", 0: "유물 (T0)"}
    diff_label = {"easy": "이지", "normal": "노멀", "hard": "하드"}.get(player.difficulty, player.difficulty)
    threat_final = get_turn_scale_multiplier(player)

    print(f"  난이도           : {diff_label}")
    print(f"  총 진행 턴       : {player.turn_count}턴")
    print(f"  최종 위협 배율   : x{threat_final:.2f}")
    print(f"  제압한 적        : {player.enemies_defeated}기")
    print(f"  잔여 HP          : {player.hp:,} / {player.max_hp:,}")
    print(f"  잔여 고철        : {player.materials}개")
    print(f"  보유 장비 수     : {len(player.inventory)}종")
    print(f"  최고 장비 등급   : {tier_names.get(tier_final, 'N/A')}")

    total_consumables = sum(player.consumables.values())
    print(f"  잔여 소모품      : {total_consumables}개")
    print_divider()
    time.sleep(1)

    print()
    time.sleep(1.2)
    type_text("  [SYSTEM]: 개척자 프로토콜 (Pioneer Protocol) 전면 승인.", 0.04)
    type_text("  [PROCESS]: 초기 스탯 환급 및 각성 클래스 스케일링 가동 대기.", 0.04)
    print()
    time.sleep(0.8)
    type_text("  \"당신은 마침내 시스템의 구역에 확고한 첫 영토를 개척해 냈습니다.\"", 0.04)
    print()
    type_text("  벙커 외부로 가이거 계수기의 비명음과 방사능 폭풍 소리가 아스라이 멀어집니다.", 0.03)
    type_text("  방공호의 비상등이 켜집니다. 이것은 끝이 아닙니다.", 0.03)
    type_text("  마스터 AI의 그리드는 아직 살아있고 — 당신의 낙인은 이제 시작입니다.", 0.03)
    print()
    time.sleep(1.2)
    type_text("  그리고 —", 0.04)
    time.sleep(0.6)
    type_text("  데드존 어딘가에서 발신되던 그 정체불명의 신호.", 0.03)
    type_text("  아직도 규칙적으로 송신되고 있다.", 0.03)
    type_text("  누군가 당신을 기다리고 있다.", 0.035)
    print()
    time.sleep(1.0)
    print(Fore.GREEN + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.GREEN + Style.BRIGHT + "  ║  " + ea_rpad("1막 [낙인] 클리어 — DEMO END", 72) + "║")
    print(Fore.GREEN + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    wait_for_keypress()

if __name__ == "__main__":
    run_game()
