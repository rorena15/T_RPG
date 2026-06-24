# player.py — Player 클래스
# 의존성: constants, core, ui, sys_log

import math
import random
import sqlite3
import sys
import constants
from core import get_equipment_data
from ui import (clear_screen, print_header, print_divider,
                safe_input, wait_for_keypress, read_key, ea_rpad)
from colorama import Fore, Style
from combat import apply_dynamic_scaling, get_turn_scale_multiplier
from quest import advance_quest
from sys_log import sys_log, track, log_error
from i18n import t
import sound

class Player:
    def __init__(self):
        # 기초 스탯 (VIT/INT_S/DEX) — 기획서 능력 체계 1절
        # int는 Python 예약어이므로 int_s(stat) 사용
        self.vit   = constants.STAT_DEFAULT_VIT
        self.int_s = constants.STAT_DEFAULT_INT
        self.dex   = constants.STAT_DEFAULT_DEX
        self.lv    = constants.STAT_DEFAULT_LV

        # HP/RAM은 스탯 파생값으로 초기화 (고정 하드코딩 제거)
        self.max_hp  = self.calc_max_hp()
        self.hp      = self.max_hp
        self.max_ram = self.calc_max_ram()
        self.hunger  = 100
        self.thirst  = 100
        self.alert_level = 0
        self.temp_weapon_uses: dict = {}
        self.job_class: str = ""          # combat / mech / net / balanced
        self.skill_slots: list = []       # 장착된 스킬 ID 목록 (최대 2)
        self.active_buffs: dict = {}      # 활성 버프 {skill_id: 잔여량}
        self.materials = 0
        self.reputation = 0 # 정식 공식 적용을 위한 밸런스 인자 기본 동기화

        self.consumables = {k: 0 for k in constants.CONSUMABLES_DB.keys()}
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
        self.equipment = {k: v for k, v in constants.SLOT_DEFAULTS.items()}
        self.diary = []
        self.active_quest = None


    # ----------------------------------------------------------------
    # 기초 스탯 파생 메서드 (기획서: RPG 핵심 연산 시스템.md)
    # ----------------------------------------------------------------
    def calc_max_hp(self):
        """VIT 기반 최대 HP 파생.
        MaxHP = STAT_HP_BASE + (Lv*STAT_HP_LV) + (VIT*STAT_HP_VIT) + floor(f(VIT)*STAT_HP_fVIT)
        VIT=10, Lv=1 기준 ≈ 1480
        """
        import math
        return (constants.STAT_HP_BASE
                + (self.lv * constants.STAT_HP_LV)
                + (self.vit * constants.STAT_HP_VIT)
                + math.floor(constants.f_A(self.vit) * constants.STAT_HP_fVIT))

    def calc_def_base(self):
        """VIT 기반 기본 방어력 파생.
        DEF_base = (Lv*STAT_DEF_LV) + (VIT*STAT_DEF_VIT) + floor(f(VIT)*STAT_DEF_fVIT)
        VIT=10, Lv=1 기준 = 27
        """
        import math
        return ((self.lv * constants.STAT_DEF_LV)
                + (self.vit * constants.STAT_DEF_VIT)
                + math.floor(constants.f_A(self.vit) * constants.STAT_DEF_fVIT))

    def calc_max_ram(self):
        """INT 기반 최대 RAM 파생.
        MaxRAM = 4 + floor(INT_S * STAT_RAM_INT)
        INT=10 기준 = 6
        """
        import math
        return 4 + math.floor(self.int_s * constants.STAT_RAM_INT)

    def calc_eva_rate(self):
        """DEX 기반 회피율 파생 (기획서 EVA 공식).
        EVA = min(0.50, (DEX*0.01) / (1 + DEX*0.01))
        DEX=10 => 9.1%, DEX=20 => 16.7%, 상한 50%
        전투 후퇴(ESCAPE) 선택 시 SAFE 확률 보정에 사용.
        """
        return min(0.50, (self.dex * 0.01) / (1 + self.dex * 0.01))

    def calc_crt_rate(self):
        """DEX 기반 치명타 확률 파생 (기획서 CRT 공식).
        CRT = min(0.75, (DEX*0.015) / (1 + DEX*0.015))
        DEX=10 => 13.0%, DEX=20 => 23.1%, 상한 75%
        공격(ATTACK) 시 1.5배 대미지 발동 확률.
        """
        return min(0.75, (self.dex * 0.015) / (1 + self.dex * 0.015))

    def calc_hunger_decay_rate(self):
        """VIT 기반 허기/갈증 소모 감쇄율 (기획서 R_decay 공식).
        R_decay = min(0.60, (VIT*0.01) / (1 + VIT*0.01))
        VIT=10 => 9.1% 감쇄 (5/턴 -> 4.55/턴)
        """
        return min(0.60, (self.vit * 0.01) / (1 + self.vit * 0.01))

    def get_highest_tier(self):
        item_data = get_equipment_data(self.equipment["main_weapon"])
        return item_data.get("tier", 4)

    def to_dict(self):
        return {
            "hp": self.hp, "max_hp": self.max_hp, "hunger": self.hunger, "thirst": self.thirst,
            "alert_level": self.alert_level,
            "temp_weapon_uses": self.temp_weapon_uses,
            "job_class": self.job_class,
            "skill_slots": self.skill_slots,
            "active_buffs": self.active_buffs,
            "vit": self.vit, "int_s": self.int_s, "dex": self.dex, "lv": self.lv,
            "max_ram": self.max_ram, "materials": self.materials,
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
        self.vit   = data.get("vit",   constants.STAT_DEFAULT_VIT)
        self.int_s = data.get("int_s", constants.STAT_DEFAULT_INT)
        self.dex   = data.get("dex",   constants.STAT_DEFAULT_DEX)
        self.lv    = data.get("lv",    constants.STAT_DEFAULT_LV)
        self.max_hp  = data.get("max_hp",  self.calc_max_hp())
        self.max_ram = data.get("max_ram", self.calc_max_ram())
        self.alert_level = data.get("alert_level", 0)
        self.temp_weapon_uses = data.get("temp_weapon_uses", {})
        self.job_class   = data.get("job_class", "")
        self.skill_slots = data.get("skill_slots", [])
        self.active_buffs = data.get("active_buffs", {})
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
        # VIT 기반 허기/갈증 감쇄율 적용 (기획서 R_decay 공식)
        r_decay = self.calc_hunger_decay_rate()
        self.hunger = max(0, self.hunger - max(1, round(5 * (1 - r_decay))))
        self.thirst = max(0, self.thirst - max(1, round(6 * (1 - r_decay))))
        sound.check_survival_alert(self.hunger, self.thirst)
        if self.hunger == 0 or self.thirst == 0:
            self.hp -= 50
            print(f"\n{Fore.YELLOW + Style.BRIGHT}" + t('resource_depleted') + Style.RESET_ALL)
            wait_for_keypress()
            if self.hp <= 0:
                print(f"\n{Fore.RED + Style.BRIGHT}" + t('resource_fatal'))
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
        diff_label = t(f'diff_label_{self.difficulty}') if self.difficulty in ('easy', 'normal', 'hard') else self.difficulty
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

        food_cnt = sum(v for k,v in self.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type")=="food")
        water_cnt = sum(v for k,v in self.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type")=="water")
        med_cnt = sum(v for k,v in self.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type")=="hp")

        print(t('status_items_line', med=med_cnt, food=food_cnt, water=water_cnt, scrap=self.materials))
        if self.active_quest:
            q = self.active_quest
            turns_left = max(0, q["deadline"] - self.turn_count)
            print_divider()
            print(t('status_quest_line', title=q['title'], progress=q['progress'], target=q['target'], turns=turns_left))
        print_divider()
        print()

    def manage_inventory(self):
        slot_keys = list(constants.SLOT_DISPLAY.keys())

        while True:
            clear_screen()
            print_header(t('inv_header'))

            print(t('inv_slot_header'))
            print_divider()
            for si, sk in enumerate(slot_keys, 1):
                label = ea_rpad(constants.SLOT_DISPLAY[sk], 8)
                eid = self.equipment.get(sk)
                if eid and eid != "WEAPON_NONE":
                    d = get_equipment_data(eid)
                    tag = constants.TIER_TAGS.get(d.get("tier", 4), "T?    ")
                    print(f"   [{si:2d}] {label}  │  ★  {d['name'][:22]}    {tag}  위력:{d['power']:>4}")
                else:
                    print(f"   [{si:2d}] {label}  │  " + t('inv_not_equipped'))
            print()

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
                    label = constants.SLOT_DISPLAY.get(sk, sk)
                    print(f"   ── {label} {'─' * max(2, 56 - len(label) * 2)}")
                    for n, iid, d in items:
                        equipped = (self.equipment.get(sk) == iid)
                        mark = "★" if equipped else " "
                        tag = constants.TIER_TAGS.get(d.get("tier", 4), "T?    ")
                        w = d.get("slot_weight", 1.0)
                        print(f"   [{n:2d}] {mark}  {d['name'][:26]:<26}  {tag}  위력:{d['power']:>4}  W:{w:.1f}")
            print_divider()

            print(t('inv_cmd_header'))
            print(t('inv_cmd_line1'))
            print(t('inv_cmd_line2'))
            print(t('inv_cmd_line3'))
            print_divider()
            try:
                cmd = safe_input(t('inv_prompt')).strip().upper()
            except Exception as _e:
                log_error(_e, "manage_inventory/DEV_GRANT_LEGACY")
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
                        print(t('inv_equipped', name=d['name'], slot=constants.SLOT_DISPLAY.get(sk, sk)))
                        if prev and prev != "WEAPON_NONE":
                            pd = get_equipment_data(prev)
                            print(t('inv_replaced', name=pd['name']))
                    else:
                        print(t('inv_invalid_number'))
                else:
                    print(t('inv_equip_usage'))
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
                            print(t('inv_unequipped', name=d['name'], slot=constants.SLOT_DISPLAY[sk]))
                        else:
                            print(t('inv_slot_empty', slot=constants.SLOT_DISPLAY[sk]))
                    else:
                        print(t('inv_slot_range', max=len(slot_keys)))
                else:
                    print(t('inv_unequip_usage'))
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

            elif cmd == "DEV_GRANT_LEGACY":
                conn = sqlite3.connect("stigma_data.db")
                cursor = conn.cursor()
                cursor.execute("SELECT item_id, name FROM equipment WHERE item_id IN ('WEAPON_LEGACY_01','DECK_LEGACY_01')")
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
            item = constants.CONSUMABLES_DB[key]
            desc = ""
            if item["type"] == "hp":
                if item["is_percent"]: desc = t('consumable_hp_percent', pct=int(item['val'] * 100))
                else: desc = t('consumable_hp_fixed', val=item['val'])
            elif item["type"] in ["food", "water"]:
                hunger_str = t('consumable_hunger', val=item['hunger']) if item['hunger'] > 0 else ""
                thirst_str = t('consumable_thirst', val=item['thirst']) if item['thirst'] > 0 else ""
                desc = hunger_str + thirst_str

            print(t('consumable_item_line', idx=i+1, name=item['name'], owned=self.consumables[key], desc=desc))

        print_divider()
        print(t('consumable_back'))
        cmd = read_key()

        if cmd.isdigit() and 0 < int(cmd) <= len(avail):
            key = avail[int(cmd)-1]
            item = constants.CONSUMABLES_DB[key]
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
