# combat.py — 전투 시스템
# 의존성: constants, core, ui, sys_log

import math
import random
import sys
import time
import constants
from colorama import Fore, Style
from core import get_equipment_data
from i18n import t
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, read_key, log_diary,
                _log_color, roll_medkit, roll_food, roll_water)
import skills as _skills
from quest import advance_quest
from sys_log import track

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
        print(Fore.RED + Style.BRIGHT + t('neoarc_destroyed') + Style.RESET_ALL)
    else:
        print(Fore.YELLOW + t('neoarc_status', remaining=remaining) + Style.RESET_ALL)


def apply_dynamic_scaling(raw_dmg, raw_hp, highest_equip_tier):
    if highest_equip_tier >= 4:
        return int(raw_dmg), int(raw_hp), ""
    elif highest_equip_tier in [2, 3]:
        return int(raw_dmg * constants.SCALE_MULT_T23_DMG), int(raw_hp * constants.SCALE_MULT_T23_HP), t('scale_log_t23')
    else:
        return int(raw_dmg * constants.SCALE_MULT_T01_DMG), int(raw_hp * constants.SCALE_MULT_T01_HP), t('scale_log_t01')


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
        name        = t('enemy_boss_name')
        header_title = t('enemy_boss_header')
        e_def, base_atk, hp = constants.BOSS_DEF, constants.BOSS_BASE_ATK, constants.BOSS_HP
        art = constants.ENEMY_ART["BOSS"]
        base_atk = int(base_atk * scale_mult)
        hp = int(hp * scale_mult)
        boss_max_hp = hp
        atk = base_atk
        player.alert_level = min(100, player.alert_level + constants.ALERT_INC_BOSS)
    elif enemy_type == "bio_hound":
        e_def, base_atk = constants.BIO_DEF, constants.BIO_BASE_ATK
        art = constants.ENEMY_ART["BIOHOUND"]
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp           = current_hp
            name         = t('enemy_bio_name_wounded')
            header_title = t('enemy_bio_header_wounded')
        else:
            hp           = int(random.randint(constants.BIO_HP_MIN, constants.BIO_HP_MAX) * scale_mult)
            name         = t('enemy_bio_name')
            header_title = t('enemy_bio_header')
        atk = base_atk
        player.alert_level = min(100, player.alert_level + constants.ALERT_INC_BIO)
    else:
        e_def, base_atk = constants.DRONE_DEF, constants.DRONE_BASE_ATK
        art = constants.ENEMY_ART["NORMAL"]
        base_atk = int(base_atk * scale_mult)
        if current_hp is not None:
            hp           = current_hp
            name         = t('enemy_drone_name_wounded')
            header_title = t('enemy_drone_header_wounded')
        else:
            hp           = int(random.randint(constants.DRONE_HP_MIN, constants.DRONE_HP_MAX) * scale_mult)
            name         = t('enemy_drone_name')
            header_title = t('enemy_drone_header')
        atk = base_atk
        player.alert_level = min(100, player.alert_level + constants.ALERT_INC_DRONE)

    # ── 보조 화기 — 네오 아크 AI 폐기 화기 전용 ─────────────────────────
    _NAIWPN = "NEOARC_AI_WPN"
    sub_wpn_power = constants.SUB_WPN_POWER
    sub_wpn_name  = t('sub_wpn_name')
    sub_charges    = 2 if _NAIWPN in player.inventory else 0
    sub_wpn_used   = False

    combat_ctx = {"skip_enemy_attack": False}

    turn = 1
    learning_index = 0
    consecutive_attacks = 0
    escaped = False
    escape_log = ""
    action_logs = [t('combat_encounter_alert', name=name)]

    hp_bonus, def_bonus = player.get_armor_bonus()
    gear_atk     = player.get_gear_atk_bonus()
    e_suppress   = player.get_cyberdeck_e_suppress()
    cyber_regen  = player.get_cyber_regen()
    stat_def     = player.calc_def_base()
    stat_eva     = player.calc_eva_rate()
    stat_crt     = player.calc_crt_rate()
    total_def    = e_def + stat_def + def_bonus
    if hp_bonus > 0:
        player.max_hp += hp_bonus
        player.hp = min(player.hp + hp_bonus, player.max_hp)

    while hp > 0 and player.hp > 0:
        if is_boss and turn > constants.BOSS_TURN_LIMIT:
            clear_screen()
            type_text(Fore.RED + Style.BRIGHT + t('combat_timeout'))
            sys.exit()

        # 보스 페이즈 2 전환 (HP 50% 이하)
        if is_boss and not phase2_triggered and hp <= boss_max_hp * constants.BOSS_PHASE2_RATIO:
            phase2_triggered = True
            atk = int(base_atk * constants.BOSS_PHASE2_ATK_MULT)
            learning_index += constants.BOSS_PHASE2_LI_BONUS
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
        print(t('combat_options_1'))
        print(t('combat_options_2'))
        print(t('combat_options_3'))
        print(t('combat_options_4'))
        if has_consumable:
            print(t('combat_options_5'))
        if sub_charges > 0:
            print(f"  {Fore.MAGENTA + Style.BRIGHT}{t('combat_sub_wpn_option', name=sub_wpn_name, charges=sub_charges)}{Style.RESET_ALL}")
        if player.skill_slots:
            for _i, _sid in enumerate(player.skill_slots):
                _sk = _skills.SKILL_DEFS.get(_sid, {})
                print(f"  {Fore.YELLOW + Style.BRIGHT}S{'12'[_i] if len(player.skill_slots) > 1 else ''}. {_sk.get('name','?')} — {_sk.get('desc','')}{Style.RESET_ALL}")

        cmd = read_key()

        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                if _skills.is_learning_blocked(player):
                    action_logs.append(t('combat_pattern_blocked'))
                else:
                    e_gain = max(0, 3 - e_suppress)
                    learning_index += e_gain
                    if e_suppress > 0:
                        action_logs.append(t('combat_repeat_cyberdeck', gain=e_gain))
                    else:
                        action_logs.append(t('combat_repeat_learning', gain=e_gain))

            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            f_multiplier = 1.0 + (player.reputation / 2000) * 1
            effective_power = player.get_attack_power() + gear_atk
            atk_mult = _skills.get_atk_mult(player)

            hyd_mult, hyd_pierce = _skills.consume_hydraulic_crush(player, action_logs)
            eff_e_def = int(e_def * (1 - hyd_pierce))

            dmg = max(50, math.floor(effective_power * f_multiplier * penalty * atk_mult * hyd_mult * 50) - eff_e_def + random.randint(-25, 25))

            forced_crit, st_mult = _skills.apply_signal_trace(player, combat_ctx, action_logs)
            ghost_crt  = player.active_buffs.pop("ghost_crt", 0.0)
            neural_mult = 2.0 if player.active_buffs.pop("neural_acc", 0) else 1.0
            if neural_mult > 1.0:
                action_logs.append(t('combat_neural_acc'))
            effective_crt = min(0.75, (stat_crt + ghost_crt) * neural_mult)
            if ghost_crt > 0:
                action_logs.append(t('combat_ghost_crit', pct=ghost_crt * 100))
            is_crit = forced_crit or random.random() < effective_crt
            crt_mult_used = st_mult if forced_crit else 1.5
            if is_crit and not forced_crit:
                action_logs.append(t('combat_crit_dex', mult=crt_mult_used))
            if is_crit:
                dmg = math.floor(dmg * crt_mult_used)

            dmg = _skills.apply_outgoing_buffs(player, dmg, action_logs)
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)
            crit_tag = Fore.YELLOW + Style.BRIGHT + " [CRITICAL!]" + Style.RESET_ALL if is_crit else ""

            print(Fore.GREEN + Style.BRIGHT + t('combat_attack_hit', dmg=f"{disp_dmg:,}") + crit_tag)
            time.sleep(1)
            hp = max(0, hp - dmg)
            _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
            print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_new:,}"))
            time.sleep(1)
            _skills.on_attack_used(player, action_logs, dmg_dealt=dmg)
            action_logs.append(t('combat_attack_log', dmg=f"{disp_dmg:,}"))
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
                eva_bonus = stat_eva * 100
                _ew = constants.ESCAPE_WEIGHTS
                weights = [
                    _ew[0] + eva_bonus,
                    max(5, _ew[1] - eva_bonus * 0.5),
                    max(2, _ew[2] - eva_bonus * 0.25),
                    max(1, _ew[3] - eva_bonus * 0.25),
                    _ew[4] + eva_bonus * 0.5
                ]
                if player.active_buffs.pop("void_shift", 0):
                    res = "SAFE"
                    action_logs.append(t('combat_void_shift'))
                else:
                    res = random.choices(["SAFE", "NORMAL", "1.5X", "2.0X", "LUCKY"], weights=weights, k=1)[0]

                escaped = True
                if res == "SAFE":
                    escape_log = t('combat_escape_safe')
                elif res in ["NORMAL", "1.5X", "2.0X"]:
                    dmg_calc = atk if res == "NORMAL" else int(atk * 1.5) if res == "1.5X" else int(atk * 2.0)
                    disp_dmg_calc, _, _ = apply_dynamic_scaling(dmg_calc, 0, tier)
                    print(t('combat_escape_hit', dmg=f"{disp_dmg_calc:,}"))
                    time.sleep(1)
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(t('combat_player_hp', hp=f"{disp_php_new:,}"))
                    time.sleep(1)

                    if res == "NORMAL":   escape_log = t('combat_escape_normal',   dmg=f"{disp_dmg_calc:,}")
                    elif res == "1.5X":  escape_log = t('combat_escape_heavy',    dmg=f"{disp_dmg_calc:,}")
                    else:                escape_log = t('combat_escape_disaster',  dmg=f"{disp_dmg_calc:,}")
                elif res == "LUCKY":
                    escape_log = t('combat_escape_lucky')
                break

        elif cmd == "5" and has_consumable:
            consecutive_attacks = 0
            avail = [k for k, v in player.consumables.items() if v > 0]
            print(t('combat_item_list'))
            for i, key in enumerate(avail):
                item = constants.CONSUMABLES_DB[key]
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
                item = constants.CONSUMABLES_DB[key]
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
                    action_logs.append(t('combat_sub_crit'))

                disp_sub_dmg, _, _ = apply_dynamic_scaling(sub_dmg, 0, tier)
                crit_tag = Fore.YELLOW + Style.BRIGHT + " [CRITICAL!]" + Style.RESET_ALL if is_crit else ""
                charges_tag = t('combat_sub_ammo_remaining', charges=sub_charges) if sub_charges > 0 else t('combat_sub_ammo_empty')
                print(Fore.MAGENTA + Style.BRIGHT + t('combat_sub_wpn_hit', name=sub_wpn_name, dmg=f"{disp_sub_dmg:,}") + crit_tag)
                time.sleep(1)
                hp = max(0, hp - sub_dmg)
                _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
                print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_new:,}"))
                time.sleep(1)
                action_logs.append(t('combat_sub_wpn_log', name=sub_wpn_name, dmg=f"{disp_sub_dmg:,}", charges_tag=charges_tag))
                time.sleep(1)
            else:
                print(t('combat_sub_no_ram_msg'))
                time.sleep(0.5)
                action_logs.append(t('combat_sub_no_ram_log'))

        elif cmd.upper() == "S" and player.skill_slots:
            slots = player.skill_slots
            consecutive_attacks = 0
            if len(slots) == 1:
                _skills.execute(player, slots[0], combat_ctx)
            else:
                print(t('combat_skill_select'))
                scmd = read_key()
                idx = 0 if scmd in ("s", "S", "1") else (1 if scmd == "2" else -1)
                if 0 <= idx < len(slots):
                    _skills.execute(player, slots[idx], combat_ctx)
                else:
                    action_logs.append(t('combat_skill_cancel'))

            aux_dmg = combat_ctx.pop("aux_skill_dmg", 0)
            if aux_dmg > 0 and hp > 0:
                hp = max(0, hp - aux_dmg)
                disp_aux, _, _ = apply_dynamic_scaling(aux_dmg, 0, tier)
                _, disp_ehp_aux, _ = apply_dynamic_scaling(0, hp, tier)
                print(Fore.YELLOW + Style.BRIGHT + t('combat_skill_dmg_msg', dmg=f"{disp_aux:,}") + Style.RESET_ALL)
                print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_aux:,}"))
                action_logs.append(t('combat_skill_dmg_log', dmg=f"{disp_aux:,}"))
                time.sleep(0.8)
            if combat_ctx.pop("pulse_e_drain", False) and is_boss:
                learning_index = max(0, learning_index - 3)
                action_logs.append(t('combat_pulse_e_drain'))

        else:
            print(t('combat_invalid_cmd'))
            time.sleep(1)
            action_logs.append(t('combat_invalid_log'))

        # --- 적의 반격 ---
        if hp > 0 and not escaped and not combat_ctx.get("skip_enemy_attack"):
            if cmd == "2":
                atk = int(base_atk * (1.6 if phase2_triggered else 1.0))

            curr_atk = int(atk * _skills.get_enemy_atk_mult(player))
            dmg_taken = max(1, curr_atk - total_def)
            dmg_taken = _skills.apply_incoming_buffs(player, dmg_taken, action_logs, combat_ctx)
            disp_dmg_taken, _, _ = apply_dynamic_scaling(dmg_taken, 0, tier)
            print(Fore.RED + Style.BRIGHT + t('combat_enemy_attack', name=name, dmg=f"{disp_dmg_taken:,}"))
            time.sleep(1)
            player.hp -= dmg_taken
            if cyber_regen > 0 and player.hp > 0:
                player.hp = min(player.max_hp, player.hp + cyber_regen)
            _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
            print(t('combat_player_hp_full', hp=f"{disp_php_new:,}", maxhp=f"{disp_pmaxhp:,}"))
            time.sleep(1)
            def_note = t('combat_def_note', val=def_bonus) if def_bonus > 0 else ""
            action_logs.append(t('combat_damage_log', dmg=f"{disp_dmg_taken:,}", def_note=def_note))
            time.sleep(1)

        combat_ctx["skip_enemy_attack"] = False
        _skills.end_of_turn_tick(player, action_logs)
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
                print(t('combat_loot_medkit', name=constants.CONSUMABLES_DB[it]['name']))
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
                print(t('combat_loot_water', name=constants.CONSUMABLES_DB[it]['name']))
            elif loot_res == "FOOD":
                it = roll_food()
                player.consumables[it] += 1
                print(t('combat_loot_food', name=constants.CONSUMABLES_DB[it]['name']))

        log_diary(player, t('combat_log_escape_diary', name=name))
        _neoarc_decay(player, sub_wpn_used)
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
            print(t('combat_farm_food', name=constants.CONSUMABLES_DB[it]['name']))
        elif drop_roll < 0.50:
            it = roll_water()
            player.consumables[it] += 1
            print(t('combat_farm_water', name=constants.CONSUMABLES_DB[it]['name']))
        elif drop_roll < 0.60:
            it = roll_medkit()
            player.consumables[it] += 1
            print(t('combat_farm_medkit', name=constants.CONSUMABLES_DB[it]['name']))
        else:
            player.materials += 20
            advance_quest(player, "scrap", 20)
            print(t('combat_farm_scrap'))

    advance_quest(player, "combat")
    log_diary(player, t('combat_log_win_diary', name=name, count=player.enemies_defeated))
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
    hp_ratio   = player.hp / player.max_hp if player.max_hp > 0 else 1.0
    alert_frac = max(0, min(100, player.alert_level)) / 100
    # 기본 10% + HP 비례 최대 +20% + 경보 레벨 비례 최대 +20%
    return 0.10 + (0.20 * hp_ratio) + (0.20 * alert_frac)
