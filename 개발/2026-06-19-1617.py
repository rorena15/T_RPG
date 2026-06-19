import math
import random
import sys
import time
import os
import json

# ====================================================================
# [1] 외부 아이템 데이터베이스 연동 (JSON 로드)
# ====================================================================
DEFAULT_ITEMS_JSON = {
    "WEAPON_NONE": {"name": "맨손", "power": 10, "type": "kinetic", "tier": 4},
    "WEAPON_SCRAP_01": {"name": "녹슨 고철 칼날", "power": 15, "type": "kinetic", "tier": 4},
    "PART_SCRAP_01": {"name": "녹슨 납땜 방열판", "power": 16, "type": "scrap", "tier": 4},
    "PART_SCRAP_02": {"name": "리사이클 저항 코일", "power": 15, "type": "cyber", "tier": 4},
    "ACCESSORY_SCRAP_01": {"name": "기계 괴수 냉각선 목걸이", "power": 15, "type": "scrap", "tier": 4},
    "ARMOR_SCRAP_01": {"name": "컴퓨터 본체 장갑", "power": 16, "type": "kinetic", "tier": 4},
    "PART_SCRAP_03": {"name": "드론 관절 이식 팔", "power": 17, "type": "scrap", "tier": 4},
    "DECK_SCRAP_01": {"name": "구형 신호 수신기", "power": 15, "type": "cyber", "tier": 4},
    "ARMOR_SCRAP_02": {"name": "와이어 결속 슬링 백팩", "power": 13, "type": "scrap", "tier": 4},
    "ACCESSORY_SCRAP_02": {"name": "기업 보안 칩셋 인장 반지", "power": 14, "type": "cyber", "tier": 4},
    "WEAPON_TEST_T2": {"name": "바이오 코어 리퍼 나이프", "power": 95, "type": "kinetic", "tier": 2},
    "WEAPON_TEST_T1": {"name": "아라사카 나노 레이저 카타나", "power": 180, "type": "kinetic", "tier": 1}
}

ITEMS_DB = {}

def init_and_load_items_db():
    global ITEMS_DB
    json_file_path = "items.json"
    if not os.path.exists(json_file_path):
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_ITEMS_JSON, f, ensure_ascii=False, indent=4)
            
    with open(json_file_path, "r", encoding="utf-8") as f:
        ITEMS_DB = json.load(f)

init_and_load_items_db()

# ====================================================================
# [1-2] 데이터베이스 & 아스키 아트 및 서사 데이터
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

AMBIENT_LORE = [
    "멀리서 거대한 기계가 갈리는 듯한 쇳소리가 울려 퍼집니다. 데드존의 포식자들이 배회하고 있습니다.",
    "발밑에서 바스라진 구시대의 메인보드가 먼지로 흩어집니다. 과거 인류의 유산은 이제 쓰레기에 불과합니다.",
    "하늘은 짙은 수은 안개로 가려져 태양의 위치조차 알 수 없습니다. 방사능 수치가 얕게 요동칩니다.",
    "지평선 너머로 5%의 특권층이 사는 가상 도시 '네오 아크'의 거대한 방벽이 아스라이 보입니다. 돌아갈 수는 없습니다.",
    "누군가 남긴 핏자국이 썩은 냉각수 웅덩이 속으로 이어져 있습니다. 스캐벤저의 말로는 항상 비참합니다.",
    "고장난 라디오 잔해에서 마스터 AI의 기계적인 찬송가 방송이 끊어지듯 흘러나옵니다.",
    "기계 괴수에게 찢겨나간 신원 미상의 의체 부품들이 녹슨 철골에 매달려 바람에 흔들립니다.",
    "바람을 타고 코를 찌르는 매연과 타버린 윤활유 냄새가 밀려옵니다. 이곳은 완전한 무법 지대입니다."
]

