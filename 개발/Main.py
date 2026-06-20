import math
import random
import sys
import time
import os
import json
import sqlite3
import db_init
from sys_log import sys_log,track
import sys
import os

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

# ====================================================================
# [0.5] 전체 로깅
# ====================================================================
def track_event(event_name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # 시스템 로그 파일에 지표 기록
            sys_log(f"Event: {event_name}", event_type="METRIC")
            return result
        return wrapper
    return decorator
# ====================================================================
# [1] 데이터베이스 및 단일 진실 공급원(SSOT) 연산 코어 로더
# ====================================================================
AMBIENT_LORE = []
CONSUMABLES_DB = {}
SESSIONS_DB = []
MASTER_FORMULAS = {}
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
        sys_log(" [SYSTEM LOG] 서사 및 생체 소모품 데이터 구조화 파싱 완료.", level="INFO")
        time.sleep(0.6)
    except Exception as e:
        sys_log(f" [SYSTEM FATAL] JSON 데이터베이스 파싱 오류: {e}", level="FATAL")
        wait_for_keypress()
        sys.exit()

@track
def get_equipment_data(item_id):
    """장비 데이터는 SQLite DB에서 실시간 쿼리합니다."""
    db_path = "stigma_data.db"
    if not os.path.exists(db_path):
        return {"name": "손상된 고철", "power": 5, "type": "kinetic", "tier": 4, "desc": "DB 파일 누락."}
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, power, type, tier, description FROM equipment WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"name": row[0], "power": row[1], "type": row[2], "tier": row[3], "desc": row[4]}
    return {"name": "미식별 고철", "power": 5, "type": "kinetic", "tier": 4, "desc": "DB 미등록 부품."}

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

def print_header(title):
    print("\n+" + "-"*76 + "+")
    print(f"| {title.center(74)} |")
    print("+" + "-"*76 + "+\n")

def print_divider():
    print("-" * 78)

