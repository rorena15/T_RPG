# story.py — 서사 흐름: 세션, 프롤로그, 보스, 엔딩
# 의존성: constants, core, ui, combat, quest, sys_log

import time
import random
import os
import sys
import constants
from colorama import Fore, Back, Style
from core import get_equipment_data
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, safe_input, read_key, log_diary,
                show_diary, ea_rpad, ea_center)
from combat import combat_loop, get_turn_scale_multiplier
from quest import advance_quest
from sys_log import sys_log, log_error
import sound
import skills as _skills

def handle_session(player, session):
    clear_screen()
    sound.play_typing_bgm()
    print_header(session['title'])
    type_text(session['text'], 0.02)
    print()
    for i, choice in enumerate(session['choices']):
        print(f"  [{i+1}] {choice['text']}")
    time.sleep(1)
    while True:
        ans = read_key()
        if ans in ["1", "2", "3"]:
            choice_data = session['choices'][int(ans) - 1]
            choice_weight = choice_data.get('weight')
            if choice_weight:
                player.weights[choice_weight] += 1

            # 장비 / 고철 보상
            if choice_data.get("reward"):
                if choice_data["reward"] == "SCRAP_MAT":
                    mat_gain = choice_data.get("materials", 30)
                    player.materials += mat_gain
                    advance_quest(player, "scrap", mat_gain)
                    print(f"\n[획득] 일반 고철 {mat_gain}개를 회수했습니다.")
                else:
                    player.inventory.append(choice_data["reward"])
                    item_data = get_equipment_data(choice_data["reward"])
                    print(f"\n[보상] 소켓 파싱 완료: 장비 '{item_data['name']}' 코드를 획득했습니다.")

            # 소모품 보상
            if choice_data.get("consumable"):
                key = choice_data["consumable"]
                if key in player.consumables:
                    player.consumables[key] += 1
                    print(f"\n[보상] {constants.CONSUMABLES_DB.get(key, {}).get('name', key)} 1개를 획득했습니다.")

            # 고철 직접 지급 (SCRAP_MAT 없이)
            raw_mat = choice_data.get("materials", 0)
            if raw_mat != 0 and not choice_data.get("reward") == "SCRAP_MAT":
                player.materials = max(0, player.materials + raw_mat)
                if raw_mat > 0:
                    advance_quest(player, "scrap", raw_mat)
                    print(f"\n[획득] 고철 +{raw_mat}개")
                else:
                    print(f"\n[소비] 고철 {raw_mat}개")

            # 생체 상태 변화
            if choice_data.get("hp_loss", 0):
                player.hp = max(1, player.hp - choice_data["hp_loss"])
                print(f"\n[피해] HP -{choice_data['hp_loss']}")
            if choice_data.get("thirst", 0):
                player.thirst = min(100, player.thirst + choice_data["thirst"])
            if choice_data.get("hunger", 0):
                player.hunger = min(100, player.hunger + choice_data["hunger"])
            if choice_data.get("ram_bonus", 0):
                player.max_ram += choice_data["ram_bonus"]
                print(f"\n[시스템] 가용 RAM +{choice_data['ram_bonus']}")

            time.sleep(0.6)
            type_text(f"\n  {choice_data['log']}", 0.025)

            _w_label = {"kinetic": "완력", "scrap": "해체", "cyber": "해킹"}.get(choice_weight, "선택")
            _reward_note = ""
            if choice_data.get("reward") and choice_data["reward"] != "SCRAP_MAT":
                _rd = get_equipment_data(choice_data["reward"])
                _reward_note = f" → {_rd['name']} 획득"
            elif choice_data.get("reward") == "SCRAP_MAT":
                _reward_note = f" → 고철 +{choice_data.get('materials', 30)}"
            if choice_data.get("ram_bonus"):
                _reward_note += f" (RAM +{choice_data['ram_bonus']})"
            log_diary(player, f"[세션] {session['title']} — {_w_label}{_reward_note}")

            if choice_weight and player.weights[choice_weight] >= 3:
                _wcb = {
                    "kinetic": "\n  [행동 패턴 고착화] 물리적 집행이 N-404의 1순위 프로토콜로 등록됩니다.",
                    "scrap":   "\n  [행동 패턴 고착화] 정밀 분해가 N-404의 1순위 프로토콜로 등록됩니다.",
                    "cyber":   "\n  [행동 패턴 고착화] 코드 침투가 N-404의 1순위 프로토콜로 등록됩니다.",
                }
                time.sleep(0.3)
                type_text(_wcb[choice_weight], 0.022)

            sound.resume_map_ambient()
            wait_for_keypress()
            break


