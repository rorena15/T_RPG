# combat.py — 전투 시스템
# 의존성: constants, core, ui, sys_log

import archive
import collections
import math
import random
import sys
import time
import constants
import playtime
import endings
import traits
from colorama import Fore, Style
from core import get_equipment_data, grant_gear_drop
from i18n import t, db_t
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, read_key, log_diary,
                _log_color, roll_medkit, roll_food, roll_water,
                glitch_flash)
import skills as _skills
import sound
from quest import advance_quest
from sys_log import track
from gui import get_terminal, get_ui_manager

# 적 고유 행동이 몇 번 나왔는지 (밸런스 봇이 읽는다. 게임은 쓰지 않는다)
BEH_STATS = collections.Counter()


def _sleep(seconds: float):
    """pygame 모드에서는 화면 갱신을 유지하며 대기, 아니면 일반 sleep. 옵션의 전투 속도를 따른다."""
    seconds *= constants.COMBAT_SPEED
    if seconds <= 0:
        return
    term = get_terminal()
    if term:
        term.sleep_render(seconds)
    else:
        time.sleep(seconds)

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


def enemy_line(key, enemy_type, is_boss=False, **kw):
    """적 종류별 문구: <key>_<drone|bio|dogs|sec|boss>가 있으면 그것, 없으면 기본 문구 (드론·보스는 대개 기본)."""
    import i18n
    tag = "boss" if is_boss else (constants.ENEMY_TYPES.get(enemy_type) or constants.ENEMY_TYPES["drone"])["key"]
    k = f"{key}_{tag}"
    return t(k, **kw) if i18n.has(k) else t(key, **kw)


def pick_enemy(player):
    """탐색 중 만날 적 종류. 경계가 높으면 네오 아크 청소 부대가 끼어든다 (constants.ENEMY_TYPES)."""
    if player.alert_level >= constants.SEC_ALERT and random.random() < constants.SEC_CHANCE:
        return "security"
    r = random.random()
    for etype, p in constants.ENEMY_SPAWN.items():
        if r < p:
            return etype
        r -= p
    return "drone"


