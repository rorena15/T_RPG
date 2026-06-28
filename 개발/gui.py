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
    "Malgun Gothic",       # Windows
    "Gulim",               # Windows
    "Batang",              # Windows
    "Apple SD Gothic Neo", # macOS
    "AppleGothic",         # macOS (구형)
    "Noto Sans CJK KR",   # Linux/Mac (noto 설치 시)
]

# assets/ 번들 폰트 (여기 놓으면 자동 최우선)
_BUNDLED_FONT_NAMES = ["D2Coding.ttf", "NanumGothicCoding.ttf", "font.ttf"]

# 박스/블록 그리기 유니코드 범위
_BOX_RANGES = (
    (0x2500, 0x257F),  # Box Drawing (─ │ ┤ ╡ ╢ … ╔ ═ ╗ ╚ ╝ ╣ ╠ ╦ ╩ ╬)
    (0x2580, 0x259F),  # Block Elements (▀ ▄ █ ░ ▒ ▓)
    (0x25A0, 0x25FF),  # Geometric Shapes (■ □ ▪ ▫ ◆ ◇)
)


class PygameTerminal:
    """pygame 창에 텍스트를 렌더링하는 터미널 에뮬레이터."""

    PAD_X = 14
    PAD_Y = 10
    COLS  = 92
    ROWS  = 42

    def __init__(self, title: str = "PROTOCOL: STIGMA"):
        pygame.display.init()
        pygame.font.init()

        self._title      = title
        self._font_size  = 20
        self._box_cache:  dict = {}
        self._char_cache: dict = {}
        self._buf: list[list[tuple[str, tuple]]] = [[]]
        self._fg     = _DEFAULT_COLOR
        self._bright = False
        self._dim    = False

        self._load_fonts(self._font_size)

        w = self._unit_w * self.COLS + self.PAD_X * 2
        h = self._ch     * self.ROWS + self.PAD_Y * 2
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        pygame.display.set_caption(title)

        # 창 아이콘 — assets/icon.ico 공유
        _ico = self._find_ico()
        if _ico:
            try:
                pygame.display.set_icon(pygame.image.load(_ico))
            except Exception:
                pass

        self._render()

    def _load_fonts(self, size: int):
        """폰트를 (재)로드하고 컬럼 너비 측정값을 갱신합니다. 창 리사이즈 시 재호출.

        ASCII/박스 문자는 font_ascii(Consolas 계열)로 렌더링해 글리프 정확도를 보장하고,
        한글은 font_kor(Malgun Gothic 계열)로 분리 렌더링합니다.
        """
        bundled = self._find_bundled_font()
        if bundled:
            # 번들 폰트가 있으면 모든 용도에 사용
            self.font_ascii = pygame.font.Font(bundled, size)
            self.font_kor   = self.font_ascii
            self.font_box   = self.font_ascii
        else:
            self.font_ascii = self._load_font(size, _FONT_ASCII_CANDIDATES)
            self.font_kor   = self._load_font(size, _FONT_KOR_CANDIDATES)
            self.font_box   = self.font_ascii  # 박스 문자도 ASCII 폰트로

        # 하위 호환: self.font → ASCII 폰트
        self.font = self.font_ascii

        self._cw, self._ch = self.font_ascii.size("W")

        # 1컬럼 = ASCII 폰트의 고정폭 기준 (Consolas는 모노스페이스 → 모든 ASCII 동일 폭)
        self._unit_w = self.font_ascii.size('A')[0]

        # 캐시 무효화
        self._box_cache  = {}
        self._char_cache = {}

    @staticmethod
    def _find_ico() -> str | None:
        """assets/icon.ico 경로를 탐색 (소스 실행 / PyInstaller 모두 대응)."""
        base_dev = os.path.dirname(os.path.abspath(__file__))
        candidates = []
        if getattr(sys, 'frozen', False):
            # PyInstaller --onefile: sys._MEIPASS 루트에 번들된 assets/
            candidates.append(os.path.join(sys._MEIPASS, 'assets', 'icon.ico'))
        # 소스 실행: 개발/ 의 상위 디렉터리에 assets/ 폴더
        candidates.append(os.path.join(base_dev, '..', 'assets', 'icon.ico'))
        for p in candidates:
            p = os.path.normpath(p)
            if os.path.exists(p):
                return p
        return None

    # ── 폰트 로딩 ────────────────────────────────────────────────────────────
    @staticmethod
    def _find_bundled_font() -> str | None:
        """assets/ 폴더에 번들된 폰트 파일을 탐색합니다."""
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
    def _load_font(size: int, candidates: list) -> pygame.font.Font:
        # 번들 폰트 우선
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

    @staticmethod
    def _is_box_char(c: str) -> bool:
        cp = ord(c)
        return any(lo <= cp <= hi for lo, hi in _BOX_RANGES)

    @staticmethod
    def _is_wide_char(c: str) -> bool:
        """CJK 등 2칸 너비 문자 여부."""
        cp = ord(c)
        return (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF or
                0xA960 <= cp <= 0xA97F or 0xAC00 <= cp <= 0xD7FF or
                0xF900 <= cp <= 0xFAFF or 0xFE10 <= cp <= 0xFE1F or
                0xFE30 <= cp <= 0xFE6F or 0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6)

    def _get_box_surf(self, c: str, color: tuple) -> pygame.Surface:
        """박스 문자를 _unit_w 너비로 스케일한 Surface (캐시)."""
        key = (c, color)
        if key not in self._box_cache:
            raw = self.font_box.render(c, True, color)
            if raw.get_width() != self._unit_w or raw.get_height() != self._ch:
                raw = pygame.transform.scale(raw, (self._unit_w, self._ch))
            self._box_cache[key] = raw
        return self._box_cache[key]

    def _get_char_surf(self, c: str, color: tuple) -> pygame.Surface:
        """한글은 font_kor, 그 외는 font_ascii로 렌더링 (글리프 정확도 보장)."""
        key = (c, color)
        if key not in self._char_cache:
            f = self.font_kor if self._is_wide_char(c) else self.font_ascii
            self._char_cache[key] = f.render(c, True, color)
        return self._char_cache[key]

    # ── sys.stdout 프로토콜 ───────────────────────────────────────────────────
    def write(self, text: str) -> int:
        # 렌더는 flush() 에서 일괄 처리 — print() 의 write+write('\n') 2회 호출 최적화
        self._parse(text, auto_render=False)
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
    def _parse(self, text: str, auto_render: bool = True):
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
                # 현재 줄 내용 삭제 → 같은 줄 처음부터 덮어쓰기 (progress bar 지원)
                self._buf[-1] = []
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

        if auto_render:
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
    def _render_seg(self, seg: str, color: tuple, x: int, y: int) -> int:
        """세그먼트를 1자씩 렌더링합니다.
        박스 문자는 _unit_w로 스케일, 일반 문자는 자연 크기로 blit 후
        x는 column 단위(_unit_w × 1 또는 2)로 이동해 정렬을 보장합니다."""
        for c in seg:
            if self._is_box_char(c):
                surf = self._get_box_surf(c, color)
                self.screen.blit(surf, (x, y))
                x += self._unit_w
            else:
                surf = self._get_char_surf(c, color)
                self.screen.blit(surf, (x, y))
                x += self._unit_w * (2 if self._is_wide_char(c) else 1)
        return x

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
                x = self._render_seg(seg, color, x, y)
            y += self._ch
            if y > h - self.PAD_Y:
                break
        pygame.display.flip()

    def _pump(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                self._on_resize(event.w, event.h)

    def _on_resize(self, new_w: int, new_h: int):
        """창 크기 변경 시 폰트를 재계산해 COLS×ROWS가 꽉 차도록 맞춥니다."""
        # 새 창 크기에서 1컬럼이 차지할 수 있는 최대 픽셀 너비/높이 역산
        col_px = (new_w - self.PAD_X * 2) / self.COLS
        row_px = (new_h - self.PAD_Y * 2) / self.ROWS
        # 폰트 크기 추정: unit_w ≈ font_size * 0.55 (경험치), ch ≈ font_size * 1.3
        size_from_w = max(8, int(col_px / 0.55))
        size_from_h = max(8, int(row_px / 1.30))
        new_size = min(size_from_w, size_from_h)
        if abs(new_size - self._font_size) < 1:
            return  # 변화 없으면 재로드 스킵
        self._font_size = new_size
        self._load_fonts(new_size)

    # ── 화면 제어 ─────────────────────────────────────────────────────────────
    def clear(self):
        self._buf        = [[]]
        self._fg         = _DEFAULT_COLOR
        self._bright     = False
        self._dim        = False
        self._box_cache  = {}
        self._char_cache = {}
        self._render()

    # ── 입력 ──────────────────────────────────────────────────────────────────

    # 물리 키코드 → ASCII 문자 매핑 (한국어 IME 활성 시 event.unicode 오염 대응)
    _KEYCODE_MAP: dict = {
        **{getattr(pygame, f'K_{i}'): str(i) for i in range(10)},
        **{getattr(pygame, f'K_{chr(c)}'): chr(c).upper()
           for c in range(ord('a'), ord('z') + 1)},
        pygame.K_RETURN:    '\r',
        pygame.K_KP_ENTER:  '\r',
        pygame.K_SPACE:     ' ',
    }

    @classmethod
    def _resolve_key(cls, event) -> str:
        """IME 간섭 없이 신뢰할 수 있는 키 문자를 반환합니다.
        event.unicode 가 출력 가능한 ASCII(0x20-0x7E)이면 그대로 사용하고,
        아니면 물리 키코드(_KEYCODE_MAP)로 폴백합니다."""
        u = event.unicode
        if u and len(u) == 1 and 0x20 <= ord(u) <= 0x7E:
            return u.upper()
        return cls._KEYCODE_MAP.get(event.key, '')

    def read_key(self) -> str:
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
            self._parse(prompt, auto_render=False)
        buf = ""
        cursor_visible = True
        cursor_timer = 0
        self._render()
        while True:
            dt = pygame.time.Clock().tick(30)
            cursor_timer += dt
            if cursor_timer >= 500:
                cursor_visible = not cursor_visible
                cursor_timer = 0
                # 현재 입력 줄 재렌더
                if self._buf[-1]:
                    # 커서 표시를 위해 임시 세그먼트 추가 후 렌더
                    pass
                self._render()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self._parse('\n', auto_render=True)
                        return buf
                    elif event.key == pygame.K_ESCAPE:
                        sys.exit()
                    elif event.key == pygame.K_BACKSPACE:
                        if buf:
                            buf = buf[:-1]
                            # 현재 줄 재구성
                            if self._buf[-1]:
                                self._buf[-1].pop()
                            self._render()
                    elif event.unicode and len(event.unicode) == 1 and 0x20 <= ord(event.unicode) <= 0x7E:
                        buf += event.unicode
                        self._parse(event.unicode, auto_render=True)

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
            self._parse(char, auto_render=True)
            if speed > 0:
                pygame.time.delay(delay_ms)
        self._parse('\n', auto_render=True)

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