CONSUMABLES_DB = {
    "MED_PER_10": {"name": "소형 반창고 팩", "type": "hp", "val": 0.1, "is_percent": True},
    "MED_PER_50": {"name": "응급 지혈대", "type": "hp", "val": 0.5, "is_percent": True},
    "MED_PER_100": {"name": "나노 스팀팩", "type": "hp", "val": 1.0, "is_percent": True},
    "MED_FIX_100": {"name": "구형 진통제", "type": "hp", "val": 100, "is_percent": False},
    "MED_FIX_300": {"name": "군용 지혈제", "type": "hp", "val": 300, "is_percent": False},
    "MED_FIX_500": {"name": "합성 바이오 젤", "type": "hp", "val": 500, "is_percent": False},
    "MED_FIX_1000": {"name": "초고밀도 회복 앰플", "type": "hp", "val": 1000, "is_percent": False},
    "FOOD_ONLY": {"name": "건조 단백질 블록", "type": "food", "hunger": 30, "thirst": 0},
    "FOOD_BOTH": {"name": "수분 함유 전투식량", "type": "food", "hunger": 40, "thirst": 20},
    "WATER_ONLY": {"name": "탁한 정수 팩", "type": "water", "hunger": 0, "thirst": 30},
    "WATER_BOTH": {"name": "미네랄 보충수", "type": "water", "hunger": 20, "thirst": 40},
}

SESSIONS_DB = [
    {
        "title": "녹슨 잔해 더미의 조우",
        "text": "무너진 거대 정찰 드론의 장갑판 아래에서 미세한 전력 반응이 감지됩니다.\n잔해 밑에 무언가 쓸만해 보이는 부품이 짓눌려 있습니다.",
        "choices": [
            {"text": "장갑판을 완력으로 밀어내고 파이프를 뽑아낸다.", "weight": "kinetic", "reward": "WEAPON_SCRAP_01", "log": "[처리] 거친 강철 비명소리와 함께 무기를 적출했습니다."},
            {"text": "구리 와이어와 방열판 배선을 정밀하게 해체한다.", "weight": "scrap", "reward": "PART_SCRAP_01", "log": "[처리] 손끝에 기름때와 스파크가 튑니다. 유용한 부품을 얻었습니다."},
            {"text": "사이버덱을 패널에 연결해 백도어를 주입한다.", "weight": "cyber", "reward": "PART_SCRAP_02", "log": "[처리] 네온빛 데이터 스트림이 흐릅니다. RAM 가용량을 확보하며 부품을 복제합니다."}
        ]
    },
    {
        "title": "오염된 오아시스 필터링",
        "text": "터진 냉각수 파이프 아래 화학 웅덩이를 발견했습니다.\n독성이 강하지만 갈증을 해결할 수단이 될지 모릅니다.",
        "choices": [
            {"text": "방사능 저항을 믿고 필터 없이 무식하게 들이켠다.", "weight": "kinetic", "reward": None, "thirst": 40, "hp_loss": 100, "log": "[처리] 식도가 타들어 가는 통증을 신체의 내구력으로 압도합니다."},
            {"text": "고철 캔과 필터 유닛을 결합해 정제 펌프를 급조한다.", "weight": "scrap", "reward": "ACCESSORY_SCRAP_01", "thirst": 30, "hp_loss": 0, "log": "[처리] 탁한 폐액이 에메랄드빛 연료로 안전하게 정제됩니다."},
            {"text": "제어 노드를 해킹해 상층부의 순수 보충수를 방출시킨다.", "weight": "cyber", "reward": None, "thirst": 50, "hp_loss": 0, "ram_bonus": 1, "log": "[처리] 시스템 보안을 해제하자 깨끗한 물이 쏟아집니다. 시스템 제어력이 상승합니다."}
        ]
    },
    {
        "title": "스캐브 드론 사체의 독식",
        "text": "방금 전 과열로 추락한 총괄국의 '스캐브 드론'을 발견했습니다.\n내부 코어는 아직 살아있으며 값어치 있는 부품을 품고 있습니다.",
        "choices": [
            {"text": "둔기로 중추 회로를 박살 내고 장갑판을 찢어발긴다.", "weight": "kinetic", "reward": "ARMOR_SCRAP_01", "log": "[처리] 파괴적인 충격음과 함께 고밀도 방어 자산을 무력으로 적출했습니다."},
            {"text": "렌즈 유닛과 서보 모터 축을 상하지 않게 정밀 분해한다.", "weight": "scrap", "reward": "PART_SCRAP_03", "log": "[처리] 복잡한 서보 모터가 완벽한 부품 형태로 손에 쥐어집니다."},
            {"text": "안테나 포트에 패킷을 주입해 맵 데이터를 흡수한다.", "weight": "cyber", "reward": "DECK_SCRAP_01", "log": "[처리] 안개 속에 가려진 유령 노드들의 데이터가 사이버덱을 가득 채웁니다."}
        ]
    },
    {
        "title": "쓰러진 선행 생존자의 민낯",
        "text": "하반신이 가시철사에 짓눌린 스캐벤저 생존자가 보입니다.\n그의 허리춤에는 자원이 가득 든 고철 배낭이 단단히 묶여 있습니다.",
        "choices": [
            {"text": "머리를 내리쳐 숨통을 끊고 자원을 강탈한다.", "weight": "kinetic", "reward": "SCRAP_MAT", "log": "[처리] 자비는 없습니다. 동족의 육체에서 흘러나온 연료가 의체로 흡수됩니다."},
            {"text": "철사를 끊어 구출해주고 자원을 분배받는다.", "weight": "scrap", "reward": "ARMOR_SCRAP_02", "log": "[처리] 피 묻은 배낭을 건네받습니다. 메마른 데드존에 아날로그적 신뢰가 미세하게 싹틉니다."},
            {"text": "소켓에 웜을 심어 마비시키고 보안 코드를 가로챈다.", "weight": "cyber", "reward": "ACCESSORY_SCRAP_02", "log": "[처리] 그가 잠든 사이, 데이터의 소유권이 당신의 덱으로 조용히 복사됩니다."}
        ]
    },
    {
        "title": "녹슨 방전 벙커의 문",
        "text": "쓰레기 바다 지하 깊숙한 곳, 푸른 전류가 흐르는 구시대 군용 벙커를 발견했습니다.\n이곳을 장악하면 최초의 은신처를 선언할 수 있습니다.",
        "choices": [
            {"text": "철근을 지렛대 삼아 완력으로 문을 뜯어발긴다.", "weight": "kinetic", "log": "[처리] 강철 문이 굉음과 함께 찢겨 나갑니다. 육체의 무력이 강철의 질서를 압도합니다."},
            {"text": "배선 패널을 열고 구리 와이어로 회로를 쇼트시킨다.", "weight": "scrap", "log": "[처리] 스파크가 튀며 타버린 논리 회로가 당신의 물리적 조작에 굴복합니다."},
            {"text": "사이버덱을 직결하여 방화벽 취약 노드에 백도어를 주입한다.", "weight": "cyber", "log": "[처리] 차가운 데이터 스트림이 벙커의 낡은 방화벽 프로토콜을 무력화합니다."}
        ]
    }
]

