"""GM 이벤트 전용 화면. 이벤트 동안 터미널 로그 대신 그린다.

왼쪽: 코드로 그린 장면 그림(잔해 실루엣, 수은 안개, 먼지) + 의체 HUD.
오른쪽: 이야기 기록 (디스코 엘리시움식 텍스트 열). 상자 대신 글자 배치와 색으로 층을 나눈다.
PygameTerminal의 _ui_manager 훅을 빌려 쓴다: open()으로 걸고 close()로 터미널 화면에 돌려준다.
그리기만 담당하고, 규칙과 GM 호출은 gm_bridge가 한다.
"""
import math
import os
import random
import re
import sys
import threading

import pygame

import scene_art
import sound
import i18n

# 장소 ID. 장면 그림(SCENES, scene_art)을 찾는 키라서 바꾸지 않는다. 화면에는 place_label()로 번역해 그린다
JUNKYARD = "폐기물 처리장"
BUNKER = "구시대 지하 방공호"
_PLACE_KEYS = {JUNKYARD: "place_junkyard", BUNKER: "place_bunker"}


def place_label(location):
    key = _PLACE_KEYS.get(location)
    return i18n.t(key) if key else location

# ── 팔레트: 녹과 수은 ─────────────────────────────────────────────────────
BG        = (9, 9, 11)
INK       = (228, 221, 207)
INK_DIM   = (150, 143, 131)
INK_FAINT = (86, 83, 78)
AMBER     = (232, 162, 66)
TEAL      = (104, 198, 196)
GREEN     = (140, 210, 122)
RED       = (224, 88, 72)
VIOLET    = (192, 146, 232)

TOKEN_COLOR = {"hp_loss": RED, "gain": GREEN, "scrap": AMBER, "item": VIOLET, "weight": TEAL, "info": INK_DIM}

PLATE_W = 340
COL_PAD = 40
FOOT_H = 52

# 장면 그림 팔레트 (위치별)
SCENES = {
    JUNKYARD: {
        "sky": [(12, 15, 17), (34, 32, 30), (92, 58, 36), (150, 90, 44)],
        "layers": [(58, 46, 40), (40, 33, 30), (25, 21, 20), (13, 12, 12)],
        "sun": (236, 150, 70), "fog": (120, 132, 128), "dust": (230, 170, 100),
        "sub": "scene_sub_junkyard",  # 언어 키
    },
    BUNKER: {
        "sky": [(8, 8, 9), (18, 17, 16), (40, 30, 22), (96, 52, 24)],
        "layers": [(44, 40, 36), (30, 28, 26), (19, 18, 17), (10, 10, 10)],
        "sun": (240, 110, 40), "fog": (90, 86, 80), "dust": (220, 140, 80),
        "sub": "scene_sub_bunker",
    },
}


# 이벤트마다 장면 그림 앞쪽에 세우는 모티프 (없으면 기본 폐허만). 날씨·색은 MOTIF_TINT로 덮는다.
EVENT_MOTIF = {
    "AUTO_TURRET": "turret", "ACTIVE_CAMERA": "camera", "ACID_RAIN": "rain", "TOXIC_WASTE_POOL": "toxic",
    "CARGO_CONTAINER": "container", "FALLEN_WATCHTOWER": "tower", "ENCRYPTED_RADIO": "signal",
    "STRANGE_SIGNAL": "signal", "AI_BROADCAST": "broadcast", "ABANDONED_CAMP": "camp",
    "DRONE_WRECK_PILE": "drones", "HALF_DRONE": "drones", "DATA_TERMINAL": "machine",
    "VENDING_MACHINE": "machine", "RUSTED_GENERATOR": "machine", "EXPLOSIVE_TRAP": "mine",
    "WOUNDED_SCAVENGER": "figure", "SOLDIER_SKELETON": "figure", "ABANDONED_MEDKIT": "crate",
    "WALL_INSCRIPTION": "wall",
}
MOTIF_TINT = {  # 하늘·안개·먼지 색 바꾸기
    "rain": {"sky": [(14, 15, 10), (40, 40, 22), (96, 88, 34), (150, 132, 50)], "sun": (220, 200, 90),
             "fog": (150, 146, 90), "dust": (220, 210, 120)},
    "toxic": {"sky": [(9, 13, 11), (22, 32, 26), (40, 70, 44), (70, 118, 60)], "sun": (150, 230, 120),
              "fog": (110, 200, 120), "dust": (160, 240, 150)},
    "broadcast": {"sun": (230, 90, 70)},
}
GROUND_MOTIFS = {"turret", "drones", "figure", "camp", "mine", "crate", "machine", "container"}
TOXIC = (120, 236, 110)
ALERT = (255, 70, 56)
SIGNAL = (104, 198, 196)
TYPE_CPS = 42          # 타자 속도 (글자/초)
TYPE_TAIL = 5          # 막 나타나는 글자 수 (서서히 떠오른다)
# 기다리는 동안 띄우는 소리 말: 행동 낱말 -> 소리. 앞에서부터 맞는 것 하나 (없으면 기본)
SFX = [
    (("해킹", "접속", "단말기", "사이버덱", "코드", "침투", "덮어"), ["치직", "삑", "치지직"]),
    (("부수", "내리치", "뜯", "꺾", "때리", "후려", "터뜨", "박살"), ["쾅", "끼익", "쿵"]),
    (("문", "열어", "여는", "연다", "개방"), ["끼이익", "덜컹"]),
    (("숨", "기어", "엎드", "몸을 낮", "웅크"), ["스르륵", "사각"]),
    (("뒤지", "뒤진", "뒤져", "뒤적", "찾", "줍", "주워", "살펴", "살핀", "둘러", "훑", "해체", "분해"),
     ["부스럭", "달그락", "부스럭"]),
    (("불", "모닥불", "연료"), ["타닥", "타닥타닥"]),
    (("듣", "귀를", "기다", "숨죽", "지켜"), ["……", "웅……", "……"]),
    (("걷", "다가", "이동", "지나", "달려", "뛰"), ["저벅", "저벅", "저벅"]),
]
SFX_RAIN = ["후두둑", "투둑"]
SFX_DEFAULT = ["바스락", "……"]
SFX_EVERY = 0.7   # 초마다 한 낱말
SFX_MAX = 5

KB_ZOOM = 1.10        # 일러스트를 장면 칸보다 이만큼 크게 두고 천천히 움직인다 (켄 번스)
PARALLAX = (0.55, 0.8, 1.0)   # 깊이 층별 흐름 크기 (먼, 중간, 가까운). 여유 폭에 대한 비율
TILT = (0.12, 0.28, 0.45)     # 깊이 층별 마우스 기울기 크기
PAUSE_AFTER = {".": 0.30, "!": 0.30, "?": 0.30, "…": 0.40, ",": 0.10}  # 문장 끝에서 숨 고르기 (초)


_NUM = re.compile(r"\d+")
_OVERLAY_CACHE = {}   # (W, H) -> 필름 노이즈·비네팅 판
_ART_CACHE = {}       # (그림, 폭, 높이) -> [먼 층, [중간, 가까운], 빛 자리]


_FADE_CACHE = {}


def _plate_fades(w, H):
    """장면 칸 위에 덮는 어둡게 판 (오른쪽 녹임, 아래 지명 자리, 위 HUD 자리)."""
    if (w, H) not in _FADE_CACHE:
        s = pygame.Surface((w, H), pygame.SRCALPHA)
        fw = 150
        for x in range(fw):
            t = x / fw
            pygame.draw.line(s, (*BG, int(255 * t * t * (3 - 2 * t))), (w - fw + x, 0), (w - fw + x, H))
        low = pygame.Surface((w, 220), pygame.SRCALPHA)
        for y in range(220):
            pygame.draw.line(low, (*BG, int(235 * (y / 220) ** 1.4)), (0, y), (w, y))
        s.blit(low, (0, H - 220))
        high = pygame.Surface((w, 160), pygame.SRCALPHA)
        for y in range(160):
            pygame.draw.line(high, (*BG, int(170 * (1 - y / 160) ** 1.5)), (0, y), (w, y))
        s.blit(high, (0, 0))
        _FADE_CACHE[(w, H)] = s
    return _FADE_CACHE[(w, H)]


def _fog_and_edge(w, H, fog_col):
    key = ("fog", w, H, tuple(fog_col))
    if key not in _FADE_CACHE:
        fog = pygame.Surface((w, 60), pygame.SRCALPHA)
        for yy in range(60):
            pygame.draw.line(fog, (*fog_col, int(26 * math.sin(math.pi * yy / 60))), (0, yy), (w, yy))
        # 안개·먼지를 오른쪽으로 갈수록 지운다: 잘라 내면 밝은 띠 끝이 세로선으로 보였다 (일러스트에서 실측)
        edge = pygame.Surface((w, H), pygame.SRCALPHA)
        for x in range(w):
            k = max(0.0, min(1.0, (x - (w - 170)) / 120))
            pygame.draw.line(edge, (255, 255, 255, int(255 * (1 - k))), (x, 0), (x, H))
        _FADE_CACHE[key] = (fog, edge)
    return _FADE_CACHE[key]


class CachedFont:
    """한 번 그린 글자를 기억해 두는 글꼴. 화면마다 매 프레임 같은 글을 다시 그리던 비용이 프레임 시간의 절반이었다.
    돌려주는 그림은 공유본이라 set_alpha 등으로 바꾸려면 .copy()로 쓴다. 글꼴 객체도 경로·크기별로 한 번만 연다."""
    _fonts = {}

    def __init__(self, path, size):
        key = (path, size)
        if key not in CachedFont._fonts:
            CachedFont._fonts[key] = pygame.font.Font(path, size)
        self._f = CachedFont._fonts[key]
        self._cache = _TEXT_CACHE.setdefault(key, {})

    def render(self, text, aa=True, color=(255, 255, 255)):
        k = (text, aa, tuple(color))
        g = self._cache.get(k)
        if g is None:
            if len(self._cache) > 3000:
                self._cache.clear()
            g = self._cache[k] = self._f.render(text, aa, color)
        return g

    def size(self, text):
        return self._f.size(text)

    def get_linesize(self):
        return self._f.get_linesize()

    def get_height(self):
        return self._f.get_height()


_TEXT_CACHE = {}


