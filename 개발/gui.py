"""
gui.py — Pygame 로그-큐 패널 렌더러

sys.stdout으로 등록하면 모든 print() 호출이 pygame 창의 로그 패널에 표시됩니다.
완성된 줄은 Surface로 미리 렌더링해 캐시하고, _render()는 캐시를 blit만 합니다.
ANSI SGR 코드를 파싱해 색상을 적용하며, read_key / input_text 등 입력 함수를
pygame 이벤트 루프로 대체합니다.
"""

import math
import re
import sys
import os
import pygame

_terminal = None   # 싱글턴 인스턴스


def get_terminal():
    return _terminal


def set_terminal(t):
    global _terminal
    _terminal = t
    _install_smooth_sleep()



def _install_smooth_sleep():
    """(예전 자리) 대기 중 화면 그리기는 PygameTerminal.__init__의 _gui_sleep이 맡는다 (메인 스레드만)."""
    return


def get_ui_manager():
    """PygameTerminal에 연결된 UIManager를 반환. 없으면 None."""
    return _terminal._ui_manager if _terminal else None


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
# 타자 연출 단위: 색상 코드(ESC[..m)는 통째로, 나머지는 한 글자씩. 쪼개면 코드가 글자로 찍힌다
_TYPE_TOKEN = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|.", re.S)
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
        self._set_window_icon()    # 창을 띄우기 전에 붙여야 작업 표시줄에도 들어간다
        self.screen = pygame.display.set_mode(self._window_size(), pygame.RESIZABLE)
        pygame.display.set_caption(title)

        self._render()

        # time.sleep → 대기 중에도 화면을 그리는 버전으로 교체 (메인 스레드만).
        # 키 입력은 꺼내지 않고 큐에 남겨 다음 입력 대기에서 받는다 (예전에는 대기 중 누른 키를 버렸다).
        # 다른 스레드(GM 서버 대기 등)는 원래 sleep: 거기서 pygame 이벤트를 만지면 안 된다 (자동 테스트에서 충돌 확인).
        import threading as _threading
        import time as _time_mod
        _orig_sleep = _time_mod.sleep
        _main = _threading.main_thread()
        _self = self

        def _gui_sleep(seconds: float):
            if seconds <= 0:
                return
            if _threading.current_thread() is not _main:
                return _orig_sleep(seconds)
            _self._dirty = True
            _self._render()
            end = _time_mod.perf_counter() + seconds
            while True:
                left = end - _time_mod.perf_counter()
                if left <= 0:
                    break
                pygame.event.pump()
                mgr = _self._ui_manager
                if mgr is not None and getattr(mgr, "_active", False):
                    _self._dirty = True
                    _self._render()
                    _orig_sleep(min(left, 1 / 60))
                else:
                    _orig_sleep(min(left, 0.01))
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
        """창 아이콘 그림. pygame은 PNG로 압축된 .ico를 못 읽어(Unsupported ICO bitmap format) 아이콘이 조용히
        빠졌었다. 그래서 같은 그림의 icon.png를 먼저 쓴다."""
        base_dev = os.path.dirname(os.path.abspath(__file__))
        dirs = []
        if getattr(sys, 'frozen', False):
            dirs.append(os.path.join(sys._MEIPASS, 'assets'))
        dirs.append(os.path.join(base_dev, '..', 'assets'))
        for d in dirs:
            for name in ('icon.png', 'icon.ico'):
                p = os.path.normpath(os.path.join(d, name))
                if os.path.exists(p):
                    return p
        return None

    def _set_window_icon(self):
        if sys.platform == 'win32':
            # 소스로 돌리면 작업 표시줄이 python.exe로 묶여 파이썬 아이콘이 뜬다: 게임 고유 ID로 따로 묶는다
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ProtocolStigma.Game')
            except Exception:
                pass
        ico = self._find_ico()
        if ico:
            try:
                img = pygame.image.load(ico)
                if img.get_width() > 256:  # 원본 icon.png는 2048px: 창 아이콘은 줄여서 붙인다
                    img = pygame.transform.smoothscale(img, (256, 256))
                pygame.display.set_icon(img)
            except Exception as e:
                if sys.__stderr__:
                    print(f"[icon] {e}", file=sys.__stderr__)

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
        """time.sleep() 대용 — 대기 중에도 화면을 계속 그린다 (그림 화면이면 30fps).
        예전에는 처음에 한 번만 그려 전투의 공격·반격 사이 1초가 통째로 멈췄다 (렉처럼 끊김)."""
        import time as _t
        self._dirty = True
        self._render()
        end = _t.perf_counter() + seconds
        while True:
            left = end - _t.perf_counter()
            if left <= 0:
                break
            self._pump()
            mgr = self._ui_manager
            if mgr is not None and getattr(mgr, "_active", False):
                self._dirty = True
                self._render()
            pygame.time.wait(int(min(left, 1 / 60) * 1000) or 1)

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
            # 버퍼에 실제 내용이 없으면 렌더 건너뜀 — 전환 중 검은 화면 방지
            if not any(self._buf):
                self._dirty = False
                return
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
            self._vis_lines = []   # (버퍼 줄 번호, y) — 글 화면 선택지를 마우스·방향키로 고를 때 쓴다

            for i, line in enumerate(self._buf[start:], start=start):
                is_current = (i == n_lines - 1)
                self._vis_lines.append((i, y))
                if self._opt_line == i:   # 고른 선택지 줄 강조
                    band = pygame.Surface((w - self.PAD_X * 2 + 8, self._ch + 4), pygame.SRCALPHA)
                    band.fill((236, 196, 92, 38))
                    self._canvas.blit(band, (self.PAD_X - 4, y - 2))
                    pygame.draw.line(self._canvas, (236, 196, 92), (self.PAD_X - 4, y - 2), (self.PAD_X - 4, y + self._ch + 1), 2)
                if line:
                    surf = self._get_line_surf(line, is_current)
                    self._canvas.blit(surf, (self.PAD_X, y))
                y += self._ch
                if y > h - self.PAD_Y:
                    break

        self._crossfade()

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
        """렌더 중에 창 이벤트만 처리한다. 그림 화면(맵·이벤트)이 떠 있으면 키 입력은 꺼내지 않고 큐에 남긴다:
        화면을 매 프레임 다시 그리게 바꾼 뒤로, 여기서 키를 꺼내 버리면 누른 키가 가끔 사라졌다."""
        resize = getattr(pygame, 'WINDOWRESIZED', -1)
        for event in pygame.event.get([pygame.QUIT, pygame.VIDEORESIZE] + ([resize] if resize != -1 else [])):
            if event.type == pygame.QUIT:
                sys.exit()
            self._dirty = True
        mgr = self._ui_manager
        if mgr is not None and getattr(mgr, "_active", False):
            return
        for event in pygame.event.get(pygame.KEYDOWN):  # 터미널 화면에서는 예전처럼 (연출 중 누른 키는 버린다)
            if event.key == pygame.K_F11:
                self.toggle_fullscreen()
            elif mgr is not None and hasattr(mgr, "_on_keydown"):
                u = event.unicode
                if u and 0x20 <= ord(u) <= 0x7E:
                    mgr._on_keydown(u.upper())

    XFADE_MS = 260

    def _crossfade(self):
        """화면(맵·이벤트·전투·메뉴·카드·장면 그림)이 바뀌면 직전 화면을 잠깐 겹쳐 녹인다.
        예전에는 한 프레임에 툭 바뀌어서, 새 그림을 읽는 동안 멈췄다가 갑자기 튀는 것처럼 보였다."""
        mgr = self._ui_manager
        active = mgr is not None and getattr(mgr, "_active", False)
        ident = (id(mgr), getattr(mgr, "art_path", None), getattr(mgr, "card", None)) if active else None
        now = pygame.time.get_ticks()
        if not hasattr(self, "_xf_prev"):
            self._xf_prev = pygame.Surface(self._canvas_size, 0, self._canvas)
            self._xf_src = pygame.Surface(self._canvas_size, 0, self._canvas)
            self._xf_ident, self._xf_start, self._xf_has_prev = ident, -10**9, False
        if ident != self._xf_ident:
            self._xf_ident = ident
            if self._xf_has_prev:  # 직전 프레임을 페이드 원본으로 (새로 만들지 않고 두 판을 맞바꾼다)
                self._xf_prev, self._xf_src = self._xf_src, self._xf_prev
                self._xf_start = now
        self._xf_prev.blit(self._canvas, (0, 0))
        self._xf_has_prev = True
        k = (now - self._xf_start) / self.XFADE_MS
        if k < 1:
            a = int(255 * (1 - k) ** 2)  # 처음엔 빨리, 끝은 부드럽게
            # 알파 255는 pygame이 느린 경로(한 장 18ms)로 그려 딱 그 프레임이 끊겼다: 그땐 그냥 복사한다
            self._xf_src.set_alpha(None if a >= 250 else a)
            self._canvas.blit(self._xf_src, (0, 0))
            self._dirty = True

    def toggle_fullscreen(self):
        """F11 전체화면 전환 — canvas는 고정, screen만 교체."""
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self._window_size(), pygame.RESIZABLE)
        self._dirty = True
        self._render()

    def _window_size(self):
        """창 크기: 보통은 canvas 그대로, 화면이 작으면(1366×768 노트북 등) 비율을 지켜 줄인다.
        canvas(948×944)가 화면보다 크면 아래 조작 안내가 화면 밖으로 잘렸다. 작업 표시줄·제목 표시줄 몫으로 90%만 쓴다."""
        cw, ch = self._canvas_size
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError, AttributeError):
            return cw, ch
        scale = min(1.0, dw * 0.9 / cw, dh * 0.9 / ch)
        return int(cw * scale), int(ch * scale)

    # ── 화면 제어 ─────────────────────────────────────────────────────────────
    def clear(self):
        if self._ui_manager and self._ui_manager._active:
            # UIManager 모드: 버퍼를 초기화하지 않고 빈 줄만 추가 (LogPanel 연속 표시)
            self._buf.append([])
            self._dirty = True
            self._render()
        else:
            # 터미널 텍스트 모드: 버퍼만 초기화, 렌더는 다음 print()가 담당
            # (_render()를 여기서 호출하면 빈 버퍼가 즉시 검은 화면으로 표시됨)
            self._buf = [[]]
            self._dirty = True
        self._fg    = _DEFAULT_COLOR
        self._bright = False
        self._dim   = False

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

    def _idle_frame(self):
        """키를 기다리는 동안: 그림 화면(맵·이벤트)이 떠 있으면 계속 다시 그려 연출이 멈추지 않게 한다 (30fps).
        예전에는 대기 시작에 한 번만 그려서 안개·패럴랙스가 입력이 올 때만 움직였다 (뚝뚝 끊김)."""
        mgr = self._ui_manager
        if mgr is not None and getattr(mgr, "_active", False):
            self._dirty = True
            self._render()
            if not hasattr(self, "_idle_clock"):
                self._idle_clock = pygame.time.Clock()
            self._idle_clock.tick(60)
        else:
            pygame.time.wait(10)

    # ── 글 화면 선택지 (마우스·방향키) ───────────────────────────────────────
    # 그림 화면이 아닌 글 화면(행상인, 소모품, 선택 이벤트 …)에 찍힌 "[1] …", "1. …" 줄을 선택지로 본다.
    # 마우스를 올리면 강조, 누르면 그 키. ↑↓로 고르고 Enter·Space로 누른다. 숫자키는 그대로.
    _OPT_RE = re.compile(r"^\s*(?:\[\s*([0-9A-Za-z]{1,2})\s*\]|([0-9])[.)])\s+\S")
    _opt_line = None

    def _text_options(self):
        out = []
        for i, y in getattr(self, "_vis_lines", ()):
            if i >= len(self._buf):
                continue
            m = self._OPT_RE.match("".join(seg[0] for seg in self._buf[i]))
            if m:
                out.append(((m.group(1) or m.group(2)).upper(), i, y))
        return out

    def _to_canvas(self, pos):
        sw, sh = self.screen.get_size()
        cw, ch = self._canvas_size
        scale = min(sw / cw, sh / ch)
        return (pos[0] - (sw - cw * scale) / 2) / scale, (pos[1] - (sh - ch * scale) / 2) / scale

    def _text_input(self, event):
        """글 화면에서 선택지 마우스·방향키 처리. 키를 돌려주면 그 키를 누른 것."""
        opts = self._text_options()
        if not opts:
            return None
        lines = [i for _, i, _ in opts]
        sel = lines.index(self._opt_line) if self._opt_line in lines else None
        new = sel
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            cx, cy = self._to_canvas(event.pos)
            hit = next((n for n, (_, _, y) in enumerate(opts) if y - 2 <= cy < y + self._ch + 2
                        and self.PAD_X - 4 <= cx <= self._canvas_size[0] - self.PAD_X), None)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and hit is not None:
                self._opt_line = None
                return opts[hit][0]
            if event.type == pygame.MOUSEMOTION:
                new = hit
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                step = -1 if event.key == pygame.K_UP else 1
                new = (0 if step > 0 else len(opts) - 1) if sel is None else (sel + step) % len(opts)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and sel is not None:
                self._opt_line = None
                return opts[sel][0]
        if new != sel:
            self._opt_line = lines[new] if new is not None else None
            try:
                import sound
                sound.sfx("ui_move")
            except Exception:
                pass
            self._dirty = True
            self._render()
        return None

    def read_key(self) -> str:
        """키 하나. 그림 화면이 떠 있으면 그 화면의 on_input(마우스·방향키·발밑 버튼)을 먼저,
        글 화면이면 찍힌 선택지를 마우스·방향키로 고를 수 있다."""
        # 입력을 받기 시작하기 전에 쌓인 키는 버린다: 연출·대기 중에 누른 키가 다음 행동으로 이어지면
        # 전투에서 공방이 두 번씩 오갔다. 이제부터 누르는 키만 받는다.
        pygame.event.clear((pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN))
        self._opt_line = None
        self._dirty = True
        self._render()
        while True:
            mgr = self._ui_manager
            active = mgr is not None and getattr(mgr, "_active", False)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                    continue
                if active and hasattr(mgr, "on_input"):
                    r = mgr.on_input(event)
                elif not active:
                    r = self._text_input(event)
                else:
                    r = None
                if r:
                    return r
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:  # 화면이 뜻을 주지 않은 ESC는 무시 (예전엔 게임이 바로 꺼졌다)
                        continue
                    ch = self._resolve_key(event)
                    if ch:
                        return ch
            self._idle_frame()

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
                    elif event.key == pygame.K_ESCAPE:  # 무시 (예전엔 게임 종료)
                        continue
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
        """메시지 없이 아무 키나(마우스 클릭도) 대기. 화면을 다시 그리지 않으므로 배너 표시 유지."""
        pygame.event.clear(pygame.MOUSEBUTTONDOWN)  # 연출 중에 누른 클릭으로 넘어가지 않게
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                        continue
                    if event.key == pygame.K_ESCAPE:  # ESC는 무시
                        continue
                    return
            self._idle_frame()

    # ── 타이핑 연출 ───────────────────────────────────────────────────────────
    def type_text_animated(self, text: str, speed: float = 0.015):
        delay_ms = max(1, int(speed * 1000))
        skipped  = False
        for char in _TYPE_TOKEN.findall(text):
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
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):  # 글자 연출 건너뛰기 (예전엔 ESC)
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
    """1막 군용/산업 색상 테마 — 인광 녹색 단말기 + 호박색 강조."""
    BG           = (3,   6,   2)
    PANEL_BG     = (6,  14,   5)
    PANEL_BORDER = (50, 120,  38)
    HEADER_BG    = (4,  10,   3)
    HEADER_FG    = (110, 225, 70)
    TEXT_FG      = (142, 202, 80)
    TEXT_DIM     = (58,  98,  42)
    TILE_EMPTY   = (8,   20,   6)
    TILE_VISITED = (22,  52,  18)
    TILE_PLAYER  = (80,  240,  55)
    TILE_BUNKER  = (205, 165,  28)
    HP_COLOR     = (55,  210,  60)
    HP_MID       = (210, 168,  28)
    HP_LOW       = (215,  45,  45)
    HUNGER_COLOR = (188, 148,  32)
    THIRST_COLOR = (35,  168, 215)
    ALERT_SAFE   = (55,  210,  60)
    ALERT_WARN   = (210, 168,  28)
    ALERT_DANGER = (215,  45,  45)
    SCANLINE_A   = 6


