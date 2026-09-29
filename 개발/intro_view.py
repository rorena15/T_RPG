"""게임을 켤 때 나오는 오프닝 (타이틀 메뉴 직전, 아무 키로 건너뛴다. ESC는 무시).

① 폐기 기록: 검은 화면, 이명 속에 네오 아크 시스템의 폐기 기록이 모노 글씨로 올라온다. 마지막 줄에서 심장 박동.
② 붉은 눈: 어둠 속 해골(게임 아이콘)의 붉은 눈만 켜졌다 꺼진다.
③ 타이틀: 타이틀 메뉴와 같은 화면(같은 그림)이 검은 화면에서 밝아지고 제목이 해독되듯 맞춰진다.
   메뉴와 제목 자리·글꼴이 같아서, 끝나면 그대로 메뉴만 나타난다.
실행할 때마다 같은 길이로 전부 나온다.
"""
import math
import os
import random

import pygame

import i18n
import sound
from event_view import AMBER, BG, INK, INK_DIM, RED, CachedFont

# (글, 색) — 설정: 네오 아크가 N-404를 불량 코드로 분류해 폐기했지만, 신호가 아직 살아 있다
# 언어 키 (빈 문자열은 빈 줄). 언어를 바꾼 뒤에도 맞게 나오도록 그릴 때 번역한다
LINE_KEYS = [
    ("intro_line_1", INK_DIM),
    ("intro_line_2", INK_DIM),
    ("intro_line_3", INK_DIM),
    ("", INK_DIM),
    ("intro_line_4", AMBER),
    ("intro_line_5", RED),
]


def _lines():
    return [(i18n.t(k) if k else "", col) for k, col in LINE_KEYS]
CHAR_MS = 13        # 한 글자
LINE_GAP_MS = 230   # 줄 사이
EYE_MS = 2800       # 붉은 눈
EYE_OFF_MS = 900    # 눈이 꺼지는 데 걸리는 시간
TITLE_MS = 4200     # 타이틀 등장
TITLE_PACE = TITLE_MS / 2300  # 밝아짐·해독·부제 시점 배율 (2.3초 판 기준으로 짠 시간을 늘린다)
SCRAMBLE = "#$%&*+=<>?/\\|_01ABCDEFGHKLMNPRSTXZ"