def run_prologue():
    """신규 게임 시작 시 전체 프롤로그 시퀀스를 재생합니다."""
    clear_screen()
    print_header("프로토콜: 낙인 — 시퀀스 초기화")
    print()
    print("  [SYSTEM] 서사 시퀀스 로드 완료.")
    print()
    sound.play_typing_bgm()
    print("  1. 프롤로그 재생  (부팅 시퀀스 → 도입 서사 → 세계관 → 조작법)")
    print("  0. 스킵           (즉시 게임 시작)")
    print()
    skip_ans = read_key()
    if skip_ans == "0":
        clear_screen()
        type_text("[SYSTEM] 서사 시퀀스 스킵. 생존 인터페이스 가동.", 0.022)
        time.sleep(0.6)
        return

    clear_screen()

    # ── 단계 1: 부팅 시퀀스 ──────────────────────────────────────────────
    boot_log = [
        ("  [SYSTEM BOOT]   시각 센서 복구 중...   0%", 0.04),
        ("  [SYSTEM BOOT]   시각 센서 복구 중...  12%", 0.04),
        ("  [SYSTEM BOOT]   시각 센서 복구 중...  45%", 0.03),
        ("  [SYSTEM BOOT]   시각 센서 복구 중... 100%", 0.03),
        ("", 0.1),
        ("  [SYSTEM LOG]    바이오 링크 프로토콜 체크 중...", 0.03),
        ("  [ERROR  ]       중앙 서버 핸드셰이크 실패 — 접속 불가.", 0.03),
        ("  [SYSTEM LOG]    유기체 일련번호 조회 중... 'N-404'", 0.03),
        ("  [ERROR  ]       등록되지 않은 코드. 승인 거부.", 0.04),
        ("  [WARNING]       분류: 무국적 불량 코드 (Civilian).", 0.04),
        ("  [SYSTEM ]       시스템 조치: 추적 후 영구 폐기.", 0.04),
    ]
    for line, spd in boot_log:
        type_text(line, spd)
        time.sleep(0.08)

    time.sleep(1.2)
    clear_screen()

    # ── 단계 2: 도입 서사 ────────────────────────────────────────────────
    print_header("1막: 낙인 (Stigma) — 시스템이 폐기한 불량 ***")
    time.sleep(0.5)

    narr = [
        "눈을 뜨자마자 온몸의 감각을 찌르는 것은 지독한 녹슨 기름 냄새와 차가운 빗방울이었다.",
        "고개를 들자 수십 미터 높이의 거대한 강철 무덤이 하늘을 완전히 가로막고 있다.",
        "네오 아크 상층민들이 쓰다 버린 드론의 사체, 마모된 메인보드 파편이 끝없는 산을 이룬 곳.",
        "이곳은 시스템이 당신을 쓰레기처럼 내던진 '폐기물 처리장' — 데드존의 외각이다.",
        "",
        "배 속에서 내장 조직이 꼬이는 듯한 강렬한 통증이 느껴진다.",
        "목 뒤의 소켓이 차갑게 식어가며, 단 하나의 메시지가 눈 앞을 아득히 채웁니다:",
        "",
        "  \"당신은 폐기된 ***입니다. 회수 또는 소거.\"",
    ]
    for line in narr:
        type_text(f"  {line}", 0.022) if line else print()
        time.sleep(0.1)

    time.sleep(1.0)
    wait_for_keypress()
    clear_screen()

    # ── 단계 3: 세계관 브리핑 ────────────────────────────────────────────
    print_header("세계관 브리핑 — 당신이 버려진 이유")
    world_log = [
        ("[1주기]  지구 천연자원이 완전히 고갈되었습니다."),
        ("         국제 연합이 대기업 연합의 마스터 AI 기동을 승인 하였습니다."),
        ("         대기업 연합의 마스터 AI가 연산을 실행했습니다."),
        ("         연산 결과: '인류의 95%를 격리해야 인류 존속 가능'. 대붕괴 시작."),
        ("         총괄국을 조직하여 인류의 95%를 격리,처단 권한 위임 하였습니다"),
        (""),
        ("[2주기]  총괄국이 남은 자원 영역에 가상현실 차단막 '네오 아크'를 건설."),
        ("         차단막 밖의 95% 영토는 방사능과 폐기된 기계의 황무지 — '데드존'이 됐다."),
        ("         총괄국 수장 주디스 케인이 네오 아크를 완전 통제하고 있다."),
        (""),
        ("[현재]   데드존의 스캐벤저들이 구시대 유물을 발굴하며 총괄국에 균열을 내고 있다."),
        ("         당신은 네오 아크 실험실에서 '불량 ***'로 낙인찍혀 이곳에 폐기됐다."),
        ("         살아있는 불법 ***는 총괄국 AI에 의해 회수 또는 소거 대상이다."),
    ]
    for line in world_log:
        type_text(f"  {line}", 0.02) if line else print()
        time.sleep(0.05)

    time.sleep(0.8)
    print()
    print_divider()
    type_text("  당신의 목표: 쓰레기 바다를 탐색해 방공호 벙커를 장악하라.", 0.025)
    type_text("  당신의 행동 방식이 당신의 삶을 결정할 것이다.", 0.025)
    print_divider()

    wait_for_keypress()
    clear_screen()

    # ── 단계 4: 조작법 안내 ──────────────────────────────────────────────
    print_header("생존 프로토콜 안내 — 운용 매뉴얼")
    guide = [
        ("W / A / S / D", "그리드 이동. 1타일 이동 시 허기/갈증이 소모됩니다."),
        ("F             ", "현재 위치 탐색. 전투·이벤트·자원 획득이 발생합니다."),
        ("I             ", "인벤토리. 장비 장착, 소모품 사용, 분해 가능."),
        ("C             ", "현재 상태 저장 (stigma_save.json 동기화)."),
        ("Q             ", "게임 종료. 저장 여부 선택 가능."),
    ]
    for key, desc in guide:
        print(f"  [{key}]  {desc}")

    print()
    print_divider()
    type_text("  [경고] 허기/갈증이 0이 되면 매 턴 HP가 감소합니다.", 0.022)
    type_text("  [경고] 이동·탐색 중 기계 괴수와의 전투가 발생할 수 있습니다.", 0.022)
    type_text("  [경보] 당신의 선택은 데이터로 기록됩니다. 선택이 곧 당신입니다.", 0.025)
    print_divider()
    print()
    type_text("  목표 좌표: (4, 4) — 방공호 벙커 [B]. 지역 우상단.", 0.022)
    type_text("  이동하며 탐색하라. 허기와 갈증을 관리하라. 살아남아라.", 0.022)

    wait_for_keypress()
    clear_screen()
    type_text("[SYSTEM] 생존 인터페이스 가동. 그리드 스캐너 활성화.", 0.022)
    time.sleep(0.6)