_THEME = _ActTheme()


# ── _Panel 기반 클래스 ────────────────────────────────────────────────────────

class _Panel:
    """모든 UI 패널의 기반. rect는 canvas 좌표계 기준."""

    def __init__(self, rect: pygame.Rect):
        self.rect  = rect
        self._surf = pygame.Surface((max(1, rect.w), max(1, rect.h)), pygame.SRCALPHA)

    def _draw_bg(self, border_color=None):
        bc   = border_color or _THEME.PANEL_BORDER
        top  = tuple(min(255, int(v * 2.0)) for v in bc)   # 상단 강조선 (더 밝음)
        self._surf.fill(_THEME.PANEL_BG)
        rw, rh = self._surf.get_size()
        # 외곽 테두리 2px
        pygame.draw.rect(self._surf, bc, (0, 0, rw, rh), 2)
        # 상단 밝은 강조선 (군용 탭 느낌)
        pygame.draw.line(self._surf, top, (2, 0), (rw - 3, 0), 2)

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
            lbl = font.render("[ SECTOR MAP ]", True, _THEME.HEADER_FG)
            self._surf.blit(lbl, (m, m + 2))
            coord = f"POS {grid.player_pos[0]},{grid.player_pos[1]}"
            cs = font.render(coord, True, _THEME.TEXT_DIM)
            self._surf.blit(cs, (self.rect.w - cs.get_width() - m, m + 2))
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
            hs = font_sm.render("[ STATUS ]", True, _THEME.HEADER_FG)
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

        else:   # idle
            if font_ascii:
                lbl = font_ascii.render("[ TACTICAL DISPLAY ]", True, _THEME.TEXT_DIM)
                cx  = (self.rect.w - lbl.get_width()) // 2
                cy  = (self.rect.h - lbl.get_height()) // 2
                self._surf.blit(lbl, (cx, cy))

        self.blit_to(target)


