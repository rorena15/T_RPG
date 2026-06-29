# story.py — 서사 흐름: 세션, 프롤로그, 보스, 엔딩
# 의존성: constants, core, ui, combat, quest, sys_log

import time
import constants
from colorama import Fore, Style
from core import get_equipment_data
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, read_key, log_diary,
                ea_rpad, ea_center)
from combat import combat_loop, get_turn_scale_multiplier
from quest import advance_quest
from i18n import t, db_t
import sound
import skills

def handle_session(player, session):
    clear_screen()
    sound.play_typing_bgm()
    print_header(db_t(session, 'title'))
    type_text(db_t(session, 'text'), 0.02)
    print()
    for i, choice in enumerate(session['choices']):
        print(f"  [{i+1}] {db_t(choice, 'text')}")
    time.sleep(1)
    while True:
        ans = read_key()
        if ans in ["1", "2", "3"]:
            choice_data = session['choices'][int(ans) - 1]
            choice_weight = choice_data.get('weight')
            if choice_weight:
                player.weights[choice_weight] += 1

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

            if choice_data.get("consumable"):
                key = choice_data["consumable"]
                if key in player.consumables:
                    player.consumables[key] += 1
                    print(t('session_consumable_gain', name=db_t(constants.CONSUMABLES_DB.get(key, {}), 'name') or key))

            raw_mat = choice_data.get("materials", 0)
            if raw_mat != 0 and not choice_data.get("reward") == "SCRAP_MAT":
                player.materials = max(0, player.materials + raw_mat)
                if raw_mat > 0:
                    advance_quest(player, "scrap", raw_mat)
                    print(t('session_scrap_add', val=raw_mat))
                else:
                    print(t('session_scrap_use', val=raw_mat))

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
            type_text(f"\n  {db_t(choice_data, 'log')}", 0.025)

            _w_label_map = {
                "kinetic": t('weight_label_kinetic'),
                "scrap":   t('weight_label_scrap'),
                "cyber":   t('weight_label_cyber'),
            }
            _w_label = _w_label_map.get(choice_weight, t('weight_label_default'))
            _reward_note = ""
            if choice_data.get("reward") and choice_data["reward"] != "SCRAP_MAT":
                _rd = get_equipment_data(choice_data["reward"])
                _reward_note = t('session_log_reward_item', name=_rd['name'])
            elif choice_data.get("reward") == "SCRAP_MAT":
                _reward_note = t('session_log_reward_scrap', val=choice_data.get('materials', 30))
            if choice_data.get("ram_bonus"):
                _reward_note += t('session_log_reward_ram', val=choice_data['ram_bonus'])
            log_diary(player, t('session_log_diary', title=db_t(session, 'title'), label=_w_label, note=_reward_note))

            if choice_weight and player.weights[choice_weight] >= 3:
                _wcb = {
                    "kinetic": t('session_pattern_kinetic'),
                    "scrap":   t('session_pattern_scrap'),
                    "cyber":   t('session_pattern_cyber'),
                }
                time.sleep(0.3)
                type_text(_wcb[choice_weight], 0.022)

            sound.resume_map_ambient()
            wait_for_keypress()
            break