# ====================================================================
# [2] 정돈된 UI 출력 유틸리티
# ====================================================================
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
    lore = random.choice(AMBIENT_LORE)
    print(f"\n[환경 로그] {lore}")
    input("\n[계속하려면 엔터 키를 누르십시오...] ")

# ====================================================================
# [3] 아이템 파밍 주사위 헬퍼
# ====================================================================
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
        
        self.consumables = {k: 0 for k in CONSUMABLES_DB.keys()}
        self.consumables["FOOD_ONLY"] = 2
        self.consumables["WATER_ONLY"] = 2
        self.consumables["MED_FIX_100"] = 1
        
        self.weights = {"kinetic": 0, "scrap": 0, "cyber": 0}
        
        # 스케일링 체감을 위해 시작 인벤토리에 고티어 장비 지급
        self.inventory = ["WEAPON_TEST_T2", "WEAPON_TEST_T1"]
        self.equipment = {"weapon": "WEAPON_NONE"}

    def get_highest_tier(self):
        if self.equipment["weapon"] in ITEMS_DB:
            return ITEMS_DB[self.equipment["weapon"]].get("tier", 4)
        return 4

    def to_dict(self):
        return {
            "hp": self.hp, "hunger": self.hunger, "thirst": self.thirst,
            "max_ram": self.max_ram, "dex": self.dex, "materials": self.materials,
            "consumables": self.consumables, "weights": self.weights,
            "inventory": self.inventory, "equipment": self.equipment
        }
        
    def from_dict(self, data):
        self.hp = data.get("hp", 1500)
        self.hunger = data.get("hunger", 100)
        self.thirst = data.get("thirst", 100)
        self.max_ram = data.get("max_ram", 4)
        self.dex = data.get("dex", 10)
        self.materials = data.get("materials", 0)
        self.consumables = data.get("consumables", {k: 0 for k in CONSUMABLES_DB.keys()})
        self.weights = data.get("weights", {"kinetic": 0, "scrap": 0, "cyber": 0})
        self.inventory = data.get("inventory", [])
        self.equipment = data.get("equipment", {"weapon": "WEAPON_NONE"})

    def get_attack_power(self):
        return ITEMS_DB[self.equipment["weapon"]]["power"]

    def consume_resources(self):
        self.hunger = max(0, self.hunger - 5)
        self.thirst = max(0, self.thirst - 6)
        
        if self.hunger == 0 or self.thirst == 0:
            self.hp -= 50
            print("\n[SYSTEM WARN] 신체 연료 고갈. 바이오 조직 괴사가 시작됩니다. (HP -50)")
            time.sleep(1)
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
            print(f"  💽 {scale_log}")
            print("+" + "-"*76 + "+")
        
        print(f"  [생명력] {display_hp:,} / {display_max_hp:,}    [허기] {self.hunger:3d} / 100      [갈증] {self.thirst:3d} / 100")
        
        wpn_name = ITEMS_DB[self.equipment['weapon']]['name']
        wpn_pwr = self.get_attack_power()
        print(f"  [장착 무기] {wpn_name:<15} (T={tier} 위력: {wpn_pwr:<3d})        [가용 RAM] {self.max_ram}")
        print_divider()
        
        food_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB[k]["type"]=="food")
        water_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB[k]["type"]=="water")
        med_cnt = sum(v for k,v in self.consumables.items() if CONSUMABLES_DB[k]["type"]=="hp")
        
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
                    item = ITEMS_DB.get(item_id)
                    if item:
                        print(f"  [{i+1}] {equip_mark}{item['name']} (위력: {item['power']} | T={item.get('tier',4)})")
            
            print_divider()
            print("[ 명령 프로토콜 ]")
            print("  1. 장비 소켓 결속 (무기 교체)")
            print("  2. 소모품 주입/섭취 시스템 (생존 관리)")
            print("  3. 불필요 장비 분해 (고철 추출)")
            print("  0. 탐색망으로 복귀")
            
            cmd = input("\n명령어 입력: ")
            
            if cmd == "1":
                if not self.inventory:
                    print("\n[알림] 교체할 장비가 없습니다.")
                    time.sleep(1)
                    continue
                choice = input("장착할 아이템 번호: ")
                if choice.isdigit() and 0 < int(choice) <= len(self.inventory):
                    item = self.inventory[int(choice)-1]
                    self.equipment["weapon"] = item
                    print(f"\n[처리] '{ITEMS_DB[item]['name']}'을(를) 시스템 소켓에 결속했습니다.")
                    time.sleep(1)
                    
            elif cmd == "2":
                self.use_consumable_menu()
                
            elif cmd == "3":
                if not self.inventory:
                    print("\n[알림] 분해할 장비가 없습니다.")
                else:
                    choice = input("분해하여 고철로 변환할 아이템 번호: ")
                    if choice.isdigit() and 0 < int(choice) <= len(self.inventory):
                        idx = int(choice) - 1
                        item_id = self.inventory[idx]
                        if self.equipment["weapon"] == item_id:
                            print("\n[거부] 시스템 소켓에 결속 중인 장비는 분해할 수 없습니다.")
                        else:
                            self.inventory.pop(idx)
                            gained_scrap = random.randint(15, 30)
                            self.materials += gained_scrap
                            print(f"\n[처리] '{ITEMS_DB[item_id]['name']}'을(를) 분쇄하여 일반 고철 {gained_scrap}개를 추출했습니다.")
                time.sleep(1.5)
                
            elif cmd == "0":
                break

    def use_consumable_menu(self):
        clear_screen()
        print_header("소모품 시스템 관리")
        
        avail = [k for k, v in self.consumables.items() if v > 0]
        if not avail:
            print("[알림] 현재 사용 가능한 소모품이 인벤토리에 없습니다.")
            time.sleep(1.5)
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
        cmd = input("\n사용할 아이템 번호: ")
        
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
            time.sleep(1.5)

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
        with open("stigma_save.json", "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        print("\n[SYSTEM] 현재 동기화 로그가 로컬 환경에 안전하게 백업되었습니다.")
    except Exception as e:
        print(f"\n[SYSTEM ERR] 백업 실패: {e}")
    time.sleep(1.5)

# ====================================================================
# [5] 전투 시스템 (🔥 타격감 및 UI 피드백 순서 전면 개선)
# ====================================================================
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
            print(f"  💽 {scale_log}")
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
        
        try: cmd = input("\n명령 코드 입력 (1-4): ")
        except: sys.exit()
            
        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                learning_index += 3
                action_logs.append("[경고] 동일 공격 반복 감지. 보스가 궤적을 딥러닝 중입니다. (E +3)")
            
            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            
            # 1. 대미지 연산 및 출력
            dmg = max(100, math.floor(player.get_attack_power() * penalty * 100) - e_def + random.randint(-50, 50))
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)
            
            print(f"\n 💥 콰아앙! 무기가 적의 장갑판을 관통했습니다! (피해량: {disp_dmg:,})")
            time.sleep(1.2)
            
            # 2. HP 차감 및 결과 출력
            hp = max(0, hp - dmg)
            _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
            print(f" 📉 [시스템 갱신] {name}의 잔여 체력: {disp_ehp_new:,}")
            time.sleep(1.2)
            
            action_logs.append(f"[타격] 적에게 {disp_dmg:,}의 피해를 입혔습니다.")

        elif cmd == "2":
            consecutive_attacks = 0
            learning_index = max(0, learning_index - 4)
            atk = int(atk * 0.5)
            
            print("\n 🛡️ 급조 바리케이드 전개! 적의 분석 궤적을 방해합니다.")
            time.sleep(1.2)
            action_logs.append("[방어] 바리케이드 전개. 다음 공격의 피해를 반감시킵니다.")

        elif cmd == "3":
            if player.max_ram >= 2:
                consecutive_attacks = 0
                learning_index = 0
                player.max_ram -= 2
                
                print("\n 💻 교란 신호 방출! 보스의 센서 데이터가 초기화됩니다. (RAM -2)")
                time.sleep(1.2)
                action_logs.append("[해킹] 교란 신호 성공. 적 분석 지수를 초기화했습니다.")
            else: 
                print("\n ❌ [오류] 시스템 RAM 가용량이 부족합니다.")
                time.sleep(1.2)
                action_logs.append("[오류] RAM 부족으로 해킹에 실패했습니다.")
                
        elif cmd == "4":
            if is_boss:
                print("\n 🚫 [거부] 보스전에서는 후퇴할 수 없습니다. 거점을 사수하십시오.")
                time.sleep(1.2)
                action_logs.append("[거부] 탈출 실패. 적이 퇴로를 차단했습니다.")
            else:
                dex_bonus = max(0, player.dex - 10) * 2
                weights = [
                    60 + dex_bonus,             
                    max(0, 20 - dex_bonus/2),   
                    max(0, 10 - dex_bonus/4),   
                    max(0, 5 - dex_bonus/4),    
                    5 + dex_bonus/2             
                ]
                res = random.choices(["SAFE", "NORMAL", "1.5X", "2.0X", "LUCKY"], weights=weights, k=1)[0]
                
                escaped = True
                if res == "SAFE":
                    escape_log = "[탈출] 적의 사각을 파고들어 피해 없이 안전하게 이탈했습니다."
                elif res in ["NORMAL", "1.5X", "2.0X"]:
                    dmg_calc = atk if res == "NORMAL" else int(atk * 1.5) if res == "1.5X" else int(atk * 2.0)
                    _, disp_eatk, _ = apply_dynamic_scaling(dmg_calc, 0, tier)
                    
                    print(f"\n ⚠️ 후퇴 중 적에게 공격을 허용했습니다! (피해량: {disp_eatk:,})")
                    time.sleep(1.2)
                    
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(f" 🩸 [시스템 갱신] 내 체력이 {disp_php_new:,}(으)로 감소했습니다.")
                    time.sleep(1.2)
                    
                    if res == "NORMAL": escape_log = f"[탈출] 후퇴 중 적의 공격에 노출되었습니다. (피해: {disp_eatk:,})"
                    elif res == "1.5X": escape_log = f"[탈출] 치명적인 손상을 입으며 이탈했습니다. (피해: {disp_eatk:,})"
                    else: escape_log = f"[탈출 참사] 도주 중 의체 중심부가 관통당했습니다! (피해: {disp_eatk:,})"
                elif res == "LUCKY":
                    escape_log = "[기적적 탈출] 무사히 이탈하며 적 주변의 잔해에서 쓸만한 물자를 챙겼습니다."
                break
            
        else: 
            print("\n ❌ [오류] 인식할 수 없는 명령 프로토콜입니다.")
            time.sleep(1.0)
            action_logs.append("[오류] 잘못된 명령어 입력.")

        # --- 적의 턴 (반격 로직도 동일한 시각적 템포 적용) ---
        if hp > 0 and not escaped:
            _, disp_eatk, _ = apply_dynamic_scaling(atk, 0, tier)
            
            print(f"\n ⚠️ {name}의 무자비한 공격! (피해량: {disp_eatk:,})")
            time.sleep(1.2)
            
            player.hp -= atk
            _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
            print(f" 🩸 [시스템 갱신] 내 잔여 체력: {disp_php_new:,} / {disp_pmaxhp:,}")
            time.sleep(1.5)
            
            action_logs.append(f"[피격] 적의 공격으로 {disp_eatk:,}의 손상을 입었습니다.")
            
            if cmd == "2": atk = 180 if is_boss else 80

        turn += 1

    # --- 전투 종료 처리 ---
    if player.hp <= 0:
        clear_screen()
        if escaped: type_text(escape_log, 0.02)
        type_text("\n[SYSTEM FATAL] 신체 손상 100%. 의체 붕괴. GAME OVER.", 0.03)
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
                print(f"  [수집] 부품 '{ITEMS_DB[part]['name']}' 획득")
            elif loot_res == "WATER": 
                it = roll_water()
                player.consumables[it] += 1
                print(f"  [수집] {CONSUMABLES_DB[it]['name']} 1개 획득")
            elif loot_res == "FOOD": 
                it = roll_food()
                player.consumables[it] += 1
                print(f"  [수집] {CONSUMABLES_DB[it]['name']} 1개 획득")
                
        time.sleep(2.5)
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
    time.sleep(2.5)
    return None