def get_turn_scale_multiplier(player):
    """진행 턴수와 난이도에 따른 적 스탯 배율을 계산한다. 플레이어 체력이 위험 수준이면 완화한다."""
    rate = constants.DIFFICULTY_SCALING_RATE.get(player.difficulty, constants.DIFFICULTY_SCALING_RATE["normal"])
    growth = min(player.turn_count, constants.ENEMY_TURN_SCALE_CAP) * rate

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
        eff_power = player.get_attack_power() + player.get_gear_atk_bonus()
        hp = int(max(hp * constants.BOSS_DIFF_MULT.get(player.difficulty, 1.0), hp * eff_power / constants.BOSS_POWER_REF))
        base_atk = int(base_atk * constants.BOSS_DIFF_ATK.get(player.difficulty, 1.0))
        art = constants.ENEMY_ART["BOSS"]
        # 보스는 턴 성장을 받지 않는다: 받으면 준비 없이 곧장 달려가는 쪽이 가장 쉬웠다 (시뮬레이션 보통 81% vs 탐색 44%)
        boss_max_hp = hp
        atk = base_atk
        player.boss_alert = player.alert_level   # 결말 판정용: 보스전 가산 전 경보
        player.alert_level = min(100, player.alert_level + constants.ALERT_INC_BOSS)
    else:
        spec = constants.ENEMY_TYPES.get(enemy_type) or constants.ENEMY_TYPES["drone"]
        e_def, base_atk = spec["def"], spec["atk"]
        art = random.choice(constants.ENEMY_ART[spec["art"]])
        base_atk = int(base_atk * scale_mult)
        k = spec["key"]
        if current_hp is not None:
            hp           = current_hp
            name         = t(f'enemy_{k}_name_wounded')
            header_title = t(f'enemy_{k}_header_wounded')
        else:
            hp           = int(random.randint(*spec["hp"]) * scale_mult)
            name         = t(f'enemy_{k}_name')
            header_title = t(f'enemy_{k}_header')
        atk = base_atk
        player.alert_level = min(100, player.alert_level + spec["alert"])

    arc_notes = [archive.meet_enemy(enemy_type, is_boss)]   # 기록 보관소: 알림은 이겼을 때 같이 찍는다
    base_atk = int(base_atk * constants.ENEMY_ATK_MULT)  # 적 공격력 일괄 조정 (보스 페이즈 2도 이 값을 기준으로 오른다)
    if not is_boss:  # 탐색 중 만나는 적은 난이도별로 한 번 더 (보스는 BOSS_DIFF_ATK로 따로 맞춘다)
        base_atk = int(base_atk * constants.ENEMY_DIFF_ATK.get(player.difficulty, 1.0))
    atk = base_atk

    scene = "enemy_collector" if is_boss else (constants.ENEMY_TYPES.get(enemy_type) or constants.ENEMY_TYPES["drone"])["scene"]
    if current_hp is None:  # 새 교전일 때만 적 그림 카드
        from event_view import scene_card
        scene_card(scene, header_title, tag=t('tag_combat'), line=name, player=player)

    enemy_max_hp = hp  # HP 바 표시용

    # ── ScenePanel 초기화 ────────────────────────────────────────────────────
    _ui = get_ui_manager()
    if _ui is None and get_terminal():  # 그림 화면 전투 (combat_view.py): 아래 UI 모드 신호를 받아 그린다
        from combat_view import CombatView
        _ui = CombatView(get_terminal(), player, scene, is_boss)
    if _ui:
        _ui.set_state("combat")
        _ui.scene_set_enemy(name, hp, hp, art)

    # ── 보조 화기 — 네오 아크 AI 폐기 화기 전용 ─────────────────────────
    _NAIWPN = "NEOARC_AI_WPN"
    sub_wpn_power = constants.SUB_WPN_POWER
    sub_wpn_name  = t('sub_wpn_name')
    sub_charges    = 2 if _NAIWPN in player.inventory else 0
    sub_wpn_used   = False

    combat_ctx = {"skip_enemy_attack": False}
    guard = False                                                     # 드론 방어 태세 (이번 턴 공격이 튕긴다)
    call_at = constants.SEC_CALL_TURN if (not is_boss and enemy_type == "security") else None   # 청소 부대 증원 도착 턴

    turn = 1
    stall = 0          # 해킹 2단계: 패킷 우회로 숙청 시퀀스를 늦춘 턴 수 (보스 턴 제한에 들지 않는다)
    learning_index = 0
    consecutive_attacks = 0
    escaped = False
    escape_log = ""
    action_logs = [t('combat_encounter_alert', name=name)]
    if call_at:
        action_logs.append(t('beh_sec_call', n=call_at))
        BEH_STATS["sec_call"] += 1
    sound.sfx("alert")

    def _summary(msg):
        """방금 화면에 찍은 행동의 요약. 터미널 모드는 화면을 지우고 다음 턴에 요약만 다시 보여 주지만,
        그림 화면 전투는 기록이 이어져 보이므로 같은 공방이 두 번 오간 것처럼 보였다. 그래서 거기선 뺀다."""
        if not _ui:
            action_logs.append(msg)

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
        if is_boss and turn > constants.BOSS_TURN_LIMIT + stall:
            clear_screen()
            sound.sfx("death")
            type_text(Fore.RED + Style.BRIGHT + t('combat_timeout'))
            print(t('playtime_line', time=playtime.finish(player, "timeout")))
            print()
            for line in endings.card("timeout"):
                print(line)
            wait_for_keypress()
            sys.exit()

        # 보스 페이즈 2 전환 (HP 50% 이하)
        if is_boss and not phase2_triggered and hp <= boss_max_hp * constants.BOSS_PHASE2_RATIO:
            phase2_triggered = True
            sound.sfx("phase2")
            sound.boss_phase2()
            atk = int(base_atk * constants.BOSS_PHASE2_ATK_MULT)
            learning_index += constants.BOSS_PHASE2_LI_BONUS
            clear_screen()
            glitch_flash([
                t('combat_phase2_header'),
                t('combat_phase2_warn1'),
                t('combat_phase2_warn2'),
            ], cycles=4, delay=0.05)
            print_header(t('combat_phase2_header'))
            type_text(Fore.RED + Style.BRIGHT + t('combat_phase2_warn1'), 0.03)
            type_text(Fore.RED + Style.BRIGHT + t('combat_phase2_warn2'), 0.03)
            type_text(Fore.YELLOW + Style.BRIGHT + t('combat_phase2_warn3'), 0.03)
            _sleep(1.5)
            action_logs.append(t('combat_phase2_log'))

        tier = player.get_highest_tier()
        _, disp_ehp, scale_log = apply_dynamic_scaling(0, hp, tier)
        _, disp_php, _ = apply_dynamic_scaling(0, player.hp, tier)
        _, disp_pmaxhp, _ = apply_dynamic_scaling(0, player.max_hp, tier)

        if is_boss:
            hp_pct = hp / boss_max_hp if boss_max_hp > 0 else 0
            bar_len = 40
            filled = int(bar_len * hp_pct)
            phase_tag = " [!! PHASE 2 !!]" if phase2_triggered else ""
            bar_col = (Fore.GREEN + Style.BRIGHT) if hp_pct > 0.5 else ((Fore.YELLOW + Style.BRIGHT) if hp_pct > 0.25 else (Fore.RED + Style.BRIGHT))
            hp_bar = f"  {bar_col}[{('█' * filled) + ('░' * (bar_len - filled))}] {hp_pct*100:.1f}%{phase_tag}"

        if _ui:
            # ── UIManager 모드: ScenePanel HP 갱신, 중복 출력 생략 ──────────────
            _ui.scene_update_hp(hp)
        else:
            # ── 터미널 모드: 기존 방식 전체 출력 ──────────────────────────────
            clear_screen()
            print_header(header_title)
            if scale_log:
                print(f"  {scale_log}")
                print_divider()
            print(art)
            if is_boss:
                print(hp_bar)
            else:
                e_hp_pct  = hp / enemy_max_hp if enemy_max_hp > 0 else 0
                e_filled  = round(e_hp_pct * 30)
                e_bar_col = (Fore.GREEN + Style.BRIGHT) if e_hp_pct > 0.6 else \
                            ((Fore.YELLOW + Style.BRIGHT) if e_hp_pct > 0.3 else (Fore.RED + Style.BRIGHT))
                print(f"  {e_bar_col}[{'█' * e_filled}{'░' * (30 - e_filled)}] {e_hp_pct*100:.0f}%{Style.RESET_ALL}")
            print(t('combat_status_turn', turn=turn, name=name, hp=f"{disp_ehp:,}"))
            print(t('combat_status_player', hp=f"{disp_php:,}", maxhp=f"{disp_pmaxhp:,}", ram=player.max_ram))
            if is_boss:
                print(t('combat_status_learning', e=learning_index))

        # 행동 로그 — 양쪽 모드 모두 출력 (UI 모드에서는 LogPanel로 표시)
        if action_logs:
            if not _ui:
                print(t('combat_log_header'))
            for log in action_logs:
                print(f"  {_log_color(log)}{log}")
            if not _ui:
                print_divider()
        action_logs.clear()

        has_consumable = any(v > 0 for v in player.consumables.values())
        if _ui:
            # ActionPanel에 현재 전투 선택지 표시
            # 기술 Q 공격 · E 바리케이드 · R 패킷 우회 · F 보조화기 / 스킬 Z·C / X 후퇴 / I 소모품 목록 / 1~0 퀵슬롯
            _acts = [
                ("Q", t('combat_act_attack'),    True),
                ("E", t('combat_act_barricade'), True),
                ("R", t('combat_act_jam'),       True),
            ]
            if sub_charges > 0:
                _acts.append(("F", t('combat_act_sub', n=sub_charges), True))
            for _i, _sid in enumerate(player.skill_slots[:2]):
                _acts.append(("ZC"[_i], _skills.skill_name(_sid, short=True), True))
            _acts += [("X", t('combat_act_retreat'), True), ("I", t('combat_act_item'), has_consumable)]
            _ui.set_actions(_acts)
        else:
            print()
            print(t('combat_options_1'))
            print(t('combat_options_2'))
            print(t('combat_options_3', cost=traits.jam_cost(player)))
            print(t('combat_options_4'))
            if has_consumable:
                print(t('combat_options_5'))
            if sub_charges > 0:
                print(f"  {Fore.MAGENTA + Style.BRIGHT}{t('combat_sub_wpn_option', name=sub_wpn_name, charges=sub_charges)}{Style.RESET_ALL}")
            if player.skill_slots:
                for _i, _sid in enumerate(player.skill_slots[:2]):
                    _sk = _skills.SKILL_DEFS.get(_sid, {})
                    print(f"  {Fore.YELLOW + Style.BRIGHT}{'ZC'[_i]}. {_skills.skill_name(_sid)} — {db_t(_sk, 'desc')}{Style.RESET_ALL}")
            _qs = "  ".join(f"[{'1234567890'[i]}] {db_t(constants.CONSUMABLES_DB[k], 'name')} x{player.consumables.get(k, 0)}"
                            for i, k in enumerate(player.quickslots) if k)
            if _qs:
                print(f"  {Fore.CYAN}{t('qs_line', slots=_qs)}{Style.RESET_ALL}")

        cmd = read_key()
        # 키 → 안쪽 행동 번호 (1 공격, 2 바리케이드, 3 패킷 우회, 4 후퇴, 5 소모품, 6 보조화기, S 스킬)
        _skill_idx = None
        _quick_key = None
        if cmd in ("Z", "C") and len(player.skill_slots) > "ZC".index(cmd):
            _skill_idx, cmd = "ZC".index(cmd), "S"
        elif cmd and cmd in player.QUICK_KEYS:  # 퀵슬롯 (누른 숫자키 그대로, 행동 번호로 바꾸기 전에): 그 소모품을 쓰는 데 한 턴
            _quick_key = player.quick_item(cmd)
            if not _quick_key or player.consumables.get(_quick_key, 0) <= 0:
                action_logs.append((t('qs_empty', n=cmd) if not _quick_key else
                                    t('qs_none_left', name=db_t(constants.CONSUMABLES_DB[_quick_key], 'name'))).strip())
                continue   # 빈 칸은 턴을 쓰지 않는다
            cmd = "5"
        else:
            cmd = {"Q": "1", "E": "2", "R": "3", "X": "4", "I": "5", "F": "6"}.get(cmd, cmd)

        if cmd == "1":
            consecutive_attacks += 1
            if consecutive_attacks >= 2 and is_boss:
                if _skills.is_learning_blocked(player):
                    action_logs.append(t('combat_pattern_blocked'))
                else:
                    e_gain = max(0, 3 - e_suppress - traits.learn_suppress(player))
                    learning_index += e_gain
                    if e_suppress > 0:
                        action_logs.append(t('combat_repeat_cyberdeck', gain=e_gain))
                    else:
                        action_logs.append(t('combat_repeat_learning', gain=e_gain))

            penalty = max(0.5, 1.0 - (learning_index - 10) * 0.05) if learning_index > 10 else 1.0
            f_multiplier = 1.0 + (player.reputation / 2000) * 1
            effective_power = player.get_attack_power() + gear_atk
            atk_mult = _skills.get_atk_mult(player) * traits.dmg_mult(player)
            if combat_ctx.pop("exposed", False):   # 해킹 2단계: 교란으로 드러난 약점
                atk_mult *= traits.EXPOSE_MULT
                action_logs.append(t('trait_exposed_hit'))

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
            if guard:
                dmg = max(1, int(dmg * constants.DRONE_GUARD_MULT))
                action_logs.append(t('beh_drone_guard_hit'))
                BEH_STATS["drone_guard_hit"] += 1
            disp_dmg, _, _ = apply_dynamic_scaling(dmg, 0, tier)
            crit_tag = Fore.YELLOW + Style.BRIGHT + " [CRITICAL!]" + Style.RESET_ALL if is_crit else ""

            sound.sfx(constants.weapon_sfx(player.equipment.get("main_weapon")))  # 무기 종류별 공격음
            if is_crit:
                sound.sfx("crit")
            print(Fore.GREEN + Style.BRIGHT + enemy_line('combat_attack_hit', enemy_type, is_boss, dmg=f"{disp_dmg:,}") + crit_tag)
            _sleep(1)
            hp = max(0, hp - dmg)
            if _ui: _ui.scene_update_hp(hp)
            _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
            print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_new:,}"))
            _sleep(1)
            _skills.on_attack_used(player, action_logs, dmg_dealt=dmg)
            _summary(t('combat_attack_log', dmg=f"{disp_dmg:,}"))
            _sleep(1)

        elif cmd == "2":
            consecutive_attacks = 0
            learning_index = max(0, learning_index - 4)
            atk = int(atk * (1 - traits.barricade_block(player)))

            sound.sfx("barricade")
            print(t('combat_defense_msg'))
            _sleep(1)
            _summary(t('combat_defense_log'))
            _sleep(2)

        elif cmd == "3":
            if player.max_ram >= traits.jam_cost(player):
                consecutive_attacks = 0
                learning_index = 0
                player.max_ram -= traits.jam_cost(player)
                if call_at:
                    call_at = None
                    action_logs.append(t('beh_sec_jammed'))
                    BEH_STATS["sec_jammed"] += 1
                if traits.jam_blocks_counter(player):   # 해킹 2단계: 교란에 걸린 적은 이번 턴 반격하지 못하고 약점이 드러난다
                    combat_ctx["skip_enemy_attack"] = True
                    combat_ctx["exposed"] = True
                    if is_boss:
                        stall += 1
                        action_logs.append(t('trait_jam_stall'))
                    action_logs.append(t('trait_jam_block'))

                sound.sfx("hack")
                print(enemy_line('combat_hack_msg', enemy_type, is_boss, cost=traits.jam_cost(player)))
                _sleep(1)
                _summary(t('combat_hack_log'))
            else:
                sound.sfx("deny")
                print(t('combat_hack_no_ram'))
                _sleep(0.5)
                action_logs.append(t('combat_hack_no_ram_log'))

        elif cmd == "4":
            if is_boss:
                sound.sfx("deny")
                print(t('combat_escape_boss'))
                _sleep(0.5)
                action_logs.append(t('combat_escape_boss_log'))
                _sleep(1)
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
                sound.sfx("escape")
                if res == "SAFE":
                    escape_log = t('combat_escape_safe')
                elif res in ["NORMAL", "1.5X", "2.0X"]:
                    dmg_calc = atk if res == "NORMAL" else int(atk * 1.5) if res == "1.5X" else int(atk * 2.0)
                    disp_dmg_calc, _, _ = apply_dynamic_scaling(dmg_calc, 0, tier)
                    sound.enemy_attack(enemy_type, heavy=res != "NORMAL")
                    print(t('combat_escape_hit', dmg=f"{disp_dmg_calc:,}"))
                    _sleep(1)
                    player.hp -= dmg_calc
                    _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
                    print(t('combat_player_hp', hp=f"{disp_php_new:,}"))
                    _sleep(1)

                    if res == "NORMAL":   escape_log = t('combat_escape_normal',   dmg=f"{disp_dmg_calc:,}")
                    elif res == "1.5X":  escape_log = t('combat_escape_heavy',    dmg=f"{disp_dmg_calc:,}")
                    else:                escape_log = t('combat_escape_disaster',  dmg=f"{disp_dmg_calc:,}")
                elif res == "LUCKY":
                    escape_log = t('combat_escape_lucky')
                break

        elif cmd == "5" and _quick_key:
            consecutive_attacks = 0
            item = constants.CONSUMABLES_DB[_quick_key]
            _before = player.hp
            player.use_consumable(_quick_key)
            if item["type"] == "hp":
                _, disp_heal, _ = apply_dynamic_scaling(player.hp - _before, 0, tier)
                action_logs.append(t('combat_recover_log', name=db_t(item, 'name'), hp=f"{disp_heal:,}"))
            else:
                action_logs.append(t('combat_eat_log', name=db_t(item, 'name')))

        elif cmd == "5" and has_consumable:
            consecutive_attacks = 0
            avail = [k for k, v in player.consumables.items() if v > 0]
            if not _ui:   # 그림 화면은 아래 버튼이 목록이다: 기록 칸에 같은 목록을 또 찍지 않는다
                print(t('combat_item_list'))
            for i, key in enumerate(avail if not _ui else []):
                item = constants.CONSUMABLES_DB[key]
                if item["type"] == "hp":
                    desc = t('consumable_hp_percent', pct=int(item['val']*100)) if item["is_percent"] else t('consumable_hp_fixed', val=item['val'])
                else:
                    h_val = t('consumable_hunger', val=item['hunger']) if item['hunger'] > 0 else ""
                    thirst_str = t('consumable_thirst', val=item['thirst']) if item['thirst'] > 0 else ""
                    desc = h_val + thirst_str
                icon = item.get('icon', '')
                name_disp = f"{icon} {db_t(item, 'name')}" if icon else db_t(item, 'name')
                print(f"  [{i+1}] {name_disp} x{player.consumables[key]} — {desc}")
            if not _ui:
                print(t('combat_cancel_item'))
            if _ui:
                _prev_sel, _ui.foot_sel = _ui.foot_sel, 0
                _ui.set_actions([(str(i + 1), f"{db_t(constants.CONSUMABLES_DB[k], 'name')} x{player.consumables[k]}", True, None, k)
                                 for i, k in enumerate(avail[:9])] + [("0", t('ui_back'), True)])
            item_cmd = read_key()
            if _ui:
                _ui.foot_sel = _prev_sel   # 다음 턴엔 원래 고르던 행동(아이템 칸)으로
            if item_cmd.isdigit() and 0 < int(item_cmd) <= len(avail):
                key = avail[int(item_cmd) - 1]
                item = constants.CONSUMABLES_DB[key]
                player.consumables[key] -= 1
                if item["type"] == "hp":
                    heal = int(player.max_hp * item["val"]) if item["is_percent"] else item["val"]
                    player.hp = min(player.max_hp, player.hp + heal)
                    _, disp_heal, _ = apply_dynamic_scaling(heal, 0, tier)
                    sound.sfx("heal")
                    action_logs.append(t('combat_recover_log', name=db_t(item, 'name'), hp=f"{disp_heal:,}"))
                else:
                    player.hunger = min(100, player.hunger + item["hunger"])
                    player.thirst = min(100, player.thirst + item["thirst"])
                    sound.sfx("eat")
                    action_logs.append(t('combat_eat_log', name=db_t(item, 'name')))
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
                if guard:
                    sub_dmg = max(1, int(sub_dmg * constants.DRONE_GUARD_MULT))
                    action_logs.append(t('beh_drone_guard_hit'))

                disp_sub_dmg, _, _ = apply_dynamic_scaling(sub_dmg, 0, tier)
                crit_tag = Fore.YELLOW + Style.BRIGHT + " [CRITICAL!]" + Style.RESET_ALL if is_crit else ""
                charges_tag = t('combat_sub_ammo_remaining', charges=sub_charges) if sub_charges > 0 else t('combat_sub_ammo_empty')
                sound.sfx("sub")
                print(Fore.MAGENTA + Style.BRIGHT + t('combat_sub_wpn_hit', name=sub_wpn_name, dmg=f"{disp_sub_dmg:,}") + crit_tag)
                _sleep(1)
                hp = max(0, hp - sub_dmg)
                if _ui: _ui.scene_update_hp(hp)
                _, disp_ehp_new, _ = apply_dynamic_scaling(0, hp, tier)
                print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_new:,}"))
                _sleep(1)
                _summary(t('combat_sub_wpn_log', name=sub_wpn_name, dmg=f"{disp_sub_dmg:,}", charges_tag=charges_tag))
                _sleep(1)
            else:
                sound.sfx("deny")
                print(t('combat_sub_no_ram_msg'))
                _sleep(0.5)
                _summary(t('combat_sub_no_ram_log'))

        elif cmd.upper() == "S" and player.skill_slots:
            slots = player.skill_slots
            consecutive_attacks = 0
            if _skill_idx is not None:
                _skills.execute(player, slots[_skill_idx], combat_ctx)
            elif len(slots) == 1:
                _skills.execute(player, slots[0], combat_ctx)
            else:
                print(t('combat_skill_select'))
                scmd = read_key()
                idx = 0 if scmd in ("S", "Z", "1") else (1 if scmd in ("C", "2") else -1)
                if 0 <= idx < len(slots):
                    _skills.execute(player, slots[idx], combat_ctx)
                else:
                    action_logs.append(t('combat_skill_cancel'))

            aux_dmg = combat_ctx.pop("aux_skill_dmg", 0)
            if aux_dmg > 0 and hp > 0:
                hp = max(0, hp - aux_dmg)
                if _ui: _ui.scene_update_hp(hp)
                disp_aux, _, _ = apply_dynamic_scaling(aux_dmg, 0, tier)
                _, disp_ehp_aux, _ = apply_dynamic_scaling(0, hp, tier)
                sound.sfx("skill")
                print(Fore.YELLOW + Style.BRIGHT + t('combat_skill_dmg_msg', dmg=f"{disp_aux:,}") + Style.RESET_ALL)
                print(t('combat_enemy_hp', name=name, hp=f"{disp_ehp_aux:,}"))
                _summary(t('combat_skill_dmg_log', dmg=f"{disp_aux:,}"))
                _sleep(0.8)
            if combat_ctx.pop("pulse_e_drain", False) and is_boss:
                learning_index = max(0, learning_index - 3)
                action_logs.append(t('combat_pulse_e_drain'))

        else:  # 잘못 누른 키는 턴을 쓰지 않는다 (적 반격 없음)
            print(t('combat_invalid_cmd'))
            _sleep(1)
            action_logs.append(t('combat_invalid_log'))
            continue

        # --- 적의 반격 ---
        if hp > 0 and not escaped and not combat_ctx.get("skip_enemy_attack"):
            curr_atk = int(atk * _skills.get_enemy_atk_mult(player))
            if not is_boss and enemy_type == "dogs":   # 무리가 줄수록 약해진다
                curr_atk = int(curr_atk * (constants.DOGS_MIN_ATK + (1 - constants.DOGS_MIN_ATK) * hp / max(1, enemy_max_hp)))
            dmg_taken = max(1, curr_atk - total_def)
            dmg_taken = _skills.apply_incoming_buffs(player, dmg_taken, action_logs, combat_ctx)
            disp_dmg_taken, _, _ = apply_dynamic_scaling(dmg_taken, 0, tier)
            sound.enemy_attack("boss" if is_boss else enemy_type, heavy=dmg_taken >= player.max_hp * 0.2)
            print(Fore.RED + Style.BRIGHT + enemy_line('combat_enemy_attack', enemy_type, is_boss, name=name, dmg=f"{disp_dmg_taken:,}"))
            _sleep(1)
            player.hp -= dmg_taken
            if cyber_regen > 0 and player.hp > 0:
                player.hp = min(player.max_hp, player.hp + cyber_regen)
            _, disp_php_new, _ = apply_dynamic_scaling(0, max(0, player.hp), tier)
            print(t('combat_player_hp_full', hp=f"{disp_php_new:,}", maxhp=f"{disp_pmaxhp:,}"))
            _sleep(1)
            def_note = t('combat_def_note', val=def_bonus) if def_bonus > 0 else ""
            _summary(t('combat_damage_log', dmg=f"{disp_dmg_taken:,}", def_note=def_note))
            _sleep(1)
            if not is_boss and enemy_type == "bio_hound" and player.hp > 0 and random.random() < constants.HOUND_DOUBLE_CHANCE:
                bite = max(1, int(dmg_taken * constants.HOUND_DOUBLE_MULT))
                player.hp -= bite
                disp_bite, _, _ = apply_dynamic_scaling(bite, 0, tier)
                sound.enemy_attack(enemy_type)
                print(Fore.RED + t('beh_hound_double', dmg=f"{disp_bite:,}"))
                action_logs.append(t('beh_hound_double', dmg=f"{disp_bite:,}").strip())
                BEH_STATS["hound_double"] += 1

        if cmd == "2":  # 바리케이드 반감은 이번 반격에만. 예전엔 반격 직전에 되돌려서 피해가 전혀 줄지 않았다
            atk = int(base_atk * (constants.BOSS_PHASE2_ATK_MULT if phase2_triggered else 1.0))
        combat_ctx["skip_enemy_attack"] = False
        _skills.end_of_turn_tick(player, action_logs)
        _rep = traits.turn_repair(player)
        if _rep and hp > 0 and 0 < player.hp < player.max_hp:   # 해체 3단계: 전투 중 자가 수리
            player.hp = min(player.max_hp, player.hp + _rep)
            BEH_STATS["scrap_repair"] += 1
        guard = False
        if hp > 0 and not is_boss:
            if enemy_type == "drone" and turn % constants.DRONE_GUARD_EVERY == constants.DRONE_GUARD_EVERY - 1:
                guard = True                                   # 다음 턴 예고: 이번엔 때리지 말고 버틸 때
                action_logs.append(t('beh_drone_guard'))
                BEH_STATS["drone_guard"] += 1
            if call_at and turn >= call_at:
                call_at = None
                extra = int(enemy_max_hp * constants.SEC_REINF_HP)
                hp += extra
                enemy_max_hp += extra
                base_atk = int(base_atk * constants.SEC_REINF_ATK)
                atk = base_atk
                if _ui: _ui.scene_set_enemy(name, hp, enemy_max_hp, art)
                sound.sfx("alert")
                action_logs.append(t('beh_sec_reinforced'))
                BEH_STATS["sec_reinforced"] += 1
            elif call_at:
                action_logs.append(t('beh_sec_call', n=call_at - turn))
        turn += 1

    if player.hp <= 0:
        clear_screen()
        if escape_log: type_text(escape_log, 0.02)
        sound.sfx("death")
        type_text(Fore.RED + Style.BRIGHT + t('combat_fatal'), 0.03)
        print(t('playtime_line', time=playtime.finish(player, "boss_death" if is_boss else "death")))
        print()
        for line in endings.card("boss_death" if is_boss else endings.death_key(enemy_type)):
            print(line)
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
                print(t('combat_loot_medkit', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
            elif loot_res == "MATERIAL":
                player.materials += 15
                advance_quest(player, "scrap", 15)
                print(t('combat_loot_scrap'))
            elif loot_res == "PART":
                part = random.choice(["PART_SCRAP_01", "PART_SCRAP_02", "PART_SCRAP_03"])
                player.inventory.append(part)
                item_data = get_equipment_data(part)
                print(t('combat_loot_part', name=db_t(item_data, 'name')))
            elif loot_res == "WATER":
                it = roll_water()
                player.consumables[it] += 1
                print(t('combat_loot_water', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
            elif loot_res == "FOOD":
                it = roll_food()
                player.consumables[it] += 1
                print(t('combat_loot_food', name=db_t(constants.CONSUMABLES_DB[it], 'name')))

        log_diary(player, t('combat_log_escape_diary', name=name))
        _neoarc_decay(player, sub_wpn_used)
        wait_for_keypress()
        if hp_bonus > 0:
            player.max_hp -= hp_bonus
            player.hp = min(player.hp, player.max_hp)
        if _ui: _ui.scene_set_idle(); _ui.set_state("exploration")
        return hp, enemy_type

    clear_screen()
    sound.sfx("win")
    print_header(t('combat_win_header'))
    print(f"\n{Fore.GREEN + Style.BRIGHT}" + enemy_line('combat_win_msg', enemy_type, is_boss, name=name))
    player.enemies_defeated += 1
    arc_notes.append(archive.defeat_enemy(enemy_type, is_boss))
    for note in dict.fromkeys(n for n in arc_notes if n):
        print(note)

    if not is_boss:
        drop_roll = random.random()
        if drop_roll < 0.25:
            it = roll_food()
            player.consumables[it] += 1
            print(enemy_line('combat_farm_food', enemy_type, name=db_t(constants.CONSUMABLES_DB[it], 'name')))
        elif drop_roll < 0.50:
            it = roll_water()
            player.consumables[it] += 1
            print(enemy_line('combat_farm_water', enemy_type, name=db_t(constants.CONSUMABLES_DB[it], 'name')))
        elif drop_roll < 0.60:
            it = roll_medkit()
            player.consumables[it] += 1
            print(t('combat_farm_medkit', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
        else:
            gained = traits.scrap(player, 20)
            player.materials += gained
            advance_quest(player, "scrap", gained)
            print(t('combat_farm_scrap_n', val=gained))
        spec = constants.ENEMY_TYPES.get(enemy_type) or {}
        if spec.get("bonus_scrap"):  # 청소 부대: 장비를 뜯어낸 고철
            bonus = traits.scrap(player, spec["bonus_scrap"])
            player.materials += bonus
            advance_quest(player, "scrap", bonus)
            print(t('combat_sec_scrap', val=bonus))
        if traits.win_ram(player):
            print(t('trait_ram_regen', ram=player.max_ram))
        if random.random() < spec.get("gear_drop", constants.GEAR_DROP_COMBAT):  # 장비 드롭은 위 보상과 따로 굴린다
            msg = grant_gear_drop(player)
            if msg:
                print(msg)

    advance_quest(player, "combat")
    log_diary(player, t('combat_log_win_diary', name=name, count=player.enemies_defeated))
    _neoarc_decay(player, sub_wpn_used)
    wait_for_keypress()
    if hp_bonus > 0:
        player.max_hp -= hp_bonus
        player.hp = min(player.hp, player.max_hp)
    if _ui: _ui.scene_set_idle(); _ui.set_state("exploration")
    return None, None

# ====================================================================
# [6] 메인 구동 루프 망 명세
# ====================================================================
def get_encounter_chance(player):
    hp_ratio   = player.hp / player.max_hp if player.max_hp > 0 else 1.0
    alert_frac = max(0, min(100, player.alert_level)) / 100
    # 기본 10% + HP 비례 최대 +20% + 경보 레벨 비례 최대 +20%
    return 0.10 + (0.20 * hp_ratio) + (0.20 * alert_frac)