def print_ambient_lore():
    if AMBIENT_LORE:
        lore = random.choice(AMBIENT_LORE)
        print(f"\n[환경 로그] {lore}")
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
        
        # T=0 유물 무기 딱 1개만 정제 지급 완료
        self.inventory = ["WEAPON_LEGACY_01"]
        self.equipment = {"weapon": "WEAPON_NONE"}

    def get_highest_tier(self):
        item_data = get_equipment_data(self.equipment["weapon"])
        return item_data.get("tier", 4)

    def to_dict(self):
        return {
            "hp": self.hp, "hunger": self.hunger, "thirst": self.thirst,
            "max_ram": self.max_ram, "dex": self.dex, "materials": self.materials,
            "consumables": self.consumables, "weights": self.weights,
            "inventory": self.inventory, "equipment": self.equipment, "reputation": self.reputation
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
        self.equipment = data.get("equipment", {"weapon": "WEAPON_NONE"})

    def get_attack_power(self):
        item_data = get_equipment_data(self.equipment["weapon"])
        return item_data.get("power", 10)

    @track
    def consume_resources(self):
        self.hunger = max(0, self.hunger - 5)
        self.thirst = max(0, self.thirst - 6)
        
        if self.hunger == 0 or self.thirst == 0:
            self.hp -= 50
            print("\n[SYSTEM WARN] 신체 연료 고갈. 바이오 조직 괴사가 시작됩니다. (HP -50)")
            wait_for_keypress()
            if self.hp <= 0:
                print("\n[SYSTEM FATAL] 신체 손상 100%. 불량 코드가 완전히 소거되었습니다.")
                sys.exit()

    def show_status(self):
        tier = self.get_highest_tier()
        _, display_hp, scale_log = apply_dynamic_scaling(0, self.hp, tier)
        _, display_max_hp, _ = apply_dynamic_scaling(0, self.max_hp, tier)

        print("+" + "-"*76 + "+")
        print("|" + "[ 내 의체 시스템 상태창 ]".center(76) + "|")
        print("+" + "-"*76 + "+")
        if scale_log:
            print(f"  {scale_log}")
            print("+" + "-"*76 + "+")
        
        print(f"  [생명력] {display_hp:,} / {display_max_hp:,}    [허기] {self.hunger:3d} / 100      [갈증] {self.thirst:3d} / 100")
        
        item_data = get_equipment_data(self.equipment['weapon'])
        wpn_name = item_data['name']
        wpn_pwr = self.get_attack_power()
        
        print(f"  [장착 무기] {wpn_name:<15} (T={tier} 위력: {wpn_pwr:<3d})        [가용 평판] {self.reputation:+d}")
        print_divider()
        
        food_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k, {}).get("type")=="food")
        water_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k, {}).get("type")=="water")
        med_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB.get(k, {}).get("type")=="hp")
        
        print(f"  [소지품] 회복약: {med_cnt} | 식량: {food_cnt} | 식수: {water_cnt} | 고철 자산: {self.materials}")
        print("+" + "-"*76 + "+\n")

    def manage_inventory(self):
        while True:
            clear_screen()
            print_header("시스템 인벤토리 및 정비")
            
            print("[ 보유 중인 장비 목록 ]")
            if not self.inventory: print("  - 데이터 없음 (비어있음)")
            else:
                for i, item_id in enumerate(self.inventory):
                    equip_mark = "[장착중] " if self.equipment["weapon"] == item_id else "         "
                    item_data = get_equipment_data(item_id)
                    print(f"  [{i+1}] {equip_mark}{item_data['name']} (위력: {item_data['power']} | T={item_data.get('tier',4)})")
            
            print_divider()
            print("[ 명령 프로토콜 ]")
            print("  1. 장비 장착")
            print("  2. 장비 해제")
            print("  3. 소모품 사용")
            print("  4. 장비 분해 (고철 추출)")
            print("  0. 탐색망으로 복귀")
            try:cmd = safe_input("\n명령어 입력: ")
            except: sys.exit()
            
            if cmd == "1":
                if not self.inventory:
                    print("\n[알림] 교체할 장비가 없습니다.")
                    wait_for_keypress()
                    continue
                choice = safe_input("장착할 아이템 번호: ")
                if choice.isdigit() and 0 < int(choice) <= len(self.inventory):
                    item_id = self.inventory[int(choice)-1]
                    self.equipment["weapon"] = item_id
                    item_data = get_equipment_data(item_id)
                    print(f"\n[처리] '{item_data['name']}'을(를) 시스템 소켓에 결속했습니다.")
                    wait_for_keypress()
                    
            elif cmd == "2":
                if self.equipment["weapon"] == "WEAPON_NONE":
                    print("\n[알림] 이미 소켓이 비어있는 맨손 상태입니다.")
                else:
                    item_data = get_equipment_data(self.equipment["weapon"])
                    print(f"\n[처리] '{item_data['name']}'의 결속을 해제했습니다.")
                    self.equipment["weapon"] = "WEAPON_NONE"
                wait_for_keypress()
                
            elif cmd == "3":
                self.use_consumable_menu()
                
            elif cmd == "4":
                if not self.inventory:
                    print("\n[알림] 분해할 장비가 없습니다.")
                else:
                    choice = safe_input("분해하여 고철로 변환할 아이템 번호: ")
                    if choice.isdigit() and 0 < int(choice) <= len(self.inventory):
                        idx = int(choice) - 1
                        item_id = self.inventory[idx]
                        if self.equipment["weapon"] == item_id:
                            print("\n[거부] 시스템 소켓에 결속 중인 장비는 분해할 수 없습니다. 먼저 해제하십시오.")
                        else:
                            self.inventory.pop(idx)
                            gained_scrap = random.randint(15, 30)
                            self.materials += gained_scrap
                            item_data = get_equipment_data(item_id)
                            print(f"\n[처리] '{item_data['name']}'을(를) 분쇄하여 일반 고철 {gained_scrap}개를 추출했습니다.")
                wait_for_keypress()
            elif cmd == "0":
                break

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
        cmd = safe_input("\n사용할 아이템 번호: ")
        
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
        coords = [(x, y) for x in range(5) for y in range(5) if (x,y) not in [(0,0), (4,4)]]
        self.event_locations = random.sample(coords, 4)
        self.session_index = 0
        self.escaped_enemy_hp = None

    def to_dict(self):
        return {
            "player_pos": self.player_pos, "event_locations": self.event_locations,
            "session_index": self.session_index, "escaped_enemy_hp": self.escaped_enemy_hp
        }
        
    def from_dict(self, data):
        self.player_pos = data.get("player_pos", [0, 0])
        self.event_locations = [tuple(x) for x in data.get("event_locations", [])]
        self.session_index = data.get("session_index", 0)
        self.escaped_enemy_hp = data.get("escaped_enemy_hp", None)

    def draw(self):
        print(" [ 데드존 섹터 그리드 스캐너 ]")
        for y in range(self.size - 1, -1, -1):
            row_str = "    "
            for x in range(self.size):
                if [x, y] == self.player_pos: row_str += "[ P ] "
                elif [x, y] == self.bunker_pos: row_str += "[ B ] "
                else: row_str += "[ . ] "
            print(row_str)
        print("  (P: 의체 위치 | B: 미식별 방공호)\n")

