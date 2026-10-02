import frozen_compat  # noqa: F401  Nuitka exe에서 PyInstaller 전제 경로를 맞춘다. 반드시 첫 import
import archive
import math
import random
import sys
import time
import os
import json
import constants
import sound
import skills
import db_init
from sys_log import sys_log, track, track_event, log_error, setup_global_exception_hook
from colorama import Fore, Back, Style, init as colorama_init
from rich.console import Console
from i18n import t, set_lang, db_t
from updater import check_and_prompt_update

from core import init_and_load_db, get_save_path, save_data, load_settings, save_settings, grant_gear_drop
from ui import (clear_screen, type_text, print_header, print_divider,
                print_ambient_lore, read_key, wait_for_keypress,
                ea_center, ea_rpad, log_diary, show_diary,
                roll_medkit, roll_food, roll_water)
from player import Player
from map import GameMap
from combat import combat_loop, get_encounter_chance, apply_dynamic_scaling, pick_enemy, enemy_line
from quest import handle_random_event, handle_trader, advance_quest, trigger_sudden_quest
from story import handle_session, run_prologue, run_boss_core_choice, run_ending, boss_prep_view
from gui import get_terminal
import gm_bridge
import gm_server
import options
import forge
import playtime
import traits
import scene_art

_console = Console(highlight=False)

init_and_load_db()


def _banner_path() -> str:
    """assets/banner.png 절대 경로 반환 (소스/onefile 모두 대응)."""
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        base = _sys._MEIPASS
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    return os.path.join(base, 'assets', 'banner.png')


def _offer_extra_data(settings, force=False):
    """동적 서사가 켜져 있는데 추가 데이터(모델)가 없으면 받을지 묻는다. 한국어 모드에서만 (서술이 한국어 전용)."""
    import i18n as _i18n
    import download_view
    term = get_terminal()
    mode = gm_bridge.get_mode()
    if term is None or _i18n.LANG != "ko" or (not force and (mode == "off" or gm_bridge.mode_installed(mode))):
        return
    if not gm_server.runtime_ok():  # 실행기가 없는 빌드: 모델을 받아도 쓸 수 없다
        return
    got = download_view.offer(term)
    if got:
        settings["gm_mode"] = got
        save_settings(settings)
        gm_bridge.set_mode(got)


