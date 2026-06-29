"""
gui.py — Pygame 로그-큐 패널 렌더러

sys.stdout으로 등록하면 모든 print() 호출이 pygame 창의 로그 패널에 표시됩니다.
완성된 줄은 Surface로 미리 렌더링해 캐시하고, _render()는 캐시를 blit만 합니다.
ANSI SGR 코드를 파싱해 색상을 적용하며, read_key / input_text 등 입력 함수를
pygame 이벤트 루프로 대체합니다.
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
_FRAME_COLOR   = (40,  40,  80)   # 패널 테두리 색상
_BRIGHT_BOOST  = 1.35
_DIM_FACTOR    = 0.55

# ASCII/박스 전용 — 신뢰할 수 있는 영문 모노스페이스 (글리프 정확도 우선)
_FONT_ASCII_CANDIDATES = [
    "D2Coding",
    "NanumGothicCoding",
    "나눔고딕코딩",
    "Consolas",
    "Lucida Console",
    "Courier New",
]

# 한글 전용 — 한글 지원 폰트 (Windows / Mac / Linux 순)
_FONT_KOR_CANDIDATES = [
    "D2Coding",
    "NanumGothicCoding",
    "나눔고딕코딩",
    "Malgun Gothic",
    "Gulim",
    "Batang",
    "Apple SD Gothic Neo",
    "AppleGothic",
    "Noto Sans CJK KR",
]

# assets/ 번들 폰트 (여기 놓으면 자동 최우선)
_BUNDLED_FONT_NAMES = ["D2Coding.ttf", "NanumGothicCoding.ttf", "font.ttf"]

# 이모티콘 전용 번들 폰트
_BUNDLED_EMOJI_FONT_NAMES = ["NotoEmoji-Regular.ttf"]

# 이모티콘 시스템 폰트 후보
_FONT_EMOJI_CANDIDATES = [
    "Segoe UI Emoji",
    "Segoe UI Symbol",
    "Apple Color Emoji",
    "Noto Emoji",
]

# 박스/블록 그리기 유니코드 범위
_BOX_RANGES = (
    (0x2500, 0x257F),  # Box Drawing
    (0x2580, 0x259F),  # Block Elements
    (0x25A0, 0x25FF),  # Geometric Shapes
)


class PygameTerminal:
    """pygame 창에 텍스트를 렌더링하는 로그-큐 패널 렌더러.

    완성된 줄(개행 수신)은 Surface로 미리 렌더링해 캐시합니다.
    _render()는 캐시 Surface를 blit만 하므로 매 프레임 재렌더링 오버헤드가 없습니다.
    """

    PAD_X = 14
    PAD_Y = 10
    COLS  = 92
    ROWS  = 42

    def __init__(self, title: str = "PROTOCOL: STIGMA"):
        pygame.display.init()
        pygame.font.init()

        self._title          = title
        self._font_size      = 20
        self._buf: list[list[tuple[str, tuple]]] = [[]]  # 라인별 세그먼트 버퍼
        self._line_surf_cache: dict = {}   # tuple(line) → Surface (완성된 줄 캐시)
        self._char_cache:  dict = {}       # (char, color) → Surface
        self._box_cache:   dict = {}       # (char, color) → Surface (스케일된 박스 문자)
        self._emoji_cache: dict = {}       # (char, color) → Surface
        self._fg     = _DEFAULT_COLOR
        self._bright = False
        self._dim    = False
        self._dirty  = True               # render 필요 여부 플래그

        self._load_fonts(self._font_size)

        w = self._unit_w * self.COLS + self.PAD_X * 2
        h = self._ch     * self.ROWS + self.PAD_Y * 2
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        pygame.display.set_caption(title)

        _ico = self._find_ico()
        if _ico:
            try:
                pygame.display.set_icon(pygame.image.load(_ico))
            except Exception:
                pass

        self._render()

        # time.sleep → pygame 이벤트 + 렌더 병행 버전으로 교체
        import time as _time_mod
        _self = self
        def _gui_sleep(seconds: float):
            if seconds <= 0:
                return
            # 대기 전에 현재 버퍼를 즉시 화면에 표시
            _self._dirty = True
            _self._render()
            end_ms = pygame.time.get_ticks() + int(seconds * 1000)
            while True:
                remaining = end_ms - pygame.time.get_ticks()
                if remaining <= 0:
                    break
                _self._pump()
                pygame.time.wait(min(10, max(1, remaining)))
        _time_mod.sleep = _gui_sleep

    # ── 폰트 로딩 ────────────────────────────────────────────────────────────
    def _load_fonts(self, size: int):
        bundled = self._find_bundled_font()
        if bundled:
            self.font_ascii = pygame.font.Font(bundled, size)
            self.font_kor   = self.font_ascii
            self.font_box   = self.font_ascii
        else:
            self.font_ascii = self._load_font(size, _FONT_ASCII_CANDIDATES)
            self.font_kor   = self._load_font(size, _FONT_KOR_CANDIDATES)
            self.font_box   = self.font_ascii
        self.font = self.font_ascii

        self._cw, self._ch = self.font_ascii.size("W")
        self._unit_w = self.font_ascii.size('A')[0]
        self.font_emoji = self._load_emoji_font(size)

        # 폰트 변경 시 모든 캐시 무효화
        self._box_cache        = {}
        self._char_cache       = {}
        self._emoji_cache      = {}
        self._line_surf_cache  = {}
        self._dirty = True

    @staticmethod
    def _find_ico() -> str | None:
        base_dev = os.path.dirname(os.path.abspath(__file__))
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(os.path.join(sys._MEIPASS, 'assets', 'icon.ico'))
        candidates.append(os.path.join(base_dev, '..', 'assets', 'icon.ico'))
        for p in candidates:
            p = os.path.normpath(p)
            if os.path.exists(p):
                return p
        return None

    @staticmethod
    def _find_bundled_font() -> str | None:
        base = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, 'frozen', False):
            assets_dir = os.path.join(sys._MEIPASS, 'assets')
        else:
            assets_dir = os.path.normpath(os.path.join(base, '..', 'assets'))
        for name in _BUNDLED_FONT_NAMES:
            p = os.path.join(assets_dir, name)
            if os.path.exists(p):
                return p
        return None

    @staticmethod
    def _find_emoji_font_path() -> str | None:
        base = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, 'frozen', False):
            assets_dir = os.path.join(sys._MEIPASS, 'assets')
        else:
            assets_dir = os.path.normpath(os.path.join(base, '..', 'assets'))
        for name in _BUNDLED_EMOJI_FONT_NAMES:
            p = os.path.join(assets_dir, name)
            if os.path.exists(p):
                return p
        for name in _FONT_EMOJI_CANDIDATES:
            p = pygame.font.match_font(name)
            if p:
                return p
        return None

    @classmethod
    def _load_emoji_font(cls, size: int) -> pygame.font.Font:
        path = cls._find_emoji_font_path()
        if path:
            try:
                return pygame.font.Font(path, size)
            except Exception:
                pass
        return pygame.font.Font(None, size)

    @staticmethod
    def _load_font(size: int, candidates: list) -> pygame.font.Font:
        bundled = PygameTerminal._find_bundled_font()
        if bundled:
            try:
                return pygame.font.Font(bundled, size)
            except Exception:
                pass
        for name in candidates:
            path = pygame.font.match_font(name)
            if path:
                try:
                    return pygame.font.Font(path, size)
                except Exception:
                    pass
        return pygame.font.Font(None, size + 4)

    # ── 문자 분류 ────────────────────────────────────────────────────────────
    @staticmethod
    def _is_box_char(c: str) -> bool:
        cp = ord(c)
        return any(lo <= cp <= hi for lo, hi in _BOX_RANGES)

    @staticmethod
    def _is_wide_char(c: str) -> bool:
        cp = ord(c)
        return (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF or
                0xA960 <= cp <= 0xA97F or 0xAC00 <= cp <= 0xD7FF or
                0xF900 <= cp <= 0xFAFF or 0xFE10 <= cp <= 0xFE1F or
                0xFE30 <= cp <= 0xFE6F or 0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6)

    @staticmethod
    def _is_emoji(c: str) -> bool:
        cp = ord(c)
        return (0x1F300 <= cp <= 0x1FAFF or
                0x2600  <= cp <= 0x26FF  or
                0x2700  <= cp <= 0x27BF)

    # ── 문자 Surface 캐시 ────────────────────────────────────────────────────
    def _get_box_surf(self, c: str, color: tuple) -> pygame.Surface:
        key = (c, color)
        if key not in self._box_cache:
            raw = self.font_box.render(c, True, color)
            if raw.get_width() != self._unit_w or raw.get_height() != self._ch:
                raw = pygame.transform.scale(raw, (self._unit_w, self._ch))
            self._box_cache[key] = raw
        return self._box_cache[key]

    def _get_emoji_surf(self, c: str, color: tuple) -> pygame.Surface:
        key = (c, color)
        if key not in self._emoji_cache:
            try:
                raw = self.font_emoji.render(c, True, color)
            except Exception:
                raw = pygame.Surface((self._unit_w * 2, self._ch), pygame.SRCALPHA)
            target_w = self._unit_w * 2
            if raw.get_width() == 0:
                raw = pygame.Surface((target_w, self._ch), pygame.SRCALPHA)
            elif raw.get_width() != target_w or raw.get_height() != self._ch:
                raw = pygame.transform.smoothscale(raw, (target_w, self._ch))
            self._emoji_cache[key] = raw
        return self._emoji_cache[key]

    def _get_char_surf(self, c: str, color: tuple) -> pygame.Surface:
        key = (c, color)
        if key not in self._char_cache:
            f = self.font_kor if self._is_wide_char(c) else self.font_ascii
            self._char_cache[key] = f.render(c, True, color)
        return self._char_cache[key]

    # ── 줄 단위 Surface 렌더링 ───────────────────────────────────────────────
    def _render_line_to_surf(self, line: list) -> pygame.Surface:
        """한 줄의 세그먼트를 Surface에 렌더링합니다."""
        panel_w = self.screen.get_width() - self.PAD_X * 2
        surf = pygame.Surface((max(panel_w, 1), self._ch), pygame.SRCALPHA)
        x = 0
        for seg, color in line:
            for c in seg:
                if self._is_box_char(c):
                    cs = self._get_box_surf(c, color)
                    surf.blit(cs, (x, 0))
                    x += self._unit_w
                elif self._is_emoji(c):
                    cs = self._get_emoji_surf(c, color)
                    surf.blit(cs, (x, 0))
                    x += self._unit_w * 2
                else:
                    cs = self._get_char_surf(c, color)
                    surf.blit(cs, (x, 0))
                    x += self._unit_w * (2 if self._is_wide_char(c) else 1)
        return surf

    def _get_line_surf(self, line: list, is_current: bool) -> pygame.Surface:
        """완성된 줄은 캐시에서, 현재 편집 중인 줄은 매번 신규 렌더링."""
        if is_current:
            return self._render_line_to_surf(line)
        key = tuple((s, c) for s, c in line)
        if key not in self._line_surf_cache:
            self._line_surf_cache[key] = self._render_line_to_surf(line)
        return self._line_surf_cache[key]

    # ── sys.stdout 프로토콜 ───────────────────────────────────────────────────
    def write(self, text: str) -> int:
        self._parse(text)
        return len(text)

    def flush(self):
        # dirty 상태일 때만 렌더링 (스로틀 없음 — 줄 Surface 캐시로 충분히 빠름)
        if self._dirty:
            self._render()

    def sleep_render(self, seconds: float):
        """time.sleep() 대용 — 대기 전에 화면을 즉시 갱신하고 이벤트를 처리합니다."""
        self._dirty = True
        self._render()
        end_ms = pygame.time.get_ticks() + int(seconds * 1000)
        while True:
            remaining = end_ms - pygame.time.get_ticks()
            if remaining <= 0:
                break
            self._pump()
            pygame.time.wait(min(10, max(1, remaining)))

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
                j = i + 2
                while j < n and (text[j].isdigit() or text[j] == ';'):
                    j += 1
                if j < n:
                    final = text[j]
                    param = text[i + 2:j]
                    i = j + 1
                    if final == 'm':
                        self._apply_sgr(param)
                else:
                    i += 1

            elif c == '\n':
                self._buf.append([])
                if len(self._buf) > 600:
                    self._buf = self._buf[-600:]
                    # 버퍼 잘림 → 라인 캐시 과거 항목 정리 (메모리 관리)
                    if len(self._line_surf_cache) > 1200:
                        self._line_surf_cache.clear()
                self._dirty = True
                i += 1

            elif c == '\r':
                # 현재 줄 초기화 (progress bar 지원)
                self._buf[-1] = []
                self._dirty = True
                i += 1

            else:
                j = i + 1
                while j < n and text[j] not in ('\x1b', '\n', '\r'):
                    j += 1
                seg   = text[i:j]
                color = self._fg
                if self._dim:
                    color = tuple(max(0, int(v * _DIM_FACTOR)) for v in color)
                self._buf[-1].append((seg, color))
                self._dirty = True
                i = j

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

        # 패널 테두리 (미묘한 프레임)
        pygame.draw.rect(
            self.screen, _FRAME_COLOR,
            (self.PAD_X - 4, self.PAD_Y - 4,
             w - (self.PAD_X - 4) * 2,
             h - (self.PAD_Y - 4) * 2),
            1
        )

        visible = (h - self.PAD_Y * 2) // self._ch
        n_lines = len(self._buf)
        start   = max(0, n_lines - visible)
        y = self.PAD_Y

        for i, line in enumerate(self._buf[start:], start=start):
            is_current = (i == n_lines - 1)
            if line:
                surf = self._get_line_surf(line, is_current)
                self.screen.blit(surf, (self.PAD_X, y))
            y += self._ch
            if y > h - self.PAD_Y:
                break

        pygame.display.flip()
        self._dirty = False

    def _pump(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                self._on_resize(event.w, event.h)

    def _on_resize(self, new_w: int, new_h: int):
        col_px = (new_w - self.PAD_X * 2) / self.COLS
        row_px = (new_h - self.PAD_Y * 2) / self.ROWS
        size_from_w = max(8, int(col_px / 0.55))
        size_from_h = max(8, int(row_px / 1.30))
        new_size = min(size_from_w, size_from_h)
        if abs(new_size - self._font_size) < 1:
            return
        self._font_size = new_size
        self._load_fonts(new_size)

    # ── 화면 제어 ─────────────────────────────────────────────────────────────
    def clear(self):
        self._buf   = [[]]
        self._fg    = _DEFAULT_COLOR
        self._bright = False
        self._dim   = False
        # 라인 캐시는 유지 (재사용 가능) — 문자 캐시는 유지
        self._dirty = True
        self._render()

    # ── 입력 ──────────────────────────────────────────────────────────────────
    _KEYCODE_MAP: dict = {
        **{getattr(pygame, f'K_{i}'): str(i) for i in range(10)},
        **{getattr(pygame, f'K_{chr(c)}'): chr(c).upper()
           for c in range(ord('a'), ord('z') + 1)},
        pygame.K_RETURN:   '\r',
        pygame.K_KP_ENTER: '\r',
        pygame.K_SPACE:    ' ',
    }

    @classmethod
    def _resolve_key(cls, event) -> str:
        u = event.unicode
        if u and len(u) == 1 and 0x20 <= ord(u) <= 0x7E:
            return u.upper()
        return cls._KEYCODE_MAP.get(event.key, '')

    def read_key(self) -> str:
        self._dirty = True
        self._render()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        sys.exit()
                    ch = self._resolve_key(event)
                    if ch:
                        return ch
            pygame.time.wait(10)

    def input_text(self, prompt: str = "") -> str:
        """pygame 이벤트 루프 기반 한 줄 텍스트 입력. input() 대체."""
        if prompt:
            self._parse(prompt)
        self._dirty = True
        self._render()
        buf = ""
        clock = pygame.time.Clock()
        while True:
            clock.tick(30)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self._parse('\n')
                        self._dirty = True
                        self._render()
                        return buf
                    elif event.key == pygame.K_ESCAPE:
                        sys.exit()
                    elif event.key == pygame.K_BACKSPACE:
                        if buf:
                            buf = buf[:-1]
                            if self._buf[-1]:
                                self._buf[-1].pop()
                            self._dirty = True
                            self._render()
                    elif event.unicode and len(event.unicode) == 1 and 0x20 <= ord(event.unicode) <= 0x7E:
                        buf += event.unicode
                        self._parse(event.unicode)
                        self._dirty = True
                        self._render()

    def wait_keypress_silent(self):
        """메시지 없이 아무 키나 대기."""
        self._dirty = True
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
        skipped  = False
        for char in text:
            self._parse(char)
            if not skipped:
                self._dirty = True
                self._render()
                if speed > 0:
                    pygame.time.delay(delay_ms)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        sys.exit()
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        skipped = True
                        break
        if skipped:
            self._dirty = True
            self._render()
        self._parse('\n')
        self._dirty = True
        self._render()
        pygame.event.clear()

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
