# combat.py — 전투 시스템
# 의존성: constants, core, ui, sys_log

import math
import random
import sys
import time
import constants
from colorama import Fore, Back, Style
from core import get_equipment_data
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, safe_input, read_key, log_diary,
                _log_color, roll_medkit, roll_food, roll_water)
import skills as _skills
from quest import advance_quest
from sys_log import sys_log, track, log_error

_NAIWPN_ID = "NEOARC_AI_WPN"

def _neoarc_decay(player, used: bool):
    """네오 아크 AI 화기 내구도 감소. 이번 전투에서 사용했을 때만 차감하고, 0 도달 시 파기."""
    if not used or _NAIWPN_ID not in player.inventory:
        return
    player.temp_weapon_uses[_NAIWPN_ID] = player.temp_weapon_uses.get(_NAIWPN_ID, 2) - 1
    remaining = player.temp_weapon_uses[_NAIWPN_ID]
    if remaining <= 0:
        player.inventory.remove(_NAIWPN_ID)
        del player.temp_weapon_uses[_NAIWPN_ID]
        print(f"\n  {Fore.RED + Style.BRIGHT}[경고] 죽은 AI의 서비스 화기 — 열손상 임계 초과. 자동 파기됨.{Style.RESET_ALL}")
    else:
        print(f"\n  {Fore.YELLOW}[화기 상태] 죽은 AI의 서비스 화기 — 잔여 내구: {remaining}전투{Style.RESET_ALL}")


def apply_dynamic_scaling(raw_dmg, raw_hp, highest_equip_tier):
    if highest_equip_tier >= 4:
        return int(raw_dmg), int(raw_hp), ""
    elif highest_equip_tier in [2, 3]:
        return int(raw_dmg * 100), int(raw_hp * 10), "[SYSTEM: 전술 동기화 가동] 시각 피질의 정보 처리량이 가속됩니다."
    else: 
        return int(raw_dmg * 100000), int(raw_hp * 100), "[WARNING: HUD 글리치 발생] 시스템 연산 한계 돌파. 신격 스케일링 개방."


def get_turn_scale_multiplier(player):
    """진행 턴수와 난이도에 따른 적 스탯 배율을 계산한다. 플레이어 체력이 위험 수준이면 완화한다."""
    rate = constants.DIFFICULTY_SCALING_RATE.get(player.difficulty, constants.DIFFICULTY_SCALING_RATE["normal"])
    growth = player.turn_count * rate

    hp_ratio = player.hp / player.max_hp if player.max_hp > 0 else 1.0
    if hp_ratio < constants.LOW_HP_RELIEF_THRESHOLD:
        growth *= constants.LOW_HP_RELIEF_FACTOR

    return 1.0 + growth


