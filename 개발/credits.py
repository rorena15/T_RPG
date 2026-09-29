"""옵션 → 크레딧: 출처 표기(assets/licenses/CREDITS.txt)와 라이선스 전문(assets/licenses/*.txt)을 보여 준다.

CC BY 3.0 음원의 원작자 표기, OFL 글꼴·Apache 2.0 GM 모델·LGPL pygame-ce 등의 라이선스 전문 동봉을 게임 안에서 맡는다.
출처를 더하거나 바꿀 때는 CREDITS.txt만 고치면 된다. 라이선스 파일을 새로 넣으면 LICENSES에 한 줄 더한다.
"""
import os

from sound import _asset
from i18n import t

# (메뉴 글, 파일들) — 한 항목에 파일이 여럿이면 이어서 보여 준다
LICENSES = [
    ("CC BY 3.0", ["CC-BY-3.0.txt"]),
    ("CC0 1.0", ["CC0-1.0.txt"]),
    ("SIL Open Font License 1.1", ["OFL-1.1.txt"]),
    ("Apache License 2.0", ["Apache-2.0.txt"]),
    ("MIT License", ["MIT.txt"]),
    ("BSD 2-Clause / 3-Clause", ["BSD-2-Clause.txt", "BSD-3-Clause.txt"]),
    ("GNU LGPL 2.1", ["LGPL-2.1.txt"]),
    ("FreeType License", ["FTL.txt"]),
    ("zlib / libpng / libtiff / IJG", ["Zlib.txt", "libpng-2.0.txt", "libtiff.txt", "IJG.txt"]),
    ("PSF License 2.0", ["PSF-2.0.txt"]),
]


def _read(name):
    try:
        with open(_asset(os.path.join("licenses", name)), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return t('credits_missing', f=name)


def credits_text():
    try:
        import pygame
        ver = pygame.version.ver
    except Exception:
        ver = "2.x"
    return _read("CREDITS.txt").replace("{pygame_ver}", ver)


def license_text(files):
    return ("\n\n" + "─" * 32 + "\n\n").join(_read(f) for f in files)


def _show_terminal(title, text):
    from ui import clear_screen, print_divider, print_header, read_key
    lines = text.splitlines()
    per = 22
    for i in range(0, max(1, len(lines)), per):
        clear_screen()
        print_header(title)
        for ln in lines[i:i + per]:
            print("  " + ln)
        print_divider()
        print(f"  {t('credits_term_more')}" if i + per < len(lines) else f"  {t('credits_term_end')}")
        if read_key() == "0":
            return


def show_text(title, text, scene="forge"):
    """긴 글 한 편 (위에서부터). ↑↓ 한 줄, PgUp/PgDn 한 쪽, Enter·0으로 닫는다."""
    from gui import get_terminal
    if not get_terminal():
        return _show_terminal(title, text)
    from screens import show_text_view
    show_text_view(title, text, scene=scene)


def menu(scr):
    """옵션 화면(MenuScreen)에서 부른다. 터미널 모드면 scr가 None."""
    while True:
        items = [("1", t('credits_sources')), ("2", t('credits_licenses')), ("0", t('ui_back'))]
        if scr:
            k = scr.ask(t('credits_title'), items, lines=[t('credits_desc')], back="0")
        else:
            k = _ask_terminal(t('credits_title'), items)
        if k == "1":
            show_text(t('credits_sources'), credits_text())
        elif k == "2":
            _licenses(scr)
        elif k == "0":
            return


def _licenses(scr):
    keys = "123456789ABCDEFGHIJ"
    items = [(keys[i], name) for i, (name, _) in enumerate(LICENSES)] + [("0", t('ui_back'))]
    last = 0
    while True:
        if scr:
            k = scr.ask(t('credits_licenses'), items, back="0", start=last)
        else:
            k = _ask_terminal(t('credits_licenses'), items)
        if k == "0":
            return
        i = keys.find(str(k).upper())
        if 0 <= i < len(LICENSES):
            last = i
            show_text(LICENSES[i][0], license_text(LICENSES[i][1]))


def _ask_terminal(title, items):
    from ui import clear_screen, print_divider, print_header, read_key
    clear_screen()
    print_header(title)
    for k, label in items[:-1]:
        print(f"  {k}. {label}")
    print_divider()
    print(f"  {items[-1][0]}. {items[-1][1]}")
    print_divider()
    return read_key()
