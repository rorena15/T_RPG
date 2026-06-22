# player.py — Player 클래스
# 의존성: constants, core, ui, sys_log

import sys
import math
import random
import sqlite3
import time
import constants
from colorama import Fore, Style
from core import get_equipment_data
from ui import (clear_screen, print_header, print_divider, type_text,
                safe_input, wait_for_keypress, read_key, log_diary,
                show_diary, ea_rpad)
from sys_log import sys_log, track


def _get_turn_scale_multiplier(player):
    rate = constants.DIFFICULTY_SCALING_RATE.get(player.difficulty, constants.DIFFICULTY_SCALING_RATE["normal"])
    growth = player.turn_count * rate
    hp_ratio = player.hp / player.max_hp if player.max_hp > 0 else 1.0
    if hp_ratio < constants.LOW_HP_RELIEF_THRESHOLD:
        growth *= constants.LOW_HP_RELIEF_FACTOR
    return 1.0 + growth


def _apply_dynamic_scaling(raw_dmg, raw_hp, highest_equip_tier):
    if highest_equip_tier >= 4:
        return int(raw_dmg), int(raw_hp), ""
    elif highest_equip_tier in [2, 3]:
        return int(raw_dmg * 100), int(raw_hp * 10), "[SYSTEM: 전술 동기화 가동] 시각 피질의 정보 처리량이 가속됩니다."
    else:
        return int(raw_dmg * 100000), int(raw_hp * 100), "[WARNING: HUD 글리치 발생] 시스템 연산 한계 돌파. 신격 스케일링 개방."