@track
def run_game():
    import diag
    diag.purge_plain_logs()   # 예전 버전의 평문 기록(log.txt, DB events 표)은 지운다 — 진단 기록은 이제 암호화
    if not get_terminal():
        if os.name == 'nt':
            os.system('title PROTOCOL: STIGMA — 1막: 낙인')
            os.system('mode con: cols=90 lines=40')
            os.system('color 0B')
        colorama_init(autoreset=True)
    else:
        colorama_init(strip=False, convert=False, autoreset=False)

    set_lang("ko")  # 기본값

    _settings = load_settings()
    options.apply(_settings, get_terminal())   # 음량·속도·화면 설정 반영 (options.py)
    gm_bridge.set_mode(_settings["gm_mode"])

    _title_scenes = ["neo_city", "ruin_city", "scrap_sea", "junkyard", "lm_cathedral"]
    _intro_title = None
    if get_terminal():  # 켤 때 오프닝 (intro_view.py). 마지막 장면이 타이틀 메뉴와 같은 화면이라 그대로 이어진다
        import intro_view
        from screens import MenuScreen
        _intro_title = MenuScreen(scene=random.choice(_title_scenes))
        intro_view.play(get_terminal(), _intro_title.view, "PROTOCOL : STIGMA", t("title_subtitle"))

    check_and_prompt_update(constants.GAME_VERSION, console=_console)
    _offer_extra_data(_settings)

    player = Player()
    grid = _new_map()

    while True:  # 타이틀 ~ 설정 루프
        clear_screen()
        _term = get_terminal()
        has_save = os.path.exists(get_save_path())
        opt_key = "3" if has_save else "2"
        exit_key = "4" if has_save else "3"
        if _term:  # 그림 화면 타이틀 (screens.MenuScreen)
            from screens import MenuScreen
            _title, _intro_title = _intro_title or MenuScreen(scene=random.choice(_title_scenes)), None
            _items = [("1", t('menu_new_game'))] + ([("2", t('menu_load_game'))] if has_save else []) + \
                [(opt_key, t('menu_options')), (exit_key, t('menu_exit'))]
            ans = _title.ask("PROTOCOL : STIGMA", _items, tag=t("title_subtitle"), hero=True,
                             lines=[t("title_quote1") + " " + t("title_quote2"), f"v{constants.GAME_VERSION}"])
            _title.close()
        else:
            ans = None
        if ans is None:
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

            print_divider()
            print(f"  1. {t('menu_new_game')}")
            if has_save:
                print(f"  2. {t('menu_load_game')}")
            print(f"  {opt_key}. {t('menu_options')}")
            print(f"  {exit_key}. {t('menu_exit')}")
            print_divider()

            ans = read_key()

        # ── 종료 ──────────────────────────────────────────────────────────
        if ans == exit_key:
            clear_screen()
            if _term:
                from screens import MenuScreen
                _bye = MenuScreen(scene="neo_city")
                _bye.message("PROTOCOL : STIGMA", [t('exit_msg')], hold_ms=1400)
                _bye.close()
                sys.exit()
            type_text(f"  {t('exit_msg')}", 0.025)
            time.sleep(0.5)
            sys.exit()

        # ── 옵션 (options.py: 소리 · 화면 · 게임) ───────────────────────────
        if ans == opt_key:
            options.run(_settings, _term, offer_data=_offer_extra_data)
            continue

        # ── 세이브 로드 ───────────────────────────────────────────────────
        if ans == "2" and has_save:
            player = Player()
            grid = _new_map()
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
            grid = _new_map()
            go_back = False

            _diff_scr = None
            if _term:
                from screens import MenuScreen
                _diff_scr = MenuScreen(scene="scrap_sea")
            while True:  # 난이도 선택 루프
                clear_screen()
                diff_map = {"1": "easy", "2": "normal", "3": "hard"}
                if _diff_scr:
                    diff_ans = _diff_scr.ask(t("diff_header"), [("1", t('diff_easy')), ("2", t('diff_normal')),
                                                                ("3", t('diff_hard')), ("0", t('diff_back'))],
                                             lines=[t('diff_desc1') + " " + t('diff_desc2')], back="0", start=1)
                    _diff_scr.close()
                    if diff_ans == "0":
                        go_back = True
                        break
                    player.difficulty = diff_map[diff_ans]
                    run_prologue()
                    log_diary(player, t('game_log_start'))
                    break
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
    playtime.start()

    _ui_mgr = None
    if get_terminal():  # 그림 + 이야기 칸 맵 화면 (map_view.py)
        from map_view import MapView
        _ui_mgr = MapView(get_terminal(), player, grid)

    def _off():
        if _ui_mgr:
            _ui_mgr.deactivate()

    # 그림 화면 발밑 버튼: (보이는 키, 설명, 쓸 수 있음, 누르면 보낼 키). 글자 키(WASD·F·I·J·C·Q·U)도 그대로 된다 (map_view.KEYMAP)
    _EXPLORE_ACTIONS = [
        ("WASD", t('act_move'),      True, None),
        ("F",    t('act_search'),    True, "F"),
        ("I",    t('act_inventory'), True, "I"),
        ("J",    t('act_diary'),     True, "J"),
        ("F5",   t('act_save'),      True, "C"),
        ("Esc",  t('act_quit'),      True, "Q"),
    ]

    _autosaved = player.turn_count   # 마지막으로 자동 저장한 턴
    while True:
        clear_screen()
        if constants.AUTOSAVE_TURNS and player.turn_count - _autosaved >= constants.AUTOSAVE_TURNS:
            _autosaved = player.turn_count
            save_data(player, grid, wait=False)
            print(t('autosave_done'))
        if player.active_quest and player.turn_count > player.active_quest["deadline"]:
            q = player.active_quest
            sound.sfx("quest_fail")
            print(t('quest_failed', title=db_t(q, 'title')))
            log_diary(player, t('quest_fail_diary', title=db_t(q, 'title')))
            player.active_quest = None
            time.sleep(1.5)
            clear_screen()

        sound.map_mood(scene_art.world_time(player.turn_count))  # 밤·새벽엔 바람 밑에 어두운 음악
        sound.map_weather(scene_art.world_weather(player.turn_count))  # 날씨 환경음 (산성비·먼지 폭풍 등)
        if forge.check_hint(player, grid):  # 발칸을 오래 못 만났으면 방향 힌트 (forge.py)
            time.sleep(1.2)
        if getattr(grid, "is_node_map", False):   # 지점 지도: 이 지점의 권역(적 세기)과 방공호 힌트
            player.zone_danger = grid.danger_at()
            _bh = grid.bunker_hint_check()
            if _bh:
                print(_bh)
                log_diary(player, _bh.strip())
                time.sleep(1.2)
        _trait_lines = traits.check_new(player)  # 성향이 새 단계에 닿았으면 알림 (traits.py)
        if _trait_lines:
            sound.sfx("job")
            for _ln in _trait_lines:
                print(_ln)
                log_diary(player, _ln.strip())
            time.sleep(1.2)
        _actions = _EXPLORE_ACTIONS
        if grid.at_forge() and grid.forge_known():  # 강화소 칸: U로 발칸 게이츠 / 강화소 (forge.py)
            _flabel = t('act_forge') if forge.built(grid) else t('act_forge_npc')
            _actions = _EXPLORE_ACTIONS[:3] + [("E", _flabel, True, "U")] + _EXPLORE_ACTIONS[3:]
        if _ui_mgr:
            _ui_mgr.update(player, grid)
            _ui_mgr.set_actions(_actions)
            _ui_mgr.activate()
        else:
            grid.draw()
            player.show_status()
            if list(grid.player_pos) != list(grid.bunker_pos):
                print(f"  {t(f'map_danger_{grid.danger_at()}')}" + (t('map_depleted', n=grid.depletion()) if grid.depletion() else ""))
            print(f" {t('cmd_header')}")
            print(f"  {t('cmd_move')}")
            print(f"  {t('cmd_search')}")
            print(f"  {t('cmd_inventory')}")
            if grid.forge.get("stage", 0) == 1:
                print(f"  {forge.progress_text(player, grid)}")
            if grid.at_forge() and grid.forge_known():
                print(f"  {t('cmd_forge') if forge.built(grid) else t('cmd_forge_npc')}")
            print(f"  {t('cmd_diary')}")
            print(f"  {t('cmd_quick')}")
            print(f"  {t('cmd_save')}")
            print(f"  {t('cmd_quit')}")
            print_divider()

        playtime.mark(player)                       # 지난 입력 뒤 이벤트·전투 처리 시간
        move = read_key()
        playtime.mark(player, playtime.IDLE_CAP)    # 입력을 기다린 시간 (자리 비움은 5분까지만)

        if move in Player.QUICK_KEYS:  # 퀵슬롯 1~0: 바로 먹고 마시고 치료 (턴은 쓰지 않는다)
            _qk = player.quick_item(move)
            _qmsg = player.use_consumable(_qk) if _qk else None
            if _qmsg:
                print(_qmsg)
            elif _qk:
                print(t('qs_none_left', name=db_t(constants.CONSUMABLES_DB[_qk], 'name')))
            else:
                print(t('qs_empty', n=move))
            if not _ui_mgr:
                time.sleep(0.8)
            continue
        if move == "\x1b":   # 글 화면에서 Esc
            move = "Q"
        elif move == "E":     # 글 화면: E = 강화소 (그림 화면은 map_view.KEYMAP이 바꿔 준다)
            move = "U"
        if move == "I":
            _off()
            player.manage_inventory()
            continue
        elif move == "U" and grid.at_forge() and grid.forge_known():
            _off()
            forge.visit(player, grid)
            continue
        elif move == "J":
            _off()
            sound.sfx("diary")
            show_diary(player)
            continue
        elif move == "C":
            save_data(player, grid)
            continue

        if move == "F":
            # 타일마다 수색 횟수(2~4회)가 있고, 다 쓰면 8~14턴 쿨타임 (map.py). 7785fff에서 빠졌던 것을 되살림
            _can_srch, _ = grid.can_search(player.turn_count)
            if not _can_srch:
                print(f"\n  {random.choice(t('tile_exhausted'))}")
                wait_for_keypress()
                continue
            player.consume_resources()
            grid.use_search(player.turn_count)
            sound.sfx("search")
            print(t('search_start'))
            time.sleep(0.5)

            _danger = grid.danger_at()                     # 칸 위험도: 조우·보상 배율 (constants.DANGER_*)
            _yield = 1.0 / (1.0 + constants.DEPLETE * grid.depletion())   # 다시 채워진 칸은 덜 나온다
            encounter_chance = get_encounter_chance(player) * constants.DANGER_ENC[_danger]
            roll = random.random()

            if roll < 0.08 and constants.TRADER_ITEMS:
                # 행상인 NPC 조우 (8%)
                _off()
                handle_trader(player)
            elif roll < 0.08 + encounter_chance:
                # 전투 조우 (encounter_chance%). 적 종류는 combat.pick_enemy (재조우 시 이전 타입 유지)
                if grid.escaped_enemy_hp is not None:
                    etype = grid.escaped_enemy_type or "drone"
                else:
                    etype = pick_enemy(player)
                print(enemy_line('encounter_warning', etype))
                wait_for_keypress()
                _off()
                sound.play_combat_bgm()
                result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                grid.escaped_enemy_hp = result_hp
                grid.escaped_enemy_type = result_type
                sound.resume_map_ambient()
            elif roll < 0.08 + encounter_chance + 0.20 and constants.RANDOM_EVENTS:
                # 랜덤 서사 이벤트 (20%) — 로컬 GM이 판정·서술, GM을 못 쓰면 대본
                if archive.hidden_ready():   # 기록 보관소 히든: 일지의 마지막 장 (평생 한 번, 수치 변화 없음)
                    from screens import run_hidden_event
                    run_hidden_event(player, grid)
                else:
                    event = random.choice(constants.RANDOM_EVENTS)
                    # GM이 꺼져 있어도 그림 화면이 있으면 같은 틀로 대본을 보여 준다 (gm_bridge.run_event_script)
                    if not gm_bridge.run_event(player, grid, event) and not gm_bridge.run_event_script(player, grid, event):
                        _off()
                        handle_random_event(player, event)
            elif roll < 0.08 + encounter_chance + 0.20 + 0.30:
                # 공탐색 (30%) — 로컬 GM이 서술, GM을 못 쓰면 분위기 로그
                if not gm_bridge.run_search(player, grid):
                    sound.sfx("search_empty")
                    _empty = random.choice(t('empty_search_msgs'))
                    print(f"\n  {_empty}")
                    print_ambient_lore()
                _frag = archive.roll_fragment(player, grid)   # 기록 보관소: 빈 탐색에서 일기 조각 (자원 확률과 무관)
                if _frag:
                    sound.sfx("loot")
                    print(_frag)
            else:
                # 자원 파밍 (나머지 ~22%). 칸 위험도에 따른 확률(DANGER_GEAR)로 자원 대신 장비
                _depleted = random.random() > _yield   # 여러 번 뒤진 칸: 이미 누가 다 가져갔다
                gear_msg = (grant_gear_drop(player, constants.DANGER_TIER_WEIGHTS.get(_danger))
                            if not _depleted and random.random() < constants.DANGER_GEAR[_danger] else None)
                item_roll = random.random()
                if _depleted:
                    sound.sfx("search_empty")
                    print(f"\n  {random.choice(t('search_depleted'))}")
                elif gear_msg:
                    print(gear_msg)
                elif item_roll <= 0.25:
                    gained = traits.scrap(player, max(1, round(random.randint(10, 25) * constants.DANGER_SCRAP[_danger])))
                    player.materials += gained
                    advance_quest(player, "scrap", gained)
                    sound.sfx("loot")
                    print(t('farm_scrap', gained=gained))
                elif item_roll <= 0.60:
                    if random.random() < 0.5:
                        it = roll_food()
                        player.consumables[it] += 1
                        sound.sfx("loot", 0.7)
                        print(t('farm_food', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
                    else:
                        it = roll_water()
                        player.consumables[it] += 1
                        sound.sfx("loot", 0.7)
                        print(t('farm_water', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
                else:
                    it = roll_medkit()
                    player.consumables[it] += 1
                    sound.sfx("loot", 0.7)
                    print(t('farm_medkit', name=db_t(constants.CONSUMABLES_DB[it], 'name')))
                wait_for_keypress()
            # 탐색 퀘스트 진행 및 돌발 퀘스트 (전투 미조우 시)
            if not (0.08 <= roll < 0.08 + encounter_chance):
                advance_quest(player, "search")
                if roll >= 0.08 + encounter_chance + 0.20:
                    trigger_sudden_quest(player)
            continue
        elif move == "Q":
            _off()
            clear_screen()
            if _ui_mgr:  # 그림 화면: 저장하고 종료 / 저장 없이 종료 / 취소 (방향키·마우스)
                from screens import MenuScreen
                _q = MenuScreen(scene="bunker_inside")
                _qa = _q.ask(t("quit_header"), [("1", t('quit_opt_save')), ("2", t('quit_opt_nosave')), ("0", t('quit_opt_cancel'))],
                             lines=[t("quit_prompt").strip()], back="0")
                _q.close()
                if _qa not in ("1", "2"):
                    continue
                save_choice = "Y" if _qa == "1" else "N"
            else:
                print_header(t("quit_header"))
                print()
                type_text(t("quit_prompt"), 0.02)
                print()
                print(t("quit_yn"), end="", flush=True)
                save_choice = read_key()
                if save_choice not in ("Y", "N"):  # 예전엔 다른 키면 저장 없이 꺼졌다: 이제는 취소
                    continue
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

        if getattr(grid, "is_node_map", False):   # 지점 지도: G로 이어진 지점 고르기 (조작은 3단계 화면에서 다시 정한다)
            if move != "G":
                continue
            _dest = _pick_node(grid)
            if _dest is None:
                continue
            _road(player, grid, _dest)
            px, py = _dest
            valid_move = True
        elif move not in ("W", "A", "S", "D"):  # 모르는 키는 조용히 무시 (예전엔 "이동 불가"를 띄우고 멈췄다)
            continue
        else:
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
            if getattr(grid, "is_node_map", False):
                grid.arrive()
                player.zone_danger = grid.danger_at()
            player.consume_resources()

            current_loc = tuple(grid.player_pos)
            is_new_tile = current_loc not in grid.visited_tiles
            grid.visited_tiles.add(current_loc)
            sound.sfx("step")
            if _ui_mgr:  # 그림 화면: 장면이 옮겨 가는 연출 (map_view.py)
                _ui_mgr.update(player, grid)
                _ui_mgr.play_move()

            if current_loc == tuple(grid.bunker_pos):
                sound.sfx("bunker_door")   # 녹슨 무쇠 문
                if constants.SESSIONS_DB and len(constants.SESSIONS_DB) > 6:
                    _off()
                    handle_session(player, constants.SESSIONS_DB[6])
                # 보스전 준비 화면
                log_diary(player, t('boss_log_prep'))
                _off()
                clear_screen()
                if constants.AUTOSAVE_TURNS:   # 보스 앞에서는 늘 한 번 (자동 저장을 켰을 때)
                    save_data(player, grid, wait=False)
                if get_terminal():   # 그림 화면 (story.boss_prep_view). 아래 터미널 판과 규칙이 같다
                    boss_prep_view(player, grid)
                    sound.play_boss_bgm()
                    combat_loop(player, is_boss=True)
                    run_boss_core_choice(player)
                    run_ending(player, grid)
                    break
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
                sound.play_boss_bgm()
                combat_loop(player, is_boss=True)
                run_boss_core_choice(player)
                run_ending(player, grid)
                break
            else:
                if grid.at_forge() and not grid.forge_known():
                    _off()
                session_triggered = forge.on_enter(player, grid, is_new_tile)  # 발칸 게이츠를 만나면 이 칸의 세션은 건너뛴다
                if not session_triggered and is_new_tile and constants.SESSIONS_DB and grid.session_index < len(constants.SESSIONS_DB) - 1:
                    _s_base = 0.40 if grid.session_index < 3 else 0.10
                    _s_prob = max(0.05, _s_base * (1.0 - player.turn_count / 100.0))
                    if random.random() < _s_prob:
                        sound.sfx("scan")
                        print(t('scan_detected'))
                        time.sleep(1.2)
                        _off()
                        handle_session(player, constants.SESSIONS_DB[grid.session_index])
                        grid.session_index += 1
                        session_triggered = True

                if not session_triggered:
                    if random.random() < get_encounter_chance(player):
                        if grid.escaped_enemy_hp is not None:
                            etype = grid.escaped_enemy_type or "drone"
                        else:
                            etype = pick_enemy(player)
                        print(enemy_line('encounter_alert', etype))
                        wait_for_keypress()
                        _off()
                        sound.play_combat_bgm()
                        result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
                        grid.escaped_enemy_hp = result_hp
                        grid.escaped_enemy_type = result_type
                        sound.resume_map_ambient()
                    else:
                        if random.random() < 0.2:
                            print_ambient_lore()


def _new_map():
    """지점 지도는 시험 중이라 constants.NODE_MAP을 켰을 때만 (node_map.py, 봇 전용)."""
    if constants.NODE_MAP:
        from node_map import NodeMap
        return NodeMap()
    return GameMap()


def _pick_node(grid):
    """지점 지도: 이어진 지점 중 하나를 번호로 고른다. 0이면 취소 (None)."""
    roads = grid.neighbors()
    for i, (q, n) in enumerate(roads, 1):
        print(f"  {t('node_road', n=i, name=grid.label(q), turns=n)}")
    print(f"  {t('node_road_cancel')}")
    while True:
        _pick = read_key()
        if _pick in ("0", "\x1b"):
            return None
        if _pick.isdigit() and 1 <= int(_pick) <= len(roads):
            return list(roads[int(_pick) - 1][0])


def _road(player, grid, dest):
    """지점 지도: 2턴 이상인 길은 가는 동안 한 턴마다 자원이 줄고 조우만 굴린다 (도착 턴은 원래 이동 처리)."""
    player.zone_danger = max(grid.danger_at(), grid.danger_at(dest))
    for _ in range(grid.edge_len(grid.player_pos, dest) - 1):
        player.consume_resources()
        if random.random() < get_encounter_chance(player) * constants.ROAD_ENC:
            etype = (grid.escaped_enemy_type or "drone") if grid.escaped_enemy_hp is not None else pick_enemy(player)
            print(enemy_line('encounter_alert', etype))
            wait_for_keypress()
            sound.play_combat_bgm()
            result_hp, result_type = combat_loop(player, is_boss=False, current_hp=grid.escaped_enemy_hp, enemy_type=etype)
            grid.escaped_enemy_hp = result_hp
            grid.escaped_enemy_type = result_type
            sound.resume_map_ambient()


if __name__ == "__main__":
    setup_global_exception_hook()
    if os.name == 'nt':
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    from gui import PygameTerminal, set_terminal
    _term = PygameTerminal()
    set_terminal(_term)
    sys.stdout = _term
    sound.init()
    run_game()