def _font_path(names):
    for n in names:
        for base in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets"),
                     os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")):
            p = os.path.join(base, n)
            if os.path.exists(p):
                return p
    return None


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class EventView:
    """화면 상태를 들고 render(canvas)로 그린다. gm_bridge가 기록을 쌓고 refresh()를 부른다."""

    def __init__(self, term, player, grid, location, event_id=None, context="", search=False, scene=None):
        self._term = term
        self._active = False
        self._prev = None
        self.player, self.grid, self.location = player, grid, location
        self.motif = scene or EVENT_MOTIF.get(event_id)  # scene: 그림 장면을 직접 지정 (전투·스토리 카드)
        self.context, self.search = context, search  # 그림 고르기에 쓰는 이벤트 문장과 빈 탐색 여부
        self._hud = {}             # HUD 수치의 화면 표시값 (실제 값을 향해 움직인다)
        self._loss = {}            # 줄어든 구간을 붉게 남겨 두는 값과 시각
        self._shake = (0, 0.0)     # (끝나는 시각 ms, 세기)
        self._hurt_until = 0
        self._menu = None          # 선택지 항목 (방향키·마우스 선택 중)
        self._rows = []            # 이번 프레임의 선택지 줄 영역 [(key, Rect)]
        self.hud_hold = False
        self._hurt = None
        self.card = False          # True면 장면 카드 (그림 전체 화면 + 제목)
        self._card_art = None
        self._card_shade = None
        self._card_t0 = 0.0
        self._sfx = []             # 기다리는 동안 띄우는 소리 말
        self._think_t0 = 0
        self._art = None           # 일러스트 (없으면 코드로 그린 장면)
        self._lights = []          # 일러스트에서 찾은 빛 자리 [(종류, x, y)]
        self._kb = (0, 0)          # 켄 번스 이동량 (먼 층)
        self._layers = []          # 깊이 층 [중간, 가까운] (없으면 None)
        self._offsets = []         # 이번 프레임 층별 이동량
        self.art_path = None
        self.log = []              # 이야기 기록 항목 (dict)
        self.footer = []           # [(키, 설명)]
        self.input_buf = None      # 입력 중이면 문자열
        self.thinking = False
        self.compose = ""        # 한글 조합 중인 글자
        self._input_pos = (0, 0)

        mono = term._find_bundled_font()
        serif = _font_path(["NanumMyeongjo.ttf", "HANBatang.ttf"]) or mono
        serif_b = _font_path(["NanumMyeongjoBold.ttf", "NanumMyeongjo.ttf"]) or serif
        sans = _font_path(["NanumBarunGothic.ttf", "malgun.ttf"]) or mono
        title = _font_path(["NanumSquareEB.ttf", "NanumSquareB.ttf", "malgunbd.ttf"]) or sans
        self.f_title = CachedFont(title, 30)
        self.f_place = CachedFont(title, 28)
        self.f_serif = CachedFont(serif, 19)
        self.f_serif_b = CachedFont(serif_b, 19)
        self.f_sans = CachedFont(sans, 17)
        self.f_mono = CachedFont(mono, 14)
        self.f_mono_b = CachedFont(mono, 16)
        self._plate = None
        self._overlay = None
        self._col_x = PLATE_W + COL_PAD

    # ── 터미널 훅 ───────────────────────────────────────────────────────────
    def open(self):
        self._prev = self._term._ui_manager
        self._active = True
        self._term._ui_manager = self
        self.refresh()

    def close(self):
        self._active = False
        self._term._ui_manager = self._prev
        self._term._dirty = True

    def refresh(self):
        self._term._dirty = True
        self._term._render()

    # ── 기록 쌓기 (gm_bridge가 부른다) ─────────────────────────────────────
    def add(self, kind, **kw):
        kw["kind"] = kind
        self.log.append(kw)
        return kw

    # ── 장면 그림 (한 번 그려 캐시) ────────────────────────────────────────
    def _build_plate(self, H):
        sc = dict(SCENES.get(self.location, SCENES[JUNKYARD]))
        sc.update(MOTIF_TINT.get(self.motif, {}))
        rng = random.Random(sum(map(ord, self.location)))
        w = PLATE_W
        s = pygame.Surface((w, H))
        horizon = int(H * 0.56)
        self._horizon = horizon
        self._art = self._load_art(H)
        if self._art is not None:  # 그려 둔 일러스트: 매 프레임 천천히 움직여 그리고 위에 가림막(아래 페이드)만 덮는다
            if getattr(self, "_cached_lights", None) is not None:
                self._lights = self._cached_lights
            else:
                self._lights = [(k, x, y, self._light_depth(x, y)) for k, x, y in self._find_lights(self._art)]
                key = getattr(self, "_art_key", None)
                if key in _ART_CACHE:
                    _ART_CACHE[key][2] = self._lights
            s = _plate_fades(w, H)  # 일러스트 위에는 어둡게 판만 덮는다 (공유 판, 새로 만들지 않는다)
        else:
            self._paint_scene(s, H, sc, horizon, rng)
            s.blit(_plate_fades(w, H), (0, 0))  # 오른쪽 녹임·아래(지명)·위(HUD) 어둡게: 크기별로 한 번만 만든다
        self._plate = s
        self._sc = sc
        self._horizon = horizon
        # 안개 띠 한 장 (매 프레임 위치만 옮긴다) + 오른쪽으로 갈수록 효과를 지우는 판 (색·크기별로 한 번만)
        self._fog, self._fx_edge = _fog_and_edge(w, H, sc["fog"])

    def _paint_scene(self, s, H, sc, horizon, rng):
        """일러스트 파일이 없을 때 코드로 그리는 장면 (하늘, 태양, 연기, 크레인, 잔해 네 겹, 모티프).
        일러스트를 새로 뽑을 때 구도 밑그림으로도 쓴다 (art_gen/gen_scenes.py)."""
        w = PLATE_W
        stops = sc["sky"]
        for y in range(H):
            t = min(1.0, y / horizon)
            seg = min(len(stops) - 2, int(t * (len(stops) - 1)))
            lt = t * (len(stops) - 1) - seg
            pygame.draw.line(s, _lerp(stops[seg], stops[seg + 1], lt), (0, y), (w, y))
        # 흐린 태양: 넓은 번짐 + 작은 핵
        glow = pygame.Surface((w, H), pygame.SRCALPHA)
        cx, cy = int(w * 0.62), horizon - 96
        for r in range(220, 0, -5):
            a = int(38 * (1 - r / 220) ** 2.2)
            pygame.draw.circle(glow, (*sc["sun"], a), (cx, cy), r)
        pygame.draw.circle(glow, (*_lerp(sc["sun"], (255, 236, 200), 0.6), 120), (cx, cy), 26)
        pygame.draw.circle(glow, (*_lerp(sc["sun"], (255, 246, 226), 0.8), 210), (cx, cy), 17)
        s.blit(glow, (0, 0))
        # 멀리 피어오르는 연기 기둥
        smoke = pygame.Surface((w, H), pygame.SRCALPHA)
        for _ in range(3):
            sx = rng.randint(20, w - 60)
            for i in range(26):
                yy = horizon - 30 - i * 16
                rr = 10 + i * 2.2
                drift = int(math.sin(i * 0.35) * 10 + i * 2.5)
                pygame.draw.circle(smoke, (18, 16, 16, max(0, 30 - i)), (sx + drift, yy), int(rr))
        s.blit(smoke, (0, 0))
        # 가장 먼 곳의 무너진 크레인 (하늘을 채우는 큰 실루엣)
        far = _lerp(sc["layers"][0], sc["sky"][2], 0.35)
        mx = int(w * 0.24)
        top = horizon - int(H * 0.33)
        pygame.draw.line(s, far, (mx, horizon), (mx + 6, top), 5)
        for i in range(0, horizon - top, 22):  # 격자 버팀대
            pygame.draw.line(s, far, (mx - 6, horizon - i), (mx + 10, horizon - i - 22), 1)
        boom_end = (mx + 170, top + 70)
        pygame.draw.line(s, far, (mx + 4, top + 6), boom_end, 4)
        pygame.draw.line(s, far, (mx - 40, top + 20), (mx + 4, top + 6), 3)
        pygame.draw.line(s, far, boom_end, (boom_end[0] + 2, boom_end[1] + 90), 1)  # 끊어진 케이블
        pygame.draw.rect(s, far, (boom_end[0] - 6, boom_end[1] + 88, 14, 10))
        # 잔해 실루엣 네 겹 (먼 곳 → 가까운 곳)
        for li, color in enumerate(sc["layers"]):
            base = horizon + li * int(H * 0.09) - 20
            amp = 40 + li * 38
            pts = [(0, H)]
            x = -10
            while x < w + 20:
                h = base - rng.randint(0, amp)
                step = rng.randint(10, 34)
                pts += [(x, h + rng.randint(-6, 6)), (x + step // 2, h - rng.randint(0, 14))]
                x += step
            pts += [(w, H)]
            pygame.draw.polygon(s, color, pts)
            for _ in range(2 + li):  # 드론 사체, 안테나, 기운 판
                px = rng.randint(0, w)
                py = base - rng.randint(amp // 2, amp)
                kind = rng.random()
                if kind < 0.35:
                    pygame.draw.ellipse(s, color, (px - 22, py - 9, 44, 18))
                    pygame.draw.line(s, color, (px - 34, py - 12), (px + 34, py - 4), 3)
                elif kind < 0.65:
                    pygame.draw.line(s, color, (px, py + 30), (px + rng.randint(-8, 8), py - 50), 2)
                    pygame.draw.line(s, color, (px - 8, py - 30), (px + 8, py - 34), 2)
                else:
                    ang = rng.uniform(-0.6, 0.6)
                    ln, th = rng.randint(30, 60), 8
                    co, sn = math.cos(ang), math.sin(ang)
                    poly = [(px + dx * co - dy * sn, py + dx * sn + dy * co)
                            for dx, dy in ((-ln, -th), (ln, -th), (ln, th), (-ln, th))]
                    pygame.draw.polygon(s, color, poly)
        self._horizon = horizon
        self._motif_static(s, H, sc)

    def _load_art(self, H):
        """상황에 맞는 그림(scene_art.choose)과 깊이 층을 장면 칸보다 KB_ZOOM배 크게 불러온다.
        돌려주는 값: 먼 층(원본) Surface. 중간·가까운 층은 self._layers에. 그림이 없으면 None."""
        if getattr(self, "no_art", False):
            return None
        path = scene_art.choose(self.location, self.motif, self.context,
                                getattr(self.player, "turn_count", 0), self.search, getattr(self, "stable_key", None))
        if not path:
            return None
        bw, bh = int(PLATE_W * KB_ZOOM), int(H * KB_ZOOM)
        cached = _ART_CACHE.get((path, bw, bh))
        if cached:  # 같은 그림을 다시 쓰면 불러오기·축소·빛 찾기를 건너뛴다 (칸 이동·화면 전환이 끊기지 않게)
            far, self._layers, self._cached_lights = cached
            self.art_path = path
            return far

        def fit(p, alpha):
            img = pygame.image.load(p)
            if pygame.display.get_surface():
                img = img.convert_alpha() if alpha else img.convert()
            scale = max(bw / img.get_width(), bh / img.get_height())
            img = pygame.transform.smoothscale(img, (int(img.get_width() * scale + 0.5), int(img.get_height() * scale + 0.5)))
            out = pygame.Surface((bw, bh), pygame.SRCALPHA if alpha else 0)
            out.blit(img, ((bw - img.get_width()) // 2, (bh - img.get_height()) // 2))
            return out
        far = fit(path, False)
        self._layers = [fit(p, True) if p else None for p in scene_art.layers(path)]
        self.art_path = path
        self._cached_lights = None
        if len(_ART_CACHE) > 16:
            _ART_CACHE.pop(next(iter(_ART_CACHE)))
        _ART_CACHE[(path, bw, bh)] = [far, self._layers, None]
        self._art_key = (path, bw, bh)
        return far

    @staticmethod
    def _find_lights(img):
        """그림 속 빛 자리를 색으로 찾는다: 불(주황), 경고(빨강), 독성(초록), 신호(청록). 그 자리에 움직이는 효과를 얹는다.
        그림마다 좌표를 적지 않아도 되게. 작게 줄여서 픽셀을 훑는다 (numpy 없이)."""
        small = pygame.transform.smoothscale(img, (img.get_width() // 8, img.get_height() // 8))
        found = {"fire": [], "alert": [], "toxic": [], "signal": []}
        for y in range(small.get_height()):
            for x in range(small.get_width()):
                r, g, b = small.get_at((x, y))[:3]
                h, sat, val, _ = pygame.Color(r, g, b).hsva
                if val < 55 or sat < 45:
                    continue
                if (h < 12 or h > 345) and sat > 60:
                    kind = "alert"
                elif h < 45 and val > 70:
                    kind = "fire"
                elif 80 <= h <= 150:
                    kind = "toxic"
                elif 160 <= h <= 200:
                    kind = "signal"
                else:
                    continue
                found[kind].append((val * sat, x * 8 + 4, y * 8 + 4))
        lights = []
        for kind, pts in found.items():
            picked = []
            for _, x, y in sorted(pts, reverse=True):  # 가장 밝은 곳부터, 서로 떨어진 곳만 최대 3개
                if all(math.hypot(x - px, y - py) > 60 for px, py in picked):
                    picked.append((x, y))
                if len(picked) == 3:
                    break
            lights += [(kind, x, y) for x, y in picked]
        return lights

    def _light_depth(self, x, y):
        """빛이 어느 깊이 층에 있는지 (0 먼, 1 중간, 2 가까운). 그 층과 같이 움직인다."""
        for i in (1, 0):
            layer = self._layers[i] if i < len(self._layers) else None
            if layer is not None and 0 <= x < layer.get_width() and 0 <= y < layer.get_height() \
                    and layer.get_at((int(x), int(y))).a > 128:
                return i + 1
        return 0

    # ── 이벤트 모티프 ───────────────────────────────────────────────────────
    def _motif_anchor(self, H):
        """모티프를 세우는 땅 높이. 지명 글자(아래 220px 어둠) 위에 온다."""
        return self._horizon + int(H * 0.09)

    def _motif_static(self, s, H, sc):
        """움직이지 않는 모티프 실루엣. 가까운 잔해 색으로 그리고 가장자리만 빛을 받는다."""
        m = self.motif
        if not m:
            return
        near, mid = sc["layers"][3], sc["layers"][2]
        rim = _lerp(mid, sc["sun"], 0.55)
        gy = self._motif_anchor(H)
        if m in GROUND_MOTIFS:  # 땅 위 물체는 뒤에 옅은 역광을 깔아 잔해 더미와 떼어 놓는다
            back = pygame.Surface((PLATE_W, 320), pygame.SRCALPHA)
            for r in range(150, 0, -6):
                pygame.draw.ellipse(back, (*sc["sun"], int(34 * (1 - r / 150) ** 1.6)), (160 - r * 1.3, 190 - r * 0.8, r * 2.6, r * 1.6))
            s.blit(back, (0, gy - 220))
        if m == "turret":
            pygame.draw.polygon(s, near, [(78, gy + 44), (222, gy + 44), (196, gy - 26), (104, gy - 26)])
            pygame.draw.rect(s, near, (130, gy - 60, 40, 36), border_radius=4)
            pygame.draw.line(s, rim, (104, gy - 26), (196, gy - 26), 2)
            pygame.draw.line(s, rim, (130, gy - 60), (170, gy - 60), 2)
        elif m == "camera":
            pygame.draw.line(s, near, (90, gy + 40), (94, gy - 190), 6)
            pygame.draw.line(s, near, (94, gy - 180), (132, gy - 196), 4)
            pygame.draw.rect(s, near, (126, gy - 212, 44, 22), border_radius=3)
            pygame.draw.line(s, rim, (126, gy - 212), (170, gy - 212), 1)
        elif m == "toxic":
            pool = pygame.Surface((300, 80), pygame.SRCALPHA)
            for i in range(40, 0, -2):
                pygame.draw.ellipse(pool, (*TOXIC, int(70 * (1 - i / 40) ** 1.5)), (150 - i * 3.6, 40 - i, i * 7.2, i * 2))
            pygame.draw.ellipse(pool, (40, 90, 40, 220), (30, 26, 240, 30))
            pygame.draw.ellipse(pool, (*TOXIC, 90), (30, 26, 240, 30), 2)
            s.blit(pool, (10, gy - 10))
        elif m == "container":
            body = pygame.Surface((190, 96), pygame.SRCALPHA)
            body.fill((*mid, 255))
            for x in range(8, 190, 14):  # 골판 무늬
                pygame.draw.line(body, (*near, 255), (x, 4), (x, 92), 3)
            pygame.draw.rect(body, (*near, 255), (0, 0, 190, 96), 4)
            pygame.draw.rect(body, (*AMBER, 200), (150, 40, 14, 10))  # 봉인 씰
            body = pygame.transform.rotate(body, 11)
            s.blit(body, (60, gy - 92))
        elif m == "tower":
            top = (190, gy - 300)
            for side in (-1, 1):
                pygame.draw.line(s, mid, (150 + side * 34, gy + 20), (top[0] + side * 10, top[1]), 4)
            for i in range(0, 300, 24):
                y = gy + 20 - i
                t = i / 300
                xl = 150 - 34 + (top[0] - 10 - 116) * t
                xr = 150 + 34 + (top[0] + 10 - 184) * t
                pygame.draw.line(s, mid, (xl, y), (xr, y - 24), 1)
                pygame.draw.line(s, mid, (xr, y), (xl, y - 24), 1)
            pygame.draw.polygon(s, mid, [(top[0] - 26, top[1]), (top[0] + 30, top[1] + 8), (top[0] + 20, top[1] - 22),
                                         (top[0] - 18, top[1] - 16)])
        elif m in ("signal", "broadcast"):
            pygame.draw.line(s, near, (170, gy + 40), (172, gy - 230), 5)
            for i in range(0, 260, 30):
                pygame.draw.line(s, near, (162, gy + 30 - i), (182, gy + 16 - i), 1)
            if m == "signal":
                pygame.draw.arc(s, near, (120, gy - 268, 70, 40), 3.3, 6.1, 5)  # 접시
            else:
                pygame.draw.polygon(s, near, [(172, gy - 214), (214, gy - 236), (214, gy - 190), (172, gy - 204)])  # 확성기
        elif m == "camp":
            pygame.draw.polygon(s, near, [(24, gy + 34), (118, gy - 104), (214, gy + 34)])
            pygame.draw.line(s, _lerp(mid, (240, 130, 50), 0.7), (118, gy - 104), (214, gy + 34), 2)  # 모닥불 쪽 모서리
            pygame.draw.line(s, near, (118, gy - 104), (116, gy - 130), 3)
            pygame.draw.polygon(s, _lerp(near, (240, 130, 50), 0.12), [(100, gy + 34), (118, gy - 30), (136, gy + 34)])  # 입구
        elif m == "drones":
            for cx, cy, sc_ in ((118, gy - 14, 1.8), (238, gy + 22, 1.3)):
                pygame.draw.ellipse(s, near, (cx - 34 * sc_, cy - 14 * sc_, 68 * sc_, 28 * sc_))
                pygame.draw.line(s, near, (cx - 60 * sc_, cy - 26 * sc_), (cx + 10, cy - 6), 4)
                pygame.draw.line(s, near, (cx + 58 * sc_, cy - 4 * sc_), (cx + 90 * sc_, cy - 40 * sc_), 3)
                pygame.draw.arc(s, rim, (cx - 34 * sc_, cy - 14 * sc_, 68 * sc_, 28 * sc_), 0.3, 2.8, 2)
                pygame.draw.circle(s, rim, (int(cx + 12 * sc_), int(cy - 2)), int(5 * sc_), 1)
        elif m == "machine":
            pygame.draw.rect(s, near, (96, gy - 150, 96, 180), border_radius=4)
            pygame.draw.rect(s, (18, 22, 24), (110, gy - 134, 68, 46))  # 화면 자리
            pygame.draw.line(s, rim, (96, gy - 150), (192, gy - 150), 1)
            for i in range(4):
                pygame.draw.rect(s, mid, (110 + i * 18, gy - 70, 12, 8))
        elif m == "mine":
            pygame.draw.ellipse(s, near, (116, gy + 2, 110, 34))
            pygame.draw.ellipse(s, rim, (116, gy + 2, 110, 34), 2)
            pygame.draw.ellipse(s, mid, (146, gy + 8, 50, 16))
        elif m == "figure":
            pygame.draw.polygon(s, mid, [(150, gy + 40), (262, gy + 40), (248, gy - 70), (178, gy - 24)])  # 기댄 잔해
            pygame.draw.polygon(s, near, [(106, gy + 42), (186, gy + 42), (176, gy - 46), (128, gy - 42)])  # 몸
            pygame.draw.circle(s, near, (150, gy - 66), 21)
            pygame.draw.line(s, near, (124, gy - 24), (72, gy + 34), 10)  # 늘어진 팔
            pygame.draw.line(s, near, (170, gy + 30), (236, gy + 44), 12)  # 뻗은 다리
            pygame.draw.arc(s, rim, (129, gy - 87, 42, 42), 0.2, 2.2, 2)
            pygame.draw.line(s, rim, (176, gy - 46), (186, gy + 30), 2)
        elif m == "crate":
            box = pygame.Surface((92, 60), pygame.SRCALPHA)
            box.fill((*mid, 255))
            pygame.draw.rect(box, (*near, 255), (0, 0, 92, 60), 4)
            pygame.draw.rect(box, (150, 60, 50, 200), (38, 14, 16, 32))
            pygame.draw.rect(box, (150, 60, 50, 200), (30, 22, 32, 16))
            s.blit(pygame.transform.rotate(box, -8), (110, gy - 40))
        elif m == "wall":
            pygame.draw.polygon(s, mid, [(40, gy + 30), (250, gy + 30), (240, gy - 170), (60, gy - 150)])
            r = random.Random(11)
            for _ in range(30):  # 긁어 새긴 이름들
                x, y = r.randint(70, 220), r.randint(gy - 140, gy + 10)
                pygame.draw.line(s, _lerp(mid, INK, 0.25), (x, y), (x + r.randint(8, 26), y + r.randint(-2, 2)), 1)

    def _mouse_tilt(self):
        """마우스가 장면 칸 어디에 있는지 (-1..1). 창 밖이거나 알 수 없으면 가운데."""
        try:
            sw, sh = self._term.screen.get_size()
            cw, ch = self._term._canvas.get_size()
            scale = min(sw / cw, sh / ch)
            mx, my = pygame.mouse.get_pos()
            cx = (mx - (sw - cw * scale) / 2) / scale
            cy = (my - (sh - ch * scale) / 2) / scale
        except (AttributeError, pygame.error):
            return (0.0, 0.0)
        tx = max(-1.0, min(1.0, (cx - cw / 2) / (cw / 2)))
        ty = max(-1.0, min(1.0, (cy - ch / 2) / (ch / 2)))
        # 부드럽게 따라온다
        px, py = getattr(self, "_tilt", (0.0, 0.0))
        self._tilt = (px + (tx - px) * 0.08, py + (ty - py) * 0.08)
        return self._tilt

    def _lights_anim(self, c, H, t):
        """일러스트 위 효과: 찾아 둔 빛 자리마다 깜박임과 입자. 빛이 있는 깊이 층과 같이 움직인다."""
        fx = pygame.Surface((PLATE_W, H), pygame.SRCALPHA)
        for i, (kind, x, y, depth) in enumerate(self._lights):
            ox, oy = self._offsets[depth] if depth < len(self._offsets) else self._kb
            x, y = x - ox, y - oy
            ph = t + i * 1.7
            if kind == "fire":
                fl = 0.55 + 0.45 * math.sin(ph * 9) * math.sin(ph * 5.3)
                for rr in range(46, 0, -4):
                    pygame.draw.circle(fx, (255, 150, 60, int(24 * fl * (1 - rr / 46))), (x, y), rr)
                r = random.Random(i)
                for _ in range(6):  # 불씨
                    off, sp = r.random() * 3, 20 + r.random() * 30
                    q = (t + off) % 3 / 3
                    pygame.draw.circle(fx, (255, 170, 70, int(200 * (1 - q))),
                                       (int(x + math.sin(t * 2 + off * 5) * 8 * q), int(y - q * sp * 3)), 1)
            elif kind == "alert":
                if (ph % 1.3) < 0.4:
                    pygame.draw.circle(fx, (*ALERT, 90), (x, y), 12)
                    pygame.draw.circle(fx, (*ALERT, 220), (x, y), 3)
            elif kind == "toxic":
                g = 0.5 + 0.5 * math.sin(ph * 1.6)
                pygame.draw.circle(fx, (*TOXIC, int(30 * g)), (x, y), 34)
                q = (ph % 2.0) / 2.0
                pygame.draw.circle(fx, (*TOXIC, int(170 * (1 - q))), (x + int(math.sin(ph) * 14), int(y - q * 24)), 2, 1)
            elif kind == "signal":
                q = (ph * 0.6) % 1.0
                pygame.draw.circle(fx, (*SIGNAL, int(130 * (1 - q))), (x, y), int(6 + q * 70), 1)
        c.blit(fx, (0, 0))

    @staticmethod
    def _rain(c, H, t):
        fx = pygame.Surface((PLATE_W, H), pygame.SRCALPHA)
        r = random.Random(5)
        for _ in range(140):
            x0, sp = r.random() * (PLATE_W + 120), 380 + r.random() * 260
            y = (r.random() * H + t * sp) % H
            x = (x0 - (t * sp) * 0.25) % (PLATE_W + 120) - 60
            pygame.draw.line(fx, (220, 210, 110, 70), (x, y), (x - 4, y + 16), 1)
        c.blit(fx, (0, 0))

    def _motif_anim(self, c, H, t):
        """움직이는 모티프 요소. 장면이 멈춰 있지 않게."""
        if self._art is not None:
            self._lights_anim(c, H, t)
            if self.motif == "rain":  # 빗줄기는 그림 위치와 상관없다
                self._rain(c, H, t)
            return
        m = self.motif
        gy = self._motif_anchor(H) if m else 0
        fx = pygame.Surface((PLATE_W, H), pygame.SRCALPHA)
        if m == "turret":
            ang = math.sin(t * 0.9) * 0.9 + math.sin(t * 2.7) * 0.25 + 3.3  # 불규칙하게 돈다
            cx, cy = 150, gy - 44
            tip = (cx + math.cos(ang) * 52, cy + math.sin(ang) * 52)
            pygame.draw.line(c, (13, 12, 12), (cx, cy), tip, 10)
            end = (cx + math.cos(ang) * 420, cy + math.sin(ang) * 420)
            pygame.draw.line(fx, (*ALERT, 70), tip, end, 3)
            pygame.draw.line(fx, (*ALERT, 170), tip, end, 1)
            if int(t * 3) % 5 == 0:
                pygame.draw.circle(fx, (*ALERT, 200), (int(tip[0]), int(tip[1])), 4)
        elif m == "camera":
            sweep = math.sin(t * 0.5) * 0.5
            o = (130, gy - 196)
            a1, a2 = 2.0 + sweep, 2.5 + sweep
            cone = [o, (o[0] + math.cos(a1) * 260, o[1] + math.sin(a1) * 260), (o[0] + math.cos(a2) * 260, o[1] + math.sin(a2) * 260)]
            pygame.draw.polygon(fx, (*ALERT, 22), cone)
            if (t % 1.0) < 0.5:
                pygame.draw.circle(fx, (*ALERT, 230), (164, gy - 206), 3)
                pygame.draw.circle(fx, (*ALERT, 60), (164, gy - 206), 9)
        elif m == "rain":
            self._rain(c, H, t)
        elif m == "toxic":
            glow = 0.5 + 0.5 * math.sin(t * 1.6)
            pygame.draw.ellipse(fx, (*TOXIC, int(30 + 30 * glow)), (30, gy + 10, 260, 40))
            r = random.Random(9)
            for _ in range(10):
                bx, period = 50 + r.random() * 220, 1.5 + r.random() * 2.5
                ph = ((t + r.random() * period) % period) / period
                y = gy + 30 - ph * 26
                pygame.draw.circle(fx, (*TOXIC, int(180 * (1 - ph))), (int(bx), int(y)), 2 + int(ph * 3), 1)
        elif m == "container":
            if (t % 2.2) < 0.18:
                pygame.draw.circle(fx, (*AMBER, 120), (218, gy - 42), 10)
        elif m == "tower":
            if (t % 1.6) < 0.25:
                pygame.draw.circle(fx, (*ALERT, 220), (190, gy - 322), 3)
                pygame.draw.circle(fx, (*ALERT, 50), (190, gy - 322), 12)
        elif m in ("signal", "broadcast"):
            col = SIGNAL if m == "signal" else ALERT
            src = (160, gy - 252) if m == "signal" else (216, gy - 213)
            for k in range(3):
                ph = ((t * 0.6 + k / 3) % 1.0)
                rr = int(10 + ph * 120)
                pygame.draw.circle(fx, (*col, int(150 * (1 - ph))), src, rr, 1)
        elif m == "camp":
            fl = 0.6 + 0.4 * math.sin(t * 9) * math.sin(t * 5.3)
            cx, cy = 256, gy + 26
            for rr in range(110, 0, -5):
                pygame.draw.circle(fx, (240, 130, 50, int(34 * fl * (1 - rr / 110) ** 1.2)), (cx, cy), rr)
            pygame.draw.polygon(fx, (255, 170, 70, int(230 * fl)), [(cx - 9, cy + 4), (cx, cy - 16 - 6 * fl), (cx + 9, cy + 4)])
            pygame.draw.circle(fx, (255, 220, 140, int(230 * fl)), (cx, cy), 4)
            r = random.Random(4)
            for _ in range(12):  # 불씨
                off, sp = r.random() * 3, 20 + r.random() * 30
                ph = (t + off) % 3 / 3
                pygame.draw.circle(fx, (255, 170, 70, int(220 * (1 - ph))),
                                   (int(cx + math.sin(t * 2 + off * 5) * 10 * ph), int(cy - ph * sp * 3)), 1)
        elif m == "drones":
            if (t % 3.1) < 0.12 or (t % 3.1 - 0.25) % 3.1 < 0.06:
                for _ in range(5):
                    a = random.random() * math.tau
                    pygame.draw.line(fx, (190, 220, 255, 230), (140, gy - 16), (140 + math.cos(a) * 16, gy - 16 + math.sin(a) * 16), 1)
                pygame.draw.circle(fx, (190, 220, 255, 90), (140, gy - 16), 14)
        elif m == "machine":
            fl = 0.55 + 0.45 * (math.sin(t * 13) > -0.7) * (0.8 + 0.2 * math.sin(t * 3))
            pygame.draw.rect(fx, (*SIGNAL, int(70 * fl)), (110, gy - 134, 68, 46))
            ly = gy - 134 + int((t * 30) % 46)
            pygame.draw.line(fx, (*SIGNAL, 110), (110, ly), (177, ly), 1)
        elif m == "mine":
            ph = (t % 1.2) / 1.2
            if ph < 0.3:
                pygame.draw.circle(fx, (*ALERT, 250), (171, gy + 14), 3)
                pygame.draw.circle(fx, (*ALERT, 70), (171, gy + 14), 12)
            pygame.draw.ellipse(fx, (*ALERT, int(110 * (1 - ph))), (171 - ph * 110, gy + 18 - ph * 26, ph * 220, ph * 52), 1)
        # 공통: 지평선 너머 먼 방전 섬광 (몇 초에 한 번)
        cyc = t % 8.5
        if cyc < 0.35:
            a = int(60 * (1 - cyc / 0.35))
            pygame.draw.ellipse(fx, (*self._sc["sun"], a), (40, self._horizon - 60, 220, 70))
        c.blit(fx, (0, 0))

    def _build_overlay(self, W, H):
        """비네팅 + 필름 노이즈 + 주사선. 크기별로 한 번만 만들어 모든 화면이 같이 쓴다 (화면 전환 때 36ms 절약)."""
        if (W, H) in _OVERLAY_CACHE:
            self._overlay = _OVERLAY_CACHE[(W, H)]
            return
        o = pygame.Surface((W, H), pygame.SRCALPHA)
        cx, cy = W / 2, H / 2
        maxd = math.hypot(cx, cy)
        step = 8
        for y in range(0, H, step):
            for x in range(0, W, step):
                d = math.hypot(x - cx, y - cy) / maxd
                a = int(170 * max(0, d - 0.55) ** 1.5)
                if a:
                    o.fill((0, 0, 0, a), (x, y, step, step))
        rng = random.Random(7)
        for _ in range(W * H // 40):
            v = rng.randint(0, 255)
            o.set_at((rng.randrange(W), rng.randrange(H)), (v, v, v, 10))
        for y in range(0, H, 3):
            pygame.draw.line(o, (0, 0, 0, 22), (0, y), (W, y))
        self._overlay = o
        _OVERLAY_CACHE[(W, H)] = o

    def _draw_plate(self, c, H):
        if self._plate is None:
            self._build_plate(H)
        sc, t = self._sc, pygame.time.get_ticks() / 1000
        if self._art is not None:  # 켄 번스 + 깊이 패럴랙스: 가까운 층일수록 더 움직인다
            mx, my = self._art.get_width() - PLATE_W, self._art.get_height() - H
            drift = (math.sin(t * 0.045), math.sin(t * 0.031 + 1.3))  # -1..1
            tilt = self._mouse_tilt()
            self._offsets = []
            pan = getattr(self, "_pan", 0.0)  # 칸 이동 연출: 시선이 옆으로 흘러간다 (-1..1, map_view.py)
            for depth, layer in enumerate([self._art] + self._layers):
                k = PARALLAX[depth]
                ox = mx / 2 + (drift[0] * 0.5 * k + tilt[0] * TILT[depth] + pan * k) * mx
                oy = my / 2 + (drift[1] * 0.5 * k + tilt[1] * TILT[depth]) * my
                off = (int(max(0, min(mx, ox))), int(max(0, min(my, oy))))
                self._offsets.append(off)
                if layer is not None:
                    c.blit(layer, (0, 0), pygame.Rect(off[0], off[1], PLATE_W, H))
            self._kb = self._offsets[0]
        c.blit(self._plate, (0, 0))
        prev_clip = c.get_clip()
        c.set_clip(pygame.Rect(0, 0, PLATE_W, H))
        fx_layer = pygame.Surface((PLATE_W, H), pygame.SRCALPHA)  # 안개·먼지·효과를 모아 오른쪽을 지운 뒤 얹는다
        real_c, c = c, fx_layer
        # 흐르는 수은 안개
        for band in range(3):
            y0 = self._horizon - 30 + band * 46
            off = (t * (8 + band * 5)) % PLATE_W
            c.blit(self._fog, (int(off), y0))
            c.blit(self._fog, (int(off) - PLATE_W, y0))
        # 떠다니는 먼지
        rng = random.Random(3)
        for _ in range(46):
            bx, by, sp = rng.random() * PLATE_W, rng.random() * H, 4 + rng.random() * 10
            x = (bx + t * sp) % PLATE_W
            y = (by - t * sp * 0.4) % H
            a = int(90 + 80 * math.sin(t * 1.3 + bx))
            dot = pygame.Surface((2, 2), pygame.SRCALPHA)
            dot.fill((*sc["dust"], max(0, a)))
            c.blit(dot, (int(x), int(y)))
        self._motif_anim(c, H, t)
        fx_layer.blit(self._fx_edge, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        real_c.blit(fx_layer, (0, 0))
        real_c.set_clip(prev_clip)

    def _draw_hud(self, c, H):
        p = self.player
        if p is None:  # 프롤로그처럼 아직 캐릭터가 없는 장면: 지명만
            c.blit(self.f_place.render(place_label(self.location), True, INK), (22, H - 118))
            return
        x, y = 22, 22
        c.blit(self.f_mono.render(i18n.t("hud_title"), True, INK_DIM), (x, y))
        y += 24
        ratio = p.hp / max(1, p.max_hp)
        hp_col = GREEN if ratio > 0.5 else (AMBER if ratio > 0.25 else RED)
        now = pygame.time.get_ticks()
        for key, label, val, mx, col in (("hp", "HP", p.hp, p.max_hp, hp_col), ("hunger", i18n.t("hud_hunger"), p.hunger, 100, AMBER),
                                         ("thirst", i18n.t("hud_thirst"), p.thirst, 100, TEAL)):
            # 표시값이 실제 값을 따라간다: 줄면 줄어든 구간을 붉게 남겼다가 지우고, 숫자는 굴러간다
            shown = self._hud.get(key, val)
            if self.hud_hold and key in self._hud:  # 서술이 끝나고 결과가 나올 때까지 옛 값을 보여 준다
                val = shown
            if val < shown and key not in self._loss:
                self._loss[key] = (shown, now)
                if key == "hp":
                    self._hurt_until = now + 450
            shown += (val - shown) * 0.12 if abs(val - shown) > 0.5 else (val - shown)
            self._hud[key] = shown
            flash = 0.0
            if key in self._loss:
                old, t0 = self._loss[key]
                flash = max(0.0, 1 - (now - t0) / 900)
                if flash == 0:
                    del self._loss[key]
            c.blit(self.f_mono.render(label, True, INK_DIM), (x, y))
            c.blit(self.f_mono.render(f"{int(round(shown)):,}", True, _lerp(INK, RED, flash)), (x + 44, y))
            bx, bw = x + 110, 150
            fill = lambda v: bx + int(bw * max(0, min(1, v / mx)))  # noqa: E731
            pygame.draw.line(c, (46, 44, 42), (bx, y + 9), (bx + bw, y + 9), 3)
            if flash:
                pygame.draw.line(c, _lerp(BG, RED, flash), (fill(val), y + 9), (fill(self._loss[key][0]), y + 9), 3)
            pygame.draw.line(c, col, (bx, y + 9), (fill(min(val, shown)), y + 9), 3)
            y += 22
        # 지명
        c.blit(self.f_place.render(place_label(self.location), True, INK), (22, H - 118))
        sub = i18n.t("place_turn", sub=i18n.t(self._sc["sub"]), turn=p.turn_count)
        c.blit(self.f_mono.render(sub, True, INK_DIM), (24, H - 78))

    # ── 이야기 열 ───────────────────────────────────────────────────────────
    @staticmethod
    def _wrap(font, text, width):
        out = []
        for para in text.split("\n"):
            cur = ""
            for w in para.split(" "):
                cand = w if not cur else cur + " " + w
                if font.size(cand)[0] <= width:
                    cur = cand
                    continue
                if cur:
                    out.append(cur)
                while font.size(w)[0] > width:  # 한 단어가 너무 길면 글자 단위로
                    i = len(w)
                    while i > 1 and font.size(w[:i])[0] > width:
                        i -= 1
                    out.append(w[:i])
                    w = w[i:]
                cur = w
            out.append(cur)
        return out

    def _layout(self, e, width):
        """항목 하나를 (높이, 그리기 함수)로 바꾼다."""
        k = e["kind"]
        if k == "title":
            tag = self.f_mono.render(e["tag"], True, AMBER)
            title_lines = self._wrap(self.f_title, e["title"], width)

            def draw(c, x, y):
                c.blit(tag, (x, y))
                for i, ln in enumerate(title_lines):
                    c.blit(self.f_title.render(ln, True, INK), (x, y + 22 + i * 40))
            return 22 + len(title_lines) * 40 + 12, draw
        if k in ("prose", "narr"):
            color = INK_DIM if k == "prose" else INK
            lines = []
            for para in e["lines"]:
                lines += self._wrap(self.f_serif, para, width)
            typing = e.get("typing")  # 타자 효과 중: (지금 시각 초, 글자별 시작 시각 목록)

            def draw(c, x, y):
                if typing is None:
                    for i, ln in enumerate(lines):
                        c.blit(self.f_serif.render(ln, True, color), (x, y + i * 32))
                    return
                now, times = typing
                fade = TYPE_TAIL / TYPE_CPS  # 한 글자가 다 떠오르는 데 걸리는 시간
                start = 0  # 이 줄 첫 글자의 전체 순번 (줄바꿈 자리의 공백 한 칸 차이는 무시)
                for i, ln in enumerate(lines):
                    alphas = [max(0.0, min(1.0, (now - times[min(start + j, len(times) - 1)]) / fade))
                              for j in range(len(ln))]
                    solid = 0
                    while solid < len(ln) and alphas[solid] >= 1:
                        solid += 1
                    if solid:
                        c.blit(self.f_serif.render(ln[:solid], True, color), (x, y + i * 32))
                    for j in range(solid, len(ln)):  # 막 나타나는 글자는 흐리게, 조금 아래에서 떠오른다
                        a = alphas[j]
                        if a <= 0:
                            return
                        g = self.f_serif.render(ln[j], True, color).copy()
                        g.set_alpha(int(255 * a))
                        c.blit(g, (x + self.f_serif.size(ln[:j])[0], y + i * 32 + int(4 * (1 - a))))
                    start += len(ln) + 1
            return len(lines) * 32 + 10, draw
        if k == "choices":
            rows = [(key, self._wrap(self.f_sans, text, width - 34)) for key, text in e["items"]]

            def draw(c, x, y):
                sel = e.get("sel")
                self._rows = []
                for idx, (key, lines) in enumerate(rows):
                    custom = key == "0"
                    h = len(lines) * 26
                    self._rows.append((key, pygame.Rect(x - 12, y - 4, width + 12, h + 6)))
                    on = sel == idx
                    if on:  # 고른 줄: 옅은 띠 + 왼쪽 막대, 글자가 살짝 들어간다
                        band = pygame.Surface((width + 12, h + 6), pygame.SRCALPHA)
                        band.fill((*(TEAL if custom else AMBER), 22))
                        c.blit(band, (x - 12, y - 4))
                        pygame.draw.line(c, TEAL if custom else AMBER, (x - 12, y - 4), (x - 12, y + h + 1), 2)
                    dx = 6 if on else 0
                    c.blit(self.f_mono_b.render(f"{key}.", True, TEAL if custom else AMBER), (x + dx, y + 2))
                    ink = (TEAL if custom else INK) if on or sel is None else (_lerp(TEAL, BG, 0.35) if custom else INK_DIM)
                    for i, ln in enumerate(lines):
                        c.blit(self.f_sans.render(ln, True, ink), (x + 34 + dx, y + i * 26))
                    y += h + 8
            return sum(len(r[1]) * 26 + 8 for r in rows) + 6, draw
        if k == "you":
            lines = self._wrap(self.f_sans, e["text"], width - 30)
            bar = TEAL if e.get("custom") else AMBER

            def draw(c, x, y):
                pygame.draw.line(c, bar, (x, y + 4), (x, y + len(lines) * 26 - 4), 2)
                for i, ln in enumerate(lines):
                    c.blit(self.f_sans.render(ln, True, INK_DIM), (x + 14, y + i * 26))
            return len(lines) * 26 + 14, draw
        if k == "sys":
            label, text = e["label"], e["text"]

            def draw(c, x, y):
                glow = pygame.Surface((width, 26), pygame.SRCALPHA)
                glow.fill((*AMBER, 18))
                c.blit(glow, (x, y - 3))
                pygame.draw.line(c, AMBER, (x, y - 3), (x, y + 22), 3)
                c.blit(self.f_mono_b.render(label, True, AMBER), (x + 12, y))
                lw = self.f_mono_b.size(label)[0]
                c.blit(self.f_mono_b.render(text, True, _lerp(AMBER, INK, 0.45)), (x + 26 + lw, y))
            return 34, draw
        if k == "result":
            if "t0" not in e:  # 처음 보일 때 결과마다 소리 (하나씩 떠오르는 간격에 맞춰)
                sound.results(e.get("sfx", []))
            t0 = e.setdefault("t0", pygame.time.get_ticks())

            def draw(c, x, y):
                now = pygame.time.get_ticks()
                for i, (text, kind) in enumerate(e["tokens"]):
                    p = max(0.0, min(1.0, (now - t0 - i * 220) / 380))  # 하나씩 떠오른다
                    if p <= 0:
                        break
                    shown = _NUM.sub(lambda mm: str(int(round(int(mm.group(0)) * p))), text) if p < 1 else text
                    col = TOKEN_COLOR.get(kind, INK)
                    surf = self.f_mono_b.render(shown, True, col).copy()
                    full_w = self.f_mono_b.size(text)[0]
                    if x + full_w > self._col_x + width:
                        x, y = self._col_x, y + 24
                    if kind == "item" and p < 1:  # 얻은 물건은 잠깐 빛난다
                        glow = pygame.Surface((full_w + 16, 26), pygame.SRCALPHA)
                        glow.fill((*col, int(60 * (1 - p))))
                        c.blit(glow, (x - 8, y - 4))
                    surf.set_alpha(int(255 * p))
                    c.blit(surf, (x, y + int(8 * (1 - p))))
                    x += full_w + 22
            return 34, draw
        if k == "sep":
            def draw(c, x, y):
                mid = x + width // 2
                for i in (-18, 0, 18):
                    pygame.draw.circle(c, INK_FAINT, (mid + i, y + 10), 2)
            return 24, draw
        return 0, lambda c, x, y: None

    def _draw_column(self, c, W, H):
        x = self._col_x
        width = W - x - 36
        top, bottom = 40, H - FOOT_H - 16
        items = [self._layout(e, width) for e in self.log]
        if self.thinking:  # 다음 서술이 나올 자리: 행동에 맞는 소리 말이 하나씩 흐릿하게 떠오른다 (기록에는 안 남는다)
            now = pygame.time.get_ticks()
            words = self._sfx or ["……"]
            elapsed = (now - self._think_t0) / 1000

            def draw_sfx(cc, xx, yy):
                x = xx
                for i in range(min(SFX_MAX, int(elapsed / SFX_EVERY) + 1)):
                    word = words[i % len(words)]
                    a = min(1.0, (elapsed - i * SFX_EVERY) / 0.5)  # 떠오르기
                    g = self.f_serif.render(word, True, INK_DIM).copy()
                    g.set_alpha(int(170 * max(0.0, a)))
                    cc.blit(g, (x, yy + 4 + int(4 * (1 - a))))
                    x += g.get_width() + 18
            items.append((34, draw_sfx))
        if self.input_buf is not None:
            caret = "▌" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            buf, comp = self.input_buf, self.compose

            def draw_input(cc, xx, yy):
                pygame.draw.line(cc, TEAL, (xx, yy + 2), (xx, yy + 24), 2)
                lines = self._wrap(self.f_sans, buf + comp, width - 14) if (buf or comp) else [""]
                for i, ln in enumerate(lines):
                    cc.blit(self.f_sans.render(ln, True, INK), (xx + 14, yy + i * 26))
                last_w = self.f_sans.size(lines[-1])[0]
                if comp:  # 한글 조합 중인 글자는 밑줄
                    cw = self.f_sans.size(comp)[0]
                    uy = yy + (len(lines) - 1) * 26 + 24
                    pygame.draw.line(cc, TEAL, (xx + 14 + last_w - cw, uy), (xx + 14 + last_w, uy), 1)
                cc.blit(self.f_sans.render(caret, True, TEAL), (xx + 14 + last_w + 2, yy + (len(lines) - 1) * 26))
                self._input_pos = (xx + 14 + last_w, yy + (len(lines) - 1) * 26)
            n = len(self._wrap(self.f_sans, buf + comp, width - 14)) if (buf or comp) else 1
            items.append((n * 26 + 18, draw_input))
        total = sum(h for h, _ in items)
        y = top if total <= bottom - top else bottom - total
        for h, draw in items:
            if y + h > top - 40:
                draw(c, x, y)
            y += h
        # 위로 흘러간 기록은 흐리게
        if total > bottom - top:
            fade = pygame.Surface((W - PLATE_W, 70), pygame.SRCALPHA)
            for yy in range(70):
                pygame.draw.line(fade, (*BG, int(255 * (1 - yy / 70))), (0, yy), (W - PLATE_W, yy))
            c.fill(BG, (PLATE_W, 0, W - PLATE_W, top))
            c.blit(fade, (PLATE_W, top))

    def _draw_footer(self, c, W, H):
        y = H - FOOT_H + 14
        x = self._col_x
        pygame.draw.line(c, (40, 38, 36), (x, H - FOOT_H), (W - 36, H - FOOT_H))
        hits = []
        items = self._foot_items()
        gap = 30 if sum(self.f_mono_b.size(k)[0] + self.f_sans.size(l)[0] + 40 for k, l, _ in items) <= W - 36 - x else 16
        for i, (key, label, ret) in enumerate(items):
            kw, lw = self.f_mono_b.size(key)[0], self.f_sans.size(label)[0]
            rect = pygame.Rect(x - 8, y - 7, kw + 10 + lw + 16, 32)
            on = ret is not None and self._foot_on(i, ret)
            if on:
                band = pygame.Surface(rect.size, pygame.SRCALPHA)
                band.fill((*AMBER, 34))
                c.blit(band, rect.topleft)
                pygame.draw.line(c, AMBER, rect.bottomleft, (rect.right - 1, rect.bottom), 1)
            c.blit(self.f_mono_b.render(key, True, AMBER), (x, y))
            c.blit(self.f_sans.render(label, True, INK if on else INK_FAINT), (x + kw + 10, y))
            if ret is not None:
                hits.append((ret, rect))
            x += kw + 10 + lw + gap
        self._foot_hits = hits

    def _hero_font(self):
        if not hasattr(self, "_f_hero"):
            path = _font_path(["NanumSquareEB.ttf", "NanumSquareB.ttf", "malgunbd.ttf"])
            self._f_hero = CachedFont(path, 46) if path else self.f_title
        return self._f_hero

    def _render_card(self, canvas):
        """장면 카드: 그림을 화면 전체에 깔고 제목을 아래쪽에 올린다 (영화 타이틀처럼). 그림은 천천히 다가온다."""
        W, H = canvas.get_size()
        canvas.fill(BG)
        t = pygame.time.get_ticks() / 1000
        if self._card_art is None:
            path = scene_art.choose(self.location, self.motif, self.context,
                                    getattr(self.player, "turn_count", 0) if self.player else 0)
            self._card_art = False
            if path:
                # 세로 그림을 전체 화면으로 늘리면 흐려지고 피사체가 잘린다 (실측) -> 포스터식:
                # 가운데는 선명한 세로 그림, 양옆은 같은 그림을 뭉개 키운 배경, 경계는 섞는다
                img = pygame.image.load(path)
                if pygame.display.get_surface():
                    img = img.convert()
                ph = int(H * 1.04)
                pw = int(img.get_width() * ph / img.get_height())
                panel = pygame.transform.smoothscale(img, (pw, ph)).convert_alpha() \
                    if pygame.display.get_surface() else pygame.transform.smoothscale(img, (pw, ph)).convert_alpha()
                edge = 90
                fade = pygame.Surface((pw, ph), pygame.SRCALPHA)
                for x in range(pw):
                    k = min(1.0, x / edge, (pw - 1 - x) / edge)
                    pygame.draw.line(fade, (255, 255, 255, int(255 * k)), (x, 0), (x, ph))
                panel.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                small = pygame.transform.smoothscale(img, (max(1, img.get_width() // 24), max(1, img.get_height() // 24)))
                scale = max(W / small.get_width(), H / small.get_height())
                back = pygame.transform.smoothscale(small, (int(small.get_width() * scale) + 1, int(small.get_height() * scale) + 1))
                dim = pygame.Surface(back.get_size(), pygame.SRCALPHA)
                dim.fill((*BG, 150))
                back.blit(dim, (0, 0))
                self._card_art = (back, panel)
                shade = pygame.Surface((W, H), pygame.SRCALPHA)  # 아래를 어둡게 (제목 자리)
                for y in range(H):
                    k = max(0.0, (y / H - 0.62) / 0.38)  # 피사체(가운데)는 가리지 않고 제목 자리만
                    pygame.draw.line(shade, (*BG, int(230 * k ** 1.1)), (0, y), (W, y))
                self._card_shade = shade
                self._card_t0 = t
        if self._card_art:
            back, panel = self._card_art
            canvas.blit(back, ((W - back.get_width()) // 2, (H - back.get_height()) // 2))
            p = min(1.0, (t - self._card_t0) / 8)  # 8초에 걸쳐 그림이 천천히 내려앉는다
            canvas.blit(panel, ((W - panel.get_width()) // 2, int(-(panel.get_height() - H) * (0.2 + 0.6 * p))))
            canvas.blit(self._card_shade, (0, 0))
        title = next((e for e in self.log if e["kind"] == "title"), None)
        narr = next((e for e in self.log if e["kind"] in ("narr", "prose")), None)
        menu = next((e for e in self.log if e["kind"] == "choices"), None)
        if menu and self._card_art and not getattr(self, "_card_dim", None):  # 메뉴가 있으면 그림을 한 톤 눌러 글을 살린다
            self._card_dim = pygame.Surface((W, H), pygame.SRCALPHA)
            self._card_dim.fill((*BG, 110))
        if menu and getattr(self, "_card_dim", None):
            canvas.blit(self._card_dim, (0, 0))
        y = int(H * (0.26 if menu else 0.80))
        if title:
            if title.get("tag"):
                tag = self.f_mono.render(title["tag"], True, AMBER)
                canvas.blit(tag, ((W - tag.get_width()) // 2, y - 30))
            font = self._hero_font() if title.get("hero") else self.f_title
            for ln in self._wrap(font, title["title"], W - 120):
                g = font.render(ln, True, INK)
                canvas.blit(g, ((W - g.get_width()) // 2, y))
                y += font.get_linesize() + 4
        if narr:
            color = INK_DIM if narr["kind"] == "prose" else INK
            for para in narr["lines"]:
                for ln in self._wrap(self.f_serif, para, W - 240):
                    g = self.f_serif.render(ln, True, color)
                    canvas.blit(g, ((W - g.get_width()) // 2, y + 8))
                    y += 30
        if menu:
            mw = min(460, W - 200)
            _, draw = self._layout(menu, mw)
            draw(canvas, (W - mw) // 2, max(y + 40, int(H * 0.56)))
        fx = W - 60  # 오른쪽에서 왼쪽으로 차례로 놓는다
        hits = []
        items = self._foot_items()
        for i, (key, label, ret) in reversed(list(enumerate(items))):
            on = ret is not None and self._foot_on(i, ret)
            g = self.f_sans.render(label, True, INK if on else INK_FAINT)
            k = self.f_mono_b.render(key, True, AMBER)
            fx -= g.get_width()
            canvas.blit(g, (fx, H - 44))
            fx -= k.get_width() + 10
            canvas.blit(k, (fx, H - 44))
            rect = pygame.Rect(fx - 8, H - 51, k.get_width() + 10 + g.get_width() + 16, 32)
            if on:
                pygame.draw.line(canvas, AMBER, rect.bottomleft, (rect.right - 1, rect.bottom), 1)
            if ret is not None:
                hits.append((ret, rect))
            fx -= 30
        self._foot_hits = hits
        if self._overlay is None:
            self._build_overlay(W, H)
        canvas.blit(self._overlay, (0, 0))

    def render(self, canvas):
        if self.card:
            self._render_card(canvas)
            return
        W, H = canvas.get_size()
        canvas.fill(BG)
        self._draw_plate(canvas, H)
        self._draw_column(canvas, W, H)
        self._draw_hud(canvas, H)
        self._draw_footer(canvas, W, H)
        if self._overlay is None:
            self._build_overlay(W, H)
        canvas.blit(self._overlay, (0, 0))
        now = pygame.time.get_ticks()
        if now < self._hurt_until:  # 피해: 가장자리가 붉게 번졌다가 빠진다
            a = (self._hurt_until - now) / 450
            if self._hurt is None or self._hurt.get_size() != (W, H):
                self._hurt = self._edge_glow(W, H, RED)
            self._hurt.set_alpha(int(150 * a))
            canvas.blit(self._hurt, (0, 0))
        end, amp = self._shake
        if now < end:  # 흔들림: 캔버스를 통째로 밀고 빈 곳은 배경색
            k = (end - now) / 400 * amp
            dx, dy = int(random.uniform(-k, k)), int(random.uniform(-k, k))
            canvas.scroll(dx, dy)

    @staticmethod
    def _edge_glow(W, H, col):
        g = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(0, 90, 3):
            pygame.draw.rect(g, (*col, int(60 * (1 - i / 90) ** 2)), (i, i, W - 2 * i, H - 2 * i), 3)
        return g

    def shake(self, amp=7, ms=400):
        """큰 피해나 대실패 때 화면을 흔든다."""
        self._shake = (pygame.time.get_ticks() + ms, amp)

    # ── 이 화면 안에서 도는 루프 (입력, 대기, 타자) ──────────────────────────
    FPS = 60  # 30에서는 느린 안개·먼지가 정수 픽셀로 튀어 고르지 않게 움직였다
    MAX_INPUT = 300

    def _events(self):
        """한 프레임: 이벤트를 모아 돌려주고 화면을 다시 그린다. 창 닫기와 F11은 여기서 처리."""
        out = []
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                self._term.toggle_fullscreen()
                continue
            out.append(ev)
        self.refresh()
        self._clock.tick(self.FPS)
        return out

    @property
    def _clock(self):
        if not hasattr(self, "_clk"):
            self._clk = pygame.time.Clock()
        return self._clk

    def wait_key(self, keys):
        """keys 안의 키가 눌릴 때까지 기다린다. Enter는 'ENTER', Esc는 'ESC'."""
        pygame.event.clear((pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN))  # 연출 중에 미리 누른 키·클릭으로 넘어가지 않게
        while True:
            for ev in self._events():
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:  # 클릭 = Enter (발밑 버튼이면 그 키)
                    hit = self.foot_at(ev.pos)
                    if hit in keys:
                        return hit
                    # 고를 게 따로 있으면(예: 0 더 묻기 / Enter 떠나기) 빈 곳 클릭으로 넘어가지 않는다
                    if not (set(keys) - {"ENTER", "ESC", " "}):
                        k = "ENTER" if "ENTER" in keys else (" " if " " in keys else None)
                        if k:
                            return k
                if ev.type == pygame.MOUSEMOTION:
                    self._foot_hover = self.foot_at(ev.pos)
                if ev.type != pygame.KEYDOWN:
                    continue
                if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    k = "ENTER"
                elif ev.key == pygame.K_ESCAPE:
                    k = "ESC"
                else:
                    k = ev.unicode.upper() if ev.unicode else ""
                if k in keys:
                    return k

    def read_line(self):
        """한글 입력(IME)을 받는 한 줄 입력. Enter로 확정, 빈 칸에서 Enter면 None (취소)."""
        self.input_buf, self.compose = "", ""
        pygame.key.start_text_input()
        pygame.event.clear((pygame.TEXTINPUT, pygame.TEXTEDITING))
        try:
            while True:
                x, y = self._input_pos
                pygame.key.set_text_input_rect(pygame.Rect(x, y, 10, 26))
                for ev in self._events():
                    if ev.type == pygame.TEXTEDITING:
                        self.compose = ev.text
                    elif ev.type == pygame.TEXTINPUT:
                        self.input_buf = (self.input_buf + ev.text)[:self.MAX_INPUT]
                        self.compose = ""
                    elif ev.type == pygame.KEYDOWN:
                        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self.compose:
                            text = self.input_buf.strip()
                            return text or None  # 빈 칸 Enter = 취소 (ESC는 쓰지 않는다)
                        elif ev.key == pygame.K_BACKSPACE and not self.compose:
                            self.input_buf = self.input_buf[:-1]
        finally:
            pygame.key.stop_text_input()
            self.input_buf, self.compose = None, ""

    def _pick_sfx(self, action):
        """행동 문장에 맞는 소리 말. 비 오는 장면이면 빗소리를 섞는다."""
        words = next((w for keys, w in SFX if any(k in action for k in keys)), SFX_DEFAULT)
        raining = self.motif == "rain" or scene_art.world_weather(getattr(self.player, "turn_count", 0)) == "acid"
        return [x for pair in zip(words, SFX_RAIN * 3) for x in pair][:len(words) + 1] if raining else list(words)

    def run_task(self, fn, action=""):
        """fn을 백그라운드 스레드에서 돌리는 동안 화면을 계속 움직인다 (행동에 맞는 소리 말을 띄운다).
        fn의 예외는 그대로 다시 던진다."""
        self._sfx = self._pick_sfx(action)
        self._think_t0 = pygame.time.get_ticks()
        box = {}

        def work():
            try:
                box["value"] = fn()
            except Exception as e:  # noqa: BLE001 - 호출한 쪽에서 판단한다
                box["error"] = e
        th = threading.Thread(target=work, daemon=True)
        self.thinking = True
        th.start()
        try:
            while th.is_alive():
                self._events()
        finally:
            self.thinking = False
        if "error" in box:
            raise box["error"]
        return box["value"]

    def type_out(self, entry, cps=TYPE_CPS):
        """서술 항목을 타자 치듯 드러낸다. 글자는 서서히 떠오르고 문장 끝에서 잠깐 쉰다.
        아무 키나 누르면 바로 전부 보인다."""
        text = " ".join(entry["lines"])  # 줄 사이도 한 칸으로 센다 (그리기 쪽 순번과 맞춘다)
        times, t = [], 0.0  # 글자마다 나타나기 시작하는 시각 (초)
        for ch in text:
            times.append(t)
            t += 1 / cps + PAUSE_AFTER.get(ch, 0)
        done = t + TYPE_TAIL / cps  # 마지막 글자까지 다 떠오르는 시각
        start = pygame.time.get_ticks()
        entry["typing"] = (0.0, times)
        while True:
            if any(ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN) for ev in self._events()):
                break
            now = (pygame.time.get_ticks() - start) / 1000
            if now >= done:
                break
            entry["typing"] = (now, times)
        entry.pop("typing", None)

    def choose(self, menu, n, extra=()):
        """선택지 고르기: 숫자키, 방향키+Enter, 마우스(올리면 강조, 누르면 선택). 고른 키('1'..'n', '0')를 돌려준다.
        extra: 추가로 받는 키 (예: 'ESC')."""
        keys = [k for k, _ in menu["items"]]  # 화면에 보이는 선택지 키 그대로 (타이틀처럼 0이 없는 메뉴도 있다)

        def _picked(k):  # 고른 소리: 0·ESC는 뒤로, 나머지는 확인
            sound.sfx("ui_back" if k in ("0", "ESC") else "ui_ok")
            return k
        pygame.event.clear((pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN))  # 연출 중에 미리 누른 키·클릭으로 넘어가지 않게
        menu["sel"] = menu.get("start", 0)
        try:
            while True:
                for ev in self._events():
                    if ev.type == pygame.KEYDOWN:
                        if ev.key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT):
                            menu["sel"] = (menu["sel"] - 1) % len(keys)
                            sound.sfx("ui_move")
                        elif ev.key in (pygame.K_DOWN, pygame.K_s, pygame.K_TAB, pygame.K_RIGHT):
                            menu["sel"] = (menu["sel"] + 1) % len(keys)
                            sound.sfx("ui_move")
                        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                            return _picked(keys[menu["sel"]])
                        elif ev.key == pygame.K_ESCAPE and "ESC" in extra:
                            return _picked("ESC")
                        elif ev.unicode and ev.unicode in keys:
                            return _picked(ev.unicode)
                    elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                        fh = self.foot_at(ev.pos)
                        self._foot_hover = fh
                        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and fh:
                            if fh in keys:
                                return _picked(fh)
                            if fh == "ESC" and "ESC" in extra:
                                return _picked("ESC")
                        hit = self._row_at(ev.pos)
                        if hit is not None:
                            if keys.index(hit) != menu["sel"]:
                                sound.sfx("ui_move")
                            menu["sel"] = keys.index(hit)
                            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                                return _picked(hit)
        finally:
            menu.pop("sel", None)

    # ── 마우스·방향키 공용 ────────────────────────────────────────────────
    # 발밑 안내(footer)는 버튼이다: 마우스를 올리면 밝아지고 누르면 그 키를 누른 것과 같다.
    # footer 항목: (보이는 키, 설명) 또는 (보이는 키, 설명, 돌려줄 키). 돌려줄 키가 없으면 보이는 키가
    # 한 글자일 때 그 글자, Enter/Esc면 "ENTER"/"ESC", 그 밖(↑↓, WASD …)은 누를 수 없는 안내.
    # foot_nav=True면 (전투처럼) 방향키로 발밑 행동을 고르고 Enter·Space로 실행한다 (foot_sel = 고른 칸).
    foot_nav = False
    foot_sel = 0
    nav_cols = 1         # 버튼이 격자면 한 줄 칸 수 (↑↓가 이만큼 건너뛴다)
    _foot_hover = None
    _foot_hits = ()

    def _foot_items(self):
        out = []
        for item in self.footer:
            key, label = item[0], item[1]
            if len(item) > 2:
                ret = item[2]
            elif len(key) == 1:
                ret = key.upper()
            else:
                ret = {"enter": "ENTER", "esc": "ESC"}.get(key.lower())
            out.append((key, label, ret))
        return out

    def _foot_on(self, i, ret):
        if ret == self._foot_hover:
            return True
        if self.foot_nav:
            rets = [r for _, _, r in self._foot_items() if r is not None]
            return bool(rets) and rets[self.foot_sel % len(rets)] == ret
        return False

    # ── 퀵슬롯 줄 (맵·전투 공용): 1~0 칸, 누르면 그 숫자키 ─────────────────────
    QB_H = 46
    _quick_hits = ()
    _quick_hover = None

    @staticmethod
    def quick_label(key):
        """칸에 들어갈 짧은 글: 회복은 양(10% / +300), 먹을 것은 식량·식수."""
        import constants
        d = constants.CONSUMABLES_DB.get(key)
        if not d:
            return "", INK_FAINT
        if d["type"] == "hp":
            return (f"{int(d['val'] * 100)}%" if d["is_percent"] else f"+{d['val']}"), RED
        if d["type"] == "food":
            return i18n.t('qs_food'), AMBER
        return i18n.t('qs_water'), TEAL

    def _draw_quickbar(self, c, x, y, width):
        """퀵슬롯 10칸. 비었으면 흐린 칸, 개수가 0이면 흐리게. 마우스를 올린 칸 이름은 위에 띄운다."""
        import constants
        p = self.player
        slots = getattr(p, "quickslots", None) or [None] * 10
        gap = 6
        bw = (width - gap * 9) // 10
        hits = []
        for i, key in enumerate(slots):
            ch = "1234567890"[i]
            rect = pygame.Rect(x + i * (bw + gap), y, bw, self.QB_H)
            n = p.consumables.get(key, 0) if key else 0
            hov = self._quick_hover == ch
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            box.fill((*AMBER, 36) if hov else (255, 255, 255, 12 if key else 5))
            c.blit(box, rect.topleft)
            pygame.draw.rect(c, AMBER if hov else ((70, 66, 60) if key else (40, 38, 36)), rect, 1)
            c.blit(self.f_mono.render(ch, True, AMBER if key else INK_FAINT), (rect.x + 4, rect.y + 2))
            if key:
                label, col = self.quick_label(key)
                col = col if n else INK_FAINT
                g = self.f_mono_b.render(label, True, col)
                c.blit(g, (rect.centerx - g.get_width() // 2, rect.y + 17))
                cnt = self.f_mono.render(f"x{n}", True, INK_DIM if n else INK_FAINT)
                c.blit(cnt, (rect.right - cnt.get_width() - 4, rect.y + 2))
            hits.append((ch, rect))
            if hov and key:
                name = self.f_sans.render(i18n.db_t(constants.CONSUMABLES_DB[key], 'name') + f"  x{n}", True, INK)
                c.blit(name, (x, y - 26))
        self._quick_hits = hits

    def quick_at(self, pos):
        cx, cy = self.to_canvas(pos)
        return next((k for k, r in self._quick_hits if r.collidepoint(cx, cy)), None)

    def to_canvas(self, pos):
        """창 좌표 → 캔버스 좌표 (gui의 레터박스 스케일과 같게)."""
        sw, sh = self._term.screen.get_size()
        cw, ch = self._term._canvas.get_size()
        scale = min(sw / cw, sh / ch)
        return (pos[0] - (sw - cw * scale) / 2) / scale, (pos[1] - (sh - ch * scale) / 2) / scale

    def foot_at(self, pos):
        cx, cy = self.to_canvas(pos)
        for ret, rect in self._foot_hits:
            if rect.collidepoint(cx, cy):
                return ret
        return None

    def on_input(self, ev):
        """gui.read_key가 이 화면이 떠 있을 때 부른다. 키 하나(문자열)를 돌려주면 그 키를 누른 것으로 친다."""
        if ev.type == pygame.MOUSEMOTION:
            hit = self.foot_at(ev.pos)
            if hit != self._foot_hover and hit is not None:
                sound.sfx("ui_move")
            self._foot_hover = hit
            self._quick_hover = self.quick_at(ev.pos)
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            q = self.quick_at(ev.pos)
            if q is not None:
                return q
            hit = self.foot_at(ev.pos)
            if hit is not None:
                sound.sfx("ui_ok")
                if self.foot_nav:
                    rets = [r for _, _, r in self._foot_items() if r is not None]
                    self.foot_sel = rets.index(hit) if hit in rets else self.foot_sel
            return hit
        if ev.type == pygame.KEYDOWN and self.foot_nav:
            rets = [r for _, _, r in self._foot_items() if r is not None]
            if not rets:
                return None
            if ev.key in (pygame.K_LEFT, pygame.K_UP, pygame.K_RIGHT, pygame.K_DOWN):
                step = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1, pygame.K_UP: -self.nav_cols, pygame.K_DOWN: self.nav_cols}[ev.key]
                n = self.foot_sel + step
                self.foot_sel = n % len(rets) if abs(step) == 1 else (n if 0 <= n < len(rets) else self.foot_sel)
                self._foot_hover = None
                sound.sfx("ui_move")
                return None
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return rets[self.foot_sel % len(rets)]
        return None

    def _row_at(self, pos):
        """창 좌표 → 캔버스 좌표 (gui의 레터박스 스케일과 같게) → 선택지 줄."""
        cx, cy = self.to_canvas(pos)
        for key, rect in self._rows:
            if rect.collidepoint(cx, cy):
                return key
        return None

    def hold(self, ms):
        """ms 동안 보여 주다가 넘어간다. 키나 마우스를 누르면 바로."""
        end = pygame.time.get_ticks() + ms
        while pygame.time.get_ticks() < end:
            if any(ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN) for ev in self._events()):
                return

    def pause(self, ms):
        end = pygame.time.get_ticks() + ms
        while pygame.time.get_ticks() < end:
            self._events()


def scene_card(scene, title, tag="", line=None, player=None, location=JUNKYARD, hold_ms=2600):
    """장면이 시작될 때 그림과 제목을 잠깐 보여 주는 카드 (전투 시작, 스토리 세션, 프롤로그).
    그 뒤 흐름은 원래 화면(터미널)이 그대로 이어간다. 그림 화면을 못 여는 환경이면 아무것도 안 한다."""
    try:
        from gui import get_terminal
        term = get_terminal()
        if term is None:
            return
        view = EventView(term, player, None, location, scene=scene)
        view.card = True
        view.add("title", tag=tag, title=title)
        if line:
            entry = view.add("narr", lines=[line])
        view.footer = [("Enter", i18n.t("ui_continue"))]
        view.open()
        try:
            if line:
                view.type_out(entry)
            view.hold(hold_ms)
        finally:
            view.close()
    except Exception:  # noqa: BLE001 - 장면 카드는 연출일 뿐, 실패해도 게임은 이어진다
        return
