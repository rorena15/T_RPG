import math
import random
import sys
import time
import os
import json
import sqlite3
import db_init
import constants
from sys_log import sys_log, track, track_event, log_error, setup_global_exception_hook
from colorama import Fore, Back, Style, init as colorama_init
from rich.console import Console
from i18n import t, set_lang
import sound
import skills
from updater import check_and_prompt_update

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
    print(f"\n{t('wait_any_key')}")
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
        return int(raw_dmg * 100), int(raw_hp * 10), t('scale_log_t23')
    else:
        return int(raw_dmg * 100000), int(raw_hp * 100), t('scale_log_t01')

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
    # 내부 너비 74, 양쪽 ║ 포함 총 78자 박스
    # 컨텐츠 영역: ║  {title}{pad}║  →  title + pad = 72 표시 너비
    print()
    print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.WHITE + Style.BRIGHT + "  ║  " + ea_rpad(title, 72) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    print()

def print_divider():
    print(Fore.WHITE + Style.BRIGHT + "  " + "─" * 74)

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
        print_header(t('diary_header'))
        print()
        print(t('diary_empty'))
        print()
        wait_for_keypress()
        return

    page_size = 18
    total = len(entries)
    pages = max(1, (total + page_size - 1) // page_size)
    page = pages - 1  # 최신 페이지부터

    while True:
        clear_screen()
        print_header(t('diary_header_paged', page=page + 1, pages=pages))
        start = page * page_size
        end = min(start + page_size, total)
        for e in entries[start:end]:
            print(f"  {e}")
        print()
        print_divider()
        nav = []
        if page > 0:
            nav.append(t('diary_nav_prev'))
        if page < pages - 1:
            nav.append(t('diary_nav_next'))
        nav.append(t('diary_nav_back'))
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
        self.vit   = constants.STAT_DEFAULT_VIT
        self.int_s = constants.STAT_DEFAULT_INT
        self.dex   = constants.STAT_DEFAULT_DEX
        self.lv    = constants.STAT_DEFAULT_LV

        self.max_hp  = self.calc_max_hp()
        self.hp      = self.max_hp
        self.max_ram = self.calc_max_ram()
        self.hunger = 100
        self.thirst = 100
        self.alert_level = 0
        self.temp_weapon_uses: dict = {}
        self.job_class: str = ""
        self.skill_slots: list = []
        self.active_buffs: dict = {}
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

    def calc_max_hp(self):
        return (constants.STAT_HP_BASE
                + (self.lv * constants.STAT_HP_LV)
                + (self.vit * constants.STAT_HP_VIT)
                + math.floor(constants.f_A(self.vit) * constants.STAT_HP_fVIT))

    def calc_max_ram(self):
        return 4 + math.floor(self.int_s * constants.STAT_RAM_INT)

    def calc_eva_rate(self):
        return min(0.50, (self.dex * 0.01) / (1 + self.dex * 0.01))

    def calc_crt_rate(self):
        return min(0.75, (self.dex * 0.015) / (1 + self.dex * 0.015))

    def calc_def_base(self):
        return ((self.lv * constants.STAT_DEF_LV)
                + (self.vit * constants.STAT_DEF_VIT)
                + math.floor(constants.f_A(self.vit) * constants.STAT_DEF_fVIT))

    def calc_hunger_decay_rate(self):
        return min(0.60, (self.vit * 0.01) / (1 + self.vit * 0.01))

    def get_highest_tier(self):
        item_data = get_equipment_data(self.equipment["main_weapon"])
        return item_data.get("tier", 4)

    def to_dict(self):
        return {
            "hp": self.hp, "max_hp": self.max_hp, "hunger": self.hunger, "thirst": self.thirst,
            "alert_level": self.alert_level, "temp_weapon_uses": self.temp_weapon_uses,
            "job_class": self.job_class, "skill_slots": self.skill_slots, "active_buffs": self.active_buffs,
            "vit": self.vit, "int_s": self.int_s, "dex": self.dex, "lv": self.lv,
            "max_ram": self.max_ram, "materials": self.materials,
            "consumables": self.consumables, "weights": self.weights,
            "inventory": self.inventory, "equipment": self.equipment, "reputation": self.reputation,
            "turn_count": self.turn_count, "difficulty": self.difficulty,
            "enemies_defeated": self.enemies_defeated, "diary": self.diary,
            "active_quest": self.active_quest,
        }

    def from_dict(self, data):
        self.vit   = data.get("vit",   constants.STAT_DEFAULT_VIT)
        self.int_s = data.get("int_s", constants.STAT_DEFAULT_INT)
        self.dex   = data.get("dex",   constants.STAT_DEFAULT_DEX)
        self.lv    = data.get("lv",    constants.STAT_DEFAULT_LV)
        self.max_hp  = data.get("max_hp",  self.calc_max_hp())
        self.max_ram = data.get("max_ram", self.calc_max_ram())
        self.hp = data.get("hp", self.max_hp)
        self.hunger = data.get("hunger", 100)
        self.thirst = data.get("thirst", 100)
        self.alert_level = data.get("alert_level", 0)
        self.temp_weapon_uses = data.get("temp_weapon_uses", {})
        self.job_class   = data.get("job_class", "")
        self.skill_slots = data.get("skill_slots", [])
        self.active_buffs = data.get("active_buffs", {})
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
        r_decay = self.calc_hunger_decay_rate()
        self.hunger = max(0, self.hunger - max(1, round(5 * (1 - r_decay))))
        self.thirst = max(0, self.thirst - max(1, round(6 * (1 - r_decay))))
        sound.check_survival_alert(self.hunger, self.thirst)
        if self.hunger == 0 or self.thirst == 0:
            self.hp -= 50
            print(f"\n{Fore.YELLOW + Style.BRIGHT}{t('resource_depleted')}")
            wait_for_keypress()
            if self.hp <= 0:
                print(f"\n{Fore.RED + Style.BRIGHT}{t('resource_fatal')}")
                sys.exit()

    def show_status(self):
        tier = self.get_highest_tier()
        _, display_hp, scale_log = apply_dynamic_scaling(0, self.hp, tier)
        _, display_max_hp, _ = apply_dynamic_scaling(0, self.max_hp, tier)

        print("  ╔" + "═" * 74 + "╗")
        print("  ║  " + ea_rpad(t('status_header'), 72) + "║")
        print("  ╚" + "═" * 74 + "╝")
        if scale_log:
            print(f"  {scale_log}")
            print_divider()

        hp_ratio = self.hp / self.max_hp if self.max_hp > 0 else 1.0
        hp_col = (Fore.GREEN + Style.BRIGHT) if hp_ratio > 0.6 else ((Fore.YELLOW + Style.BRIGHT) if hp_ratio > 0.3 else (Fore.RED + Style.BRIGHT))
        hp_colored = f"{hp_col}{display_hp:,}{Style.RESET_ALL}"
        print(t('status_hp', hp=hp_colored, maxhp=f"{display_max_hp:,}", hunger=self.hunger, thirst=self.thirst))

        item_data = get_equipment_data(self.equipment['main_weapon'])
        wpn_name = item_data['name']
        wpn_pwr = self.get_attack_power()
        gear_atk = self.get_gear_atk_bonus()
        hp_b, def_b = self.get_armor_bonus()

        print(t('status_weapon', name=wpn_name, tier=tier, power=wpn_pwr, rep=self.reputation))
        if gear_atk > 0 or hp_b > 0 or def_b > 0:
            bonus_parts = []
            if gear_atk > 0: bonus_parts.append(t('status_atk_bonus', val=gear_atk))
            if hp_b   > 0: bonus_parts.append(t('status_hp_bonus', val=hp_b))
            if def_b  > 0: bonus_parts.append(t('status_def_bonus', val=def_b))
            print(t('status_gear_bonus', bonus=' | '.join(bonus_parts)))

        threat_mult = get_turn_scale_multiplier(self)
        diff_label = {"easy": t('diff_label_easy'), "normal": t('diff_label_normal'), "hard": t('diff_label_hard')}.get(self.difficulty, self.difficulty)
        print(t('status_turn_line', turn=self.turn_count, diff=diff_label, mult=threat_mult))

        eva  = self.calc_eva_rate()
        crt  = self.calc_crt_rate()
        def_ = self.calc_def_base()
        print(t('status_stats_line', vit=self.vit, int_s=self.int_s, dex=self.dex,
                def_val=def_, eva=eva * 100, crt=crt * 100))

        al = max(0, min(100, self.alert_level))
        al_filled = al // 5
        al_bar = "█" * al_filled + "░" * (20 - al_filled)
        if al >= 80:
            al_col = Fore.RED + Style.BRIGHT
        elif al >= 50:
            al_col = Fore.YELLOW + Style.BRIGHT
        else:
            al_col = Fore.GREEN
        al_label = t('alert_danger') if al >= 80 else (t('alert_caution') if al >= 50 else t('alert_safe'))
        print(t('alert_level_prefix') + f"{al_col}{al_bar}{Style.RESET_ALL}  {al:3d} / 100  [{al_label}]"
              f"  {Fore.WHITE + Style.DIM}{t('alert_2nd_act')}{Style.RESET_ALL}")
        print_divider()

        food_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k, {}).get("type")=="food")
        water_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k, {}).get("type")=="water")
        med_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k, {}).get("type")=="hp")

        print(t('status_items_line', med=med_cnt, food=food_cnt, water=water_cnt, scrap=self.materials))
        if self.active_quest:
            q = self.active_quest
            turns_left = max(0, q["deadline"] - self.turn_count)
            print_divider()
            print(t('status_quest_line', title=q['title'], progress=q['progress'], target=q['target'], turns=turns_left))
        print_divider()
        print()

    def manage_inventory(self):
        slot_keys = list(SLOT_DISPLAY.keys())

        while True:
            clear_screen()
            print_header(t('inv_header'))

            # ── 장착 슬롯 현황 패널 ───────────────────────────────────────────
            print(t('inv_slot_header'))
            print_divider()
            for si, sk in enumerate(slot_keys, 1):
                label = ea_rpad(SLOT_DISPLAY[sk], 8)
                eid = self.equipment.get(sk)
                if eid and eid != "WEAPON_NONE":
                    d = get_equipment_data(eid)
                    tag = TIER_TAGS.get(d.get("tier", 4), "T?    ")
                    print(f"   [{si:2d}] {label}  │  ★  {d['name'][:22]}    {tag}  위력:{d['power']:>4}")
                else:
                    print(f"   [{si:2d}] {label}  │  {t('inv_not_equipped')}")
            print()

            # ── 보유 장비 목록 (슬롯별 그룹) ────────────────────────────────────
            print(t('inv_items_header', count=len(self.inventory), scrap=self.materials))
            print_divider()
            if not self.inventory:
                print(t('inv_empty'))
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
            print(t('inv_cmd_header'))
            print(t('inv_cmd_line1'))
            print(t('inv_cmd_line2'))
            print(t('inv_cmd_line3'))
            print_divider()
            try:
                cmd = safe_input(t('inv_prompt')).strip().upper()
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
                        print(t('inv_equipped', name=d['name'], slot=SLOT_DISPLAY.get(sk, sk)))
                        if prev and prev != "WEAPON_NONE":
                            pd = get_equipment_data(prev)
                            print(t('inv_replaced', name=pd['name']))
                    else:
                        print(t('inv_invalid_number'))
                else:
                    print(t('inv_equip_usage'))
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
                            print(t('inv_unequipped', name=d['name'], slot=SLOT_DISPLAY[sk]))
                        else:
                            print(t('inv_slot_empty', slot=SLOT_DISPLAY[sk]))
                    else:
                        print(t('inv_slot_range', max=len(slot_keys)))
                else:
                    print(t('inv_unequip_usage'))
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
                            print(t('inv_dismantle_equipped'))
                        else:
                            self.inventory.pop(n - 1)
                            gained = random.randint(15, 30)
                            self.materials += gained
                            advance_quest(self, "scrap", gained)
                            d = get_equipment_data(item_id)
                            print(t('inv_dismantled', name=d['name'], gained=gained))
                    else:
                        print(t('inv_invalid_number'))
                else:
                    print(t('inv_dismantle_usage'))
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
                print(t('inv_dev_grant', granted=granted))
                wait_for_keypress()

    def use_consumable_menu(self):
        clear_screen()
        print_header(t('consumable_header'))

        avail = [k for k, v in self.consumables.items() if v > 0]
        if not avail:
            print(t('consumable_empty'))
            wait_for_keypress()
            return

        for i, key in enumerate(avail):
            item = CONSUMABLES_DB[key]
            desc = ""
            if item["type"] == "hp":
                if item["is_percent"]: desc = t('consumable_hp_percent', pct=int(item['val']*100))
                else: desc = t('consumable_hp_fixed', val=item['val'])
            elif item["type"] in ["food", "water"]:
                h_val = t('consumable_hunger', val=item['hunger']) if item['hunger'] > 0 else ""
                thirst_str = t('consumable_thirst', val=item['thirst']) if item['thirst'] > 0 else ""
                desc = h_val + thirst_str

            print(t('consumable_item_line', idx=i+1, name=item['name'], owned=self.consumables[key], desc=desc))

        print_divider()
        print(t('consumable_back'))
        cmd = read_key()

        if cmd.isdigit() and 0 < int(cmd) <= len(avail):
            key = avail[int(cmd)-1]
            item = CONSUMABLES_DB[key]
            self.consumables[key] -= 1

            if item["type"] == "hp":
                heal_amt = int(self.max_hp * item["val"]) if item["is_percent"] else item["val"]
                self.hp = min(self.max_hp, self.hp + heal_amt)
                print(t('consumable_used_hp', name=item['name'], amt=heal_amt))
            else:
                self.hunger = min(100, self.hunger + item["hunger"])
                self.thirst = min(100, self.thirst + item["thirst"])
                print(t('consumable_used_food', name=item['name']))
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
        print(t('map_header'))
        for y in range(self.size - 1, -1, -1):
            row_str = "    "
            for x in range(self.size):
                if [x, y] == self.player_pos:
                    row_str += "[ P ] "
                elif [x, y] == self.bunker_pos:
                    row_str += "[ B ] "
                else:
                    row_str += "[ . ] "
            print(row_str)
        print(t('map_legend'))