def save_data(player, grid):
    save_file = {"player": player.to_dict(), "grid": grid.to_dict()}
    try:
        with open(resource_path("stigma_save.json"), "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        print("\n[SYSTEM] 현재 동기화 로그가 로컬 환경에 안전하게 백업되었습니다.")
    except Exception as e:
        print(f"\n[SYSTEM ERR] 백업 실패: {e}")
        
    wait_for_keypress() # 메시지 확인 후 다음으로 넘어가도록 대기

# ====================================================================
# [5] 전투 시스템 (master_formulas.json 정합 수식 적용 및 UX 대기 제어)
# ====================================================================
@track
def combat_loop(player, is_boss=False, current_hp=None):
    if is_boss:
        name, e_def, atk, hp = "스캐브 컬렉터 [BOSS]", 45, 180, 35000
        art, header_title = ENEMY_ART["BOSS"], "SYSTEM ALERT: 숙청 시퀀스 가동"
    else:
        name, e_def, atk, hp = "오염된 스캐브 드론", 5, 80, 8000
        art, header_title = ENEMY_ART["NORMAL"], "ENCOUNTER: 포식자 조우"
        if current_hp is not None:
            hp = current_hp
            name = "상처입은 스캐브 드론"
            header_title = "ENCOUNTER: 추적된 개체"

    turn = 1
    learning_index = 0
    consecutive_attacks = 0
    escaped = False
    action_logs = [f"[경보] 안개 속에서 {name}이(가) 나타났습니다!"]

    while hp > 0 and player.hp > 0:
        if is_boss and turn > 15:
            clear_screen()
            type_text("\n[SYSTEM FATAL] 15턴 임계점 초과. 거점이 고철 분진으로 분쇄되었습니다. GAME OVER.")
            sys.exit()

        clear_screen()
        tier = player.get_highest_tier()
        
        _, disp_ehp, scale_log = apply_dynamic_scaling(0, hp, tier)
        _, disp_php, _ = apply_dynamic_scaling(0, player.hp, tier)
        _, disp_pmaxhp, _ = apply_dynamic_scaling(0, player.max_hp, tier)

        print_header(header_title)
        if scale_log: 
            print(f"  {scale_log}")
            print_divider()
            
        print(art)
        print(f"--- 전투 턴 [{turn}] | {name} HP: {disp_ehp:,} ---")
        print(f" [내 의체] HP: {disp_php:,}/{disp_pmaxhp:,} | 가용 RAM: {player.max_ram}")
        if is_boss: 
            print(f" [적 상태] 패턴 분석 지수 (E): {learning_index}/10")
            
        print("\n[ 전투 로그 ]")
        for log in action_logs: print(f"  {log}")
        print("-" * 78 + "\n")
        action_logs.clear()

        print("  1. 주무기 물리 타격 (ATTACK)")
        print("  2. 급조 바리케이드 전개 (DEFENSE - 피격 반감 및 적 분석 지수 차감)")
        print("  3. 패킷 우회 교란 (HACK - RAM 2 소모, 적 분석 지수 초기화)")
        print("  4. 전술적 후퇴 (ESCAPE - 민첩 스탯 비례 탈출 및 확률적 파밍)")
        
        try: cmd = safe_input("\n명령 코드 입력 (1-4): ")
        except: sys.exit()
            
        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                learning_index += 3
                action_logs.append("[경고] 동일 공격 반복 감지. 보스가 궤적을 딥러닝 중입니다. (E +3)")
            
            # master_formulas.json 최우선 정합성 연산 공식 기준 패치 완료
            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            
            # 평판 가중치 F 정식 정합식 대입 (Wasteland_Gate = 1)
            f_multiplier = 1.0 + (player.reputation / 2000) * 1
            
            # 1. 대미지 연산 및 화면 선 출력
            dmg = max(100, math.floor(player.get_attack_power() * f_multiplier * penalty * 100) - e_def + random.randint(-50, 50))
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)
            
            print(f"\n  콰아앙! 무기가 적의 장갑판을 관통했습니다! (피해량: {disp_dmg:,})")
            time.sleep(1)
            # 2. 유저 피해 확인 후 체력 차감 및 시스템 스캔 갱신
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
                
                print("\n  교란 신호 방출! 보스의 센서 데이터가 초기화됩니다. (RAM -2)")
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
                    _, disp_eatk, _ = apply_dynamic_scaling(dmg_calc, 0, tier)
                    
                    print(f"\n  후퇴 중 적에게 공격을 허용했습니다! (피해량: {disp_eatk:,})")
                    time.sleep(1)
                    
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(f"  [시스템 갱신] 내 체력이 {disp_php_new:,}(으)로 감소했습니다.")
                    wait_for_keypress()
                    
                    if res == "NORMAL": escape_log = f"[탈출] 후퇴 중 적의 공격에 노출되었습니다. (피해: {disp_eatk:,})"
                    elif res == "1.5X": escape_log = f"[탈출] 치명적인 손상을 입으며 이탈했습니다. (피해: {disp_eatk:,})"
                    else: escape_log = f"[탈출 참사] 도주 중 의체 중심부가 관통당했습니다! (피해: {disp_eatk:,})"
                elif res == "LUCKY":
                    escape_log = "[기적적 탈출] 무사히 이탈하며 적 주변의 잔해에서 쓸만한 물자를 챙겼습니다."
                break
            
        else: 
            print("\n  [오류] 인식할 수 없는 명령 프로토콜입니다.")
            wait_for_keypress()
            action_logs.append("[오류] 잘못된 명령어 입력.")

        # --- 적의 반격 및 동적 수치 갱신 피드백 ---
        if hp > 0 and not escaped:
            _, disp_eatk, _ = apply_dynamic_scaling(atk, 0, tier)
            
            print(f"\n  {name}의 무자비한 공격! (피해량: {disp_eatk:,})")
            time.sleep(1)
            player.hp -= atk
            _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
            print(f"  [시스템 갱신] 내 잔여 체력: {disp_php_new:,} / {disp_pmaxhp:,}")
            time.sleep(1)
            
            action_logs.append(f"[피격] 적의 공격으로 {disp_eatk:,}의 손상을 입었습니다.")
            time.sleep(1)
            if cmd == "2": atk = 180 if is_boss else 80

        turn += 1

    if player.hp <= 0:
        clear_screen()
        if escaped: type_text(escape_log, 0.02)
        type_text("\n[SYSTEM FATAL] 신체 손상 100%. 의체 붕괴. GAME OVER.", 0.03)
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
                
        #후퇴 행동 완료 시 즉시 튕기지 않고 무조건 인지 대기 가동
        wait_for_keypress()
        return hp  
    
    clear_screen()
    print_header("TARGET ELIMINATED (적 제압 완료)")
    print(f"\n[승리] {name}의 시스템 가동이 중지되었습니다.")
    
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
            print("  [파밍] 고가치 일반 고철 20개를 회수했습니다.")
            
    wait_for_keypress()
    return None 