def run_prologue():
    """신규 게임 시작 시 전체 프롤로그 시퀀스를 재생합니다."""
    clear_screen()
    print_header(t('prologue_header'))
    print()
    print(t('prologue_loaded'))
    print()
    sound.play_typing_bgm()
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

    # ── 단계 1: 부팅 시퀀스 ──────────────────────────────────────────────
    boot_log = [
        (t('prologue_boot_0'),      0.04),
        (t('prologue_boot_12'),     0.04),
        (t('prologue_boot_45'),     0.03),
        (t('prologue_boot_100'),    0.03),
        ("",                        0.1),
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


def _banner_path() -> str:
    import sys as _sys, os as _os
    if getattr(_sys, 'frozen', False):
        base = _sys._MEIPASS
    else:
        base = _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
    return _os.path.join(base, 'assets', 'banner.png')


def run_ending(player):
    clear_screen()
    sound.stop_all()
    from gui import get_terminal
    _term = get_terminal()
    if _term:
        _term.show_banner(_banner_path())
        _term.wait_keypress_silent()   # print() 없이 대기 — 배너 덮어쓰기 방지
        clear_screen()
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
    print(t('ending_scrap_label',   bar=make_bar(w_s, total), count=w_s))
    print(t('ending_cyber_label',   bar=make_bar(w_c, total), count=w_c))
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

    print(t('ending_stat_diff',        val=diff_label))
    print(t('ending_stat_turns',       val=player.turn_count))
    print(t('ending_stat_threat',      val=threat_final))
    print(t('ending_stat_enemies',     val=player.enemies_defeated))
    print(t('ending_stat_hp',          hp=player.hp, maxhp=player.max_hp))
    print(t('ending_stat_scrap',       val=player.materials))
    print(t('ending_stat_items',       val=len(player.inventory)))
    print(t('ending_stat_tier',        val=tier_name))
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
    run_act2_teaser(player)


def run_act2_teaser(player):
    """1막 클리어 후 2막 예고 시퀀스 — 직업 스킬 미리보기 + 두 진영 신호."""
    w_k = player.weights['kinetic']
    w_s = player.weights['scrap']
    w_c = player.weights['cyber']

    if w_k == w_s == w_c:
        job_key = "balanced"
    elif w_k >= w_s and w_k >= w_c:
        job_key = "kinetic"
    elif w_s >= w_k and w_s >= w_c:
        job_key = "scrap"
    else:
        job_key = "cyber"

    job_tag = t(f'act2_tease_{job_key}_job')
    skills = t(f'act2_skills_{job_key}')

    # ── 스크린 1: 직업 스킬 예고 ────────────────────────────────────────
    clear_screen()
    print_header(t('act2_tease_skill_header', job=job_tag))
    print()
    type_text(t('act2_tease_skill_intro_1', job=job_tag), 0.028)
    type_text(t('act2_tease_skill_intro_2'), 0.025)
    print()
    print_divider()
    print(t('act2_tease_unlock_header'))
    print_divider()
    time.sleep(0.4)
    for sname, sdesc in skills:
        print(f"\n  {Fore.CYAN + Style.BRIGHT}▶  {sname}{Style.RESET_ALL}")
        type_text(f"     {sdesc}", 0.018)
        time.sleep(0.2)
    print()
    wait_for_keypress()

    # ── 스크린 2: 두 진영의 신호 수신 ───────────────────────────────────
    clear_screen()
    print_header(t('act2_signal_header'))
    print()
    time.sleep(0.6)
    type_text(t('act2_signal_intro'), 0.025)
    print()
    time.sleep(0.5)

    print_divider()
    type_text(Fore.CYAN + Style.BRIGHT + t('act2_signal_a_header') + Style.RESET_ALL, 0.02)
    time.sleep(0.3)
    print()
    type_text(t('act2_signal_a_1'), 0.03)
    type_text(t('act2_signal_a_2'), 0.03)
    type_text(t('act2_signal_a_3'), 0.03)
    print()
    print(Fore.CYAN + Style.BRIGHT + t('act2_signal_a_tag') + Style.RESET_ALL)
    time.sleep(0.8)

    print_divider()
    type_text(Fore.YELLOW + Style.BRIGHT + t('act2_signal_b_header') + Style.RESET_ALL, 0.02)
    time.sleep(0.3)
    print()
    type_text(t('act2_signal_b_1'), 0.03)
    type_text(t('act2_signal_b_2'), 0.03)
    type_text(t('act2_signal_b_3'), 0.03)
    print()
    print(Fore.YELLOW + Style.BRIGHT + t('act2_signal_b_tag') + Style.RESET_ALL)
    print_divider()
    time.sleep(0.5)
    print()
    type_text(t('act2_signal_footer_1'), 0.028)
    type_text(t('act2_signal_footer_2'), 0.028)
    print()
    time.sleep(0.6)
    print_divider()
    print(t('act2_signal_prompt'))
    print()
    print(f"  {Fore.CYAN + Style.BRIGHT}[1]{Style.RESET_ALL} " + t('act2_signal_opt1'))
    print(f"  {Fore.YELLOW + Style.BRIGHT}[2]{Style.RESET_ALL} " + t('act2_signal_opt2'))
    print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} " + t('act2_signal_opt3'))
    print_divider()
    print(Fore.WHITE + Style.DIM + t('act2_signal_later') + Style.RESET_ALL)

    while True:
        ans = read_key()
        if ans in ["1", "2", "3"]:
            break

    print()
    if ans == "1":
        type_text(t('act2_reply_a_send'), 0.03)
        time.sleep(0.5)
        type_text(Fore.CYAN + Style.BRIGHT + t('act2_reply_a_recv') + Style.RESET_ALL, 0.03)
        log_diary(player, t('act2_diary_a'))
    elif ans == "2":
        type_text(t('act2_reply_b_send'), 0.03)
        time.sleep(0.5)
        type_text(Fore.YELLOW + Style.BRIGHT + t('act2_reply_b_recv') + Style.RESET_ALL, 0.03)
        log_diary(player, t('act2_diary_b'))
    else:
        type_text(t('act2_reply_none'), 0.03)
        log_diary(player, t('act2_diary_none'))

    time.sleep(0.8)
    wait_for_keypress()

    # ── 스크린 3: 2막 타이틀 카드 ───────────────────────────────────────
    clear_screen()
    print()
    time.sleep(1.0)
    type_text(t('act2_title_1'), 0.032)
    print()
    time.sleep(0.6)
    type_text(t('act2_title_2'), 0.025)
    print()
    time.sleep(0.8)
    print_divider()
    print()
    print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
    print(Fore.CYAN  + Style.BRIGHT + "  ║" + ea_center("P  R  O  T  O  C  O  L  :  S  T  I  G  M  A", 74) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + ea_center(t('act2_title_act2'), 74) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
    print(Fore.YELLOW + Style.BRIGHT + "  ║" + ea_center("— COMING SOON —", 74) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    print()
    time.sleep(0.5)
    type_text(t('act2_title_thanks'), 0.025)
    time.sleep(1.2)
    run_credits()


def run_credits():
    """엔딩 후 크레딧 화면 — 감사 메시지 + 링크."""
    clear_screen()
    print()
    time.sleep(0.4)

    print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.WHITE + Style.BRIGHT + "  ║  " + ea_rpad(t('credits_header'), 72) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    print()
    time.sleep(0.3)

    type_text(t('credits_line1'), 0.022)
    type_text(t('credits_line2'), 0.022)
    print()
    time.sleep(0.5)

    print_divider()
    print()

    github_url = constants.CREDITS_GITHUB
    itch_url   = constants.CREDITS_ITCH

    print(f"  {Fore.CYAN + Style.BRIGHT}{'GitHub':<12}{Style.RESET_ALL}  {github_url}")
    if itch_url:
        print(f"  {Fore.GREEN + Style.BRIGHT}{'itch.io':<12}{Style.RESET_ALL}  {itch_url}")
    else:
        print(f"  {Fore.WHITE + Style.DIM}{'itch.io':<12}  {t('credits_itch_soon')}{Style.RESET_ALL}")

    print()
    print_divider()
    print()
    type_text(Fore.YELLOW + Style.DIM + t('credits_star_note') + Style.RESET_ALL, 0.018)
    print()
    time.sleep(0.4)
    print_divider()

    wait_for_keypress()