def save_data(player, grid):
    save_file = {"player": player.to_dict(), "grid": grid.to_dict()}
    try:
        with open(get_save_path(), "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        print(t('save_success'))
    except Exception as e:
        print(t('save_fail', e=e))
        
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
        name, e_def, base_atk, hp = t('enemy_boss_name'), 45, 180, 35000
        art, header_title = ENEMY_ART["BOSS"], t('enemy_boss_header')
        base_atk = int(base_atk * scale_mult)
        hp = int(hp * scale_mult)
        boss_max_hp = hp
        atk = base_atk
    elif enemy_type == "bio_hound":
        name, e_def, base_atk, hp = t('enemy_bio_name'), 15, 110, 10000
        art, header_title = ENEMY_ART["BIOHOUND"], t('enemy_bio_header')
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp = current_hp
            name = t('enemy_bio_name_wounded')
            header_title = t('enemy_bio_header_wounded')
        else:
            hp = int(hp * scale_mult)
        atk = base_atk
    else:
        name, e_def, base_atk, hp = t('enemy_drone_name'), 5, 80, 8000
        art, header_title = ENEMY_ART["NORMAL"], t('enemy_drone_header')
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp = current_hp
            name = t('enemy_drone_name_wounded')
            header_title = t('enemy_drone_header_wounded')
        else:
            hp = int(hp * scale_mult)
        atk = base_atk

    turn = 1
    learning_index = 0
    consecutive_attacks = 0
    escaped = False
    escape_log = ""
    combat_ctx: dict = {}
    action_logs = [t('combat_encounter_alert', name=name)]

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
            type_text(Fore.RED + Style.BRIGHT + t('combat_timeout'))
            sys.exit()

        # 보스 페이즈 2 전환 (HP 50% 이하)
        if is_boss and not phase2_triggered and hp <= boss_max_hp * 0.5:
            phase2_triggered = True
            atk = int(base_atk * 1.6)
            learning_index += 5
            clear_screen()
            print_header(t('combat_phase2_header'))
            type_text(Fore.RED + Style.BRIGHT + t('combat_phase2_warn1'), 0.03)
            type_text(Fore.RED + Style.BRIGHT + t('combat_phase2_warn2'), 0.03)
            type_text(Fore.YELLOW + Style.BRIGHT + t('combat_phase2_warn3'), 0.03)
            time.sleep(1.5)
            action_logs.append(t('combat_phase2_log'))

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
        print(t('combat_status_turn', turn=turn, name=name, hp=f"{disp_ehp:,}"))
        print(t('combat_status_player', hp=f"{disp_php:,}", maxhp=f"{disp_pmaxhp:,}", ram=player.max_ram))
        if is_boss:
            print(t('combat_status_learning', e=learning_index))

        print(t('combat_log_header'))
        for log in action_logs: print(f"    {_log_color(log)}{log}")
        print_divider()
        print()
        action_logs.clear()

        has_consumable = any(v > 0 for v in player.consumables.values())
        has_skill = bool(player.skill_slots)
        print(t('combat_options_1'))
        print(t('combat_options_2'))
        print(t('combat_options_3'))
        print(t('combat_options_4'))
        if has_consumable:
            print(t('combat_options_5'))
        if has_skill:
            print(t('combat_options_6'))

        cmd = read_key()

        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                e_gain = max(0, 3 - e_suppress)
                if skills.is_learning_blocked(player):
                    action_logs.append(t('combat_learning_blocked'))
                else:
                    learning_index += e_gain
                    if e_suppress > 0:
                        action_logs.append(t('combat_repeat_cyberdeck', gain=e_gain))
                    else:
                        action_logs.append(t('combat_repeat_learning', gain=e_gain))

            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            f_multiplier = 1.0 + (player.reputation / 2000) * 1
            effective_power = player.get_attack_power() + gear_atk

            atk_mult = skills.get_atk_mult(player)
            crush_mult, def_pierce = skills.consume_hydraulic_crush(player, action_logs)
            effective_e_def = max(0, int(e_def * (1 - def_pierce)))
            forced_crit, sig_crt_mult = skills.apply_signal_trace(player, combat_ctx, action_logs)
            ghost_crt = player.active_buffs.pop("ghost_crt", 0.0)
            crt_rate = min(0.75, player.calc_crt_rate() + ghost_crt)
            natural_crit = (not forced_crit) and (random.random() < crt_rate)
            crt_mult = sig_crt_mult if forced_crit else (1.5 if natural_crit else 1.0)
            if natural_crit:
                action_logs.append(t('combat_crit_log'))

            base_dmg = math.floor(effective_power * f_multiplier * penalty * 100)
            dmg = max(100, int(base_dmg * atk_mult * crush_mult * crt_mult) - effective_e_def + random.randint(-50, 50))
            dmg = skills.apply_outgoing_buffs(player, dmg, action_logs)
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)

            print(f"\n  {Fore.GREEN + Style.BRIGHT}" + t('combat_attack_hit', dmg=f"{disp_dmg:,}"))
            time.sleep(1)
            hp = max(0, hp - dmg)
            _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
            print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_new:,}"))
            time.sleep(1)
            action_logs.append(t('combat_attack_log', dmg=f"{disp_dmg:,}"))
            skills.on_attack_used(player, action_logs, dmg_dealt=dmg)
            time.sleep(1)

        elif cmd == "2":
            consecutive_attacks = 0
            learning_index = max(0, learning_index - 4)
            atk = int(atk * 0.5)

            print(t('combat_defense_msg'))
            time.sleep(1)
            action_logs.append(t('combat_defense_log'))
            time.sleep(2)

        elif cmd == "3":
            if player.max_ram >= 2:
                consecutive_attacks = 0
                learning_index = 0
                player.max_ram -= 2

                print(t('combat_hack_msg'))
                time.sleep(1)
                action_logs.append(t('combat_hack_log'))
            else:
                print(t('combat_hack_no_ram'))
                time.sleep(0.5)
                action_logs.append(t('combat_hack_no_ram_log'))

        elif cmd == "4":
            if is_boss:
                print(t('combat_escape_boss'))
                time.sleep(0.5)
                action_logs.append(t('combat_escape_boss_log'))
                time.sleep(1)
            else:
                if player.active_buffs.pop("void_shift", 0):
                    escaped = True
                    escape_log = t('combat_escape_safe')
                    break
                dex_bonus = max(0, player.dex - 10) * 2
                weights = [60 + dex_bonus, max(0, 20 - dex_bonus/2), max(0, 10 - dex_bonus/4), max(0, 5 - dex_bonus/4), 5 + dex_bonus/2]
                res = random.choices(["SAFE", "NORMAL", "1.5X", "2.0X", "LUCKY"], weights=weights, k=1)[0]

                escaped = True
                if res == "SAFE":
                    escape_log = t('combat_escape_safe')
                elif res in ["NORMAL", "1.5X", "2.0X"]:
                    dmg_calc = atk if res == "NORMAL" else int(atk * 1.5) if res == "1.5X" else int(atk * 2.0)

                    print(t('combat_escape_hit', dmg=f"{dmg_calc:,}"))
                    time.sleep(1)
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(t('combat_player_hp', hp=f"{disp_php_new:,}"))
                    time.sleep(1)

                    if res == "NORMAL": escape_log = t('combat_escape_normal', dmg=f"{dmg_calc:,}")
                    elif res == "1.5X": escape_log = t('combat_escape_heavy', dmg=f"{dmg_calc:,}")
                    else: escape_log = t('combat_escape_disaster', dmg=f"{dmg_calc:,}")
                elif res == "LUCKY":
                    escape_log = t('combat_escape_lucky')
                break

        elif cmd == "5" and has_consumable:
            consecutive_attacks = 0
            avail = [k for k, v in player.consumables.items() if v > 0]
            print(t('combat_item_list'))
            for i, key in enumerate(avail):
                item = CONSUMABLES_DB[key]
                if item["type"] == "hp":
                    desc = t('consumable_hp_percent', pct=int(item['val']*100)) if item["is_percent"] else t('consumable_hp_fixed', val=item['val'])
                else:
                    h_val = t('consumable_hunger', val=item['hunger']) if item['hunger'] > 0 else ""
                    thirst_str = t('consumable_thirst', val=item['thirst']) if item['thirst'] > 0 else ""
                    desc = h_val + thirst_str
                print(f"  [{i+1}] {item['name']} x{player.consumables[key]} — {desc}")
            print(t('combat_cancel_item'))
            item_cmd = read_key()
            if item_cmd.isdigit() and 0 < int(item_cmd) <= len(avail):
                key = avail[int(item_cmd) - 1]
                item = CONSUMABLES_DB[key]
                player.consumables[key] -= 1
                if item["type"] == "hp":
                    heal = int(player.max_hp * item["val"]) if item["is_percent"] else item["val"]
                    player.hp = min(player.max_hp, player.hp + heal)
                    _, disp_heal, _ = apply_dynamic_scaling(heal, 0, tier)
                    action_logs.append(t('combat_recover_log', name=item['name'], hp=f"{disp_heal:,}"))
                else:
                    player.hunger = min(100, player.hunger + item["hunger"])
                    player.thirst = min(100, player.thirst + item["thirst"])
                    action_logs.append(t('combat_eat_log', name=item['name']))
            else:
                action_logs.append(t('combat_cancel_log'))

        elif cmd == "S" and has_skill:
            consecutive_attacks = 0
            if len(player.skill_slots) == 1:
                sid = player.skill_slots[0]
                sk_name = skills.SKILL_DEFS[sid]['name']
                ok = skills.execute(player, sid, combat_ctx)
                if ok:
                    s_dmg = combat_ctx.pop("aux_skill_dmg", 0)
                    if s_dmg:
                        hp = max(0, hp - s_dmg)
                        _, disp_sdmg, _ = apply_dynamic_scaling(s_dmg, 0, tier)
                        print(f"\n  {Fore.CYAN + Style.BRIGHT}" + t('combat_skill_dmg_msg', dmg=f"{disp_sdmg:,}"))
                        time.sleep(1)
                        action_logs.append(t('combat_skill_dmg_log', dmg=f"{disp_sdmg:,}"))
                    if combat_ctx.pop("pulse_e_drain", False):
                        learning_index = max(0, learning_index - 3)
                    action_logs.append(f"[스킬] {sk_name}")
                time.sleep(1)
            else:
                print(t('combat_skill_select'))
                sc = read_key()
                target_sid = None
                if sc == "1" and len(player.skill_slots) >= 1:
                    target_sid = player.skill_slots[0]
                elif sc == "2" and len(player.skill_slots) >= 2:
                    target_sid = player.skill_slots[1]
                if target_sid:
                    sk_name = skills.SKILL_DEFS[target_sid]['name']
                    ok = skills.execute(player, target_sid, combat_ctx)
                    if ok:
                        s_dmg = combat_ctx.pop("aux_skill_dmg", 0)
                        if s_dmg:
                            hp = max(0, hp - s_dmg)
                            _, disp_sdmg, _ = apply_dynamic_scaling(s_dmg, 0, tier)
                            print(f"\n  {Fore.CYAN + Style.BRIGHT}" + t('combat_skill_dmg_msg', dmg=f"{disp_sdmg:,}"))
                            time.sleep(1)
                            action_logs.append(t('combat_skill_dmg_log', dmg=f"{disp_sdmg:,}"))
                        if combat_ctx.pop("pulse_e_drain", False):
                            learning_index = max(0, learning_index - 3)
                        action_logs.append(f"[스킬] {sk_name}")
                    time.sleep(1)
                else:
                    action_logs.append(t('combat_skill_cancel'))

        else:
            print(t('combat_invalid_cmd'))
            time.sleep(1)
            action_logs.append(t('combat_invalid_log'))

        # --- 적의 반격 ---
        skip_atk = combat_ctx.pop("skip_enemy_attack", False)
        if hp > 0 and not escaped and not skip_atk:
            if cmd == "2":
                atk = int(base_atk * (1.6 if phase2_triggered else 1.0))
            enemy_atk_mult = skills.get_enemy_atk_mult(player)
            raw_dmg_taken = max(1, int(atk * enemy_atk_mult) - def_bonus)
            dmg_taken = skills.apply_incoming_buffs(player, raw_dmg_taken, action_logs, combat_ctx)
            if dmg_taken > 0:
                print(f"\n  {Fore.RED + Style.BRIGHT}" + t('combat_enemy_attack', name=name, dmg=f"{dmg_taken:,}"))
                time.sleep(1)
                player.hp -= dmg_taken
                if cyber_regen > 0 and player.hp > 0:
                    player.hp = min(player.max_hp, player.hp + cyber_regen)
                _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                print(t('combat_player_hp_full', hp=f"{disp_php_new:,}", maxhp=f"{disp_pmaxhp:,}"))
                time.sleep(1)
                def_note = t('combat_def_note', val=def_bonus) if def_bonus > 0 else ""
                action_logs.append(t('combat_damage_log', dmg=f"{dmg_taken:,}", def_note=def_note))
                time.sleep(1)

        skills.end_of_turn_tick(player, action_logs)
        turn += 1

    if player.hp <= 0:
        clear_screen()
        if escape_log: type_text(escape_log, 0.02)
        type_text(Fore.RED + Style.BRIGHT + t('combat_fatal'), 0.03)
        wait_for_keypress()
        sys.exit()

    if escaped:
        clear_screen()
        print_header(t('combat_escape_header'))
        print(f"\n{escape_log}")
        if res == "LUCKY":
            loot_types = ["MEDKIT", "MATERIAL", "PART", "WATER", "FOOD"]
            loot_weights = [10, 10, 10, 35, 35]
            loot_res = random.choices(loot_types, weights=loot_weights, k=1)[0]

            if loot_res == "MEDKIT":
                it = roll_medkit()
                player.consumables[it] += 1
                print(t('combat_loot_medkit', name=CONSUMABLES_DB[it]['name']))
            elif loot_res == "MATERIAL":
                player.materials += 15
                advance_quest(player, "scrap", 15)
                print(t('combat_loot_scrap'))
            elif loot_res == "PART":
                part = random.choice(["PART_SCRAP_01", "PART_SCRAP_02", "PART_SCRAP_03"])
                player.inventory.append(part)
                item_data = get_equipment_data(part)
                print(t('combat_loot_part', name=item_data['name']))
            elif loot_res == "WATER":
                it = roll_water()
                player.consumables[it] += 1
                print(t('combat_loot_water', name=CONSUMABLES_DB[it]['name']))
            elif loot_res == "FOOD":
                it = roll_food()
                player.consumables[it] += 1
                print(t('combat_loot_food', name=CONSUMABLES_DB[it]['name']))

        log_diary(player, t('combat_log_escape_diary', name=name))
        wait_for_keypress()
        if hp_bonus > 0:
            player.max_hp -= hp_bonus
            player.hp = min(player.hp, player.max_hp)
        return hp, enemy_type

    clear_screen()
    print_header(t('combat_win_header'))
    print(f"\n{Fore.GREEN + Style.BRIGHT}" + t('combat_win_msg', name=name))
    player.enemies_defeated += 1

    if not is_boss:
        drop_roll = random.random()
        if drop_roll < 0.25:
            it = roll_food()
            player.consumables[it] += 1
            print(t('combat_farm_food', name=CONSUMABLES_DB[it]['name']))
        elif drop_roll < 0.50:
            it = roll_water()
            player.consumables[it] += 1
            print(t('combat_farm_water', name=CONSUMABLES_DB[it]['name']))
        elif drop_roll < 0.60:
            it = roll_medkit()
            player.consumables[it] += 1
            print(t('combat_farm_medkit', name=CONSUMABLES_DB[it]['name']))
        else:
            player.materials += 20
            advance_quest(player, "scrap", 20)
            print(t('combat_farm_scrap'))

    advance_quest(player, "combat")
    log_diary(player, t('combat_log_win_diary', name=name, count=player.enemies_defeated))
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
    os.system('title PROTOCOL: STIGMA — 1막: 낙인')
    os.system('mode con: cols=90 lines=40')
    os.system('color 0B')
    colorama_init(autoreset=True)

    check_and_prompt_update(constants.GAME_VERSION, console=_console)
    set_lang("ko")  # 기본값

    player = Player()
    grid = GameMap()

    while True:  # 타이틀 ~ 설정 루프
        clear_screen()
        print()
        ver_str = f"v{constants.GAME_VERSION}"
        ver_pad = " " * (74 - len(ver_str))
        print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + ea_center("P  R  O  T  O  C  O  L  :  S  T  I  G  M  A", 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.CYAN  + Style.BRIGHT + "  ║" + ea_center(t("title_subtitle"), 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ╠" + "═" * 74 + "╣")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.CYAN  + "  ║" + ea_center(t("title_quote1"), 74) + "║")
        print(Fore.CYAN  + "  ║" + ea_center(t("title_quote2"), 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.DIM    + "  ║" + ver_pad + ver_str + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
        print()

        has_save = os.path.exists(get_save_path())
        print_divider()
        print(f"  1. {t('menu_new_game')}")
        if has_save:
            print(f"  2. {t('menu_load_game')}")
        opt_key = "3" if has_save else "2"
        exit_key = "4" if has_save else "3"
        print(f"  {opt_key}. {t('menu_options')}")
        print(f"  {exit_key}. {t('menu_exit')}")
        print_divider()

        ans = read_key()

        # ── 종료 ──────────────────────────────────────────────────────────
        if ans == exit_key:
            clear_screen()
            type_text(f"  {t('exit_msg')}", 0.025)
            time.sleep(0.5)
            sys.exit()

        # ── 옵션 (언어 선택) ──────────────────────────────────────────────
        if ans == opt_key:
            while True:
                clear_screen()
                print_header(t('menu_options'))
                print_divider()
                print(f"  {t('lang_header')}")
                print_divider()
                print(f"  1. {t('lang_ko')}")
                print(f"  2. {t('lang_en')}")
                print_divider()
                print(f"  0. {t('diff_back')}")
                print_divider()
                lk = read_key()
                if lk == "1":
                    set_lang("ko")
                    break
                elif lk == "2":
                    set_lang("en")
                    break
                elif lk == "0":
                    break
            continue

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
                type_text(f"  {t('load_success')}", 0.02)
            except Exception as e:
                type_text(f"  {t('load_fail', e=e)}", 0.02)
            wait_for_keypress()
            break  # 게임 루프 진입

        # ── 새로운 게임 ───────────────────────────────────────────────────
        if ans == "1":
            player = Player()
            grid = GameMap()
            go_back = False

            while True:  # 난이도 선택 루프
                clear_screen()
                print_header(t("diff_header"))
                print(f"  {t('diff_desc1')}")
                print(f"  {t('diff_desc2')}\n")
                print(f"  1. {t('diff_easy')}")
                print(f"  2. {t('diff_normal')}")
                print(f"  3. {t('diff_hard')}")
                print_divider()
                print(f"  0. {t('diff_back')}")
                print_divider()

                diff_map = {"1": "easy", "2": "normal", "3": "hard"}
                diff_ans = read_key()

                if diff_ans == "0":
                    go_back = True
                    break

                if diff_ans in diff_map:
                    player.difficulty = diff_map[diff_ans]
                    run_prologue()
                    log_diary(player, t('game_log_start'))
                    break

                print(f"\n  {t('diff_invalid')}")
                time.sleep(0.8)

            if go_back:
                continue  # 타이틀 루프 재시작
            break  # 게임 루프 진입

        # 잘못된 입력 → 타이틀 재표시

    sound.play_map_ambient()
    while True:
        clear_screen()
        if player.active_quest and player.turn_count > player.active_quest["deadline"]:
            q = player.active_quest
            print(t('quest_failed', title=q['title']))
            log_diary(player, t('quest_fail_diary', title=q['title']))
            player.active_quest = None
            time.sleep(1.5)
            clear_screen()
        grid.draw()
        player.show_status()
        
        print(f" {t('cmd_header')}")
        print(f"  {t('cmd_move')}")
        print(f"  {t('cmd_search')}")
        print(f"  {t('cmd_inventory')}")
        print(f"  {t('cmd_diary')}")
        print(f"  {t('cmd_save')}")
        print(f"  {t('cmd_quit')}")
        print_divider()
        
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
            print(t('search_start'))
            time.sleep(0.5)

            encounter_chance = get_encounter_chance(player)
            roll = random.random()

            if roll < 0.08 and TRADER_ITEMS:
                # 행상인 NPC 조우 (8%)
                handle_trader(player)
            elif roll < 0.08 + encounter_chance:
                # 전투 조우 (encounter_chance%)
                print(t('encounter_warning'))
                wait_for_keypress()
                # 바이오 하운드 20% 확률 등장 (재조우 시 이전 타입 유지)
                if grid.escaped_enemy_hp is not None:
                    etype = grid.escaped_enemy_type or "drone"
                else:
                    etype = "bio_hound" if random.random() < 0.20 else "drone"
                sound.play_combat_bgm()
                result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                grid.escaped_enemy_hp = result_hp
                grid.escaped_enemy_type = result_type
                sound.resume_map_ambient()
            elif roll < 0.08 + encounter_chance + 0.20 and RANDOM_EVENTS:
                # 랜덤 서사 이벤트 (20%)
                event = random.choice(RANDOM_EVENTS)
                handle_random_event(player, event)
            elif roll < 0.08 + encounter_chance + 0.20 + 0.30:
                # 공탐색 — 분위기 로그 (30%)
                _empty = random.choice(t('empty_search_msgs'))
                print(f"\n  {_empty}")
                print_ambient_lore()
            else:
                # 자원 파밍 (나머지 ~22%)
                item_roll = random.random()
                if item_roll <= 0.25:
                    gained = random.randint(10, 25)
                    player.materials += gained
                    advance_quest(player, "scrap", gained)
                    print(t('farm_scrap', gained=gained))
                elif item_roll <= 0.60:
                    if random.random() < 0.5:
                        it = roll_food()
                        player.consumables[it] += 1
                        print(t('farm_food', name=CONSUMABLES_DB[it]['name']))
                    else:
                        it = roll_water()
                        player.consumables[it] += 1
                        print(t('farm_water', name=CONSUMABLES_DB[it]['name']))
                else:
                    it = roll_medkit()
                    player.consumables[it] += 1
                    print(t('farm_medkit', name=CONSUMABLES_DB[it]['name']))
                wait_for_keypress()
            # 탐색 퀘스트 진행 및 돌발 퀘스트 (전투 미조우 시)
            if not (0.08 <= roll < 0.08 + encounter_chance):
                advance_quest(player, "search")
                if roll >= 0.08 + encounter_chance + 0.20:
                    trigger_sudden_quest(player)
            continue
        elif move == "Q":
            clear_screen()
            print_header(t("quit_header"))
            print()
            type_text(t("quit_prompt"), 0.02)
            print()
            print(t("quit_yn"), end="", flush=True)
            save_choice = read_key()
            if save_choice == 'Y':
                save_data(player, grid)
                print(t("quit_saved"))
            else:
                print(t("quit_nosave"))
            print()
            print("  ╔" + "═" * 74 + "╗")
            print("  ║  " + ea_rpad(t("quit_banner"), 72) + "║")
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
            print(f"\n{t('move_blocked')}")
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
                log_diary(player, t('boss_log_prep'))
                clear_screen()
                print_header(t('boss_alert_header'))
                type_text(t('boss_approach_1'), 0.025)
                type_text(t('boss_approach_2'), 0.025)
                type_text(t('boss_approach_3'), 0.025)
                print()
                type_text(t('boss_approach_4'), 0.025)
                type_text(t('boss_approach_5'), 0.025)
                print()
                type_text(t('boss_approach_6') + "\n", 0.025)
                while True:
                    print_divider()
                    tier_now = player.get_highest_tier()
                    _, disp_hp_now, _ = apply_dynamic_scaling(0, player.hp, tier_now)
                    _, disp_maxhp_now, _ = apply_dynamic_scaling(0, player.max_hp, tier_now)
                    print(t('boss_prep_status', hp=f"{disp_hp_now:,}", maxhp=f"{disp_maxhp_now:,}", hunger=player.hunger, thirst=player.thirst, scrap=player.materials))
                    print_divider()
                    print(t('boss_prep_1'))
                    print(t('boss_prep_2'))
                    print(t('boss_prep_3'))
                    prep_cmd = read_key()
                    if prep_cmd == "1":
                        player.use_consumable_menu()
                    elif prep_cmd == "2":
                        save_data(player, grid)
                    elif prep_cmd == "3":
                        break
                sound.play_combat_bgm()
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
                        print(t('scan_detected'))
                        time.sleep(1.2)
                        handle_session(player, SESSIONS_DB[grid.session_index])
                        grid.session_index += 1
                        session_triggered = True

                if not session_triggered:
                    if random.random() < get_encounter_chance(player):
                        print(t('encounter_alert'))
                        wait_for_keypress()
                        if grid.escaped_enemy_hp is not None:
                            etype = grid.escaped_enemy_type or "drone"
                        else:
                            etype = "bio_hound" if random.random() < 0.20 else "drone"
                        sound.play_combat_bgm()
                        result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                        grid.escaped_enemy_hp = result_hp
                        grid.escaped_enemy_type = result_type
                        sound.resume_map_ambient()
                    else:
                        if random.random() < 0.2:
                            print_ambient_lore()

def handle_session(player, session):
    clear_screen()
    sound.play_typing_bgm()
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
                    print(t('session_scrap_gain', mat=mat_gain))
                else:
                    player.inventory.append(choice_data["reward"])
                    item_data = get_equipment_data(choice_data["reward"])
                    print(t('session_item_gain', name=item_data['name']))

            # 소모품 보상
            if choice_data.get("consumable"):
                key = choice_data["consumable"]
                if key in player.consumables:
                    player.consumables[key] += 1
                    print(t('session_consumable_gain', name=CONSUMABLES_DB.get(key, {}).get('name', key)))

            # 고철 직접 지급 (SCRAP_MAT 없이)
            raw_mat = choice_data.get("materials", 0)
            if raw_mat != 0 and not choice_data.get("reward") == "SCRAP_MAT":
                player.materials = max(0, player.materials + raw_mat)
                if raw_mat > 0:
                    advance_quest(player, "scrap", raw_mat)
                    print(t('session_scrap_add', val=raw_mat))
                else:
                    print(t('session_scrap_use', val=raw_mat))

            # 생체 상태 변화
            if choice_data.get("hp_loss", 0):
                player.hp = max(1, player.hp - choice_data["hp_loss"])
                print(t('session_hp_loss', val=choice_data['hp_loss']))
            if choice_data.get("thirst", 0):
                player.thirst = min(100, player.thirst + choice_data["thirst"])
            if choice_data.get("hunger", 0):
                player.hunger = min(100, player.hunger + choice_data["hunger"])
            if choice_data.get("ram_bonus", 0):
                player.max_ram += choice_data["ram_bonus"]
                print(t('session_ram_gain', val=choice_data['ram_bonus']))

            time.sleep(0.6)
            type_text(f"\n  {choice_data['log']}", 0.025)

            _w_label = {"kinetic": "완력", "scrap": "해체", "cyber": "해킹"}.get(choice_weight, "선택")
            _reward_note = ""
            if choice_data.get("reward") and choice_data["reward"] != "SCRAP_MAT":
                _rd = get_equipment_data(choice_data["reward"])
                _reward_note = t('session_log_reward_item', name=_rd['name'])
            elif choice_data.get("reward") == "SCRAP_MAT":
                _reward_note = t('session_log_reward_scrap', val=choice_data.get('materials', 30))
            if choice_data.get("ram_bonus"):
                _reward_note += t('session_log_reward_ram', val=choice_data['ram_bonus'])
            log_diary(player, t('session_log_diary', title=session['title'], label=_w_label, note=_reward_note))

            if choice_weight and player.weights[choice_weight] >= 3:
                _wcb = {
                    "kinetic": t('session_pattern_kinetic'),
                    "scrap":   t('session_pattern_scrap'),
                    "cyber":   t('session_pattern_cyber'),
                }
                time.sleep(0.3)
                type_text(_wcb[choice_weight], 0.022)

            wait_for_keypress()
            sound.resume_map_ambient()
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
    print_header(t('quest_trigger_header', title=tpl['title']))
    type_text(f"  {tpl['desc']}", 0.022)
    print()
    print(t('quest_goal_label', detail=tpl['detail']))
    print(t('quest_deadline_label', turns=tpl['turns'], current=player.turn_count, deadline=deadline))
    print(t('quest_reward_label', reward=tpl['reward_desc']))
    print()
    log_diary(player, t('quest_log_start', title=tpl['title'], deadline=deadline))
    wait_for_keypress()


def _complete_quest(player):
    """퀘스트 완료 처리: 보상 지급 후 active_quest 초기화."""
    q = player.active_quest
    if q is None:
        return
    clear_screen()
    print_header(t('quest_complete_header', title=q['title']))
    print()
    print(t('quest_reward_header', reward=q['reward_desc']))
    rtype = q["reward_type"]
    if rtype == "consumable":
        rid = q["reward_id"]
        player.consumables[rid] = player.consumables.get(rid, 0) + 1
        print(t('quest_consumable_added', name=CONSUMABLES_DB.get(rid, {}).get('name', rid)))
    elif rtype == "materials":
        amt = q.get("reward_amount", 30)
        player.materials += amt
        print(t('quest_scrap_remaining', val=player.materials))
    elif rtype == "ram":
        amt = q.get("reward_amount", 1)
        player.max_ram += amt
        print(t('quest_ram_remaining', val=player.max_ram))
    print()
    log_diary(player, t('quest_log_complete', title=q['title'], reward=q['reward_desc']))
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
    print_header(t('event_header', title=event['title']))
    type_text(event["text"], 0.02)
    print()

    if event["type"] == "simple":
        result = event["result"]
        time.sleep(0.5)
        type_text(result["log"], 0.02)
        if result.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - result["hp_loss"])
            print(t('event_hp_loss', val=result['hp_loss']))
        if result.get("materials", 0) != 0:
            player.materials = max(0, player.materials + result["materials"])
            sign = "+" if result["materials"] > 0 else ""
            print(t('event_scrap', sign=sign, val=result['materials']))
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
                print(t('event_item_gain', name=CONSUMABLES_DB[key]['name']))
        log_diary(player, t('event_log_simple', title=event['title']))
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
            print(t('event_hp_loss', val=c['hp_loss']))
        mat = c.get("materials", 0)
        if mat != 0:
            player.materials = max(0, player.materials + mat)
            sign = "+" if mat > 0 else ""
            print(t('event_scrap', sign=sign, val=mat))
            if mat > 0:
                advance_quest(player, "scrap", mat)
        if c.get("hunger", 0) > 0:
            player.hunger = min(100, player.hunger + c["hunger"])
        if c.get("thirst", 0) > 0:
            player.thirst = min(100, player.thirst + c["thirst"])
        if c.get("ram_bonus", 0) > 0:
            player.max_ram += c["ram_bonus"]
            print(t('event_ram_gain', val=c['ram_bonus']))
        if c.get("consumable"):
            key = c["consumable"]
            if key in player.consumables:
                player.consumables[key] += 1
                print(t('event_item_gain', name=CONSUMABLES_DB[key]['name']))
        _ew_label = {
            "kinetic": t('weight_label_kinetic'),
            "scrap":   t('weight_label_scrap'),
            "cyber":   t('weight_label_cyber'),
        }.get(c.get("weight"), t('weight_label_default'))
        log_diary(player, t('event_log_choice', title=event['title'], label=_ew_label))
        wait_for_keypress()


def handle_trader(player):
    """행상인 NPC 조우 — 고철로 소모품을 구매합니다."""
    clear_screen()
    print_header(t('trader_header'))
    type_text(t('trader_intro_1'), 0.02)
    type_text(t('trader_intro_2'), 0.02)
    print()

    while True:
        print_divider()
        print(f"{t('trader_scrap_label', val=player.materials)}\n")
        print(t('trader_stock_header'))
        for i, item in enumerate(TRADER_ITEMS):
            stock_key = item["id"]
            owned = player.consumables.get(stock_key, 0)
            print(t('trader_item_line', idx=i+1, name=f"{item['name']:<20}", cost=item['cost'], owned=owned))
        print_divider()
        print(t('trader_exit'))

        cmd = read_key()

        if cmd == "0":
            type_text(t('trader_goodbye'), 0.02)
            wait_for_keypress()
            break

        if cmd.isdigit() and 1 <= int(cmd) <= len(TRADER_ITEMS):
            chosen = TRADER_ITEMS[int(cmd) - 1]
            if player.materials >= chosen["cost"]:
                player.materials -= chosen["cost"]
                key = chosen["id"]
                player.consumables[key] += 1
                print(t('trader_bought', name=chosen['name'], scrap=player.materials))
                log_diary(player, t('trader_log_bought', name=chosen['name'], cost=chosen['cost']))
                time.sleep(1)
            else:
                print(t('trader_no_scrap', owned=player.materials, cost=chosen['cost']))
                time.sleep(1)
        else:
            print(t('trader_invalid'))
            time.sleep(0.5)


def run_prologue():
    """신규 게임 시작 시 전체 프롤로그 시퀀스를 재생합니다."""
    clear_screen()
    print_header(t('prologue_header'))
    print()
    print(t('prologue_loaded'))
    print()
    print(t('prologue_option_play'))
    print(t('prologue_option_skip'))
    print()
    skip_ans = read_key()
    if skip_ans == "0":
        clear_screen()
        type_text(t('prologue_skipped'), 0.022)
        time.sleep(0.6)
        return

    clear_screen()
    sound.play_typing_bgm()

    # ── 단계 1: 부팅 시퀀스 ──────────────────────────────────────────────
    boot_log = [
        (t('prologue_boot_0'),   0.04),
        (t('prologue_boot_12'),  0.04),
        (t('prologue_boot_45'),  0.03),
        (t('prologue_boot_100'), 0.03),
        ("", 0.1),
        (t('prologue_boot_check'),  0.03),
        (t('prologue_boot_fail1'),  0.03),
        (t('prologue_boot_id'),     0.03),
        (t('prologue_boot_fail2'),  0.04),
        (t('prologue_boot_class'),  0.04),
        (t('prologue_boot_action'), 0.04),
    ]
    for line, spd in boot_log:
        type_text(line, spd)
        time.sleep(0.08)

    time.sleep(1.2)
    clear_screen()

    # ── 단계 2: 도입 서사 ────────────────────────────────────────────────
    print_header(t('prologue_act1_header'))
    time.sleep(0.5)

    for line in t('prologue_narr'):
        type_text(f"  {line}", 0.022) if line else print()
        time.sleep(0.1)

    time.sleep(1.0)
    wait_for_keypress()
    clear_screen()

    # ── 단계 3: 세계관 브리핑 ────────────────────────────────────────────
    print_header(t('prologue_world_header'))
    for line in t('prologue_world'):
        type_text(f"  {line}", 0.02) if line else print()
        time.sleep(0.05)

    time.sleep(0.8)
    print()
    print_divider()
    type_text(t('prologue_goal_1'), 0.025)
    type_text(t('prologue_goal_2'), 0.025)
    print_divider()

    wait_for_keypress()
    clear_screen()

    # ── 단계 4: 조작법 안내 ──────────────────────────────────────────────
    print_header(t('prologue_manual_header'))
    for key, desc in t('prologue_guide'):
        print(f"  [{key}]  {desc}")

    print()
    print_divider()
    type_text(t('prologue_warn_1'), 0.022)
    type_text(t('prologue_warn_2'), 0.022)
    type_text(t('prologue_warn_3'), 0.025)
    print_divider()
    print()
    type_text(t('prologue_nav_1'), 0.022)
    type_text(t('prologue_nav_2'), 0.022)

    wait_for_keypress()
    clear_screen()
    type_text(t('prologue_start'), 0.022)
    time.sleep(0.6)


def run_boss_core_choice(player):
    """보스 격파 후 코어 처분 선택 — 최종 직업 가중치에 영향을 미칩니다."""
    clear_screen()
    print_header(t('boss_core_header'))
    type_text(t('boss_core_kneel_1'), 0.03)
    type_text(t('boss_core_kneel_2'), 0.03)
    type_text(t('boss_core_kneel_3'), 0.03)
    print()
    time.sleep(1.0)
    type_text(t('boss_core_warn_1'), 0.03)
    type_text(t('boss_core_warn_2'), 0.03)
    print()
    print_divider()
    wk, ws, wc = player.weights["kinetic"], player.weights["scrap"], player.weights["cyber"]

    def _balance_hint(pre_k, pre_s, pre_c):
        if pre_k + 3 == pre_s == pre_c: return "1"
        if pre_s + 3 == pre_k == pre_c: return "2"
        if pre_c + 3 == pre_k == pre_s: return "3"
        return None

    _hint_key = _balance_hint(wk, ws, wc)
    _h1 = f"  {Style.DIM}…{Style.RESET_ALL}" if _hint_key == "1" else ""
    _h2 = f"  {Style.DIM}…{Style.RESET_ALL}" if _hint_key == "2" else ""
    _h3 = f"  {Style.DIM}…{Style.RESET_ALL}" if _hint_key == "3" else ""

    print(t('boss_core_opt1') + _h1)
    print(t('boss_core_opt1_sub'))
    print()
    print(t('boss_core_opt2') + _h2)
    print(t('boss_core_opt2_sub'))
    print()
    print(t('boss_core_opt3') + _h3)
    print(t('boss_core_opt3_sub'))
    print_divider()

    while True:
        ans = read_key()
        if ans == "1":
            player.weights["kinetic"] += 3
            print()
            type_text(t('boss_core_kinetic_1'), 0.03)
            type_text(t('boss_core_kinetic_2'), 0.03)
            break
        elif ans == "2":
            player.weights["scrap"] += 3
            print()
            type_text(t('boss_core_scrap_1'), 0.03)
            type_text(t('boss_core_scrap_2'), 0.03)
            break
        elif ans == "3":
            player.weights["cyber"] += 3
            print()
            type_text(t('boss_core_cyber_1'), 0.03)
            type_text(t('boss_core_cyber_2'), 0.03)
            break

    time.sleep(1.5)
    print()
    print_divider()
    job, granted = skills.grant_awakening_skill(player)
    job_label = skills.JOB_LABEL.get(job, job)
    print(t('ending_skill_header', job_label=job_label))
    print_divider()
    if granted:
        skill_names = ", ".join(skills.SKILL_DEFS[sid]['name'] for sid in granted)
        print(t('ending_skill_slots', max_col=2, count=len(player.skill_slots)))
        print(f"  {skill_names}")
        print(t('ending_skill_notice'))
        print(t('ending_skill_usage'))
        log_diary(player, t('ending_skill_log', job_label=job_label, skills=skill_names))
    wait_for_keypress()
    run_perimeter_encounter(player)


def run_perimeter_encounter(player):
    clear_screen()
    print_header(t('perimeter_header'))
    type_text(t('perimeter_alert_1'), 0.025)
    type_text(t('perimeter_alert_2'), 0.025)
    print()
    print_divider()
    print(t('perimeter_opt1'))
    print(t('perimeter_opt2'))
    print_divider()

    ans = read_key()
    if ans == "1":
        low_hp = int(8000 * get_turn_scale_multiplier(player) * 0.30)
        sound.play_combat_bgm()
        combat_loop(player, is_boss=False, current_hp=low_hp, enemy_type="drone")
        sound.stop_all()
        print()
        type_text(t('perimeter_win'), 0.025)
    else:
        print()
        type_text(t('perimeter_skip'), 0.025)
    time.sleep(0.8)
    wait_for_keypress()


def run_ending(player):
    clear_screen()
    sound.stop_all()
    print_header("PIONEER PROTOCOL: NORMALIZATION EXECUTION")
    type_text(t('ending_core_1'), 0.03)
    type_text(t('ending_core_2'), 0.03)
    type_text(t('ending_core_3'), 0.03)
    type_text(t('ending_core_4') + "\n", 0.03)

    total = sum(player.weights.values()) or 1
    w_k, w_s, w_c = player.weights['kinetic'], player.weights['scrap'], player.weights['cyber']

    time.sleep(1)
    print_divider()
    print(t('ending_analysis_header'))
    print_divider()

    bar_len = 30
    def make_bar(val, tot):
        filled = int(bar_len * val / tot) if tot else 0
        return f"[{'█' * filled}{'░' * (bar_len - filled)}] {val/tot*100:.1f}%"

    print(t('ending_kinetic_label', bar=make_bar(w_k, total), count=w_k))
    print(t('ending_scrap_label', bar=make_bar(w_s, total), count=w_s))
    print(t('ending_cyber_label', bar=make_bar(w_c, total), count=w_c))
    print()
    time.sleep(1.5)

    print_divider()
    if w_k == w_s == w_c:
        type_text(t('ending_balanced_1'), 0.035)
        print()
        type_text(t('ending_balanced_2'), 0.03)
        type_text(t('ending_balanced_3'), 0.03)
        type_text(t('ending_balanced_4'), 0.03)
        type_text(t('ending_balanced_5'), 0.03)
    elif w_k >= w_s and w_k >= w_c:
        type_text(t('ending_kinetic_1'), 0.035)
        print()
        type_text(t('ending_kinetic_2'), 0.03)
        type_text(t('ending_kinetic_3'), 0.03)
        type_text(t('ending_kinetic_4'), 0.03)
        type_text(t('ending_kinetic_5'), 0.03)
    elif w_s >= w_k and w_s >= w_c:
        type_text(t('ending_scrap_1'), 0.035)
        print()
        type_text(t('ending_scrap_2'), 0.03)
        type_text(t('ending_scrap_3'), 0.03)
        type_text(t('ending_scrap_4'), 0.03)
        type_text(t('ending_scrap_5'), 0.03)
    else:
        type_text(t('ending_cyber_1'), 0.035)
        print()
        type_text(t('ending_cyber_2'), 0.03)
        type_text(t('ending_cyber_3'), 0.03)
        type_text(t('ending_cyber_4'), 0.03)
        type_text(t('ending_cyber_5'), 0.03)
    print_divider()

    print()
    time.sleep(1)

    # 플레이 통계
    print_divider()
    print(t('ending_stats_header'))
    print_divider()
    tier_final = player.get_highest_tier()
    tier_name = {4: t('tier_4'), 3: t('tier_3'), 2: t('tier_2'), 1: t('tier_1'), 0: t('tier_0')}.get(tier_final, 'N/A')
    diff_label = {"easy": t('diff_label_easy'), "normal": t('diff_label_normal'), "hard": t('diff_label_hard')}.get(player.difficulty, player.difficulty)
    threat_final = get_turn_scale_multiplier(player)

    print(t('ending_stat_diff', val=diff_label))
    print(t('ending_stat_turns', val=player.turn_count))
    print(t('ending_stat_threat', val=threat_final))
    print(t('ending_stat_enemies', val=player.enemies_defeated))
    print(t('ending_stat_hp', hp=player.hp, maxhp=player.max_hp))
    print(t('ending_stat_scrap', val=player.materials))
    print(t('ending_stat_items', val=len(player.inventory)))
    print(t('ending_stat_tier', val=tier_name))

    total_consumables = sum(player.consumables.values())
    print(t('ending_stat_consumables', val=total_consumables))
    if player.skill_slots:
        end_job_label = skills.JOB_LABEL.get(player.job_class, player.job_class)
        end_skill_names = ", ".join(skills.SKILL_DEFS.get(sid, {}).get('name', sid) for sid in player.skill_slots)
        print_divider()
        print(t('ending_skill_header', job_label=end_job_label))
        print(t('ending_skill_slots', max_col=2, count=len(player.skill_slots)))
        print(f"  {end_skill_names}")
    print_divider()
    time.sleep(1)

    print()
    time.sleep(1.2)
    type_text(t('ending_epilogue_1'), 0.04)
    type_text(t('ending_epilogue_2'), 0.04)
    print()
    time.sleep(0.8)
    type_text(t('ending_epilogue_3'), 0.04)
    print()
    type_text(t('ending_epilogue_4'), 0.03)
    type_text(t('ending_epilogue_5'), 0.03)
    type_text(t('ending_epilogue_6'), 0.03)
    print()
    time.sleep(1.2)
    type_text(t('ending_epilogue_7'), 0.04)
    time.sleep(0.6)
    type_text(t('ending_epilogue_8'), 0.03)
    type_text(t('ending_epilogue_9'), 0.03)
    type_text(t('ending_epilogue_10'), 0.035)
    print()
    time.sleep(1.0)
    print(Fore.GREEN + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.GREEN + Style.BRIGHT + "  ║  " + ea_rpad(t('ending_clear_banner'), 72) + "║")
    print(Fore.GREEN + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    wait_for_keypress()

if __name__ == "__main__":
    setup_global_exception_hook()
    sound.init()
    run_game()