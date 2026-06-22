# constants.py — 전역 상수 및 인라인 데이터 정의
# 이 모듈은 아무것도 import하지 않는다 (최하단 의존성).
# 런타임 전역(AMBIENT_LORE 등)은 core.init_and_load_db()가
# import constants 후 constants.XXX = ... 로 직접 갱신한다.

GAME_VERSION = "1.0.0"

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


DIFFICULTY_SCALING_RATE = {"easy": 0.01, "normal": 0.02, "hard": 0.035}

# 전투 시작 시점 플레이어 체력 비율이 이 값 미만이면, '위험 상태 완화'가 적용되어
# 그 전투에 한해 턴수 증가분의 절반만 반영한다. 장비가 좋아졌다고 적이 강해지는
# 역설계가 아니라, 순수하게 플레이어가 죽기 직전인 상황을 구제하는 안전핀이다.
LOW_HP_RELIEF_THRESHOLD = 0.3
LOW_HP_RELIEF_FACTOR = 0.5



# ====================================================================
# 기초 스탯 파생 공식 상수 (기획서: RPG 핵심 연산 시스템.md 기준)
# HP 스케일: 현재 게임 기준값 1500에 맞춰 역산 조정된 상수
# ====================================================================

def f_A(A):
    """기초 스탯 A의 실효 가치 f(A).
    구간 1 (A≤15): 효율 100% — 안정적 동기화
    구간 2 (15<A≤25): 효율 50% — 연산 과부하
    구간 3 (A>25): 효율 10% — 임계점 마비
    """
    if A <= 15:   return A * 0.02
    elif A <= 25: return 0.30 + (A - 15) * 0.01
    else:         return 0.40 + (A - 25) * 0.002

# MaxHP: STAT_HP_BASE + (Lv*STAT_HP_LV) + (VIT*STAT_HP_VIT) + floor(f(VIT)*STAT_HP_fVIT)
# VIT=10, Lv=1 => 300 + 30 + 1000 + 150 = 1480 ≈ 1500
STAT_HP_BASE  = 300
STAT_HP_LV    = 30
STAT_HP_VIT   = 100
STAT_HP_fVIT  = 750

# DEF_base: (Lv*STAT_DEF_LV) + (VIT*STAT_DEF_VIT) + floor(f(VIT)*STAT_DEF_fVIT)
STAT_DEF_LV   = 1
STAT_DEF_VIT  = 2
STAT_DEF_fVIT = 30

# MaxRAM: 4 + floor(INT_S * STAT_RAM_INT)
STAT_RAM_INT  = 0.2

# 스탯 기본값 (민간인/1막 시작 시)
STAT_DEFAULT_VIT = 10
STAT_DEFAULT_INT = 10
STAT_DEFAULT_DEX = 10
STAT_DEFAULT_LV  = 1
