"""이벤트 화면과 같은 틀의 공용 메뉴 화면 (타이틀, 설정, 언어, 난이도, 종료 확인 …).

두 가지 모양:
  card=True   그림을 화면 전체에 깔고 가운데에 제목·설명·선택지 (타이틀처럼)
  card=False  왼쪽 장면 그림 + 오른쪽 이야기 칸에 제목·설명·선택지
선택: 방향키/W·S + Enter, 숫자키, 마우스. ESC는 쓰지 않는다 (뒤로 가기는 back 키, 보통 0).
값이 바뀌는 메뉴(설정)는 같은 화면을 두고 ask()만 다시 불러 글자만 바꾼다 (그림이 깜박이지 않게).
그림 화면을 못 여는 환경이면 get_terminal()이 None이라 쓰지 않는다 (Main.py가 터미널 메뉴로 대체).
"""
from event_view import EventView
from gui import get_terminal
from i18n import t


class MenuScreen:
    def __init__(self, scene="junkyard", card=True, location="폐기물 처리장", player=None):
        self.view = EventView(get_terminal(), player, None, location, scene=scene)
        self.view.card = card
        self._opened = False

    def ask(self, title, items, tag="", lines=None, back=None, hero=False, start=0, footer=None):
        """items: [(키, 글)]. 고른 키를 돌려준다. back: 뒤로 가기 항목의 키 (발밑 안내에 표시)."""
        v = self.view
        v.log = []
        v.add("title", tag=tag, title=title, hero=hero)
        if lines:
            v.add("prose", lines=list(lines))
        menu = v.add("choices", items=list(items), start=start)
        default = [("↑↓", t('ui_select')), ("Enter", t('ui_confirm'))] + ([(back, t('ui_back'))] if back else [])
        v.footer = footer if footer is not None else default
        if not self._opened:
            v.open()
            self._opened = True
        key = v.choose(menu, len(items), extra=("ESC",) if back else ())
        return back if key == "ESC" else key

    def message(self, title, lines, tag="", hold_ms=None):
        """알림 한 장 (키를 누르거나 hold_ms가 지나면 넘어간다)."""
        v = self.view
        v.log = []
        v.add("title", tag=tag, title=title)
        v.add("prose", lines=list(lines))
        v.footer = [("Enter", t('ui_continue'))]
        if not self._opened:
            v.open()
            self._opened = True
        if hold_ms:
            v.hold(hold_ms)
        else:
            v.wait_key({"ENTER", "ESC", " "})

    def close(self):
        if self._opened:
            self.view.close()
            self._opened = False


def show_diary_view(player):
    """항법 일지 (이벤트 화면 틀). ↑↓ 한 줄, PgUp/PgDn 한 쪽, Enter·0으로 닫는다. 최신 기록부터."""
    import pygame
    from event_view import AMBER, INK, INK_DIM, INK_FAINT

    class DiaryView(EventView):
        def _draw_column(self, c, W, H):
            x, width, y = self._col_x, W - self._col_x - 36, 40
            c.blit(self.f_mono.render(f"{t('diary_header').strip()}  ·  {len(entries)}", True, AMBER), (x, y))
            y += 40
            lines = []
            for e in entries:
                lines += [(ln, i == 0) for i, ln in enumerate(self._wrap(self.f_serif, e, width))]
            per = (H - 140 - y) // 30
            self.max_off = max(0, len(lines) - per)
            self.off = max(0, min(self.off, self.max_off))
            start = max(0, len(lines) - per - self.off)
            for ln, first in lines[start:start + per]:
                c.blit(self.f_serif.render(ln, True, INK if first else INK_DIM), (x, y))
                y += 30
            if not entries:
                c.blit(self.f_serif.render(t('diary_empty').strip(), True, INK_FAINT), (x, y))

    entries = list(player.diary)
    v = DiaryView(get_terminal(), player, None, "폐기물 처리장", scene="bunker_inside")
    v.off, v.max_off = 0, 0
    v.footer = [("↑↓", t('ui_select')), ("PgUp/PgDn", "쪽"), ("Enter", t('ui_back'))]
    v.open()
    try:
        while True:
            for ev in v._events():
                if ev.type != pygame.KEYDOWN:
                    continue
                if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_0, pygame.K_j):
                    return
                step = {pygame.K_UP: 1, pygame.K_w: 1, pygame.K_DOWN: -1, pygame.K_s: -1,
                        pygame.K_PAGEUP: 10, pygame.K_PAGEDOWN: -10}.get(ev.key, 0)
                v.off = max(0, min(v.max_off, v.off + step))
    finally:
        v.close()


def story_page(scene, title, lines, tag="", location="폐기물 처리장", player=None, footer_label=None):
    """그림 + 이야기 칸 한 페이지: 제목, 문단을 하나씩 타자로 보여 주고 Enter를 기다린다 (프롤로그·엔딩 등)."""
    v = EventView(get_terminal(), player, None, location, scene=scene)
    v.add("title", tag=tag, title=title)
    v.footer = [("Enter", footer_label or t('ui_continue'))]
    v.open()
    try:
        for para in [x for x in lines if str(x).strip()]:
            entry = v.add("narr", lines=[" ".join(str(para).split())])
            v.type_out(entry)
        v.wait_key({"ENTER", "ESC", " "})
    finally:
        v.close()