class Player:
    def __init__(self):
        self.hp = 1500
        self.max_hp = 1500
        self.hunger = 100
        self.thirst = 100
        self.max_ram = 4
        self.dex = 10
        self.materials = 0
        self.reputation = 0

        self.consumables = {k: 0 for k in constants.CONSUMABLES_DB.keys()}
        if "FOOD_ONLY" in self.consumables: self.consumables["FOOD_ONLY"] = 2
        if "WATER_ONLY" in self.consumables: self.consumables["WATER_ONLY"] = 2
        if "MED_FIX_100" in self.consumables: self.consumables["MED_FIX_100"] = 1

        self.weights = {"kinetic": 0, "scrap": 0, "cyber": 0}
        self.enemies_defeated = 0
        self.turn_count = 0
        self.difficulty = "normal"
        self.inventory = []
        self.equipment = {k: v for k, v in constants.SLOT_DEFAULTS.items()}
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
        self.consumables = data.get("consumables", {k: 0 for k in constants.CONSUMABLES_DB.keys()})
        self.weights = data.get("weights", {"kinetic": 0, "scrap": 0, "cyber": 0})
        self.inventory = data.get("inventory", [])
        raw_eq = data.get("equipment", {})
        if "weapon" in raw_eq and "main_weapon" not in raw_eq:
            raw_eq["main_weapon"] = raw_eq.pop("weapon")
        self.equipment = {k: raw_eq.get(k, v) for k, v in constants.SLOT_DEFAULTS.items()}
        self.turn_count = data.get("turn_count", 0)
        self.difficulty = data.get("difficulty", "normal")
        self.enemies_defeated = data.get("enemies_defeated", 0)
        self.diary = data.get("diary", [])
        self.active_quest = data.get("active_quest", None)

    def get_attack_power(self):
        item_data = get_equipment_data(self.equipment["main_weapon"])
        return item_data.get("power", 10)

    def get_armor_bonus(self):
        hp_b = 0; def_b = 0
        for slot in ("top", "bottom"):
            eid = self.equipment.get(slot)
            if eid:
                d = get_equipment_data(eid)
                hp_b  += d.get("power", 0) * 8
                def_b += d.get("power", 0) // 8
            else:
                hp_b  += 80
                def_b += 1
        return hp_b, def_b

    def get_gear_atk_bonus(self):
        ATKSLT = {"cyberdeck","cybernetic_parts","back_gear","face",
                  "footwear","necklace","ring","custom_part"}
        bonus = 0.0
        for sl in ATKSLT:
            eid = self.equipment.get(sl)
            if eid:
                d = get_equipment_data(eid)
                bonus += d.get("power", 0) * 0.4
            else:
                bonus += 5
        return int(bonus)

    def get_cyberdeck_e_suppress(self):
        eid = self.equipment.get("cyberdeck")
        if eid:
            d = get_equipment_data(eid)
            return min(2, d.get("power", 0) // 25)
        return 0

    def get_cyber_regen(self):
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
        _, display_hp, scale_log = _apply_dynamic_scaling(0, self.hp, tier)
        _, display_max_hp, _ = _apply_dynamic_scaling(0, self.max_hp, tier)

        print("  ╔" + "═" * 74 + "╗")
        print("  ║  " + ea_rpad("[ 내 의체 시스템 상태창 ]", 72) + "║")
        print("  ╚" + "═" * 74 + "╝")
        if scale_log:
            print(f"  {scale_log}")
            print_divider()

        hp_ratio = self.hp / self.max_hp if self.max_hp > 0 else 1.0
        hp_col = (Fore.GREEN + Style.BRIGHT) if hp_ratio > 0.6 else ((Fore.YELLOW + Style.BRIGHT) if hp_ratio > 0.3 else (Fore.RED + Style.BRIGHT))
        print(f"  [생명력] {hp_col}{display_hp:,}{Style.RESET_ALL} / {display_max_hp:,}    [허기] {self.hunger:3d} / 100      [갈증] {self.thirst:3d} / 100")

        item_data = get_equipment_data(self.equipment['main_weapon'])
        wpn_name = item_data['name']
        wpn_pwr = self.get_attack_power()
        gear_atk = self.get_gear_atk_bonus()
        hp_b, def_b = self.get_armor_bonus()

        print(f"  [장착 무기] {wpn_name:<15} (T={tier} 위력: {wpn_pwr:<3d})        [가용 평판] {self.reputation:+d}")
        if gear_atk > 0 or hp_b > 0 or def_b > 0:
            bonus_parts = []
            if gear_atk > 0: bonus_parts.append(f"공격력 +{gear_atk}")
            if hp_b   > 0: bonus_parts.append(f"HP +{hp_b}")
            if def_b  > 0: bonus_parts.append(f"방어 -{def_b}")
            print(f"  [장비 보너스] {' | '.join(bonus_parts)}")

        threat_mult = _get_turn_scale_multiplier(self)
        diff_label = {"easy": "이지", "normal": "노멀", "hard": "하드"}.get(self.difficulty, self.difficulty)
        print(f"  [진행 턴] {self.turn_count:>4d}   [난이도] {diff_label}   [적 위협 배율] x{threat_mult:.2f}")
        print_divider()

        food_cnt  = sum(v for k,v in self.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type")=="food")
        water_cnt = sum(v for k,v in self.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type")=="water")
        med_cnt   = sum(v for k,v in self.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type")=="hp")

        print(f"  [소지품] 회복약: {med_cnt} | 식량: {food_cnt} | 식수: {water_cnt} | 고철 자산: {self.materials}")
        if self.active_quest:
            q = self.active_quest
            turns_left = max(0, q["deadline"] - self.turn_count)
            print_divider()
            print(f"  [돌발 퀘스트] {q['title']}  ─  진행: {q['progress']}/{q['target']}  남은 기한: {turns_left}턴")
        print_divider()
        print()

    def manage_inventory(self):
        from quest import advance_quest  # 지연 임포트 (순환 참조 방지)
        slot_keys = list(constants.SLOT_DISPLAY.keys())

        while True:
            clear_screen()
            print_header("시스템 인벤토리 및 정비")

            print("  ▌ 장착 슬롯 현황")
            print_divider()
            for si, sk in enumerate(slot_keys, 1):
                label = ea_rpad(constants.SLOT_DISPLAY[sk], 8)
                eid = self.equipment.get(sk)
                if eid and eid != "WEAPON_NONE":
                    d = get_equipment_data(eid)
                    tag = constants.TIER_TAGS.get(d.get("tier", 4), "T?    ")
                    print(f"   [{si:2d}] {label}  │  ★  {d['name'][:22]}    {tag}  위력:{d['power']:>4}")
                else:
                    print(f"   [{si:2d}] {label}  │  ─  미장착")
            print()

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
                    label = constants.SLOT_DISPLAY.get(sk, sk)
                    print(f"   ── {label} {'─' * max(2, 56 - len(label) * 2)}")
                    for n, iid, d in items:
                        equipped = (self.equipment.get(sk) == iid)
                        mark = "★" if equipped else " "
                        tag = constants.TIER_TAGS.get(d.get("tier", 4), "T?    ")
                        w = d.get("slot_weight", 1.0)
                        print(f"   [{n:2d}] {mark}  {d['name'][:26]:<26}  {tag}  위력:{d['power']:>4}  W:{w:.1f}")
            print_divider()

            print("  [ 명령 ]")
            print("   E <번호>     : 장착 (슬롯 자동 인식)     U <슬롯번호>  : 슬롯 해제")
            print("   C            : 소모품 사용                D <번호>      : 분해 (고철 추출)")
            print("   0            : 탐색망으로 복귀")
            print_divider()
            try:
                cmd = safe_input("\n  명령어 입력: ").strip().upper()
            except:
                sys.exit()

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
                        print(f"\n  [결속] '{d['name']}' → {constants.SLOT_DISPLAY.get(sk, sk)} 슬롯에 장착되었습니다.")
                        if prev and prev != "WEAPON_NONE":
                            pd = get_equipment_data(prev)
                            print(f"  [교체] 기존 '{pd['name']}' 해제 — 인벤토리에 보관됩니다.")
                    else:
                        print("\n  [오류] 유효하지 않은 번호입니다.")
                else:
                    print("\n  [오류] 사용법: E <번호>  예) E 2")
                wait_for_keypress()

            elif cmd.startswith("U "):
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    si = int(parts[1])
                    if 1 <= si <= len(slot_keys):
                        sk = slot_keys[si - 1]
                        eid = self.equipment.get(sk)
                        if eid and eid != "WEAPON_NONE":
                            d = get_equipment_data(eid)
                            self.equipment[sk] = constants.SLOT_DEFAULTS[sk]
                            print(f"\n  [해제] '{d['name']}' — {constants.SLOT_DISPLAY[sk]} 슬롯 결속 해제되었습니다.")
                        else:
                            print(f"\n  [알림] {constants.SLOT_DISPLAY[sk]} 슬롯은 이미 비어 있습니다.")
                    else:
                        print(f"\n  [오류] 슬롯 번호는 1~{len(slot_keys)} 범위입니다.")
                else:
                    print("\n  [오류] 사용법: U <슬롯번호>  예) U 1 = 주무기 해제")
                wait_for_keypress()

            elif cmd == "C":
                self.use_consumable_menu()

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
            item = constants.CONSUMABLES_DB[key]
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
            item = constants.CONSUMABLES_DB[key]
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