# ====================================================================
# [6] 메인 구동 루프 망 명세
# ====================================================================
def get_encounter_chance(player):
    hp_ratio = player.hp / player.max_hp
    base_chance = 0.10
    return base_chance + (0.25 * hp_ratio)

@track
def run_game():
    clear_screen()
    print_header("PROTOCOL: STIGMA (1막: 낙인)")
    
    print("  1. 새로운 게임 (New Game)")
    has_save = os.path.exists("stigma_save.json")
    if has_save:
        print("  2. 동기화 복구 (Load Game)")
        
    ans = safe_input("\n시스템 모드 선택: ")
    
    player = Player()
    grid = GameMap()

    if ans == "2" and has_save:
        try:
            with open(resource_path("stigma_save.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            player.from_dict(data["player"])
            grid.from_dict(data["grid"])
            clear_screen()
            type_text("[SYSTEM] 로컬 백업소에서 생체 신호를 성공적으로 복구했습니다.", 0.02)
        except Exception as e:
            type_text(f"[ERROR] 백업 파일 손상 ({e}). 초기화 프로토콜을 가동합니다.", 0.02)
    else:
        clear_screen()
        type_text("[SYSTEM BOOT] 생체 신호 복구 중... 인코딩 결함 발견.", 0.02)
        type_text("[LOG] 당신은 '네오 아크'의 실험실에서 폐기 처리된 불량 코드입니다.", 0.02)
        type_text("[LOG] 버려진 불모지, '데드존'의 쓰레기 바다 한복판.", 0.02)
        type_text("[WARNING] 무국적 불량(Civilian) 시스템 작동.\n", 0.02)
        
    wait_for_keypress()

    while True:
        clear_screen()
        grid.draw()
        player.show_status()
        
        print(" [명령 프로토콜]")
        print("  W, A, S, D  : 그리드 이동")
        print("  F           : 현재 타일 탐색 및 자원 파싱")
        print("  I           : 인벤토리 및 시스템 정비")
        print("  C           : 현재 상태 로컬 백업 (저장)")
        print("  Q           : 시스템 접속 종료 (Exit)")
        print_divider()
        
        try: move = safe_input("\n입력: ").strip().upper()
        except: sys.exit()

        if move == "I":
            player.manage_inventory()
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
            
            if roll <= encounter_chance: 
                print("\n[경고] 탐색 중 발생한 소음이 기계 괴수를 끌어들였습니다!")
                wait_for_keypress()
                grid.escaped_enemy_hp = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp)
            elif roll <= encounter_chance + 0.45: 
                print("\n[알림] 쓸만한 것을 아무것도 찾지 못했습니다. 시간만 낭비했습니다.")
                print_ambient_lore()
            else: 
                item_roll = random.random()
                if item_roll <= 0.25:
                    gained = random.randint(10, 25)
                    player.materials += gained
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
        elif move == "Q":
                clear_screen()
                print_header("시스템 접속 종료")
                print("현재까지의 개척 로그를 백업하시겠습니까? (Y/N)")
                # 유저의 저장 의사 확인 (버퍼 클리어 및 입력 제어)
                save_choice = safe_input("저장 후 종료하시겠습니까? (Y/N): ").strip().upper()
                if save_choice == 'Y':
                    save_data(player, grid) # 기존에 정의한 save_data 함수 활용
                    print("\n[SYSTEM] 데이터 동기화 완료. 프로토콜을 종료합니다.")
                else:
                    print("\n[SYSTEM] 데이터 백업 없이 접속을 종료합니다.")
                    print("\n" + "="*78)
                    print(" 생체 접속 종료. 그리드망에서 이탈합니다. ".center(76))
                    print("="*78 + "\n")
                time.sleep(0.8)
                sys.exit()
                continue
        
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
            if current_loc == tuple(grid.bunker_pos):
                if SESSIONS_DB and len(SESSIONS_DB) > 4:
                    handle_session(player, SESSIONS_DB[4])
                combat_loop(player, is_boss=True) 
                run_ending(player)
                break
            elif current_loc in grid.event_locations:
                if SESSIONS_DB and grid.session_index < len(SESSIONS_DB):
                    handle_session(player, SESSIONS_DB[grid.session_index])
                grid.event_locations.remove(current_loc)
                grid.session_index += 1
            else:
                if random.random() < get_encounter_chance(player):
                    print("\n[경보] 안개 속에서 기계 괴수의 광학 센서가 번뜩입니다!")
                    wait_for_keypress()
                    grid.escaped_enemy_hp = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp)
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
        try: ans = safe_input("\n행동 선택 (1-3): ")
        except: sys.exit()
        if ans in ["1", "2", "3"]:
            choice_data = session['choices'][int(ans) - 1]
            player.weights[choice_data['weight']] += 1
            
            if "reward" in choice_data and choice_data["reward"]:
                if choice_data["reward"] == "SCRAP_MAT": player.materials += 30
                else: 
                    player.inventory.append(choice_data["reward"])
                    item_data = get_equipment_data(choice_data["reward"])
                    print(f"\n[보상] 소켓 파싱 완료: 장비 '{item_data['name']}' 코드를 획득했습니다.")
                    
            if "hp_loss" in choice_data: player.hp -= choice_data["hp_loss"]
            time.sleep(1)
            if "thirst" in choice_data: player.thirst = min(100, player.thirst + choice_data["thirst"])
            time.sleep(1)
            if "ram_bonus" in choice_data: player.max_ram += choice_data["ram_bonus"]
            time.sleep(1)
            print(f"\n{choice_data['log']}")
            wait_for_keypress()
            break