# ====================================================================
# [6] 메인 구동 엔진
# ====================================================================
def get_encounter_chance(player):
    hp_ratio = player.hp / player.max_hp
    base_chance = 0.10
    return base_chance + (0.25 * hp_ratio)

def run_game():
    clear_screen()
    print_header("PROTOCOL: STIGMA (1막: 낙인)")
    
    print("  1. 새로운 게임 (New Game)")
    has_save = os.path.exists("stigma_save.json")
    if has_save:
        print("  2. 동기화 복구 (Load Game)")
        
    ans = input("\n시스템 모드 선택: ")
    
    player = Player()
    grid = GameMap()

    if ans == "2" and has_save:
        try:
            with open("stigma_save.json", "r", encoding="utf-8") as f:
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
        
    time.sleep(1)

    while True:
        clear_screen()
        grid.draw()
        player.show_status()
        
        print(" [명령 프로토콜]")
        print("  W, A, S, D  : 그리드 이동")
        print("  F           : 현재 타일 탐색 및 자원 파싱")
        print("  I           : 인벤토리 및 시스템 정비")
        print("  C           : 현재 상태 로컬 백업 (저장)")
        print_divider()
        
        try: move = input("\n입력: ").strip().upper()
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
            time.sleep(1)
            
            encounter_chance = get_encounter_chance(player)
            roll = random.random()
            
            if roll <= encounter_chance: 
                print("\n[경고] 탐색 중 발생한 소음이 기계 괴수를 끌어들였습니다!")
                time.sleep(1.5)
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
                
                time.sleep(2)
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
                handle_session(player, SESSIONS_DB[4])
                combat_loop(player, is_boss=True) 
                run_ending(player)
                break
            elif current_loc in grid.event_locations:
                handle_session(player, SESSIONS_DB[grid.session_index])
                grid.event_locations.remove(current_loc)
                grid.session_index += 1
            else:
                if random.random() < get_encounter_chance(player):
                    print("\n[경보] 안개 속에서 기계 괴수의 광학 센서가 번뜩입니다!")
                    time.sleep(1)
                    grid.escaped_enemy_hp = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp)
                else:
                    if random.random() < 0.3:
                        print_ambient_lore()

