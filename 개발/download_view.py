"""추가 데이터(동적 서사 모델) 다운로드 화면. 이벤트 화면(event_view)과 같은 색·글꼴을 쓴다.

offer(term)가 안내 → 선택 → 받기 → 확인 → 완료까지 진행하고, 받은 모드("full"/"lite")나 None을 돌려준다.
받기는 gm_server.Download가 백그라운드 스레드에서 하고, 이 화면은 진행 상황만 그린다.
"""
import sys
import threading

import pygame

import gm_server
from event_view import AMBER, BG, INK, INK_DIM, INK_FAINT, RED, TEAL, _font_path
from i18n import t

W_TEXT = 620


def _fmt_size(n):
    return f"{n / (1 << 30):.1f}GB" if n >= (1 << 30) else f"{n / (1 << 20):.0f}MB"


def _fmt_eta(sec):
    if sec >= 3600:
        return t('eta_hours', n=sec / 3600)
    return t('eta_min', n=max(1, round(sec / 60))) if sec >= 60 else t('eta_sec', n=int(sec))


class DownloadView:
    def __init__(self, term):
        self._term = term
        self._active = False
        self._prev = None
        mono = term._find_bundled_font()
        sans = _font_path(["NanumBarunGothic.ttf", "malgun.ttf"]) or mono
        serif = _font_path(["NanumMyeongjo.ttf", "HANBatang.ttf"]) or mono
        title = _font_path(["NanumSquareEB.ttf", "NanumSquareB.ttf", "malgunbd.ttf"]) or sans
        self.f_title = pygame.font.Font(title, 26)
        self.f_serif = pygame.font.Font(serif, 20)
        self.f_sans = pygame.font.Font(sans, 17)
        self.f_mono = pygame.font.Font(mono, 15)
        self.lines = []          # 본문 [(문장, 색)]
        self.options = []        # [(키, 문장)]
        self.progress = None     # 0~1, None이면 막대 없음
        self.status = ""
        self.footer = []
        self._clock = pygame.time.Clock()

    # ── 터미널 훅 ───────────────────────────────────────────────────────────
    def open(self):
        self._prev = self._term._ui_manager
        self._active = True
        self._term._ui_manager = self

    def close(self):
        self._active = False
        self._term._ui_manager = self._prev
        self._term._dirty = True

    def _frame(self):
        out = []
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                self._term.toggle_fullscreen()
                continue
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:  # ESC는 무시
                continue
            out.append(ev)
        self._term._dirty = True
        self._term._render()
        self._clock.tick(30)
        return out

    def _wait_key(self, keys):
        while True:
            for ev in self._frame():
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

    # ── 그리기 ─────────────────────────────────────────────────────────────
    def render(self, c):
        W, H = c.get_size()
        c.fill(BG)
        x = (W - W_TEXT) // 2
        y = int(H * 0.28)
        c.blit(self.f_mono.render(t('dl_title'), True, AMBER), (x, y))
        y += 34
        for text, color in self.lines:
            for ln in text.split("\n"):
                c.blit(self.f_serif.render(ln, True, color), (x, y))
                y += 34
        y += 18
        for key, text in self.options:
            c.blit(self.f_mono.render(f"{key}.", True, AMBER if key != "0" else INK_FAINT), (x, y + 2))
            c.blit(self.f_sans.render(text, True, INK if key != "0" else INK_DIM), (x + 30, y))
            y += 34
        if self.progress is not None:
            y += 10
            pygame.draw.line(c, (46, 44, 42), (x, y), (x + W_TEXT, y), 4)
            pygame.draw.line(c, TEAL, (x, y), (x + int(W_TEXT * max(0.0, min(1.0, self.progress))), y), 4)
            y += 18
        if self.status:
            c.blit(self.f_mono.render(self.status, True, INK_DIM), (x, y))
        fx = x
        for key, label in self.footer:
            k = self.f_mono.render(key, True, AMBER)
            c.blit(k, (fx, H - 60))
            fx += k.get_width() + 8
            s = self.f_sans.render(label, True, INK_FAINT)
            c.blit(s, (fx, H - 62))
            fx += s.get_width() + 26

    # ── 흐름 ───────────────────────────────────────────────────────────────
    def _choose(self):
        m = gm_server.manifest()["models"]
        self.lines = [(t('dl_offer'), INK)]
        self.options = [("1", t('dl_full', size=_fmt_size(m["full"]["size"]))),
                        ("2", t('dl_lite', size=_fmt_size(m["lite"]["size"]))),
                        ("0", t('dl_later'))]
        self.footer = [("1-2", t('gm_foot_choose')), ("0", t('dl_later'))]
        k = self._wait_key({"1", "2", "0", "ESC"})
        return {"1": "full", "2": "lite"}.get(k)

    def _download(self, mode):
        job = gm_server.Download(mode)
        self.options = []
        if not job.free_space_ok():
            self.lines = [(t('dl_space', need=_fmt_size(job.total * 2)), RED)]
            self.footer = [("Enter", t('dl_continue'))]
            self._wait_key({"ENTER", "ESC"})
            return False
        self.lines = [(t('dl_getting'), INK)]
        self.footer = [("0", t('dl_esc'))]
        th = threading.Thread(target=job.run, daemon=True)
        th.start()
        while th.is_alive():
            if any(ev.type == pygame.KEYDOWN and ev.key in (pygame.K_0, pygame.K_KP0) for ev in self._frame()):
                job.cancel = True
            self.progress = job.done / max(1, job.total)
            if job.phase == "verify":
                self.status = t('dl_verify')
            else:
                eta = (job.total - job.done) / job.speed if job.speed > 0 else 0
                self.status = t('dl_progress', done=_fmt_size(job.done), total=_fmt_size(job.total),
                                speed=_fmt_size(job.speed), eta=_fmt_eta(eta)) if job.speed else _fmt_size(job.done)
        self.progress = None
        self.status = ""
        self.footer = [("Enter", t('dl_continue'))]
        if job.phase == "done":
            self.lines = [(t('dl_done'), INK)]
        elif job.phase == "cancelled":
            self.lines = [(t('dl_cancelled'), INK_DIM)]
        else:
            self.lines = [(t('dl_error'), RED), (job.error[:60], INK_FAINT)]
        self._wait_key({"ENTER", "ESC", " "})
        return job.phase == "done"


def offer(term):
    """추가 데이터 안내부터 완료까지. 받은 모드를 돌려주고, 나중에·중단·실패면 None."""
    view = DownloadView(term)
    view.open()
    try:
        mode = view._choose()
        if mode and view._download(mode):
            return mode
        return None
    finally:
        view.close()
