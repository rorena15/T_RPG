"""
gui.py — Pygame 기반 터미널 에뮬레이터

sys.stdout 으로 등록하면 모든 print() 호출이 pygame 창에 렌더링됩니다.
colorama ANSI 코드를 파싱해 색상을 적용하며, read_key / wait_for_keypress 등
터미널 입력 함수를 pygame 이벤트 루프로 대체합니다.
"""

import sys
import os
import pygame

_terminal = None   # 싱글턴 인스턴스


def get_terminal():
    return _terminal


def set_terminal(t):
    global _terminal
    _terminal = t


# ── ANSI SGR 코드 → RGB ──────────────────────────────────────────────────────
_ANSI_COLORS = {
    '30': (80,  80,  80),
    '31': (200, 60,  60),
    '32': (60,  200, 60),
    '33': (200, 200, 60),
    '34': (80,  130, 220),
    '35': (180, 80,  180),
    '36': (60,  200, 200),
    '37': (200, 200, 200),
    '90': (140, 140, 140),
    '91': (255, 90,  90),
    '92': (90,  255, 90),
    '93': (255, 255, 90),
    '94': (90,  160, 255),
    '95': (255, 90,  255),
    '96': (90,  255, 255),
    '97': (255, 255, 255),
}

_DEFAULT_COLOR = (200, 200, 200)
_BG_COLOR      = (4,   4,   12)
_BRIGHT_BOOST  = 1.35
_DIM_FACTOR    = 0.55

_FONT_CANDIDATES = [
    "D2Coding",
    "나눔고딕코딩",
    "Malgun Gothic",
    "Gulim",
    "Consolas",
    "Courier New",
    "monospace",
]


class PygameTerminal:
    """pygame 창에 텍스트를 렌더링하는 터미널 에뮬레이터."""

    PAD_X = 14
    PAD_Y = 10
    COLS  = 92
    ROWS  = 42

    def __init__(self, title: str = "PROTOCOL: STIGMA"):
        pygame.display.init()
        pygame.font.init()

        self.font   = self._load_font(18)
        self._cw, self._ch = self.font.size("W")

        w = self._cw * self.COLS + self.PAD_X * 2
        h = self._ch * self.ROWS + self.PAD_Y * 2
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        pygame.display.set_caption(title)

        # 버퍼: 줄 목록, 각 줄은 (텍스트 세그먼트, RGB 색상) 튜플 목록
        self._buf: list[list[tuple[str, tuple]]] = [[]]
        self._fg     = _DEFAULT_COLOR
        self._bright = False
        self._dim    = False

        self._render()

    # ── 폰트 로딩 ────────────────────────────────────────────────────────────
    def _load_font(self, size: int) -> pygame.font.Font:
        for name in _FONT_CANDIDATES:
            path = pygame.font.match_font(name)
            if path:
                try:
                    return pygame.font.Font(path, size)
                except Exception:
                    pass
        return pygame.font.Font(None, size + 4)

    # ── sys.stdout 프로토콜 ───────────────────────────────────────────────────
    def write(self, text: str) -> int:
        self._parse(text)
        return len(text)

    def flush(self):
        self._render()

    @property
    def encoding(self):
        return 'utf-8'

    @property
    def errors(self):
        return 'replace'

    def isatty(self) -> bool:
        return False

    # ── ANSI 파서 ─────────────────────────────────────────────────────────────
    def _parse(self, text: str):
        i = 0
        n = len(text)
        while i < n:
            c = text[i]

            if c == '\x1b' and i + 1 < n and text[i + 1] == '[':
                # ESC [ ... <final> 시퀀스
                j = i + 2
                while j < n and (text[j].isdigit() or text[j] == ';'):
                    j += 1
                if j < n:
                    final = text[j]
                    param = text[i + 2:j]
                    i = j + 1
                    if final == 'm':
                        self._apply_sgr(param)
                    # 커서 이동 등 기타 시퀀스는 무시
                else:
                    i += 1

            elif c == '\n':
                self._buf.append([])
                i += 1

            elif c == '\r':
                i += 1

            else:
                # 다음 특수문자까지 일반 텍스트 수집
                j = i + 1
                while j < n and text[j] not in ('\x1b', '\n', '\r'):
                    j += 1
                seg   = text[i:j]
                color = self._fg
                if self._dim:
                    color = tuple(max(0, int(v * _DIM_FACTOR)) for v in color)
                self._buf[-1].append((seg, color))
                i = j

        self._render()

    def _apply_sgr(self, param: str):
        codes = param.split(';') if param else ['0']
        for code in codes:
            code = code.strip()
            if code in ('0', ''):
                self._fg     = _DEFAULT_COLOR
                self._bright = False
                self._dim    = False
            elif code == '1':
                self._bright = True
                self._dim    = False
                self._fg = tuple(min(255, int(v * _BRIGHT_BOOST)) for v in self._fg)
            elif code == '2':
                self._dim    = True
                self._bright = False
            elif code in _ANSI_COLORS:
                base = _ANSI_COLORS[code]
                if self._bright:
                    base = tuple(min(255, int(v * _BRIGHT_BOOST)) for v in base)
                self._fg = base

    # ── 렌더링 ────────────────────────────────────────────────────────────────
    def _render(self):
        self._pump()
        self.screen.fill(_BG_COLOR)
        w, h = self.screen.get_size()
        visible = (h - self.PAD_Y * 2) // self._ch
        start   = max(0, len(self._buf) - visible)
        y = self.PAD_Y
        for line in self._buf[start:]:
            x = self.PAD_X
            for seg, color in line:
                surf = self.font.render(seg, True, color)
                self.screen.blit(surf, (x, y))
                x += surf.get_width()
            y += self._ch
            if y > h - self.PAD_Y:
                break
        pygame.display.flip()

    def _pump(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()

    # ── 화면 제어 ─────────────────────────────────────────────────────────────
    def clear(self):
        self._buf    = [[]]
        self._fg     = _DEFAULT_COLOR
        self._bright = False
        self._dim    = False
        self._render()

    # ── 입력 ──────────────────────────────────────────────────────────────────
    def read_key(self) -> str:
        self._render()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        sys.exit()
                    if event.unicode:
                        return event.unicode.upper()
                    if event.key == pygame.K_RETURN:
                        return '\r'
            pygame.time.wait(10)

    def wait_keypress_silent(self):
        """메시지 없이 아무 키나 대기."""
        self._render()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    return
            pygame.time.wait(10)

    # ── 타이핑 연출 ───────────────────────────────────────────────────────────
    def type_text_animated(self, text: str, speed: float = 0.015):
        delay_ms = max(1, int(speed * 1000))
        for char in text:
            self._parse(char)
            if speed > 0:
                pygame.time.delay(delay_ms)
        self._parse('\n')

    # ── 배너 이미지 ───────────────────────────────────────────────────────────
    def show_banner(self, path: str):
        """이미지를 화면 전체에 맞게 표시 (타이틀/엔딩용)."""
        if not os.path.exists(path):
            return
        try:
            img = pygame.image.load(path).convert()
            sw, sh = self.screen.get_size()
            iw, ih = img.get_size()
            scale = min(sw / iw, sh / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = pygame.transform.smoothscale(img, (nw, nh))
            self.screen.fill(_BG_COLOR)
            self.screen.blit(img, ((sw - nw) // 2, (sh - nh) // 2))
            pygame.display.flip()
        except Exception:
            pass