def handle_session(player, session):
    clear_screen()
    print_header(session['title'])
    type_text(session['text'], 0.02)
    print()
    for i, choice in enumerate(session['choices']): 
        print(f"  [{i+1}] {choice['text']}")
    
    while True:
        try: ans = input("\n행동 선택 (1-3): ")
        except: sys.exit()
        if ans in ["1", "2", "3"]:
            choice_data = session['choices'][int(ans) - 1]
            player.weights[choice_data['weight']] += 1
            
            if "reward" in choice_data and choice_data["reward"]:
                if choice_data["reward"] == "SCRAP_MAT": player.materials += 30
                else: player.inventory.append(choice_data["reward"])
                    
            if "hp_loss" in choice_data: player.hp -= choice_data["hp_loss"]
            if "thirst" in choice_data: player.thirst = min(100, player.thirst + choice_data["thirst"])
            if "ram_bonus" in choice_data: player.max_ram += choice_data["ram_bonus"]
            
            print(f"\n{choice_data['log']}")
            time.sleep(2)
            break

def run_ending(player):
    clear_screen()
    print_header("PIONEER PROTOCOL: NORMALIZATION EXECUTION")
    type_text("거대한 기계 괴수가 스파크를 뿜으며 무릎을 꿇습니다.", 0.03)
    type_text("마스터 AI의 추적을 피해, 데드존의 벙커 터미널에 중앙 코어를 직결합니다.", 0.03)
    type_text("순간, 벙커 전체가 백색 빛으로 가득 차며 당신의 행위 로그가 스캔됩니다.\n", 0.03)
    
    total = sum(player.weights.values()) or 1
    w_k, w_s, w_c = player.weights['kinetic'], player.weights['scrap'], player.weights['cyber']
    
    time.sleep(1)
    print(f"  [분석] 컴뱃 포스 동기화율      : {w_k/total*100:.1f}%")
    print(f"  [분석] 메카니컬 테크 동기화율  : {w_s/total*100:.1f}%")
    print(f"  [분석] 넷 포스 동기화율        : {w_c/total*100:.1f}%\n")
    time.sleep(1)

    if w_k == w_s == w_c: 
        type_text("[히든 각성] 황금 분할의 조율사: 모든 노드가 교차 활성화됩니다.", 0.04)
    elif w_k >= w_s and w_k >= w_c: 
        type_text("[각성] 컴뱃 포스: 뼈를 깎는 무력의 집행자 코드가 신경망에 직결됩니다.", 0.04)
    elif w_s >= w_k and w_s >= w_c: 
        type_text("[각성] 메카니컬 테크: 고철의 연금술사 라이선스가 전이됩니다.", 0.04)
    else: 
        type_text("[각성] 넷 포스: 현실을 왜곡하는 아나키스트의 악성 웜 코드가 주입됩니다.", 0.04)
        
    type_text("\n\"당신은 마침내 시스템의 모순 구역 내부에 확고한 첫 영토를 개척해 냈습니다.\"", 0.05)
    print("\n" + "="*78)
    print(" 1막 [낙인] 클리어 (DEMO END) ".center(76))
    print("="*78)

if __name__ == "__main__":
    run_game()