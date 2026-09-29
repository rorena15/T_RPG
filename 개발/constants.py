# constants.py — 전역 상수 및 인라인 데이터 정의
# 이 모듈은 아무것도 import하지 않는다 (최하단 의존성).
# 런타임 전역(AMBIENT_LORE 등)은 core.init_and_load_db()가
# import constants 후 constants.XXX = ... 로 직접 갱신한다.

GAME_VERSION = "1.9.0"

TEXT_SPEED_MULT = 1.0  # 텍스트 출력 속도 배수 (0=즉시, 0.5=빠름, 1.0=보통, 2.0=느림)

CREDITS_GITHUB = "https://github.com/rorena15/T_RPG"
CREDITS_ITCH   = ""  # itch.io 배포 후 URL 삽입

AMBIENT_LORE = []
AMBIENT_LORE_EN = []
CONSUMABLES_DB = {}
SESSIONS_DB = []
RANDOM_EVENTS = []
TRADER_ITEMS = []
MASTER_FORMULAS = {}

# 특수 아이템 — SQLite에 없는 이벤트 전용 아이템 (get_equipment_data fallback 참조)
SPECIAL_ITEMS = {
    "NEOARC_AI_WPN": {
        "id": "NEOARC_AI_WPN",
        "name": "죽은 AI의 서비스 화기",
        "name_en": "Dead AI's Service Firearm",
        "power": 100,
        "tier": 1,
        "slot": "main_weapon",
        "type": "weapon",
        "slot_weight": 1.5,
        "hp_bonus": 0,
        "def_bonus": 0,
        "e_suppress": 0,
        "cyber_regen": 0,
        "desc": "[T=1 기업제·폐기 예정] 네오 아크 AI 잔해에서 회수한 과부하 화기. 2전투 후 열손상으로 자동 파기.",
        "desc_en": "[T=1 Corporate · Pending Disposal] An overloaded firearm salvaged from the wreck of a Neo Arc AI. Self-destructs from heat damage after 2 battles.",
    }
}

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


def slot_label(slot):
    """장비 슬롯 표시 이름 (언어별). SLOT_DISPLAY는 한국어 원본. 모르는 슬롯은 '기타'."""
    from i18n import t
    return t(f"slot_{slot}") if slot in SLOT_DISPLAY else t("slot_other")


def tier_tag(tier, default=""):
    """등급 태그 (언어별)."""
    from i18n import t
    return t(f"tier_tag_{tier}") if tier in TIER_TAGS else default

_eq_cache: dict = {}