@track
def combat_loop(player, is_boss=False, current_hp=None, enemy_type="drone"):
    scale_mult = get_turn_scale_multiplier(player)
    boss_max_hp = 0
    phase2_triggered = False

    if is_boss:
        name, e_def, base_atk, hp = "스캐브 컬렉터 [BOSS]", 45, 400, 35000
        art, header_title = constants.ENEMY_ART["BOSS"], "SYSTEM ALERT: 숙청 시퀀스 가동"
        base_atk = int(base_atk * scale_mult)
        hp = int(hp * scale_mult)
        boss_max_hp = hp
        atk = base_atk
        player.alert_level = min(100, player.alert_level + 60)
    elif enemy_type == "bio_hound":
        name, e_def, base_atk, hp = "바이오 하운드 [변이체]", 15, 250, 16000
        art, header_title = constants.ENEMY_ART["BIOHOUND"], "ENCOUNTER: 생물형 기계 괴수"
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp = current_hp
            name = "상처입은 바이오 하운드"
            header_title = "ENCOUNTER: 추적된 변이체"
        else:
            hp = int(random.randint(12000, 22000) * scale_mult)
        atk = base_atk
        player.alert_level = min(100, player.alert_level + 30)
    else:
        name, e_def, base_atk, hp = "오염된 스캐브 드론", 5, 200, 12000
        art, header_title = constants.ENEMY_ART["NORMAL"], "ENCOUNTER: 포식자 조우"
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp = current_hp
            name = "상처입은 스캐브 드론"
            header_title = "ENCOUNTER: 추적된 개체"
        else:
            hp = int(random.randint(8000, 16000) * scale_mult)
        atk = base_atk
        player.alert_level = min(100, player.alert_level + 15)

    # ── 보조 화기 — 네오 아크 AI 폐기 화기 전용 ─────────────────────────
    _NAIWPN = "NEOARC_AI_WPN"
    sub_wpn_power = 100
    sub_wpn_name  = "죽은 AI의 서비스 화기"
    sub_charges    = 2 if _NAIWPN in player.inventory else 0
    sub_wpn_used   = False  # 이 전투에서 사용 여부 (전투 종료 시 내구도 차감 판정)

    combat_ctx = {"skip_enemy_attack": False}  # skills 모듈이 턴마다 갱신

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
    # 기초 스탯 파생 지표 (VIT/DEX 기반)
    stat_def     = player.calc_def_base()      # VIT → 기본 방어력
    stat_eva     = player.calc_eva_rate()      # DEX → 회피율 (후퇴 SAFE 보정)
    stat_crt     = player.calc_crt_rate()      # DEX → 치명타 확률 (공격 1.5배)
    total_def    = e_def + stat_def + def_bonus  # 적 방어 + 플레이어 방어 합산 → 플레이어가 받는 피해 감소에 사용
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
        if sub_charges > 0:
            print(f"  {Fore.MAGENTA + Style.BRIGHT}6. 보조 화기 투입 [{sub_wpn_name}] — {sub_charges}발 잔여 (RAM 2 소모, 과부하 단기 사격){Style.RESET_ALL}")
        if player.skill_slots:
            for _i, _sid in enumerate(player.skill_slots):
                _sk = _skills.SKILL_DEFS.get(_sid, {})
                print(f"  {Fore.YELLOW + Style.BRIGHT}S{'12'[_i] if len(player.skill_slots) > 1 else ''}. {_sk.get('name','?')} — {_sk.get('desc','')}{Style.RESET_ALL}")

        cmd = read_key()

        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                if _skills.is_learning_blocked(player):
                    action_logs.append("[패턴 차단] 보스 딥러닝 신호 차단 — E 증가 무효!")
                else:
                    e_gain = max(0, 3 - e_suppress)
                    learning_index += e_gain
                    if e_suppress > 0:
                        action_logs.append(f"[경고] 동일 공격 반복. 사이버덱이 학습 신호를 교란합니다. (E +{e_gain})")
                    else:
                        action_logs.append(f"[경고] 동일 공격 반복. 보스가 궤적을 딥러닝 중입니다. (E +{e_gain})")

            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            f_multiplier = 1.0 + (player.reputation / 2000) * 1
            effective_power = player.get_attack_power() + gear_atk
            atk_mult = _skills.get_atk_mult(player)

            # 유압 분쇄: 배율 + 방어 관통
            hyd_mult, hyd_pierce = _skills.consume_hydraulic_crush(player, action_logs)
            eff_e_def = int(e_def * (1 - hyd_pierce))

            dmg = max(50, math.floor(effective_power * f_multiplier * penalty * atk_mult * hyd_mult * 50) - eff_e_def + random.randint(-25, 25))

            # 주파수 역추적 강제 치명타 / 고스트 치명타율 +30% / 신경 가속기 ×2 / DEX 기본 치명타
            forced_crit, st_mult = _skills.apply_signal_trace(player, combat_ctx, action_logs)
            ghost_crt  = player.active_buffs.pop("ghost_crt", 0.0)
            neural_mult = 2.0 if player.active_buffs.pop("neural_acc", 0) else 1.0
            if neural_mult > 1.0:
                action_logs.append("[신경 가속기] 시냅스 가속 — 치명타율 2배!")
            effective_crt = min(0.75, (stat_crt + ghost_crt) * neural_mult)
            if ghost_crt > 0:
                action_logs.append(f"[고스트 프로토콜] 치명타율 +{ghost_crt*100:.0f}%!")
            is_crit = forced_crit or random.random() < effective_crt
            crt_mult_used = st_mult if forced_crit else 1.5
            if is_crit and not forced_crit:
                action_logs.append(f"[치명타] DEX 반응속도 — 치명적 타격! (×{crt_mult_used})")
            if is_crit:
                dmg = math.floor(dmg * crt_mult_used)

            dmg = _skills.apply_outgoing_buffs(player, dmg, action_logs)  # 그리드 침투 +15%
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)
            crit_tag = Fore.YELLOW + Style.BRIGHT + " [CRITICAL!]" + Style.RESET_ALL if is_crit else ""

            print(f"\n  {Fore.GREEN + Style.BRIGHT}콰아앙! 무기가 적의 장갑판을 관통했습니다! (피해량: {disp_dmg:,}){crit_tag}")
            time.sleep(1)
            hp = max(0, hp - dmg)
            _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
            print(f"  [시스템 갱신] {name}의 잔여 체력: {disp_ehp_new:,}")
            time.sleep(1)
            _skills.on_attack_used(player, action_logs, dmg_dealt=dmg)
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
                # DEX 회피율 기반 후퇴 성공 가중치 (기획서 EVA 공식 연동)
                # stat_eva: DEX=10→9.1%, DEX=20→16.7%
                eva_bonus = stat_eva * 100   # % 단위로 환산
                weights = [
                    60 + eva_bonus,                      # SAFE: 기본 60% + EVA 보정
                    max(5, 20 - eva_bonus * 0.5),        # NORMAL: EVA 오를수록 감소
                    max(2, 10 - eva_bonus * 0.25),       # 1.5X
                    max(1, 5  - eva_bonus * 0.25),       # 2.0X
                    5  + eva_bonus * 0.5                 # LUCKY: DEX 높을수록 가끔 행운
                ]
                if player.active_buffs.pop("void_shift", 0):
                    res = "SAFE"
                    action_logs.append("[허공 전위] 탈출 경로 확정 — SAFE!")
                else:
                    res = random.choices(["SAFE", "NORMAL", "1.5X", "2.0X", "LUCKY"], weights=weights, k=1)[0]

                escaped = True
                if res == "SAFE":
                    escape_log = "[탈출] 적의 사각을 파고들어 피해 없이 안전하게 이탈했습니다."
                elif res in ["NORMAL", "1.5X", "2.0X"]:
                    dmg_calc = atk if res == "NORMAL" else int(atk * 1.5) if res == "1.5X" else int(atk * 2.0)
                    disp_dmg_calc, _, _ = apply_dynamic_scaling(dmg_calc, 0, tier)
                    print(f"\n  후퇴 중 적에게 공격을 허용했습니다! (피해량: {disp_dmg_calc:,})")
                    time.sleep(1)
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(f"  [시스템 갱신] 내 체력이 {disp_php_new:,}(으)로 감소했습니다.")
                    time.sleep(1)

                    if res == "NORMAL": escape_log = f"[탈출] 후퇴 중 적의 공격에 노출되었습니다. (피해: {disp_dmg_calc:,})"
                    elif res == "1.5X": escape_log = f"[탈출] 치명적인 손상을 입으며 이탈했습니다. (피해: {disp_dmg_calc:,})"
                    else: escape_log = f"[탈출 참사] 도주 중 의체 중심부가 관통당했습니다! (피해: {disp_dmg_calc:,})"
                elif res == "LUCKY":
                    escape_log = "[기적적 탈출] 무사히 이탈하며 적 주변의 잔해에서 쓸만한 물자를 챙겼습니다."
                break

        elif cmd == "5" and has_consumable:
            consecutive_attacks = 0
            avail = [k for k, v in player.consumables.items() if v > 0]
            print("\n[ 소모품 목록 ]")
            for i, key in enumerate(avail):
                item = constants.CONSUMABLES_DB[key]
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
                item = constants.CONSUMABLES_DB[key]
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

        elif cmd == "6" and sub_charges > 0:
            if player.max_ram >= 2:
                consecutive_attacks += 1
                if consecutive_attacks >= 2 and is_boss:
                    e_gain = max(0, 3 - e_suppress)
                    learning_index += e_gain
                sub_charges -= 1
                sub_wpn_used = True
                player.max_ram -= 2

                f_multiplier = 1.0 + (player.reputation / 2000)
                penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
                sub_dmg = max(75, math.floor((sub_wpn_power + gear_atk) * f_multiplier * penalty * 70) - e_def + random.randint(-25, 50))
                sub_dmg = _skills.apply_outgoing_buffs(player, sub_dmg, action_logs)

                is_crit = random.random() < stat_crt
                if is_crit:
                    sub_dmg = math.floor(sub_dmg * 1.5)
                    action_logs.append("[치명타] 보조 화기 치명 사격 발동! (×1.5)")

                disp_sub_dmg, _, _ = apply_dynamic_scaling(sub_dmg, 0, tier)
                crit_tag = Fore.YELLOW + Style.BRIGHT + " [CRITICAL!]" + Style.RESET_ALL if is_crit else ""
                charges_tag = f"잔여 {sub_charges}발" if sub_charges > 0 else "탄약 소진 — 보조 화기 열손상"
                print(f"\n  {Fore.MAGENTA + Style.BRIGHT}보조 화기 투입! [{sub_wpn_name}] 과부하 단기 사격! (피해: {disp_sub_dmg:,}){crit_tag}")
                time.sleep(1)
                hp = max(0, hp - sub_dmg)
                _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
                print(f"  [시스템 갱신] {name}의 잔여 체력: {disp_ehp_new:,}")
                time.sleep(1)
                action_logs.append(f"[보조 화기] {sub_wpn_name} — {disp_sub_dmg:,} 피해. {charges_tag}")
                time.sleep(1)
            else:
                print("\n  [오류] RAM 부족. 보조 화기를 투입할 수 없습니다.")
                time.sleep(0.5)
                action_logs.append("[오류] RAM 부족. 보조 화기 투입 실패.")

        elif cmd.upper() == "S" and player.skill_slots:
            slots = player.skill_slots
            consecutive_attacks = 0
            if len(slots) == 1:
                _skills.execute(player, slots[0], combat_ctx)
            else:
                print("\n  [S1] 또는 [S2] 를 입력하세요.")
                scmd = read_key()
                idx = 0 if scmd in ("s", "S", "1") else (1 if scmd == "2" else -1)
                if 0 <= idx < len(slots):
                    _skills.execute(player, slots[idx], combat_ctx)
                else:
                    action_logs.append("[취소] 스킬 입력 취소.")

            # 보조 스킬 직접 피해 처리 (junk_cannon, pulse_grenade)
            aux_dmg = combat_ctx.pop("aux_skill_dmg", 0)
            if aux_dmg > 0 and hp > 0:
                hp = max(0, hp - aux_dmg)
                disp_aux, _, _ = apply_dynamic_scaling(aux_dmg, 0, tier)
                _, disp_ehp_aux, _ = apply_dynamic_scaling(0, hp, tier)
                print(f"\n  {Fore.YELLOW + Style.BRIGHT}[스킬 직접 피해] {disp_aux:,}!{Style.RESET_ALL}")
                print(f"  [시스템 갱신] {name}의 잔여 체력: {disp_ehp_aux:,}")
                action_logs.append(f"[스킬] 직접 피해 {disp_aux:,}")
                time.sleep(0.8)
            # 펄스 수류탄 보스 E지수 감소
            if combat_ctx.pop("pulse_e_drain", False) and is_boss:
                learning_index = max(0, learning_index - 3)
                action_logs.append("[펄스 수류탄] 보스 패턴 학습 지수 -3")

        else:
            print("\n  [오류] 인식할 수 없는 명령 프로토콜입니다.")
            time.sleep(1)
            action_logs.append("[오류] 잘못된 명령어 입력.")

        # --- 적의 반격 ---
        if hp > 0 and not escaped and not combat_ctx.get("skip_enemy_attack"):
            # 페이즈 2 전환 후 방어가 풀리지 않도록 atk 재복구
            if cmd == "2":
                atk = int(base_atk * (1.6 if phase2_triggered else 1.0))

            # 데이터 사이펀 적 공격력 감소 + VIT/장비 방어 합산
            curr_atk = int(atk * _skills.get_enemy_atk_mult(player))
            dmg_taken = max(1, curr_atk - def_bonus - stat_def)
            dmg_taken = _skills.apply_incoming_buffs(player, dmg_taken, action_logs, combat_ctx)
            disp_dmg_taken, _, _ = apply_dynamic_scaling(dmg_taken, 0, tier)
            print(f"\n  {Fore.RED + Style.BRIGHT}{name}의 무자비한 공격! (피해량: {disp_dmg_taken:,})")
            time.sleep(1)
            player.hp -= dmg_taken
            if cyber_regen > 0 and player.hp > 0:
                player.hp = min(player.max_hp, player.hp + cyber_regen)
            _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
            print(f"  [시스템 갱신] 내 잔여 체력: {disp_php_new:,} / {disp_pmaxhp:,}")
            time.sleep(1)
            def_note = f" (방어 -{def_bonus})" if def_bonus > 0 else ""
            action_logs.append(f"[피격] 적의 공격으로 {disp_dmg_taken:,}의 손상을 입었습니다.{def_note}")
            time.sleep(1)

        combat_ctx["skip_enemy_attack"] = False   # 매 턴 리셋
        _skills.end_of_turn_tick(player, action_logs)
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
                print(f"  [수집] {constants.CONSUMABLES_DB[it]['name']} 1개 획득")
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
                print(f"  [수집] {constants.CONSUMABLES_DB[it]['name']} 1개 획득")
            elif loot_res == "FOOD":
                it = roll_food()
                player.consumables[it] += 1
                print(f"  [수집] {constants.CONSUMABLES_DB[it]['name']} 1개 획득")

        log_diary(player, f"[전투] {name} — 전술적 후퇴")
        _neoarc_decay(player, sub_wpn_used)
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
            print(f"  [파밍] 적의 파편에서 '{constants.CONSUMABLES_DB[it]['name']}' 1개를 적출했습니다.")
        elif drop_roll < 0.50:
            it = roll_water()
            player.consumables[it] += 1
            print(f"  [파밍] 적의 냉각 기관에서 '{constants.CONSUMABLES_DB[it]['name']}' 1개를 추출했습니다.")
        elif drop_roll < 0.60:
            it = roll_medkit()
            player.consumables[it] += 1
            print(f"  [파밍] 기적적으로 온전한 '{constants.CONSUMABLES_DB[it]['name']}' 1개를 회수했습니다.")
        else:
            player.materials += 20
            advance_quest(player, "scrap", 20)
            print("  [파밍] 고가치 일반 고철 20개를 회수했습니다.")

    advance_quest(player, "combat")
    log_diary(player, f"[전투] {name} — 제압 완료 (총 {player.enemies_defeated}기)")
    _neoarc_decay(player, sub_wpn_used)
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