def run_boss_core_choice(player):
    """보스 격파 후 코어 처분 선택 — 최종 직업 가중치에 영향을 미칩니다."""
    clear_screen()
    sound.play_typing_bgm()
    print_header("BOSS GLITCH LOG — 핵심 코어 노출")
    type_text("  거대한 기계 괴수가 스파크를 뿜으며 무릎을 꿇습니다.", 0.03)
    type_text("  중앙 제어선이 마비되며 파랗게 요동치는 동력 코어가 노출됩니다.", 0.03)
    type_text("  이 코어를 아지트 터미널에 꽂는 순간, 거점이 완성된다.", 0.03)
    print()
    time.sleep(1.0)
    type_text("  [SYSTEM] 경고. 코어 처분 방식이 행동 코드에 영구 기록됩니다.", 0.03)
    type_text("           이 선택이 당신의 각성 경로를 확정합니다.", 0.03)
    print()
    print_divider()
    print("  1. 코어를 과부하 시켜 의체에 직접 이식한다.")
    print("     ➔ 물리 격돌 W_kinetic 대폭 상승")
    print()
    print("  2. 코어의 희귀 희토류를 분해해 방공호 발전기에 직결한다.")
    print("     ➔ 자원 정제 W_scrap 대폭 상승")
    print()
    print("  3. 코어 내부의 네오 아크 암호화 칩을 사이버덱에 강제 포팅한다.")
    print("     ➔ 연산 침투 W_cyber 대폭 상승")
    print_divider()

    while True:
        ans = read_key()
        if ans == "1":
            player.weights["kinetic"] += 3
            print()
            type_text("  신경망 리미터가 과부하 상태로 돌입합니다. 의체 전역에 금속음이 울립니다.", 0.03)
            type_text("  폭발적인 에너지가 근육 신경망을 재배선합니다. 강해집니다.", 0.03)
            break
        elif ans == "2":
            player.weights["scrap"] += 3
            print()
            type_text("  코어를 정밀 분해합니다. 방공호 발전기가 오렌지빛으로 점화됩니다.", 0.03)
            type_text("  터미널 화면에 '장인 인증 코드'가 파싱됩니다. 기술이 각인됩니다.", 0.03)
            break
        elif ans == "3":
            player.weights["cyber"] += 3
            print()
            type_text("  사이버덱이 달아오르며 암호화 칩이 신경망 내부에 포팅됩니다.", 0.03)
            type_text("  총괄국 군사 기밀 코드가 덱에 박혀 흐릅니다. 세계가 코드로 보입니다.", 0.03)
            break

    time.sleep(1.5)
    wait_for_keypress()