def run_ending(player):
    clear_screen()
    print_header("PIONEER PROTOCOL: NORMALIZATION EXECUTION")
    type_text("거대한 기계 괴수가 스파크를 뿜으며 무릎을 꿇습니다.", 0.03)
    type_text("마스터 AI의 추적을 피해, 데드존의 벙커 터미널에 중앙 코어를 직결합니다.", 0.03)
    type_text("순간, 벙커 전체가 백색 빛으로 가득 차며 당신의 행위 로그가 스캔됩니다.\\n", 0.03)
    
    total = sum(player.weights.values()) or 1
    w_k, w_s, w_c = player.weights['kinetic'], player.weights['scrap'], player.weights['cyber']
    
    time.sleep(1) # 극적 템포를 위한 타임 슬립 유지
    print(f"  [분석] 컴뱃 포스 동기화율      : {w_k/total*100:.1f}%")
    print(f"  [분석] 메카니컬 테크 동기화율  : {w_s/total*100:.1f}%")
    print(f"  [분석] 넷 포스 동기화율        : {w_c/total*100:.1f}%\n")
    time.sleep(1)

    # master_formulas.json의 규정 명칭 분리 수렴 완료 (awakening vs resonance)
    if w_k == w_s == w_c: 
        type_text("[히든 전직 프로토콜 가동] tri_balance_awakening ➔ '황금 분할의 조율사' 신경망이 교차 개방됩니다.", 0.04)
    elif w_k >= w_s and w_k >= w_c: 
        type_text("[각성] 컴뱃 포스 코드가 의체에 직결됩니다.", 0.04)
    elif w_s >= w_k and w_s >= w_c: 
        type_text("[각성] 메카니컬 테크 기술 인덱스가 전이됩니다.", 0.04)
    else: 
        type_text("[각성] 넷 포스 아나키스트 패킷이 주입됩니다.", 0.04)
        
    type_text("\n\"당신은 마침내 시스템의 모순 구역 내부(Sector_0)에 확고한 첫 영토를 개척해 냈습니다.\"", 0.05)
    print("\n" + "="*78)
    print(" 1막 [낙인] 클리어 (DEMO END) ".center(76))
    print("="*78)
    wait_for_keypress()

if __name__ == "__main__":
    run_game()