class Intro:
    def __init__(self, term, title_view, title, tag):
        self._term = term
        self.view = title_view  # 타이틀 메뉴의 화면 (카드). 그림을 여기서 먼저 골라 두면 메뉴도 같은 그림이다
        self.title, self.tag = title, tag
        self.lines = _lines()
        self._active = False
        self._prev = None
        mono = term._find_bundled_font()
        self.f_mono = CachedFont(mono, 18)
        self._eye = None
        # 시간표 (ms)
        self.t_text = 300
        text_ms = sum(len(s) * CHAR_MS + LINE_GAP_MS for s, _ in self.lines) + 500
        self.t_eye = self.t_text + text_ms
        self.eye_ms, self._eye_off, self.title_ms = EYE_MS, EYE_OFF_MS, TITLE_MS
        self.t_title = self.t_eye + self.eye_ms
        self.t_end = self.t_title + self.title_ms
        self._played = set()

    # ── 준비 (검은 화면일 때 무거운 것을 미리) ──────────────────────────────
    def _prepare(self, W, H):
        off = pygame.Surface((W, H))
        self.view.render(off)  # 장면 그림을 여기서 읽는다 (③에서 멈칫하지 않게)
        path = os.path.join(os.path.dirname(self._term._find_ico() or ""), "icon.png")
        if os.path.exists(path):
            img = pygame.image.load(path).convert_alpha()
            size = int(H * 0.78)
            img = pygame.transform.smoothscale(img, (size, size))
            img.fill((34, 34, 38), special_flags=pygame.BLEND_RGB_MULT)  # 해골은 거의 안 보이게
            flat = pygame.Surface((size, size))  # 검은 배경 위에 미리 얹어 두고 더하기로 그린다 (아이콘의 검은 사각이 안 보이게)
            flat.fill((0, 0, 0))
            flat.blit(img, (0, 0))
            self._eye = (flat, size)
        # 눈빛: 검은 바탕에 밝기로 그린 번짐 (더하기 합성은 투명도를 안 쓰므로 밝기 자체로 세기를 준다)
        self._glow = pygame.Surface((260, 260))
        self._glow.fill((0, 0, 0))
        for r in range(130, 0, -1):
            k = (1 - r / 130) ** 2.4
            pygame.draw.circle(self._glow, (int(255 * k), int(38 * k), int(28 * k)), (130, 130), r)
        self._black = pygame.Surface((W, H))
        self._black.fill(BG)
        self._dim = pygame.Surface((W, H), pygame.SRCALPHA)
        self._dim.fill((*BG, 110))  # 타이틀 메뉴(카드+선택지)와 같은 눌림

    def _sfx(self, name, key, vol=0.8, fade_ms=0):
        if key in self._played or getattr(sound, "_muted", False):
            return None
        self._played.add(key)
        try:
            s = pygame.mixer.Sound(sound._asset(name))
            s.set_volume(vol * min(1.0, getattr(sound, "_sfx_mult", 0.5) * 2))   # 효과음 음량을 따른다
            s.play(fade_ms=fade_ms)
            return s
        except Exception:
            return None

    # ── 그리기 ────────────────────────────────────────────────────────────
    def render(self, canvas):
        W, H = canvas.get_size()
        now = pygame.time.get_ticks() - self.t0
        if now < self.t_eye:
            self._draw_text(canvas, W, H, now)
        elif now < self.t_title:
            self._draw_eye(canvas, W, H, now - self.t_eye)
        else:
            self._draw_title(canvas, W, H, now - self.t_title)

    def _draw_text(self, c, W, H, now):
        c.fill(BG)
        if now < self.t_text:
            return
        if self._tinnitus is None:
            self._tinnitus = self._sfx("tinnitus.mp3", "tin", 0.30, fade_ms=900) or False
        x, y = int(W * 0.16), int(H * 0.36)
        t = now - self.t_text
        for i, (text, col) in enumerate(self.lines):
            start = sum(len(s) * CHAR_MS + LINE_GAP_MS for s, _ in self.lines[:i])
            if t < start:
                break
            n = min(len(text), int((t - start) / CHAR_MS))
            shown = text[:n]
            last = i == len(self.lines) - 1
            if last and n > 0:
                self._sfx("heartbeat4.wav", "hb", 0.9)
            if shown:
                gx = 0
                if last and random.random() < 0.18:  # 마지막 줄은 글리치로 떨린다
                    gx = random.randint(-6, 6)
                g = self.f_mono.render(shown, True, col)
                c.blit(g, (x + gx, y))
                if last and random.random() < 0.12:
                    band = random.randint(0, g.get_height() - 4)
                    c.blit(g, (x + random.randint(-14, 14), y + band), (0, band, g.get_width(), 4))
            if n < len(text) and (t // 90) % 2 == 0:  # 커서
                cx = x + self.f_mono.size(shown)[0] + 2
                pygame.draw.rect(c, col, (cx, y + 3, 9, 17))
            y += 32

    def _draw_eye(self, c, W, H, t):
        c.fill(BG)
        if self._tinnitus:
            self._tinnitus.fadeout(700)
            self._tinnitus = False
        if not self._eye:
            return
        img, size = self._eye
        ox, oy = (W - size) // 2, int(H * 0.08)
        # 켜짐: 잠깐 깜박였다가 켜지고, 끝에 꺼진다
        if t < 120:
            k = 0.0
        elif t < 260:
            k = 0.9 if (t // 45) % 2 else 0.15
        elif t < self.eye_ms - self._eye_off:
            k = 1.0
        else:
            k = max(0.0, 1 - (t - (self.eye_ms - self._eye_off)) / self._eye_off)
        if t >= 120:
            self._sfx("heartbeat4.wav", "hb2", 0.7)
        if k <= 0:
            return
        skull = img.copy()
        v = int(255 * min(1.0, k * 1.3))
        skull.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
        c.blit(skull, (ox, oy), special_flags=pygame.BLEND_RGB_ADD)
        ex, ey = ox + int(size * 153 / 256), oy + int(size * 121 / 256)  # 아이콘의 붉은 눈 자리
        pulse = 1 + 0.06 * math.sin(t / 70)
        for scale, a in ((2.2 * pulse, 0.45), (0.8 * pulse, 1.0)):
            g = pygame.transform.smoothscale(self._glow, (int(260 * scale), int(260 * scale)))
            v = int(255 * k * a)
            g.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
            c.blit(g, (ex - g.get_width() // 2, ey - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(c, (255, int(190 * k), int(170 * k)), (ex, ey), max(1, int(4 * k)))

    def _draw_title(self, c, W, H, t):
        if "wind" not in self._played:
            self._played.add("wind")
            sound.play_map_ambient()  # 바람 소리는 타이틀 메뉴까지 그대로 이어진다
            sound.play_title_bgm()    # 그 위로 타이틀 곡
        v = self.view
        saved = v.log
        v.log = []
        v.render(c)  # 그림 + 필름 결 (글 없이)
        v.log = saved
        c.blit(self._dim, (0, 0))
        # 제목: 뒤섞인 기호에서 한 글자씩 맞춰진다 (타이틀 메뉴와 같은 자리·글꼴)
        font = v._hero_font()
        y = int(H * 0.26)
        f = TITLE_PACE
        p = min(1.0, max(0.0, (t - 500 * f) / (1300 * f)))
        fixed = int(len(self.title) * p)
        rng = random.Random(t // 60)
        text = "".join(ch if (i < fixed or ch == " ") else rng.choice(SCRAMBLE)
                       for i, ch in enumerate(self.title))
        g = font.render(text, True, INK)
        final_w = font.size(self.title)[0]
        c.blit(g, ((W - final_w) // 2, y))
        if self.tag and p >= 1:
            k = min(1.0, (t - 1800 * f) / (500 * f))
            if k > 0:
                tg = self.f_mono.render(self.tag, True, AMBER)
                tg.set_alpha(int(255 * k))
                c.blit(tg, ((W - tg.get_width()) // 2, y - 30))
        # 검은 화면에서 밝아진다
        a = max(0.0, 1 - t / (1400 * f))
        if a > 0:
            self._black.set_alpha(int(255 * a))
            c.blit(self._black, (0, 0))

    # ── 흐름 ──────────────────────────────────────────────────────────────
    def run(self):
        term = self._term
        W, H = term._canvas.get_size()
        self._tinnitus = None
        self._prepare(W, H)
        self._prev = term._ui_manager
        term._ui_manager = self
        self._active = True
        self.t0 = pygame.time.get_ticks()
        clock = pygame.time.Clock()
        pygame.event.clear(pygame.KEYDOWN)
        try:
            while pygame.time.get_ticks() - self.t0 < self.t_end:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        raise SystemExit
                    if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                        term.toggle_fullscreen()
                    elif ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                            continue
                        now = pygame.time.get_ticks() - self.t0
                        if now < self.t_title:  # 건너뛰기: 타이틀 등장 끝부분으로
                            self.t0 -= self.t_title - now + self.title_ms - 700
                        else:
                            self.t0 = pygame.time.get_ticks() - self.t_end
                term._dirty = True
                term._render()
                clock.tick(60)
        finally:
            if self._tinnitus:
                self._tinnitus.fadeout(300)
            if "wind" not in self._played:
                sound.play_map_ambient()
                sound.play_title_bgm()
            self._active = False
            term._ui_manager = self._prev
            pygame.event.clear(pygame.KEYDOWN)  # 건너뛰려고 누른 키가 메뉴를 고르지 않게


def play(term, title_view, title, tag):
    """오프닝을 튼다 (실행 횟수와 상관없이 매번 전부)."""
    try:
        Intro(term, title_view, title, tag).run()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - 오프닝은 연출일 뿐, 실패해도 게임은 이어진다
        term._ui_manager = None