def run_ending(player):
    clear_screen()
    print_header("PIONEER PROTOCOL: NORMALIZATION EXECUTION")
    type_text("  코어가 아지트 터미널에 꽂히는 순간 —", 0.03)
    type_text("  암흑천지였던 지하 방공호에 오렌지색 비상등이 켜지며 아날로그 진동음이 바닥을 울립니다.", 0.03)
    type_text("  총괄국의 마스터 AI 감시망을 차단한 첫 번째 디지털 은신처가 완성됩니다.", 0.03)
    type_text("  눈부신 경고창과 함께 당신의 행위 로그 전체가 스캔되기 시작합니다.\n", 0.03)

    total = sum(player.weights.values()) or 1
    w_k, w_s, w_c = player.weights['kinetic'], player.weights['scrap'], player.weights['cyber']

    time.sleep(1)
    print_divider()
    print("  [ 행위 로그 분석 — 의식 코드 동기화율 ]")
    print_divider()

    bar_len = 30
    def make_bar(val, tot):
        filled = int(bar_len * val / tot) if tot else 0
        return f"[{'█' * filled}{'░' * (bar_len - filled)}] {val/tot*100:.1f}%"

    print(f"  컴뱃 포스     (kinetic) : {make_bar(w_k, total)}  ({w_k}회)")
    print(f"  메카니컬 테크 (scrap)   : {make_bar(w_s, total)}  ({w_s}회)")
    print(f"  넷 포스       (cyber)   : {make_bar(w_c, total)}  ({w_c}회)")
    print()
    time.sleep(1.5)

    print_divider()
    if w_k == w_s == w_c:
        type_text("  [HIDDEN PROTOCOL] tri_balance_awakening — 황금의 조율사 해제", 0.035)
        print()
        type_text("  경고. 모든 가중치 배열이 완벽한 데드락 균형을 이루었습니다.", 0.03)
        type_text("  시스템이 당신의 성향을 단일 코드로 정의하지 못해 히든 개척자 프로토콜을 개방합니다.", 0.03)
        type_text("  모든 역할군의 기본 노드가 동시에 교차 활성화됩니다.", 0.03)
        type_text("  당신은 어느 한 쪽의 논리에도 귀속되지 않는 유일한 존재입니다.", 0.03)
    elif w_k >= w_s and w_k >= w_c:
        type_text("  [각성] 컴뱃 포스 (Combat Force) 코드 직결.", 0.035)
        print()
        type_text("  당신의 육체적 집행 기록이 정량화되었습니다.", 0.03)
        type_text("  찢어발긴 기계들의 강화 장갑 프로토콜이 신경망 리미터를 영구 해제합니다.", 0.03)
        type_text("  뼈를 깎는 무력의 집행자 — [컴뱃 포스]가 당신의 척수에 직결됩니다.", 0.03)
        type_text("  강한 자가 살아남는다. 당신은 이제 데드존의 법칙 그 자체입니다.", 0.03)
    elif w_s >= w_k and w_s >= w_c:
        type_text("  [각성] 메카니컬 테크 (Mechanical Tech) 인덱스 전이.", 0.035)
        print()
        type_text("  그리드 화면에 고철 분해 및 유물 제어 시퀀스가 파싱됩니다.", 0.03)
        type_text("  녹슨 발전기가 복구되자, 고대 설계도가 당신을 장인으로 인정합니다.", 0.03)
        type_text("  고철의 연금술사 — [메카니컬 테크] 자격이 부여됩니다.", 0.03)
        type_text("  폐철 하나도 낭비하지 않는다. 당신의 손 끝에서 데드존이 재건됩니다.", 0.03)
    else:
        type_text("  [각성] 넷 포스 (Net Force) 아나키스트 패킷 주입.", 0.035)
        print()
        type_text("  마스터 AI 감시망 '그리드'에 당신이 새겨넣은 유령 백도어가 고정 노드로 승인됩니다.", 0.03)
        type_text("  가상현실 프로토콜을 왜곡하는 아나키스트 — [넷 포스]의 코드가 주입됩니다.", 0.03)
        type_text("  코드는 현실보다 강하다. 당신은 시스템의 균열을 타고 흐릅니다.", 0.03)
        type_text("  총괄국 AI가 당신을 단 한 번도 예측하지 못했습니다.", 0.03)
    print_divider()
    time.sleep(0.8)

    # ── 각성 스킬 지급 ──────────────────────────────────────────────────
    job, skill_id = _skills.grant_awakening_skill(player)
    if skill_id:
        sk = _skills.SKILL_DEFS[skill_id]
        job_label = _skills.JOB_LABEL.get(job, job)
        print()
        print(f"  {Fore.YELLOW + Style.BRIGHT}[ 각성 스킬 해금 ]{Style.RESET_ALL}")
        print(f"  직업: {Fore.CYAN + Style.BRIGHT}{job_label}{Style.RESET_ALL}")
        print(f"  스킬: {Fore.GREEN + Style.BRIGHT}{sk['name']}{Style.RESET_ALL}")
        type_text(f"  ▶ {sk['desc']}", 0.022)
        type_text("  전투 중 [S] 키로 사용 가능합니다.", 0.022)
        log_diary(player, f"[각성] {job_label} — {sk['name']} 해금")

    print()
    time.sleep(1)

    # 플레이 통계
    print_divider()
    print("  [ 1막 클리어 통계 ]")
    print_divider()
    tier_final = player.get_highest_tier()
    tier_names = {4: "급조 (T4)", 3: "규격 (T3)", 2: "정제 (T2)", 1: "기업제 (T1)", 0: "유물 (T0)"}
    diff_label = {"easy": "이지", "normal": "노멀", "hard": "하드"}.get(player.difficulty, player.difficulty)
    threat_final = get_turn_scale_multiplier(player)

    print(f"  난이도           : {diff_label}")
    print(f"  총 진행 턴       : {player.turn_count}턴")
    print(f"  최종 위협 배율   : x{threat_final:.2f}")
    print(f"  제압한 적        : {player.enemies_defeated}기")
    print(f"  잔여 HP          : {player.hp:,} / {player.max_hp:,}")
    print(f"  잔여 고철        : {player.materials}개")
    print(f"  보유 장비 수     : {len(player.inventory)}종")
    print(f"  최고 장비 등급   : {tier_names.get(tier_final, 'N/A')}")

    total_consumables = sum(player.consumables.values())
    print(f"  잔여 소모품      : {total_consumables}개")
    print_divider()
    time.sleep(1)

    print()
    time.sleep(1.2)
    type_text("  [SYSTEM]: 개척자 프로토콜 (Pioneer Protocol) 전면 승인.", 0.04)
    type_text("  [PROCESS]: 초기 스탯 환급 및 각성 클래스 스케일링 가동 대기.", 0.04)
    print()
    time.sleep(0.8)
    type_text("  \"당신은 마침내 시스템의 구역에 확고한 첫 영토를 개척해 냈습니다.\"", 0.04)
    print()
    type_text("  벙커 외부로 가이거 계수기의 비명음과 방사능 폭풍 소리가 아스라이 멀어집니다.", 0.03)
    type_text("  방공호의 비상등이 켜집니다. 이것은 끝이 아닙니다.", 0.03)
    type_text("  마스터 AI의 그리드는 아직 살아있고 — 당신의 낙인은 이제 시작입니다.", 0.03)
    print()
    time.sleep(1.2)
    type_text("  그리고 —", 0.04)
    time.sleep(0.6)
    type_text("  데드존 어딘가에서 발신되던 그 정체불명의 신호.", 0.03)
    type_text("  아직도 규칙적으로 송신되고 있다.", 0.03)
    type_text("  누군가 당신을 기다리고 있다.", 0.035)
    print()
    time.sleep(1.0)
    print(Fore.GREEN + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.GREEN + Style.BRIGHT + "  ║  " + ea_rpad("1막 [낙인] 클리어 — DEMO END", 72) + "║")
    print(Fore.GREEN + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    wait_for_keypress()
    run_act2_teaser(player)
    sound.stop_all()
    wait_for_keypress()


def run_act2_teaser(player):
    """1막 클리어 후 2막 예고 시퀀스 — 직업 스킬 미리보기 + 두 진영 신호."""
    w_k = player.weights['kinetic']
    w_s = player.weights['scrap']
    w_c = player.weights['cyber']

    if w_k == w_s == w_c:
        job_tag = "황금 분할의 조율사"
        skills = [
            ("삼위일체 오버클럭",  "VIT · INT · DEX 전체 +3 임시 강화 (3턴)"),
            ("균형 파열",          "패턴 노출 지수를 즉시 절반으로 초기화"),
            ("프로토콜 위조",      "적의 마지막 공격 로그를 자해로 역전환 (RAM 3 소모)"),
        ]
    elif w_k >= w_s and w_k >= w_c:
        job_tag = "컴뱃 포스 (Combat Force)"
        skills = [
            ("의체 오버클럭",  "2턴간 공격력 200% — 턴당 HP 5% 소모"),
            ("바이오 적출",    "타격 성공 시 적의 생체연료 흡수 (허기·갈증 +15)"),
            ("타이탄 클리어",  "적 방어력 완전 무시 관통 타격 (RAM 3 소모)"),
        ]
    elif w_s >= w_k and w_s >= w_c:
        job_tag = "메카니컬 테크 (Mechanical Tech)"
        skills = [
            ("센트리 건 배치",  "전투 중 자동 포탑 설치 — 매 턴 적에게 고정 피해"),
            ("분해 분석",       "적 격파 시 희귀 파츠 추출 확률 +60%"),
            ("긴급 정제",       "전투 중 고철 50개 소모 → HP 20% 즉시 회복"),
        ]
    else:
        job_tag = "넷 포스 (Net Force)"
        skills = [
            ("그리드 침투",   "적 패턴 분석 지수를 즉시 0 초기화 (RAM 2 소모)"),
            ("신호 위장",     "Alert Level 누적 정지 3턴 (네오 아크 전용)"),
            ("코드 역해킹",   "적의 다음 공격을 자해로 전환 (RAM 4 소모, 50% 성공률)"),
        ]

    # ── 스크린 1: 직업 스킬 예고 ────────────────────────────────────────
    clear_screen()
    print_header(f"각성 코드 분석 — {job_tag}")
    print()
    type_text(f"  [{job_tag}]의 의식 코드가 신경망 깊숙이 새겨졌습니다.", 0.028)
    type_text("  본편(2막)이 시작되는 순간, 다음 능력들이 해금됩니다.", 0.025)
    print()
    print_divider()
    print("  [ 해금 예정 스킬 — 2막 ]")
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
    print_header("긴급 수신 — 미지의 이중 신호 포착")
    print()
    time.sleep(0.6)
    type_text("  방공호 터미널이 두 개의 주파수를 동시에 포착합니다.", 0.025)
    print()
    time.sleep(0.5)

    print_divider()
    type_text(f"  {Fore.CYAN + Style.BRIGHT}[신호 A — 네오 아크 방면 암호화 채널]{Style.RESET_ALL}", 0.02)
    time.sleep(0.3)
    print()
    type_text('  "...불량 코드. 흥미롭군. 나는 주디스 케인이다.', 0.03)
    type_text('   당신의 행위 로그를 분석했다. 제안이 있다.', 0.03)
    type_text('   우리 편이 되면 살아남는다. 거부하면 — 소거한다."', 0.03)
    print()
    print(f"  {Fore.CYAN + Style.BRIGHT}[ 총괄국 집행관  ·  진영 우호도 시스템  ·  2막 해금 ]{Style.RESET_ALL}")
    time.sleep(0.8)

    print_divider()
    type_text(f"  {Fore.YELLOW + Style.BRIGHT}[신호 B — 데드존 심부 아날로그 주파수]{Style.RESET_ALL}", 0.02)
    time.sleep(0.3)
    print()
    type_text('  "[잡음] ...살아있나? 발칸이다.', 0.03)
    type_text('   기업 놈들이 너를 사냥하러 온다. 이미 냄새를 맡았어.', 0.03)
    type_text('   우리 라인에 합류해. 대신 — 쉽지 않을 거다."', 0.03)
    print()
    print(f"  {Fore.YELLOW + Style.BRIGHT}[ 스크랩 연합 수장  ·  저항군 평판 시스템  ·  2막 해금 ]{Style.RESET_ALL}")
    print_divider()
    time.sleep(0.5)
    print()
    type_text("  두 신호는 서로를 모른다.", 0.028)
    type_text("  그러나 둘 다 당신을 원한다.", 0.028)
    print()
    time.sleep(0.6)
    print_divider()
    print("  이 신호에 응답하겠습니까?")
    print()
    print(f"  {Fore.CYAN + Style.BRIGHT}[1]{Style.RESET_ALL} 주디스 케인에게 응답한다  — 총괄국 라인")
    print(f"  {Fore.YELLOW + Style.BRIGHT}[2]{Style.RESET_ALL} 발칸 게이츠에게 응답한다  — 저항군 라인")
    print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} 양쪽 모두 무시한다          — 독자 노선")
    print_divider()
    print(f"  {Fore.WHITE + Style.DIM}[ 이 선택은 본편(2막)에서 이어집니다 ]{Style.RESET_ALL}")

    while True:
        ans = read_key()
        if ans in ["1", "2", "3"]:
            break

    print()
    if ans == "1":
        type_text('  [송신] "...수신했다, 케인. 제안을 듣겠다."', 0.03)
        time.sleep(0.5)
        type_text(f'  {Fore.CYAN + Style.BRIGHT}[수신] "현명한 선택이다. 좌표를 전송한다. 임무는 2막에서 시작된다."{Style.RESET_ALL}', 0.03)
        log_diary(player, "[2막 예고] 주디스 케인의 제안 수락 — 총괄국 라인 선택")
    elif ans == "2":
        type_text('  [송신] "...발칸. 합류한다. 좌표 보내줘."', 0.03)
        time.sleep(0.5)
        type_text(f'  {Fore.YELLOW + Style.BRIGHT}[수신] "[잡음] ...하. 역시. 기다리고 있겠다."{Style.RESET_ALL}', 0.03)
        log_diary(player, "[2막 예고] 발칸 게이츠의 제안 수락 — 저항군 라인 선택")
    else:
        type_text("  두 신호를 모두 무시한다. 당신만의 코드로 움직인다.", 0.03)
        log_diary(player, "[2막 예고] 두 진영 모두 무시 — 독자 노선")

    time.sleep(0.8)
    wait_for_keypress()

    # ── 스크린 3: 2막 타이틀 카드 ───────────────────────────────────────
    clear_screen()
    print()
    time.sleep(1.0)
    type_text("  당신의 낙인은 끝이 아닌 시작이었습니다.", 0.032)
    print()
    time.sleep(0.6)
    type_text("  데드존의 고철 더미 아래 — 세계의 균열이 벌어지고 있습니다.", 0.025)
    print()
    time.sleep(0.8)
    print_divider()
    print()
    print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
    print(Fore.CYAN  + Style.BRIGHT + "  ║" + ea_center("P  R  O  T  O  C  O  L  :  S  T  I  G  M  A", 74) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + ea_center("2막: 화려한 가축과 야만적 해방자", 74) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
    print(Fore.YELLOW + Style.BRIGHT + "  ║" + ea_center("— COMING SOON —", 74) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" + " " * 74 + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    print()
    time.sleep(0.5)
    type_text("  데모 플레이에 감사합니다. 당신의 선택이 본편에서 이어집니다.", 0.025)

