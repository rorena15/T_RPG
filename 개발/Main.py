# Main.py — 진입점 및 메인 게임 루프
# 의존성: 전 모듈 조율

import os
import sys
import json
import time
import math
import random
from rich.console import Console
from colorama import Fore, Back, Style, init as colorama_init
import constants
from core import get_save_path, save_data
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, safe_input, read_key, log_diary,
                show_diary, print_ambient_lore, roll_medkit, roll_food, roll_water,
                ea_center, ea_rpad)
from player import Player
from map import GameMap
from combat import combat_loop, get_encounter_chance, apply_dynamic_scaling
from quest import trigger_sudden_quest, handle_random_event, handle_trader, advance_quest
from story import handle_session, run_prologue, run_boss_core_choice, run_ending
from updater import check_and_prompt_update
from sys_log import sys_log, track, track_event
import core

_console = Console(highlight=False)

def run_game():
    os.system('title PROTOCOL: STIGMA — 1막: 낙인')
    os.system('mode con: cols=90 lines=40')
    os.system('color 0B')
    colorama_init(autoreset=True)
    check_and_prompt_update(constants.GAME_VERSION, console=_console)
    player = Player()
    grid = GameMap()

    while True:  # 타이틀 ~ 설정 루프
        clear_screen()
        print()
        print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + ea_center("P  R  O  T  O  C  O  L  :  S  T  I  G  M  A", 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.CYAN  + Style.BRIGHT + "  ║" + ea_center("1막: 낙인  —  시스템이 폐기한 불량 코드", 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ╠" + "═" * 74 + "╣")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.CYAN  + "  ║" + ea_center("\"세상이 당신을 거부했다면,", 74) + "║")
        print(Fore.CYAN  + "  ║" + ea_center("당신은 세상의 규칙 밖에서 숨 쉬는 법을 배워야 한다.\"", 74) + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
        print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
        print()

        has_save = os.path.exists(get_save_path())
        print_divider()
        print("  1. 새로운 게임 (New Game)")
        if has_save:
            print("  2. 동기화 복구 (Load Game)")
        exit_key = "3" if has_save else "2"
        print(f"  {exit_key}. 시스템 종료 (Exit)")
        print_divider()

        ans = read_key()

        # ── 종료 ──────────────────────────────────────────────────────────
        if ans == exit_key:
            clear_screen()
            type_text("  [SYSTEM] 그리드 접속을 종료합니다.", 0.025)
            time.sleep(0.5)
            sys.exit()

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
                type_text("  [SYSTEM] 로컬 백업소에서 생체 신호를 성공적으로 복구했습니다.", 0.02)
            except Exception as e:
                type_text(f"  [ERROR] 데이터 파일 손상 ({e}). 초기화 프로토콜을 가동합니다.", 0.02)
            wait_for_keypress()
            break  # 게임 루프 진입

        # ── 새로운 게임 ───────────────────────────────────────────────────
        if ans == "1":
            player = Player()
            grid = GameMap()
            go_back = False

            while True:  # 난이도 선택 루프
                clear_screen()
                print_header("난이도 선택 (DIFFICULTY PROTOCOL)")
                print("  진행 턴이 누적될수록 적의 체력과 공격력이 함께 상승합니다.")
                print("  상승 속도는 난이도에 따라 달라집니다.\n")
                print("  1. 이지   (EASY)   — 세상은 당신을 환영하며 따뜻하게 맞이 할 것 입니다")
                print("  2. 노멀   (NORMAL) — 아직 세상은 따듯할 수도 있습니다")
                print("  3. 하드   (HARD)   — 세상은 당신을 증오 합니다, 살아 남을 수 있을 까요?")
                print_divider()
                print("  0. 메인 화면으로 돌아가기")
                print_divider()

                diff_map = {"1": "easy", "2": "normal", "3": "hard"}
                diff_ans = read_key()

                if diff_ans == "0":
                    go_back = True
                    break

                if diff_ans in diff_map:
                    player.difficulty = diff_map[diff_ans]
                    run_prologue()
                    log_diary(player, "[시작] 생존 프로토콜 개시 — N-404, 데드존 투입")
                    break

                print("\n  [오류] 1, 2, 3 중에서 선택하십시오.")
                time.sleep(0.8)

            if go_back:
                continue  # 타이틀 루프 재시작
            break  # 게임 루프 진입

        # 잘못된 입력 → 타이틀 재표시

    while True:
        clear_screen()
        if player.active_quest and player.turn_count > player.active_quest["deadline"]:
            q = player.active_quest
            print(f"\n  [퀘스트 실패] '{q['title']}' — 제한 턴 초과")
            log_diary(player, f"[퀘스트 실패] {q['title']}")
            player.active_quest = None
            time.sleep(1.5)
            clear_screen()
        grid.draw()
        player.show_status()

        print(" [명령 프로토콜]")
        print("  W, A, S, D  : 그리드 이동")
        print("  F           : 현재 타일 탐색 및 자원 파싱")
        print("  I           : 인벤토리 및 시스템 정비")
        print("  J           : 항법 일지 열람")
        print("  C           : 현재 상태 로컬 백업 (저장)")
        print("  Q           : 시스템 접속 종료 (Exit)")
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
            player.consume_resources()
            print("\n[행동] 주변의 고철 더미를 뒤지기 시작합니다...")
            time.sleep(0.5)

            encounter_chance = get_encounter_chance(player)
            roll = random.random()

            if roll < 0.08 and constants.TRADER_ITEMS:
                handle_trader(player)
            elif roll < 0.08 + encounter_chance:
                print("\n[경고] 탐색 중 발생한 소음이 기계 괴수를 끌어들였습니다!")
                wait_for_keypress()
                if grid.escaped_enemy_hp is not None:
                    etype = grid.escaped_enemy_type or "drone"
                else:
                    etype = "bio_hound" if random.random() < 0.20 else "drone"
                result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                grid.escaped_enemy_hp = result_hp
                grid.escaped_enemy_type = result_type
            elif roll < 0.08 + encounter_chance + 0.20 and constants.RANDOM_EVENTS:
                event = random.choice(constants.RANDOM_EVENTS)
                handle_random_event(player, event)
            elif roll < 0.08 + encounter_chance + 0.20 + 0.30:
                _empty = random.choice([
                    "적막만이 돌아옵니다. 이 구역은 이미 누군가 쓸고 간 흔적입니다.",
                    "먼지와 녹슨 고철 외에는 쓸만한 게 없습니다.",
                    "바람 소리와 정적뿐. 오늘은 운이 따르지 않습니다.",
                    "탐색에 성과가 없었습니다. 허기와 갈증만 소모됩니다.",
                    "이 구역은 완전히 비어 있습니다. 다른 스캐벤저가 먼저였을 겁니다.",
                    "콘크리트 파편과 연소된 배선만 남아 있습니다.",
                ])
                print(f"\n  {_empty}")
                print_ambient_lore()
            else:
                item_roll = random.random()
                if item_roll <= 0.25:
                    gained = random.randint(10, 25)
                    player.materials += gained
                    advance_quest(player, "scrap", gained)
                    print(f"\n[획득] 엉켜있는 배선에서 일반 고철 {gained}개를 주웠습니다.")
                elif item_roll <= 0.60:
                    if random.random() < 0.5:
                        it = roll_food()
                        player.consumables[it] += 1
                        print(f"\n[획득] 낡은 컨테이너에서 '{constants.CONSUMABLES_DB[it]['name']}' 1개를 발견했습니다.")
                    else:
                        it = roll_water()
                        player.consumables[it] += 1
                        print(f"\n[획득] 끊어진 냉각 파이프에서 '{constants.CONSUMABLES_DB[it]['name']}' 1개를 추출했습니다.")
                else:
                    it = roll_medkit()
                    player.consumables[it] += 1
                    print(f"\n[획득] 구석의 구급 상자에서 희귀한 '{constants.CONSUMABLES_DB[it]['name']}' 1개를 획득했습니다.")
                wait_for_keypress()
            if not (0.08 <= roll < 0.08 + encounter_chance):
                advance_quest(player, "search")
                if roll >= 0.08 + encounter_chance + 0.20:
                    trigger_sudden_quest(player)
            continue
        elif move == "Q":
            clear_screen()
            print_header("생체 접속 종료 — 그리드 이탈")
            print()
            type_text("  현재까지의 당신의 흔적을 세상에 남겨 두시겠습니까?", 0.02)
            print()
            print("  저장 후 종료하시겠습니까? (Y/N): ", end="", flush=True)
            save_choice = read_key()
            if save_choice == 'Y':
                save_data(player, grid)
                print("\n  [SYSTEM] 데이터 동기화 완료. 그리드 접속을 종료합니다.")
            else:
                print("\n  [SYSTEM] 저장 없이 이탈합니다. 진행 기록은 소실됩니다.")
            print()
            print("  ╔" + "═" * 74 + "╗")
            print("  ║  " + ea_rpad("생체 접속 종료. 그리드망에서 이탈합니다.", 72) + "║")
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
            print("\n[거부] 이동 불가능한 폐기물 장벽입니다.")
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
                log_diary(player, "[보스] 스캐브 컬렉터 추적 확인 — 최종 전투 준비")
                clear_screen()
                print_header("!! CRITICAL ALERT — 스캐브 컬렉터 접근 중 !!")
                type_text("  지면이 거대하게 진동하기 시작합니다.", 0.025)
                type_text("  수십 개의 유압 분쇄 칼날과 회수 집게를 펼치며,", 0.025)
                type_text("  총괄국의 자동화 청소기계 '스캐브 컬렉터'가 벙커를 향해 돌진해 옵니다.", 0.025)
                print()
                type_text("  사이버덱에 경보가 떴습니다 ─ [추적 목표: N-404 / 회수 우선순위: 최고 등급]", 0.025)
                type_text("  이 기계는 처음부터 당신을 추적하고 있었습니다.", 0.025)
                print()
                type_text("  이 문이 부서지면 내일은 없습니다. 마지막 준비를 완료하십시오.\n", 0.025)
                while True:
                    print_divider()
                    tier_now = player.get_highest_tier()
                    _, disp_hp_now, _ = apply_dynamic_scaling(0, player.hp, tier_now)
                    _, disp_maxhp_now, _ = apply_dynamic_scaling(0, player.max_hp, tier_now)
                    print(f"  [현재 상태] HP: {disp_hp_now:,}/{disp_maxhp_now:,}  허기: {player.hunger}  갈증: {player.thirst}  고철: {player.materials}")
                    print_divider()
                    print("  1. 소모품 사용")
                    print("  2. 현재 상태 저장")
                    print("  3. 보스전 돌입 (ENTER COMBAT)")
                    prep_cmd = read_key()
                    if prep_cmd == "1":
                        player.use_consumable_menu()
                    elif prep_cmd == "2":
                        save_data(player, grid)
                    elif prep_cmd == "3":
                        break
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
                        print("\n  [스캔] 이 구역에서 특이한 반응이 감지됩니다...")
                        time.sleep(1.2)
                        handle_session(player, constants.SESSIONS_DB[grid.session_index])
                        grid.session_index += 1
                        session_triggered = True

                if not session_triggered:
                    if random.random() < get_encounter_chance(player):
                        print("\n[경보] 안개 속에서 기계 괴수의 광학 센서가 번뜩입니다!")
                        wait_for_keypress()
                        if grid.escaped_enemy_hp is not None:
                            etype = grid.escaped_enemy_type or "drone"
                        else:
                            etype = "bio_hound" if random.random() < 0.20 else "drone"
                        result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                        grid.escaped_enemy_hp = result_hp
                        grid.escaped_enemy_type = result_type
                    else:
                        if random.random() < 0.2:
                            print_ambient_lore()


if __name__ == "__main__":
    core.init_and_load_db()
    run_game()