SUDDEN_QUESTS = [
    {"id": "SQ_SCRAP_A", "title": "잔해 자원 긴급 확보", "title_en": "Emergency Salvage",
     "desc": "산개한 고철 잔해에서 자원을 집중적으로 확보하십시오.", "desc_en": "Secure resources from the scattered scrap debris.",
     "detail": "고철 +50개 수집", "detail_en": "Collect +50 scrap", "type": "scrap", "target": 50, "turns": 10,
     "reward_type": "consumable", "reward_id": "MED_FIX_300", "reward_desc": "군용 지혈제 1개", "reward_desc_en": "1 Military Hemostatic"},
    {"id": "SQ_SCRAP_B", "title": "집중 파밍 프로토콜", "title_en": "Intensive Farming Protocol",
     "desc": "이 구역 전체에 회수 가능한 잔해가 산재합니다. 최대한 확보하십시오.", "desc_en": "Recoverable debris is scattered across this sector. Secure as much as you can.",
     "detail": "고철 +80개 수집", "detail_en": "Collect +80 scrap", "type": "scrap", "target": 80, "turns": 14,
     "reward_type": "materials", "reward_amount": 50, "reward_desc": "고철 50개 추가", "reward_desc_en": "50 extra scrap"},
    {"id": "SQ_COMBAT_A", "title": "구역 정화", "title_en": "Sector Purge",
     "desc": "이 구역의 기계 밀도가 비정상입니다. 적 일부를 제압하여 경로를 확보하십시오.", "desc_en": "Machine density in this sector is abnormal. Suppress some enemies to secure a route.",
     "detail": "전투 2회 승리", "detail_en": "Win 2 battles", "type": "combat", "target": 2, "turns": 12,
     "reward_type": "consumable", "reward_id": "MED_PER_50", "reward_desc": "응급 지혈대 1개", "reward_desc_en": "1 Emergency Tourniquet"},
    {"id": "SQ_COMBAT_B", "title": "데드존 청소부", "title_en": "Dead Zone Sweeper",
     "desc": "총괄국이 자동화 기계 포대를 증파했습니다. 전투 역량을 검증하십시오.", "desc_en": "The Bureau has deployed more automated gun batteries. Prove your combat capability.",
     "detail": "전투 3회 승리", "detail_en": "Win 3 battles", "type": "combat", "target": 3, "turns": 18,
     "reward_type": "consumable", "reward_id": "MED_FIX_500", "reward_desc": "합성 바이오 젤 1개", "reward_desc_en": "1 Synthetic Bio-Gel"},
    {"id": "SQ_SEARCH_A", "title": "지형 데이터 스캔", "title_en": "Terrain Data Scan",
     "desc": "사이버덱이 불완전한 지형 정보를 감지했습니다. 추가 스캔이 필요합니다.", "desc_en": "Your cyberdeck detected incomplete terrain data. Further scans are needed.",
     "detail": "탐색 3회", "detail_en": "Search 3 times", "type": "search", "target": 3, "turns": 7,
     "reward_type": "ram", "reward_amount": 1, "reward_desc": "RAM +1", "reward_desc_en": "RAM +1"},
    {"id": "SQ_SEARCH_B", "title": "광역 환경 스캐닝", "title_en": "Wide-Area Scan",
     "desc": "광범위한 지형 정보 수집이 요청됩니다. 반복 스캔을 실시하십시오.", "desc_en": "Wide-range terrain data collection requested. Run repeated scans.",
     "detail": "탐색 5회", "detail_en": "Search 5 times", "type": "search", "target": 5, "turns": 12,
     "reward_type": "consumable", "reward_id": "FOOD_BOTH", "reward_desc": "수분 함유 전투식량 1개", "reward_desc_en": "1 Hydrated Combat Ration"},
]