# ── LogPanel ──────────────────────────────────────────────────────────────────

class LogPanel(_Panel):
    _M = 10

    def __init__(self, rect: pygame.Rect):
        super().__init__(rect)
        self._prev_n   = 0
        self._scroll_y = 0.0   # 양수 = 콘텐츠가 아래로 밀려남 (올라오며 0에 수렴)

    def render(self, target: pygame.Surface, term: 'PygameTerminal'):
        self._draw_bg()
        m   = self._M
        ch  = term._ch
        uw  = term._unit_w
        buf = term._buf

        visible = max(1, (self.rect.h - m * 2) // ch)
        n       = len(buf)

        # 새 줄 추가 시 스크롤 오프셋 설정 → lerp로 0 수렴
        if n > self._prev_n:
            added = min(n - self._prev_n, visible)
            self._scroll_y = min(float(ch * 2), self._scroll_y + added * ch * 0.75)
        self._prev_n = n
        if self._scroll_y > 0.8:
            self._scroll_y *= 0.80
        else:
            self._scroll_y = 0.0

        # 스크롤 여유분만큼 더 위에서 읽기 (상단 공백 방지)
        extra = int(self._scroll_y) // max(ch, 1) + 1
        start = max(0, n - visible - extra)
        y     = m + int(self._scroll_y)

        for line in buf[start:]:
            x = m
            if m <= y < self.rect.h - m:  # 가시 범위 내 줄만 렌더
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
            if y >= self.rect.h - m + int(self._scroll_y):
                break

        self.blit_to(target)


# ── ActionPanel ───────────────────────────────────────────────────────────────

class ActionPanel(_Panel):
    _M    = 12
    _COLS = 2

    def __init__(self, rect: pygame.Rect):
        super().__init__(rect)
        self._actions:   list = []
        self._flash_key: str  = ""
        self._flash_ms:  int  = 0

    def set_actions(self, actions: list):
        self._actions = actions

    def flash_key(self, char: str):
        """입력된 키 문자에 해당하는 배지를 250ms 동안 하이라이트."""
        self._flash_key = char.upper()
        self._flash_ms  = pygame.time.get_ticks()

    def _is_flash(self, action_key: str) -> bool:
        if not self._flash_key:
            return False
        if pygame.time.get_ticks() - self._flash_ms > 250:
            return False
        return self._flash_key in action_key.upper()

    def render(self, target: pygame.Surface, font_ascii, font_kor):
        self._draw_bg()
        m = self._M
        f = font_kor or font_ascii

        if not self._actions:
            if font_ascii:
                lbl = font_ascii.render("[ COMMANDS ]", True, _THEME.TEXT_DIM)
                self._surf.blit(lbl, (m, m + 2))
            self.blit_to(target)
            return

        # 헤더
        if font_ascii:
            hdr = font_ascii.render("[ COMMANDS ]", True, _THEME.HEADER_FG)
            self._surf.blit(hdr, (m, m + 2))
        hdr_h = (font_ascii.get_height() + 6) if font_ascii else 0

        ncols = self._COLS
        avail_h = self.rect.h - m * 2 - hdr_h
        nrows   = max(1, (len(self._actions) + ncols - 1) // ncols)
        col_w   = (self.rect.w - m * 2) // ncols
        row_h   = max(22, avail_h // nrows)

        for i, (key, label, enabled) in enumerate(self._actions):
            col   = i % ncols
            row   = i // ncols
            x     = m + col * col_w
            y     = m + hdr_h + row * row_h
            flash = self._is_flash(key)

            # 키 배지 — 군용 스타일: 각진 사각형 + 밝은 테두리
            key_bg   = _THEME.HEADER_FG if flash else (_THEME.PANEL_BORDER if enabled else _THEME.TEXT_DIM)
            key_fg   = _THEME.PANEL_BG  if flash else (_THEME.PANEL_BG if enabled else _THEME.TEXT_DIM)
            badge_w  = max(26, font_ascii.size(key[:4])[0] + 8) if font_ascii else 28
            badge_h  = row_h - 4
            pygame.draw.rect(self._surf, key_bg,  (x, y + 2, badge_w, badge_h))
            pygame.draw.rect(self._surf, tuple(min(255, int(v * 1.5)) for v in key_bg),
                             (x, y + 2, badge_w, badge_h), 1)
            if font_ascii:
                short_key = key[:4]
                ks = font_ascii.render(short_key, True, key_fg)
                kx = x + (badge_w - ks.get_width()) // 2
                ky = y + 2 + (badge_h - ks.get_height()) // 2
                self._surf.blit(ks, (kx, ky))

            # 라벨
            lc = _THEME.HEADER_FG if flash else (_THEME.TEXT_FG if enabled else _THEME.TEXT_DIM)
            try:
                ls = f.render(label, True, lc) if f else None
            except Exception:
                ls = font_ascii.render(label[:10], True, lc) if font_ascii else None
            if ls:
                ly = y + 2 + (badge_h - ls.get_height()) // 2
                self._surf.blit(ls, (x + badge_w + 6, ly))

        self.blit_to(target)


# ── UIManager ─────────────────────────────────────────────────────────────────

class UIManager:
    """패널 기반 UI 조율자. set_state()로 상태 전환, update()로 데이터 갱신."""

    _HEADER_H    = 46
    _ACTION_H    = 100     # 3열 2행 배지 기준
    _LEFT_RATIO  = 0.30    # 좌측 패널 너비 (맵+스탯)
    _SCENE_RATIO = 0.22    # 씬 패널 높이 (전투 시 적 아트) — 줄여서 로그 공간 확보
    _MAP_RATIO   = 0.40    # 좌측 중 맵 패널 비율

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
        hh   = self._HEADER_H
        act  = self._ACTION_H
        lw   = int(cw * self._LEFT_RATIO)
        rw   = cw - lw
        cont = ch - hh                         # 헤더 제외 콘텐츠 높이
        sc   = int(cont * self._SCENE_RATIO)   # 씬 패널 높이
        log_h   = max(1, cont - sc - act)
        map_h   = int(cont * self._MAP_RATIO)
        stat_h  = cont - map_h

        self.map_panel    = MapPanel(pygame.Rect(0,        hh,          lw, map_h))
        self.status_panel = StatusPanel(pygame.Rect(0,     hh + map_h,  lw, stat_h))
        self.scene_panel  = ScenePanel(pygame.Rect(lw,     hh,          rw, sc))
        self.log_panel    = LogPanel(pygame.Rect(lw,       hh + sc,     rw, log_h))
        self.action_panel = ActionPanel(pygame.Rect(lw,    ch - act,    rw, act))

        # 레이아웃 파라미터 캐시 (render()에서 재사용)
        self._lw = lw

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

    def _on_keydown(self, char: str):
        """_pump()에서 키 입력 시 호출 — ActionPanel 플래시 트리거."""
        if self.action_panel:
            self.action_panel.flash_key(char)
        self._term._dirty = True

    # ── 렌더링 ────────────────────────────────────────────────────────────────

    def render(self, canvas: pygame.Surface):
        if not self._active:
            return
        cw, ch = canvas.get_size()
        lw = getattr(self, '_lw', int(cw * self._LEFT_RATIO))

        canvas.fill(_THEME.BG)
        self._draw_header(canvas)

        if self._player and self._grid:
            self.map_panel.render(canvas, self._grid, self._player,
                                  self._term.font_ascii)
            self.status_panel.render(canvas, self._player,
                                     self._term.font_ascii, self._term.font_kor)

        self.scene_panel.render(canvas, self._term.font_ascii, self._term.font_kor)
        self.log_panel.render(canvas, self._term)
        self.action_panel.render(canvas, self._term.font_ascii, self._term.font_kor)

        # 구분선 — 군용: 2px 실선
        bright = tuple(min(255, int(v * 2.0)) for v in _THEME.PANEL_BORDER)
        pygame.draw.line(canvas, bright, (lw, self._HEADER_H), (lw, ch), 2)
        sc_h = self.scene_panel.rect.h if self.scene_panel else 0
        if sc_h > 0:
            sep_y = self._HEADER_H + sc_h
            pygame.draw.line(canvas, _THEME.PANEL_BORDER, (lw, sep_y), (cw, sep_y), 2)

        self._draw_scanlines(canvas)

    def _draw_header(self, canvas: pygame.Surface):
        cw = canvas.get_width()
        hh = self._HEADER_H
        # 헤더 배경
        pygame.draw.rect(canvas, _THEME.HEADER_BG, (0, 0, cw, hh))
        # 하단 밝은 구분선 2px
        bright = tuple(min(255, int(v * 2.0)) for v in _THEME.PANEL_BORDER)
        pygame.draw.line(canvas, bright,          (0, hh - 1), (cw, hh - 1), 2)
        pygame.draw.line(canvas, _THEME.PANEL_BORDER, (0, hh - 3), (cw, hh - 3), 1)
        # 세로 구분 마커 (군용 느낌)
        pygame.draw.rect(canvas, _THEME.PANEL_BORDER, (0, 0, 3, hh))

        f = self._term.font_ascii
        if f:
            ts = f.render("// PROTOCOL : STIGMA //", True, _THEME.HEADER_FG)
            canvas.blit(ts, (14, (hh - ts.get_height()) // 2))
            if self._player:
                diff_label = {"easy": "EASY", "normal": "NORMAL", "hard": "HARD"}.get(
                    getattr(self._player, 'difficulty', 'normal'), 'NORMAL')
                turn_str = f"{self._player.turn_count:03d}"
                info = f"[ v{self._version} ]  T:{turn_str}  {diff_label}"
                is_ = f.render(info, True, _THEME.TEXT_DIM)
                canvas.blit(is_, (cw - is_.get_width() - 14,
                                  (hh - is_.get_height()) // 2))

    def _draw_scanlines(self, canvas: pygame.Surface):
        cw, ch = canvas.get_size()
        sl = pygame.Surface((cw, ch), pygame.SRCALPHA)
        for y in range(0, ch, 3):
            pygame.draw.line(sl, (0, 0, 0, _THEME.SCANLINE_A), (0, y), (cw, y))
        canvas.blit(sl, (0, 0))
