import random
import sys
import time
import os
import json
import constants
import sound
from sys_log import track, setup_global_exception_hook
from colorama import Fore, Style, init as colorama_init
from rich.console import Console
from i18n import t, set_lang, db_t
from updater import check_and_prompt_update

from core import init_and_load_db, get_save_path, save_data
from ui import (clear_screen, type_text, print_header, print_divider,
                print_ambient_lore, read_key, wait_for_keypress,
                ea_center, ea_rpad, log_diary, show_diary,
                roll_medkit, roll_food, roll_water)
from player import Player
from map import GameMap
from combat import combat_loop, get_encounter_chance, apply_dynamic_scaling
from quest import handle_random_event, handle_trader, advance_quest, trigger_sudden_quest
from story import handle_session, run_prologue, run_boss_core_choice, run_ending

_console = Console(highlight=False)

init_and_load_db()


@track
def run_game():
    os.system('title PROTOCOL: STIGMA — 1막: 낙인')
    os.system('mode con: cols=90 lines=40')
    os.system('color 0B')
    colorama_init(autoreset=True)

    set_lang("ko")  # 기본값
    check_and_prompt_update(constants.GAME_VERSION, console=_console)

    player = Player()
    grid = GameMap()

    while True:  # 타이틀 ~ 설정 루프
        clear_screen()
        print()
        ver_str = f"v{constants.GAME_VERSION}"
        ver_pad = " " * (74 - len(ver_str))
        print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + ea_center("P  R  O  T  O  C  O  L  :  S  T  I  G  M  A", 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.CYAN  + Style.BRIGHT + "  ║" + ea_center(t("title_subtitle"), 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ╠" + "═" * 74 + "╣")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.CYAN  + "  ║" + ea_center(t("title_quote1"), 74) + "║")
        print(Fore.CYAN  + "  ║" + ea_center(t("title_quote2"), 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.DIM    + "  ║" + ver_pad + ver_str + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
        print()

        has_save = os.path.exists(get_save_path())
        print_divider()
        print(f"  1. {t('menu_new_game')}")
        if has_save:
            print(f"  2. {t('menu_load_game')}")
        opt_key = "3" if has_save else "2"
        exit_key = "4" if has_save else "3"
        print(f"  {opt_key}. {t('menu_options')}")
        print(f"  {exit_key}. {t('menu_exit')}")
        print_divider()

        ans = read_key()

        # ── 종료 ──────────────────────────────────────────────────────────
        if ans == exit_key:
            clear_screen()
            type_text(f"  {t('exit_msg')}", 0.025)
            time.sleep(0.5)
            sys.exit()

        # ── 옵션 (언어 선택) ──────────────────────────────────────────────
        if ans == opt_key:
            while True:
                clear_screen()
                print_header(t('menu_options'))
                print_divider()
                print(f"  {t('lang_header')}")
                print_divider()
                print(f"  1. {t('lang_ko')}")
                print(f"  2. {t('lang_en')}")
                print_divider()
                print(f"  0. {t('diff_back')}")
                print_divider()
                lk = read_key()
                if lk == "1":
                    set_lang("ko")
                    break
                elif lk == "2":
                    set_lang("en")
                    break
                elif lk == "0":
                    break
            continue

        # ── 세이브 로드 ───────────────────────────────────────────────────
        if ans == "2" and has_save:
            player = Player()
            grid = GameMap()
            try:
                with open(get_save_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                player.from_dict(data["player"])
                grid.from_dict(data["grid"])
                clear_screen()
                type_text(f"  {t('load_success')}", 0.02)
            except Exception as e:
                type_text(f"  {t('load_fail', e=e)}", 0.02)
            wait_for_keypress()
            break  # 게임 루프 진입

        # ── 새로운 게임 ───────────────────────────────────────────────────
        if ans == "1":
            player = Player()
            grid = GameMap()
            go_back = False

            while True:  # 난이도 선택 루프
                clear_screen()
                print_header(t("diff_header"))
                print(f"  {t('diff_desc1')}")
                print(f"  {t('diff_desc2')}\n")
                print(f"  1. {t('diff_easy')}")
                print(f"  2. {t('diff_normal')}")
                print(f"  3. {t('diff_hard')}")
                print_divider()
                print(f"  0. {t('diff_back')}")
                print_divider()

                diff_map = {"1": "easy", "2": "normal", "3": "hard"}
                diff_ans = read_key()

                if diff_ans == "0":
                    go_back = True
                    break

                if diff_ans in diff_map:
                    player.difficulty = diff_map[diff_ans]
                    run_prologue()
                    log_diary(player, t('game_log_start'))
                    break

                print(f"\n  {t('diff_invalid')}")
                time.sleep(0.8)

            if go_back:
                continue  # 타이틀 루프 재시작
            break  # 게임 루프 진입

        # 잘못된 입력 → 타이틀 재표시

    sound.play_map_ambient()
    while True:
        clear_screen()
        if player.active_quest and player.turn_count > player.active_quest["deadline"]:
            q = player.active_quest
            print(t('quest_failed', title=q['title']))
            log_diary(player, t('quest_fail_diary', title=q['title']))
            player.active_quest = None
            time.sleep(1.5)
            clear_screen()
        grid.draw(player.turn_count)
        player.show_status()

        print(f" {t('cmd_header')}")
        print(f"  {t('cmd_move')}")
        print(f"  {t('cmd_search')}")
        print(f"  {t('cmd_inventory')}")
        print(f"  {t('cmd_diary')}")
        print(f"  {t('cmd_save')}")
        print(f"  {t('cmd_quit')}")
        print_divider()

        move = read_key()

        if move == "I":
            player.manage_inventory()
            continue
        elif move == "J":
            show_diary(player)
            continue
        elif move == "C":
            save_data(player, grid)
            continue

        if move == "F":
            _can_srch, _ = grid.can_search(player.turn_count)
            if not _can_srch:
                print(f"\n  {random.choice(t('tile_exhausted'))}")
                wait_for_keypress()
                continue

            player.consume_resources()
            grid.use_search(player.turn_count)
            print(t('search_start'))
            time.sleep(0.5)

            encounter_chance = get_encounter_chance(player)
            roll = random.random()

            if roll < 0.08 and constants.TRADER_ITEMS:
                # 행상인 NPC 조우 (8%)
                handle_trader(player)
            elif roll < 0.08 + encounter_chance:
                # 전투 조우 (encounter_chance%)
                print(t('encounter_warning'))
                wait_for_keypress()
                # 바이오 하운드 20% 확률 등장 (재조우 시 이전 타입 유지)
                if grid.escaped_enemy_hp is not None:
                    etype = grid.escaped_enemy_type or "drone"
                else:
                    etype = "bio_hound" if random.random() < 0.20 else "drone"
                sound.play_combat_bgm()
                result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                grid.escaped_enemy_hp = result_hp
                grid.escaped_enemy_type = result_type
                sound.resume_map_ambient()
            elif roll < 0.08 + encounter_chance + 0.20 and constants.RANDOM_EVENTS:
                # 랜덤 서사 이벤트 (20%)
                event = random.choice(constants.RANDOM_EVENTS)
                handle_random_event(player, event)
            elif roll < 0.08 + encounter_chance + 0.20 + 0.30:
                # 공탐색 — 분위기 로그 (30%)
                _empty = random.choice(t('empty_search_msgs'))
                print(f"\n  {_empty}")
                print_ambient_lore()
            else:
                # 자원 파밍 (나머지 ~22%)
                item_roll = random.random()
                if item_roll <= 0.25:
                    gained = random.randint(10, 25)
                    player.materials += gained
                    advance_quest(player, "scrap", gained)
                    print(t('farm_scrap', gained=gained))
                elif item_roll <= 0.60:
                    if random.random() < 0.5:
                        it = roll_food()
                        player.consumables[it] += 1
                        print(t('farm_food', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
                    else:
                        it = roll_water()
                        player.consumables[it] += 1
                        print(t('farm_water', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
                else:
                    it = roll_medkit()
                    player.consumables[it] += 1
                    print(t('farm_medkit', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
                wait_for_keypress()
            # 탐색 퀘스트 진행 및 돌발 퀘스트 (전투 미조우 시)
            if not (0.08 <= roll < 0.08 + encounter_chance):
                advance_quest(player, "search")
                if roll >= 0.08 + encounter_chance + 0.20:
                    trigger_sudden_quest(player)
            continue
        elif move == "Q":
            clear_screen()
            print_header(t("quit_header"))
            print()
            type_text(t("quit_prompt"), 0.02)
            print()
            print(t("quit_yn"), end="", flush=True)
            save_choice = read_key()
            if save_choice == 'Y':
                save_data(player, grid)
                print(t("quit_saved"))
            else:
                print(t("quit_nosave"))
            print()
            print("  ╔" + "═" * 74 + "╗")
            print("  ║  " + ea_rpad(t("quit_banner"), 72) + "║")
            print("  ╚" + "═" * 74 + "╝")
            print()
            time.sleep(0.8)
            sys.exit()

        px, py = grid.player_pos[0], grid.player_pos[1]
        valid_move = False
        if move == "W" and py < grid.size - 1: py += 1; valid_move = True
        elif move == "S" and py > 0: py -= 1; valid_move = True
        elif move == "A" and px > 0: px -= 1; valid_move = True
        elif move == "D" and px < grid.size - 1: px += 1; valid_move = True
        else:
            print(f"\n{t('move_blocked')}")
            time.sleep(0.5)
            continue

        if valid_move:
            grid.player_pos = [px, py]
            player.consume_resources()

            current_loc = tuple(grid.player_pos)
            is_new_tile = current_loc not in grid.visited_tiles
            grid.visited_tiles.add(current_loc)

            if current_loc == tuple(grid.bunker_pos):
                if constants.SESSIONS_DB and len(constants.SESSIONS_DB) > 6:
                    handle_session(player, constants.SESSIONS_DB[6])
                # 보스전 준비 화면
                log_diary(player, t('boss_log_prep'))
                clear_screen()
                print_header(t('boss_alert_header'))
                type_text(t('boss_approach_1'), 0.025)
                type_text(t('boss_approach_2'), 0.025)
                type_text(t('boss_approach_3'), 0.025)
                print()
                type_text(t('boss_approach_4'), 0.025)
                type_text(t('boss_approach_5'), 0.025)
                print()
                type_text(t('boss_approach_6') + "\n", 0.025)
                while True:
                    print_divider()
                    tier_now = player.get_highest_tier()
                    _, disp_hp_now, _ = apply_dynamic_scaling(0, player.hp, tier_now)
                    _, disp_maxhp_now, _ = apply_dynamic_scaling(0, player.max_hp, tier_now)
                    print(t('boss_prep_status', hp=f"{disp_hp_now:,}", maxhp=f"{disp_maxhp_now:,}", hunger=player.hunger, thirst=player.thirst, scrap=player.materials))
                    print_divider()
                    print(t('boss_prep_1'))
                    print(t('boss_prep_2'))
                    print(t('boss_prep_3'))
                    prep_cmd = read_key()
                    if prep_cmd == "1":
                        player.use_consumable_menu()
                    elif prep_cmd == "2":
                        save_data(player, grid)
                    elif prep_cmd == "3":
                        break
                sound.play_combat_bgm()
                combat_loop(player, is_boss=True)
                run_boss_core_choice(player)
                run_ending(player)
                break
            else:
                session_triggered = False
                if is_new_tile and constants.SESSIONS_DB and grid.session_index < len(constants.SESSIONS_DB) - 1:
                    _s_base = 0.40 if grid.session_index < 3 else 0.10
                    _s_prob = max(0.05, _s_base * (1.0 - player.turn_count / 100.0))
                    if random.random() < _s_prob:
                        print(t('scan_detected'))
                        time.sleep(1.2)
                        handle_session(player, constants.SESSIONS_DB[grid.session_index])
                        grid.session_index += 1
                        session_triggered = True

                if not session_triggered:
                    if random.random() < get_encounter_chance(player):
                        print(t('encounter_alert'))
                        wait_for_keypress()
                        if grid.escaped_enemy_hp is not None:
                            etype = grid.escaped_enemy_type or "drone"
                        else:
                            etype = "bio_hound" if random.random() < 0.20 else "drone"
                        sound.play_combat_bgm()
                        result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                        grid.escaped_enemy_hp = result_hp
                        grid.escaped_enemy_type = result_type
                        sound.resume_map_ambient()
                    else:
                        if random.random() < 0.2:
                            print_ambient_lore()


if __name__ == "__main__":
    setup_global_exception_hook()
    sound.init()
    run_game()
