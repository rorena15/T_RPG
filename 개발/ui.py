# ui.py — 모든 화면 입출력 유틸리티
# 의존성: constants (AMBIENT_LORE), sys_log
# Player/combat을 import하지 않는다 (단방향 의존 유지).

import os
import sys
import time
import random
from colorama import Fore, Back, Style
import constants
from sys_log import sys_log, track, log_error

def flush_input():
    """타이핑 연출 중 유저가 미리 입력한 키를 강제로 날려 무차별 오작동을 차단합니다."""
    if os.name == 'nt':
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    else:
        import termios
        termios.tcflush(sys.stdin, termios.TCIOFLUSH)

@track
def safe_input(prompt):
    """버퍼 청소 후 명령코드를 온전히 입력받는 래퍼"""
    time.sleep(0.05)
    flush_input()
    return input(prompt)

@track
def wait_for_keypress():
    """엔터 입력 불필요 아무 키나 누르는 즉시 화면 템포가 연출 모드로 진행"""
    flush_input()
    print("\n[아무 키나 누르면 진행됩니다...]")
    if os.name == 'nt':
        import msvcrt
        msvcrt.getch()
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def read_key():
    """엔터 없이 단일 키를 즉시 감지해 대문자 문자열로 반환합니다."""
    flush_input()
    if os.name == 'nt':
        import msvcrt
        ch = msvcrt.getch()
        if ch == b'\x03':
            sys.exit()
        if ch in (b'\xe0', b'\x00'):  # 방향키 등 특수 키 — 두 번째 바이트 소비 후 무시
            msvcrt.getch()
            return ''
        try:
            return ch.decode('cp949').upper()
        except Exception:
            return ''
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x03':
                sys.exit()
            return ch.upper()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def type_text(text, speed=0.015):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    print()


def _ea_width(s):
    """CJK 문자를 포함한 문자열의 터미널 표시 너비를 반환합니다 (한글·한자 = 2칸)."""
    w = 0
    for c in s:
        cp = ord(c)
        if (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF or
                0xA960 <= cp <= 0xA97F or 0xAC00 <= cp <= 0xD7FF or
                0xF900 <= cp <= 0xFAFF or 0xFE10 <= cp <= 0xFE1F or
                0xFE30 <= cp <= 0xFE6F or 0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6):
            w += 2
        else:
            w += 1
    return w

def ea_center(s, width):
    """CJK 표시 너비 기준 center."""
    pad = max(0, width - _ea_width(s))
    return " " * (pad // 2) + s + " " * (pad - pad // 2)

def ea_rpad(s, width):
    """CJK 표시 너비 기준 ljust (오른쪽 공백 패딩)."""
    return s + " " * max(0, width - _ea_width(s))

def print_header(title):
    # 내부 너비 74, 양쪽 ║ 포함 총 78자 박스
    # 컨텐츠 영역: ║  {title}{pad}║  →  title + pad = 72 표시 너비
    print()
    print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * 74 + "╗")
    print(Fore.WHITE + Style.BRIGHT + "  ║  " + ea_rpad(title, 72) + "║")
    print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * 74 + "╝")
    print()

def print_divider():
    print(Fore.WHITE + Style.BRIGHT + "  " + "─" * 74)

def _log_color(log):
    """전투 로그 항목의 색상을 반환합니다."""
    if any(log.startswith(p) for p in ("[타격]", "[회복]", "[파밍]", "[수집]", "[승리]")):
        return Fore.GREEN + Style.BRIGHT
    if any(log.startswith(p) for p in ("[피격]", "[페이즈 전환]")):
        return Fore.RED + Style.BRIGHT
    if any(log.startswith(p) for p in ("[경고]", "[탈출]", "[탈출 참사]", "[기적적 탈출]", "[경보]")):
        return Fore.YELLOW + Style.BRIGHT
    if any(log.startswith(p) for p in ("[해킹]", "[방어]")):
        return Fore.CYAN + Style.BRIGHT
    return ""

def log_diary(player, entry):
    player.diary.append(f"[턴 {player.turn_count:>4d}]  {entry}")

def show_diary(player):
    entries = player.diary
    if not entries:
        clear_screen()
        print_header("항법 일지 — N-404 행동 코드 누적 로그")
        print()
        print("  기록 없음. 아직 어떤 선택도 누적되지 않았습니다.")
        print()
        wait_for_keypress()
        return

    page_size = 18
    total = len(entries)
    pages = max(1, (total + page_size - 1) // page_size)
    page = pages - 1  # 최신 페이지부터

    while True:
        clear_screen()
        print_header(f"항법 일지 — N-404 행동 코드 누적 로그  [{page + 1} / {pages}]")
        start = page * page_size
        end = min(start + page_size, total)
        for e in entries[start:end]:
            print(f"  {e}")
        print()
        print_divider()
        nav = []
        if page > 0:
            nav.append("P: 이전")
        if page < pages - 1:
            nav.append("N: 다음")
        nav.append("0: 복귀")
        print(f"  {' | '.join(nav)}")
        cmd = read_key()
        if cmd == "0":
            break
        elif cmd == "N" and page < pages - 1:
            page += 1
        elif cmd == "P" and page > 0:
            page -= 1

def print_ambient_lore():
    if AMBIENT_LORE:
        lore = random.choice(AMBIENT_LORE)
        print()
        print("  " + "─" * 70)
        type_text(f"  {lore}", 0.018)
        print("  " + "─" * 70)
        wait_for_keypress()

def roll_medkit():
    r = random.randint(1, 100)
    if r <= 40: return "MED_PER_10"       
    elif r <= 60: return "MED_FIX_100"    
    elif r <= 75: return "MED_PER_50"     
    elif r <= 85: return "MED_FIX_300"    
    elif r <= 93: return "MED_FIX_500"    
    elif r <= 98: return "MED_PER_100"    
    else: return "MED_FIX_1000"           

def roll_food():
    return "FOOD_BOTH" if random.random() < 0.3 else "FOOD_ONLY"

def roll_water():
    return "WATER_BOTH" if random.random() < 0.3 else "WATER_ONLY"

# ====================================================================
# [4] 게임 코어 (Player, Map & Save/Load)