ENEMY_ART = {
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
    "NORMAL": [
        """
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
        """
      ___________
     /  [GCS-MK2] \\
    | [=] |  | [=] |  <-- [이중 고압 화기]
    |_____|  |_____|
       ||||||||
      /||||||||\\     <-- [총괄국 중형 플랫폼]
     |   ____   |
     |  | GC |  |   <-- [GCS 제식 인장]
     |__|____|__|
    //  '----'  \\\\  <-- [중장갑 지지대]
   //            \\\\
        """,
        """
      ( . . )    <-- [마이크로 광학 쌍안]
       \\___/
      .-'X'-.        <-- [스텔스 경량 동체]
     / ~~~~~ \\
    | (/)  (\\) |  <-- [접이식 추진 날개]
     \\_______/
      |  |  |
     /|  |  |\\   <-- [삼각 경량 지지대]
    / |  |  | \\
        """,
    ],
    "BIOHOUND": [
        """
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
        """,
        """
   ~~~~~~~~~~~~~~~~~~~~
  ( [BIO:NEURAL COLONY] )  <-- [신경 기생체 군집]
   ~~~~~~~~~~~~~~~~~~~~
  /|()|()|()|()|()|()|\\
 / |                  |\\ <-- [다절지 변이 하지 ×8]
|  '~~~~~~~~~~~~~~~~~~'  |
|   [SPINE : OVERLOAD]   |  <-- [척추 과부하 코어]
 \\______________________/
        """,
        """
       /\\ /\\
      ( X   )    <-- [적출 복안 추적 센서]
       \\___/
     __|   |__
    /  |GEL|  \\   <-- [유기 젤 충격 흡수 흉강]
   |   |___|   |
   |   |   |   |
    \\ /|   |\\ /   <-- [강화 도약 하지]
     V  '---'  V
        """,
    ],
}


DIFFICULTY_SCALING_RATE = {"easy": 0.01, "normal": 0.02, "hard": 0.035}
ENEMY_TURN_SCALE_CAP    = 20   # 일반 적은 이 턴까지만 강해진다: 오래 파밍해도 손해가 끝없이 쌓이지 않게
ENEMY_ATK_MULT          = 0.95 # 적(보스 포함) 공격력 일괄 배율: 강화 하락·내구도, 강화소 퀘스트가 더해져 5% 낮춤

# ── 전투 균형 상수 ────────────────────────────────────────────────────────────
BOSS_DEF             = 45
BOSS_BASE_ATK        = 100
BOSS_HP              = 100000
BOSS_TURN_LIMIT      = 15
BOSS_PHASE2_RATIO    = 0.5    # HP 이 비율 이하 → Phase 2 전환
BOSS_PHASE2_ATK_MULT = 1.6
BOSS_PHASE2_LI_BONUS = 5
# 보스는 강해야 이긴다 (combat.py):
#   체력 = max(BOSS_HP × 난이도 배율, BOSS_HP × 내 실효 공격력 / BOSS_POWER_REF)
#   - 난이도 배율(BOSS_DIFF_MULT): 이만큼 강해지기 전에는 15턴 안에 못 잡는다 → 파밍 없이 0%
#   - 공격력이 기준을 넘으면 체력이 같이 늘어 잡는 데 늘 약 11타가 든다 → 끝없이 쉬워지지 않는다
#   - 공격력 배율(BOSS_DIFF_ATK): 강한 플레이어의 최대 성공률 (쉬움 약 70% / 보통 약 40% / 어려움 약 20%)
# 어려움은 일반 전투가 치명적이라(탐색 90회면 보스 도달 40%) 보스 공격력은 보통보다 낮다
BOSS_DIFF_MULT       = {"easy": 1.25, "normal": 1.30, "hard": 1.30}
BOSS_DIFF_ATK        = {"easy": 1.78, "normal": 1.88, "hard": 1.74}
BOSS_POWER_REF       = 180
# 검증 (봇 150판씩, 탐색 0 / 20 / 45 / 90회): 쉬움 0 / 7 / 33 / 68%, 보통 0 / 3 / 20 / 44%, 어려움 0 / 1 / 12 / 19%
ALERT_INC_BOSS       = 40
ALERT_INC_BIO        = 20
ALERT_INC_DRONE      = 10

BIO_DEF              = 15
BIO_BASE_ATK         = 250
BIO_HP_MIN           = 8000
BIO_HP_MAX           = 17000

DRONE_DEF            = 5
DRONE_BASE_ATK       = 175
DRONE_HP_MIN         = 8000
DRONE_HP_MAX         = 16000

SUB_WPN_POWER        = 100

# 장비 드롭: 일반 전투 승리 / 탐색 파밍에서 나올 확률, 나오면 등급 비율 (T4 80% / T3 19% / T2 1%)
GEAR_DROP_COMBAT     = 0.30
GEAR_DROP_SEARCH     = 0.15
GEAR_DROP_TIER_WEIGHTS = {4: 80, 3: 19, 2: 1}

# 강화 (upgrade.py): 시도 1회 고철 = max(1, floor(α·(k+1)^1.2)) × 이 배율
UPGRADE_COST_MULT    = 3
ESCAPE_WEIGHTS       = (60, 20, 10, 5, 5)  # SAFE / NORMAL / 1.5X / 2.0X / LUCKY

# 고티어 장비의 '숫자가 커지는' 연출 배율. 피해와 체력에 같은 배율을 써야 표시된 피해만큼 표시된 체력이 줄어든다
# (예전 피해 x100000 / 체력 x100 은 수천만 피해에도 체력이 조금만 줄어 보였다).
SCALE_MULT_T23_DMG   = 10
SCALE_MULT_T23_HP    = 10
SCALE_MULT_T01_DMG   = 100
SCALE_MULT_T01_HP    = 100

# ── 장비 계산 상수 ────────────────────────────────────────────────────────────
ARMOR_HP_MULT        = 8      # 방어구 power × N → HP 보너스
ARMOR_DEF_DIV        = 8      # 방어구 power // N → DEF 보너스
GEAR_ATK_MULT        = 0.4    # 기어 power × N → ATK 보너스
DEFAULT_ARMOR_HP     = 80     # 미장착 방어구 슬롯 가상 HP 보정
DEFAULT_ARMOR_DEF    = 1      # 미장착 방어구 슬롯 가상 DEF 보정
DEFAULT_GEAR_ATK     = 5      # 미장착 기어 슬롯 가상 ATK 보정

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


# ── 무기 공격음 (sound.py의 atk_<종류>) ──────────────────────────────────────
# 무기 데이터에 종류 칸이 없어 이름·설명으로 나눴다. 없는 무기는 맨손 소리.
WEAPON_SFX = {
    "WEAPON_NONE": "fist",
    # 칼·창·단검
    "WEAPON_SCRAP_01": "blade", "WEAPON_SCRAP_06": "blade", "WEAPON_STD_02": "blade", "WEAPON_STD_10": "blade",
    "WEAPON_REF_01": "blade", "WEAPON_CORP_06": "blade", "WEAPON_LEGACY_06": "blade",
    # 에너지 검
    "WEAPON_STD_05": "eblade", "WEAPON_REF_06": "eblade", "WEAPON_CORP_01": "eblade", "WEAPON_LEGACY_01": "eblade",
    # 둔기·도끼·압착
    "WEAPON_SCRAP_05": "blunt", "WEAPON_SCRAP_10": "blunt", "WEAPON_STD_04": "blunt", "WEAPON_REF_04": "blunt", "WEAPON_REF_08": "blunt",
    # 톱날
    "WEAPON_SCRAP_07": "saw",
    # 전기 충격
    "WEAPON_SCRAP_03": "shock", "WEAPON_SCRAP_08": "shock", "WEAPON_REF_02": "shock",
    # 화염
    "WEAPON_SCRAP_04": "flame",
    # 총 (소총·권총·저격총·리벳 건)
    "WEAPON_SCRAP_02": "gun", "WEAPON_STD_01": "gun", "WEAPON_STD_07": "gun", "WEAPON_STD_08": "gun",
    "WEAPON_REF_10": "gun", "WEAPON_CORP_05": "gun",
    # 산탄
    "WEAPON_SCRAP_09": "shotgun", "WEAPON_STD_06": "shotgun",
    # 폭발 (유탄기·파일 벙커·파쇄포)
    "WEAPON_STD_09": "heavy", "WEAPON_REF_05": "heavy", "WEAPON_REF_09": "heavy",
    # 레일·플라즈마·전자기
    "WEAPON_STD_03": "energy", "WEAPON_REF_03": "energy", "WEAPON_REF_07": "energy", "WEAPON_CORP_02": "energy",
    "WEAPON_CORP_03": "energy", "WEAPON_LEGACY_02": "energy", "WEAPON_LEGACY_03": "energy",
    # 신경독소·나노 분사
    "WEAPON_CORP_04": "toxin", "WEAPON_LEGACY_04": "toxin", "WEAPON_LEGACY_05": "toxin",
}


def weapon_sfx(item_id):
    """주무기의 공격 효과음 이름 (atk_fist 등)."""
    return "atk_" + WEAPON_SFX.get(item_id, "fist")
