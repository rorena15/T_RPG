"""
gui.py — Pygame 로그-큐 패널 렌더러

sys.stdout으로 등록하면 모든 print() 호출이 pygame 창의 로그 패널에 표시됩니다.
완성된 줄은 Surface로 미리 렌더링해 캐시하고, _render()는 캐시를 blit만 합니다.
ANSI SGR 코드를 파싱해 색상을 적용하며, read_key / input_text 등 입력 함수를
pygame 이벤트 루프로 대체합니다.
"""

import math
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
        self._canvas      = pygame.Surface((w, h))   # 논리 서피스 — 항상 고정 크기
        self._canvas_size = (w, h)
        self._fullscreen  = False
        self._ui_manager  = None   # UIManager 연결 시 패널 렌더링 모드로 전환
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
        panel_w = self._canvas.get_width() - self.PAD_X * 2
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

        if self._ui_manager and self._ui_manager._active:
            self._ui_manager.render(self._canvas)
        else:
            self._canvas.fill(_BG_COLOR)
            w, h = self._canvas_size

            # 패널 테두리 (미묘한 프레임)
            pygame.draw.rect(
                self._canvas, _FRAME_COLOR,
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
                    self._canvas.blit(surf, (self.PAD_X, y))
                y += self._ch
                if y > h - self.PAD_Y:
                    break

        # canvas → screen letterbox 스케일링
        sw, sh = self.screen.get_size()
        cw, ch = self._canvas_size
        if (sw, sh) == (cw, ch):
            self.screen.blit(self._canvas, (0, 0))
        else:
            scale = min(sw / cw, sh / ch)
            scaled_w = int(cw * scale)
            scaled_h = int(ch * scale)
            scaled = pygame.transform.smoothscale(self._canvas, (scaled_w, scaled_h))
            self.screen.fill((0, 0, 0))
            self.screen.blit(scaled, ((sw - scaled_w) // 2, (sh - scaled_h) // 2))

        pygame.display.flip()
        self._dirty = False

    def _pump(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self.toggle_fullscreen()
            elif event.type in (pygame.VIDEORESIZE, getattr(pygame, 'WINDOWRESIZED', -1)):
                self._dirty = True

    def toggle_fullscreen(self):
        """F11 전체화면 전환 — canvas는 고정, screen만 교체."""
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self._canvas_size, pygame.RESIZABLE)
        self._dirty = True
        self._render()

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
                    if event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                        continue
                    ch = self._resolve_key(event)
                    if ch:
                        return ch
            pygame.time.wait(10)

    def input_text(self, prompt: str = "") -> str:
        """pygame 이벤트 루프 기반 한 줄 텍스트 입력. input() 대체."""
        # prompt를 현재 줄에 추가하고 입력 시작 위치 기록
        if prompt:
            self._parse(prompt)
        # 입력 시작 시점의 줄 세그먼트 수 기록 — 백스페이스가 prompt를 침범하지 않도록
        _input_start_seg = len(self._buf[-1])
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
                            # 현재 줄의 입력 세그먼트만 재구성 (prompt 보호)
                            self._buf[-1] = self._buf[-1][:_input_start_seg]
                            if buf:
                                self._buf[-1].append((buf, _DEFAULT_COLOR))
                            self._dirty = True
                            self._render()
                    elif event.unicode and len(event.unicode) == 1 and 0x20 <= ord(event.unicode) <= 0x7E:
                        buf += event.unicode
                        # 입력 세그먼트를 통째로 교체 (단일 세그먼트로 유지)
                        self._buf[-1] = self._buf[-1][:_input_start_seg]
                        self._buf[-1].append((buf, _DEFAULT_COLOR))
                        self._dirty = True
                        self._render()

    def wait_keypress_silent(self):
        """메시지 없이 아무 키나 대기. 화면을 다시 그리지 않으므로 배너 표시 유지."""
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                        continue
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
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_F11:
                            self.toggle_fullscreen()
                        elif event.key == pygame.K_ESCAPE:
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
        """이미지를 canvas에 맞게 표시 후 screen으로 letterbox 출력."""
        if not os.path.exists(path):
            return
        try:
            img = pygame.image.load(path).convert()
            cw, ch = self._canvas_size
            iw, ih = img.get_size()
            scale = min(cw / iw, ch / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = pygame.transform.smoothscale(img, (nw, nh))
            self._canvas.fill(_BG_COLOR)
            self._canvas.blit(img, ((cw - nw) // 2, (ch - nh) // 2))
            # canvas → screen
            sw, sh = self.screen.get_size()
            if (sw, sh) == (cw, ch):
                self.screen.blit(self._canvas, (0, 0))
            else:
                s = min(sw / cw, sh / ch)
                bw, bh = int(cw * s), int(ch * s)
                self.screen.fill((0, 0, 0))
                self.screen.blit(
                    pygame.transform.smoothscale(self._canvas, (bw, bh)),
                    ((sw - bw) // 2, (sh - bh) // 2)
                )
            pygame.display.flip()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# UIManager 패널 시스템 — Act 1막~이후 확장성 설계
# ══════════════════════════════════════════════════════════════════════════════

class _ActTheme:
    """1막 색상 테마. act 번호로 교체 가능하도록 클래스 분리."""
    BG           = (4,   4,  12)
    PANEL_BG     = (7,   7,  22)
    PANEL_BORDER = (0,  130, 170)
    HEADER_BG    = (8,   8,  26)
    HEADER_FG    = (0,  210, 228)
    TEXT_FG      = (175, 175, 198)
    TEXT_DIM     = (75,  75, 108)
    TILE_EMPTY   = (16,  16,  40)
    TILE_VISITED = (22,  44,  76)
    TILE_PLAYER  = (0,  196, 218)
    TILE_BUNKER  = (198, 156,  18)
    HP_COLOR     = (48,  196,  68)
    HP_MID       = (198, 156,  18)
    HP_LOW       = (198,  48,  48)
    HUNGER_COLOR = (208, 148,  28)
    THIRST_COLOR = (28,  158, 208)
    ALERT_SAFE   = (48,  196,  68)
    ALERT_WARN   = (208, 156,  18)
    ALERT_DANGER = (208,  38,  38)
    SCANLINE_A   = 12


_THEME = _ActTheme()


# ── _Panel 기반 클래스 ────────────────────────────────────────────────────────

class _Panel:
    """모든 UI 패널의 기반. rect는 canvas 좌표계 기준."""

    def __init__(self, rect: pygame.Rect):
        self.rect  = rect
        self._surf = pygame.Surface((max(1, rect.w), max(1, rect.h)), pygame.SRCALPHA)

    def _draw_bg(self, border_color=None):
        bc = border_color or _THEME.PANEL_BORDER
        self._surf.fill((*_THEME.PANEL_BG, 228))
        rw, rh = self._surf.get_size()
        for inset, alpha in ((2, 55), (1, 115), (0, 195)):
            gr = pygame.Rect(inset, inset, rw - inset * 2, rh - inset * 2)
            glow = pygame.Surface((rw, rh), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*bc, alpha), gr, 1)
            self._surf.blit(glow, (0, 0))

    def blit_to(self, target: pygame.Surface):
        target.blit(self._surf, (self.rect.x, self.rect.y))


# ── MapPanel ──────────────────────────────────────────────────────────────────

class MapPanel(_Panel):
    _M = 10   # 내부 여백

    def render(self, target: pygame.Surface, grid, player, font):
        self._draw_bg()
        m    = self._M
        size = grid.size
        avw  = self.rect.w - m * 2
        avh  = self.rect.h - m * 2 - 26   # 26: 섹션 라벨 높이
        cell = min(avw // max(size, 1), avh // max(size, 1))
        ox   = m + (avw - cell * size) // 2
        oy   = m + 26 + (avh - cell * size) // 2
        t_ms = pygame.time.get_ticks()

        for gy in range(size - 1, -1, -1):
            for gx in range(size):
                sx = ox + gx * cell
                sy = oy + (size - 1 - gy) * cell
                cr = pygame.Rect(sx + 1, sy + 1, cell - 3, cell - 3)
                is_pl = ([gx, gy] == grid.player_pos)
                is_bk = ([gx, gy] == grid.bunker_pos)
                is_vi = (gx, gy) in grid.visited_tiles

                if is_pl:
                    pulse = 0.62 + 0.38 * math.sin(t_ms / 270)
                    col   = _THEME.TILE_PLAYER
                    for ex, al in ((7, 18), (5, 38), (3, 75)):
                        gw = cr.w + ex * 2
                        gh = cr.h + ex * 2
                        gs = pygame.Surface((gw, gh), pygame.SRCALPHA)
                        pygame.draw.rect(gs, (*col, int(al * pulse)),
                                         gs.get_rect(), border_radius=5)
                        self._surf.blit(gs, (cr.x - ex, cr.y - ex))
                    pygame.draw.rect(self._surf, col, cr, border_radius=3)

                elif is_bk:
                    col = _THEME.TILE_BUNKER
                    pygame.draw.rect(self._surf, (18, 14, 4), cr, border_radius=2)
                    for ex, al in ((4, 25), (2, 65)):
                        gw = cr.w + ex * 2
                        gh = cr.h + ex * 2
                        gs = pygame.Surface((gw, gh), pygame.SRCALPHA)
                        pygame.draw.rect(gs, (*col, al), gs.get_rect(), border_radius=4)
                        self._surf.blit(gs, (cr.x - ex, cr.y - ex))
                    pygame.draw.rect(self._surf, col, cr, 2, border_radius=2)

                elif is_vi:
                    pygame.draw.rect(self._surf, _THEME.TILE_VISITED, cr, border_radius=2)
                    pygame.draw.rect(self._surf, (*_THEME.PANEL_BORDER, 90), cr, 1, border_radius=2)

                else:
                    pygame.draw.rect(self._surf, _THEME.TILE_EMPTY, cr, border_radius=2)
                    pygame.draw.rect(self._surf, (*_THEME.PANEL_BORDER, 35), cr, 1, border_radius=2)

        if font:
            lbl = font.render("SECTOR MAP", True, _THEME.HEADER_FG)
            self._surf.blit(lbl, (m, m + 2))
        self.blit_to(target)


# ── StatusPanel ───────────────────────────────────────────────────────────────

class StatusPanel(_Panel):
    _M      = 12
    _BAR_H  = 13
    _LBL_H  = 15
    _GAP    = 6

    def __init__(self, rect: pygame.Rect):
        super().__init__(rect)
        self._disp_hp  = None
        self._disp_mhp = None

    def _draw_bar(self, y: int, label: str, val: float, max_val: float,
                  color: tuple, font, bar_w: int, m: int,
                  ticks: int, pulse: bool = False) -> int:
        ratio = max(0.0, min(1.0, val / max_val)) if max_val > 0 else 0.0
        if font:
            ls = font.render(label, True, _THEME.TEXT_DIM)
            self._surf.blit(ls, (m, y))
            val_str = f"{int(val)}/{int(max_val)}" if max_val > 1 else f"{int(val)}"
            vs = font.render(val_str, True, _THEME.TEXT_FG)
            self._surf.blit(vs, (m + bar_w - vs.get_width(), y))
            y += self._LBL_H + 1
        tr = pygame.Rect(m, y, bar_w, self._BAR_H)
        pygame.draw.rect(self._surf, (13, 13, 30), tr, border_radius=3)
        if ratio > 0:
            fw    = max(3, int(bar_w * ratio))
            alpha = 255
            if pulse:
                alpha = int(148 + 107 * abs(math.sin(ticks / 215)))
            fs = pygame.Surface((fw, self._BAR_H), pygame.SRCALPHA)
            r, g, b = color
            pygame.draw.rect(fs, (r, g, b, alpha), fs.get_rect(), border_radius=3)
            self._surf.blit(fs, (m, y))
        pygame.draw.rect(self._surf, (*_THEME.PANEL_BORDER, 65), tr, 1, border_radius=3)
        return y + self._BAR_H + self._GAP

    def render(self, target: pygame.Surface, player, font_sm, font_lbl):
        self._draw_bg()
        m    = self._M
        y    = m
        t_ms = pygame.time.get_ticks()
        bw   = self.rect.w - m * 2

        if font_sm:
            hs = font_sm.render("STATUS", True, _THEME.HEADER_FG)
            self._surf.blit(hs, (m, y))
            y += hs.get_height() + 5

        # HP lerp
        th, tm = float(player.hp), float(player.max_hp)
        if self._disp_hp is None:
            self._disp_hp, self._disp_mhp = th, tm
        else:
            self._disp_hp  += (th - self._disp_hp)  * 0.18
            self._disp_mhp += (tm - self._disp_mhp) * 0.18
        hr = self._disp_hp / self._disp_mhp if self._disp_mhp > 0 else 0
        hc = _THEME.HP_COLOR if hr > 0.5 else (_THEME.HP_MID if hr > 0.25 else _THEME.HP_LOW)
        y  = self._draw_bar(y, "HP", self._disp_hp, self._disp_mhp, hc, font_lbl, bw, m, t_ms)

        y = self._draw_bar(y, "허기", player.hunger, 100,
                           _THEME.HUNGER_COLOR, font_lbl, bw, m, t_ms)
        y = self._draw_bar(y, "갈증", player.thirst, 100,
                           _THEME.THIRST_COLOR, font_lbl, bw, m, t_ms)
        ar = player.alert_level / 100
        ac = (_THEME.ALERT_SAFE if ar < 0.4
              else _THEME.ALERT_WARN if ar < 0.7 else _THEME.ALERT_DANGER)
        y  = self._draw_bar(y, "경보", player.alert_level, 100, ac, font_lbl,
                            bw, m, t_ms, pulse=(ar > 0.7))

        y += 5
        if font_lbl:
            extras = [
                (f"고철: {player.materials}",           _THEME.TEXT_FG),
                (f"평판: {player.reputation:+d}",
                 _THEME.HP_COLOR if player.reputation >= 0 else _THEME.HP_LOW),
                (f"턴:   {player.turn_count}",           _THEME.TEXT_DIM),
            ]
            for txt, col in extras:
                if y + self._LBL_H < self.rect.h - m:
                    s = font_lbl.render(txt, True, col)
                    self._surf.blit(s, (m, y))
                    y += self._LBL_H + 3

        self.blit_to(target)


# ── ScenePanel ────────────────────────────────────────────────────────────────

class ScenePanel(_Panel):
    """2단계(Phase 2) 씬 패널 — 몬스터/이벤트/파밍 시각화."""
    _M = 10

    def __init__(self, rect: pygame.Rect):
        super().__init__(rect)
        self._mode   = "idle"    # "idle" | "enemy" | "event"
        self._title  = ""
        self._body   = ""
        self._art    = ""
        self._hp     = 0
        self._max_hp = 1

    def set_enemy(self, name: str, hp: int, max_hp: int, art: str = ""):
        self._mode   = "enemy"
        self._title  = name
        self._hp     = float(hp)
        self._max_hp = float(max_hp)
        self._art    = art

    def update_enemy_hp(self, hp: int):
        self._hp = float(hp)

    def set_event(self, title: str, body: str):
        self._mode  = "event"
        self._title = title
        self._body  = body

    def set_idle(self):
        self._mode = "idle"

    def render(self, target: pygame.Surface, font_ascii, font_kor):
        self._draw_bg()
        m    = self._M
        t_ms = pygame.time.get_ticks()

        if self._mode == "enemy":
            # 적 HP 바
            ratio = max(0.0, min(1.0, self._hp / self._max_hp)) if self._max_hp > 0 else 0
            bw    = self.rect.w - m * 2
            if font_ascii:
                ts = font_ascii.render(self._title, True, _THEME.HEADER_FG)
                self._surf.blit(ts, (m, m))
                vs = font_ascii.render(f"{int(self._hp)}/{int(self._max_hp)}", True, _THEME.TEXT_FG)
                self._surf.blit(vs, (m + bw - vs.get_width(), m))
            tr  = pygame.Rect(m, m + 26, bw, 12)
            pygame.draw.rect(self._surf, (13, 13, 30), tr, border_radius=3)
            if ratio > 0:
                fw   = max(2, int(bw * ratio))
                ec   = _THEME.ALERT_SAFE if ratio > 0.5 else (
                       _THEME.ALERT_WARN if ratio > 0.25 else _THEME.ALERT_DANGER)
                fs   = pygame.Surface((fw, 12), pygame.SRCALPHA)
                r, g, b = ec
                pygame.draw.rect(fs, (r, g, b, 220), fs.get_rect(), border_radius=3)
                self._surf.blit(fs, (m, m + 26))
            pygame.draw.rect(self._surf, (*_THEME.PANEL_BORDER, 65), tr, 1, border_radius=3)

            # ASCII 아트
            if self._art and font_ascii:
                art_y = m + 46
                for line in self._art.strip('\n').split('\n')[:12]:
                    # 글리치 효과 (HP 낮을 때)
                    if ratio < 0.3 and t_ms % 400 < 40:
                        line = line[:max(0, len(line) - 3)] + "░▒▓"[:3]
                    s = font_ascii.render(line, True, _THEME.TEXT_FG)
                    if art_y + s.get_height() < self.rect.h - m:
                        self._surf.blit(s, (m, art_y))
                    art_y += s.get_height()

        elif self._mode == "event":
            if font_ascii:
                ts = font_ascii.render(self._title, True, _THEME.HEADER_FG)
                self._surf.blit(ts, (m, m))
            if font_kor:
                body_y = m + 28
                for line in self._body[:200].split('\n')[:8]:
                    bs = font_kor.render(line, True, _THEME.TEXT_FG)
                    if body_y + bs.get_height() < self.rect.h - m:
                        self._surf.blit(bs, (m, body_y))
                    body_y += bs.get_height() + 2

        self.blit_to(target)


# ── LogPanel ──────────────────────────────────────────────────────────────────

class LogPanel(_Panel):
    _M = 10

    def render(self, target: pygame.Surface, term: 'PygameTerminal'):
        self._draw_bg()
        m  = self._M
        ch = term._ch
        uw = term._unit_w
        buf = term._buf

        visible = max(1, (self.rect.h - m * 2) // ch)
        n       = len(buf)
        start   = max(0, n - visible)
        y       = m + (self.rect.h - m * 2) % ch // 2   # 하단 정렬을 위한 시작 오프셋

        # 실제 표시 줄수 계산 후 상단에서 시작
        shown = min(visible, n - start)
        y = m + (self.rect.h - m * 2 - shown * ch) // 2
        y = max(m, y)

        for line in buf[start:]:
            x = m
            for seg, color in line:
                for c in seg:
                    if term._is_box_char(c):
                        cs = term._get_box_surf(c, color)
                    elif term._is_emoji(c):
                        cs = term._get_emoji_surf(c, color)
                    else:
                        cs = term._get_char_surf(c, color)
                    if x + cs.get_width() <= self.rect.w - m:
                        self._surf.blit(cs, (x, y))
                    x += uw * (2 if term._is_wide_char(c) else 1)
            y += ch
            if y >= self.rect.h - m:
                break

        self.blit_to(target)


# ── ActionPanel ───────────────────────────────────────────────────────────────

class ActionPanel(_Panel):
    _M    = 12
    _COLS = 2

    def __init__(self, rect: pygame.Rect):
        super().__init__(rect)
        self._actions: list = []

    def set_actions(self, actions: list):
        self._actions = actions

    def render(self, target: pygame.Surface, font_ascii, font_kor):
        self._draw_bg()
        m = self._M
        if not self._actions:
            self.blit_to(target)
            return

        ncols  = self._COLS
        nrows  = max(1, (len(self._actions) + ncols - 1) // ncols)
        col_w  = (self.rect.w - m * 2) // ncols
        row_h  = max(20, (self.rect.h - m * 2) // nrows)

        for i, (key, label, enabled) in enumerate(self._actions):
            col = i % ncols
            row = i // ncols
            x   = m + col * col_w
            y   = m + row * row_h

            # 키 배지
            bc = _THEME.TILE_PLAYER if enabled else _THEME.TEXT_DIM
            badge = pygame.Rect(x, y + 1, 26, 20)
            bs = pygame.Surface((badge.w, badge.h), pygame.SRCALPHA)
            pygame.draw.rect(bs, (*bc, 200), bs.get_rect(), border_radius=3)
            self._surf.blit(bs, (badge.x, badge.y))

            if font_ascii:
                short_key = key[:3]
                ks = font_ascii.render(short_key, True,
                                       _THEME.PANEL_BG if enabled else (35, 35, 55))
                kx = badge.x + (badge.w - ks.get_width()) // 2
                ky = badge.y + (badge.h - ks.get_height()) // 2
                self._surf.blit(ks, (kx, ky))

            # 라벨
            lc  = _THEME.TEXT_FG if enabled else _THEME.TEXT_DIM
            f   = font_kor or font_ascii
            try:
                ls = f.render(label, True, lc)
            except Exception:
                ls = font_ascii.render(label[:10], True, lc) if font_ascii else None
            if ls:
                ly = y + (22 - ls.get_height()) // 2 + 1
                self._surf.blit(ls, (x + 30, ly))

        self.blit_to(target)


# ── UIManager ─────────────────────────────────────────────────────────────────

class UIManager:
    """패널 기반 UI 조율자. set_state()로 상태 전환, update()로 데이터 갱신."""

    _LEFT_W   = 280
    _HEADER_H = 44
    _ACTION_H = 148
    _SCENE_H  = 0    # Phase 1: 씬 패널 비활성 (로그가 우측 전체 차지)

    def __init__(self, terminal: 'PygameTerminal', version: str = ""):
        self._term    = terminal
        self._version = version
        self._active  = False
        self._state   = "exploration"
        self._player  = None
        self._grid    = None

        # 패널 (activate() 시 초기화)
        self.map_panel    = None
        self.status_panel = None
        self.scene_panel  = None
        self.log_panel    = None
        self.action_panel = None

    # ── 초기화 ────────────────────────────────────────────────────────────────

    def activate(self):
        """UIManager를 활성화하고 터미널에 등록."""
        cw, ch = self._term._canvas_size
        lw  = self._LEFT_W
        hh  = self._HEADER_H
        act = self._ACTION_H
        rw  = cw - lw
        half_lh = (ch - hh) // 2

        self.map_panel    = MapPanel(pygame.Rect(0,        hh,            lw, half_lh))
        self.status_panel = StatusPanel(pygame.Rect(0,     hh + half_lh,  lw, ch - hh - half_lh))
        self.scene_panel  = ScenePanel(pygame.Rect(lw,     hh,            rw, 0))   # 비활성
        self.log_panel    = LogPanel(pygame.Rect(lw,       hh,            rw, ch - hh - act))
        self.action_panel = ActionPanel(pygame.Rect(lw,    ch - act,      rw, act))

        self._active           = True
        self._term._ui_manager = self
        self._term._dirty      = True

    def deactivate(self):
        self._active           = False
        self._term._ui_manager = None
        self._term._dirty      = True

    # ── 상태 갱신 ─────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        self._state = state
        self._term._dirty = True

    def update(self, player, grid):
        self._player      = player
        self._grid        = grid
        self._term._dirty = True

    def set_actions(self, actions: list):
        """actions: [(key, label, enabled), ...]"""
        if self.action_panel:
            self.action_panel.set_actions(actions)
        self._term._dirty = True

    # Phase 2 ScenePanel 연동용 메서드
    def scene_set_enemy(self, name: str, hp: int, max_hp: int, art: str = ""):
        if self.scene_panel:
            self.scene_panel.set_enemy(name, hp, max_hp, art)
        self._term._dirty = True

    def scene_update_hp(self, hp: int):
        if self.scene_panel:
            self.scene_panel.update_enemy_hp(hp)
        self._term._dirty = True

    def scene_set_event(self, title: str, body: str):
        if self.scene_panel:
            self.scene_panel.set_event(title, body)
        self._term._dirty = True

    def scene_set_idle(self):
        if self.scene_panel:
            self.scene_panel.set_idle()
        self._term._dirty = True

    # ── 렌더링 ────────────────────────────────────────────────────────────────

    def render(self, canvas: pygame.Surface):
        if not self._active:
            return
        cw, ch = canvas.get_size()
        lw     = self._LEFT_W

        canvas.fill(_THEME.BG)
        self._draw_header(canvas)

        if self._player and self._grid:
            self.map_panel.render(canvas, self._grid, self._player,
                                  self._term.font_ascii)
            self.status_panel.render(canvas, self._player,
                                     self._term.font_ascii, self._term.font_ascii)

        self.log_panel.render(canvas, self._term)
        self.action_panel.render(canvas, self._term.font_ascii, self._term.font_kor)

        # 구분선
        pygame.draw.line(canvas, _THEME.PANEL_BORDER, (lw, self._HEADER_H), (lw, ch), 1)

        self._draw_scanlines(canvas)

    def _draw_header(self, canvas: pygame.Surface):
        cw = canvas.get_width()
        hh = self._HEADER_H
        hs = pygame.Surface((cw, hh), pygame.SRCALPHA)
        hs.fill((*_THEME.HEADER_BG, 242))
        for i, a in enumerate((28, 68, 155)):
            pygame.draw.line(hs, (*_THEME.PANEL_BORDER, a),
                             (0, hh - 1 - i), (cw, hh - 1 - i))
        canvas.blit(hs, (0, 0))

        f = self._term.font_ascii
        if f:
            ts = f.render("PROTOCOL : STIGMA", True, _THEME.HEADER_FG)
            canvas.blit(ts, (14, (hh - ts.get_height()) // 2))
            if self._player:
                diff_label = {"easy": "EASY", "normal": "NORMAL", "hard": "HARD"}.get(
                    getattr(self._player, 'difficulty', 'normal'), 'NORMAL')
                info = (f"v{self._version}  |  TURN {self._player.turn_count}"
                        f"  |  {diff_label}")
                is_ = f.render(info, True, _THEME.TEXT_DIM)
                canvas.blit(is_, (cw - is_.get_width() - 14,
                                  (hh - is_.get_height()) // 2))

    def _draw_scanlines(self, canvas: pygame.Surface):
        cw, ch = canvas.get_size()
        sl = pygame.Surface((cw, ch), pygame.SRCALPHA)
        for y in range(0, ch, 3):
            pygame.draw.line(sl, (0, 0, 0, _THEME.SCANLINE_A), (0, y), (cw, y))
        canvas.blit(sl, (0, 0))
