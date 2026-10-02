"""이벤트 화면과 같은 틀의 공용 메뉴 화면 (타이틀, 설정, 언어, 난이도, 종료 확인 …).

두 가지 모양:
  card=True   그림을 화면 전체에 깔고 가운데에 제목·설명·선택지 (타이틀처럼)
  card=False  왼쪽 장면 그림 + 오른쪽 이야기 칸에 제목·설명·선택지
선택: 방향키/W·S + Enter, 숫자키, 마우스 (발밑 안내도 버튼). ESC = 뒤로 가기 (back 키가 있는 메뉴만).
값이 바뀌는 메뉴(설정)는 같은 화면을 두고 ask()만 다시 불러 글자만 바꾼다 (그림이 깜박이지 않게).
그림 화면을 못 여는 환경이면 get_terminal()이 None이라 쓰지 않는다 (Main.py가 터미널 메뉴로 대체).
"""
import sound
from event_view import EventView, JUNKYARD
from gui import get_terminal
from i18n import t


class MenuScreen:
    def __init__(self, scene="junkyard", card=True, location=JUNKYARD, player=None):
        self.view = EventView(get_terminal(), player, None, location, scene=scene)
        self.view.card = card
        self._opened = False

    def ask(self, title, items, tag="", lines=None, back=None, hero=False, start=0, footer=None, adjust=()):
        """items: [(키, 글)]. 고른 키를 돌려준다. back: 뒤로 가기 항목의 키 (발밑 안내에 표시).
        adjust: ←→로 값을 조절하는 줄의 키들. 그 줄에서 ←/→를 누르면 "<키" / ">키"를 돌려준다."""
        v = self.view
        v.log = []
        v.add("title", tag=tag, title=title, hero=hero)
        if lines:
            v.add("prose", lines=list(lines))
        menu = v.add("choices", items=list(items), start=start)
        default = [("↑↓", t('ui_select'))] + ([("←→", t('ui_adjust'))] if adjust else []) + [("Enter", t('ui_confirm'))] \
            + ([(back, t('ui_back'))] if back else [])
        v.footer = footer if footer is not None else default
        if not self._opened:
            v.open()
            self._opened = True
        key = v.choose(menu, len(items), extra=("ESC",) if back else (), adjust=adjust)
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
    """항법 일지 (이벤트 화면 틀). ↑↓·휠 한 줄, PgUp/PgDn 한 쪽, Esc·Enter·0·클릭(뒤로)으로 닫는다. 최신 기록부터."""
    import pygame
    from event_view import AMBER, INK, INK_DIM, INK_FAINT

    class DiaryView(EventView):
        def _draw_column(self, c, W, H):
            x, width, y = self._col_x, W - self._col_x - 36, 40
            c.blit(self.f_mono.render(f"{t('diary_header').strip()}  ·  {len(entries)}", True, AMBER), (x, y))
            y += 40
            lines = []
            for e in entries:
                lines += [(ln, i == 0) for i, ln in enumerate(self._wrap(self.f_story, e, width))]
            per = (H - 140 - y) // (self.LH_S - 2)
            self.max_off = max(0, len(lines) - per)
            self.off = max(0, min(self.off, self.max_off))
            start = max(0, len(lines) - per - self.off)
            for ln, first in lines[start:start + per]:
                c.blit(self.f_story.render(ln, True, INK if first else INK_DIM), (x, y))
                y += self.LH_S - 2
            if not entries:
                c.blit(self.f_story.render(t('diary_empty').strip(), True, INK_FAINT), (x, y))

    entries = list(player.diary)
    v = DiaryView(get_terminal(), player, None, JUNKYARD, scene="bunker_inside")
    v.off, v.max_off = 0, 0
    v.footer = [("↑↓", t('ui_select')), ("PgUp/PgDn", t('diary_page')), ("Esc", t('ui_back'), "ENTER")]
    v.open()
    try:
        while True:
            for ev in v._events():
                if ev.type == pygame.MOUSEWHEEL:   # 휠 위 = 예전 기록 쪽
                    v.off = max(0, min(v.max_off, v.off + ev.y * 3))
                    continue
                if ev.type == pygame.MOUSEMOTION:
                    v._foot_hover = v.foot_at(ev.pos)
                    continue
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and v.foot_at(ev.pos) == "ENTER":
                    sound.sfx("ui_back")
                    return
                if ev.type != pygame.KEYDOWN:
                    continue
                if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_0, pygame.K_j):
                    return
                step = {pygame.K_UP: 1, pygame.K_w: 1, pygame.K_DOWN: -1, pygame.K_s: -1,
                        pygame.K_PAGEUP: 10, pygame.K_PAGEDOWN: -10}.get(ev.key, 0)
                v.off = max(0, min(v.max_off, v.off + step))
    finally:
        v.close()


def show_codex():
    """옵션의 결말 기록: 본 결말과 각성만 이름이 보인다 (endings.codex_lines). 줄이 많아 그림 옆 이야기 칸에 적는다."""
    import endings
    scr = MenuScreen(scene="bunker_inside", card=False)
    try:
        scr.message(t('opt_endings'), endings.codex_lines(), tag=t('tag_record'))
    finally:
        scr.close()


def show_text_view(title, text, scene="forge"):
    """긴 글을 위에서부터 읽는 화면 (크레딧·라이선스 전문, 그림 없이 글만). ↑↓·휠 한 줄, PgUp/PgDn 한 쪽, Home/End, Esc·Enter·0·클릭(뒤로)으로 닫는다."""
    import pygame
    from event_view import AMBER, BG, INK, INK_DIM, INK_FAINT

    class TextView(EventView):
        def render(self, canvas):   # 그림 없이 글만: 읽을 거리라 장면 그림·장소 표시는 두지 않는다
            W, H = canvas.get_size()
            canvas.fill(BG)
            self._col_x = (W - min(W - 120, 960)) // 2   # 발밑 안내도 글 칸 왼쪽에 맞춘다
            self._draw_column(canvas, W, H)
            self._draw_footer(canvas, W, H)

        def _draw_column(self, c, W, H):
            width = min(W - 120, 960)
            x, y = (W - width) // 2, 40
            c.blit(self.f_mono.render(title, True, AMBER), (x, y))
            y += 40
            if self._wrapped is None or self._wrapped[0] != width:   # 수백 줄이라 폭이 바뀔 때만 다시 자른다
                lines = []
                for para in text.split("\n"):
                    lines += self._wrap(self.f_story, para.strip(), width) if para.strip() else [""]
                self._wrapped = (width, lines)
            lines = self._wrapped[1]
            self.per = max(1, (H - 140 - y) // (self.LH_S - 2))
            self.max_off = max(0, len(lines) - self.per)
            self.off = max(0, min(self.off, self.max_off))
            for ln in lines[self.off:self.off + self.per]:
                c.blit(self.f_story.render(ln, True, INK_DIM if ln.startswith("─") else INK), (x, y))
                y += self.LH_S - 2
            if self.max_off:
                pos = f"{self.off + min(self.per, len(lines))}/{len(lines)}"
                c.blit(self.f_mono.render(pos, True, INK_FAINT), (x, H - 132))

    v = TextView(get_terminal(), None, None, JUNKYARD, scene=scene)
    v.card = False
    v.off, v.max_off, v.per, v._wrapped = 0, 0, 20, None
    v.footer = [("↑↓", t('ui_select')), ("PgUp/PgDn", t('diary_page')), ("Esc", t('ui_back'), "ENTER")]
    v.open()
    try:
        while True:
            for ev in v._events():
                if ev.type == pygame.MOUSEWHEEL:
                    v.off = max(0, min(v.max_off, v.off - ev.y * 3))
                    continue
                if ev.type == pygame.MOUSEMOTION:
                    v._foot_hover = v.foot_at(ev.pos)
                    continue
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and v.foot_at(ev.pos) == "ENTER":
                    sound.sfx("ui_back")
                    return
                if ev.type != pygame.KEYDOWN:
                    continue
                if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_0, pygame.K_KP0):
                    return
                step = {pygame.K_UP: -1, pygame.K_w: -1, pygame.K_DOWN: 1, pygame.K_s: 1,
                        pygame.K_PAGEUP: -v.per, pygame.K_PAGEDOWN: v.per, pygame.K_SPACE: v.per,
                        pygame.K_HOME: -10 ** 6, pygame.K_END: 10 ** 6}.get(ev.key, 0)
                v.off = max(0, min(v.max_off, v.off + step))
    finally:
        v.close()


def story_page(scene, title, lines, tag="", location=JUNKYARD, player=None, footer_label=None):
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


ARCHIVE_PAGE = 8   # 보관소 목록 한 쪽에 몇 개


def _archive_read(scene, title, lines, tag):
    """보관소 글 한 편: 그 장면 그림 옆에 글이 타자 치듯 떠오른다 (아무 키나 누르면 다 보인다).
    글이 길면 ↑↓·휠 한 줄, PgUp/PgDn 한 쪽으로 넘긴다. Esc·Enter·0·클릭(뒤로)으로 닫는다."""
    import pygame
    from event_view import AMBER, INK, INK_DIM, TYPE_CPS

    class ReadView(EventView):
        def _draw_column(self, c, W, H):
            x, width, y = self._col_x, W - self._col_x - 36, 40
            c.blit(self.f_mono.render(tag, True, AMBER), (x, y))
            y += 26
            for ln in self._wrap(self.f_title, title, width):
                c.blit(self.f_title.render(ln, True, INK), (x, y))
                y += 40
            y += 14
            rows, left = [], self.shown
            for para in lines:   # 기록은 한 줄 = 종이의 한 줄. 빈 줄만 반 줄 띄운다
                if not para.strip():
                    rows.append(None)
                    continue
                for ln in self._wrap(self.f_story, para, width):
                    rows.append(ln[:max(0, left)])
                    left -= len(ln)
            while rows and rows[-1] is None:
                rows.pop()
            per = (H - 140 - y) // (self.LH_S - 2)
            self.max_off = max(0, len(rows) - per)
            if self.shown < total:   # 떠오르는 중에는 지금 쓰는 줄이 보이게 따라 내려간다
                last = max((i for i, r in enumerate(rows) if r), default=0)
                self.off = max(0, last - per + 1)
            self.off = max(0, min(self.off, self.max_off))
            for r in rows[self.off:self.off + per]:
                if r is None:
                    y += (self.LH_S - 2) // 2
                    continue
                c.blit(self.f_story.render(r, True, INK), (x, y))
                y += self.LH_S - 2
            if self.max_off:
                c.blit(self.f_mono.render(f"{self.off + 1}-{min(len(rows), self.off + per)} / {len(rows)}",
                                          True, INK_DIM), (x, H - 120))

    total = sum(len(p) for p in lines)
    v = ReadView(get_terminal(), None, None, JUNKYARD, scene=scene)
    v.off, v.max_off, v.shown = 0, 0, 0
    v.footer = [("↑↓", t('ui_select')), ("PgUp/PgDn", t('diary_page')), ("Esc", t('ui_back'), "ENTER")]
    v.open()
    start = pygame.time.get_ticks()
    try:
        while True:
            if v.shown < total:
                v.shown = int((pygame.time.get_ticks() - start) / 1000 * TYPE_CPS)
            for ev in v._events():
                if ev.type == pygame.MOUSEWHEEL:
                    v.off = max(0, min(v.max_off, v.off - ev.y * 3))
                    continue
                if ev.type == pygame.MOUSEMOTION:
                    v._foot_hover = v.foot_at(ev.pos)
                    continue
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if v.foot_at(ev.pos) == "ENTER":
                        sound.sfx("ui_back")
                        return
                    v.shown = total
                    continue
                if ev.type != pygame.KEYDOWN:
                    continue
                if v.shown < total:   # 처음 누르는 키는 글을 다 펼친다
                    v.shown = total
                    continue
                if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_0, pygame.K_SPACE):
                    return
                step = {pygame.K_UP: -1, pygame.K_w: -1, pygame.K_DOWN: 1, pygame.K_s: 1,
                        pygame.K_PAGEUP: -10, pygame.K_PAGEDOWN: 10}.get(ev.key, 0)
                v.off = max(0, min(v.max_off, v.off + step))
    finally:
        v.close()


def _archive_pick(scr, title, rows, tag, lines=None):
    """rows: [(키, 글, 열림)]. 쪽 넘김이 있는 목록. 고른 열린 키 또는 None(뒤로)."""
    page = 0
    pages = max(1, -(-len(rows) // ARCHIVE_PAGE))
    while True:
        part = rows[page * ARCHIVE_PAGE:(page + 1) * ARCHIVE_PAGE]
        items = [(str(i + 1), text if ok or text else "???") for i, (_, text, ok) in enumerate(part)]
        if page + 1 < pages:
            items.append((">", t('arc_next')))
        if page:
            items.append(("<", t('arc_prev')))
        items.append(("0", t('ui_back')))
        head = list(lines or []) + ([t('arc_page', n=page + 1, total=pages)] if pages > 1 else [])
        k = scr.ask(title, items, tag=tag, lines=head, back="0")
        if k in (None, "0"):
            return None
        if k == ">":
            page += 1
        elif k == "<":
            page -= 1
        elif k.isdigit() and part[int(k) - 1][2]:
            return part[int(k) - 1][0]


def show_archive():
    """옵션의 기록 보관소: 결말 기록, 적 이야기, 장면 이야기, 일기 조각. 보기만 한다 (archive.py)."""
    import archive
    import endings
    tag = t('tag_record')
    while True:
        c = archive.counts()
        scr = MenuScreen(scene="bunker_inside", card=False)
        try:
            items = [("1", t('arc_menu_endings', n=c["endings"][0], total=c["endings"][1])),
                     ("2", t('arc_menu_enemy', n=c["enemy"][0], total=c["enemy"][1])),
                     ("3", t('arc_menu_scene', n=c["scene"][0], total=c["scene"][1])),
                     ("4", t('arc_menu_fragment', n=c["fragment"][0], total=c["fragment"][1])),
                     ("0", t('ui_back'))]
            k = scr.ask(t('opt_archive'), items, tag=tag, lines=[t('arc_intro')], back="0")
            if k in (None, "0"):
                return
            if k == "1":
                scr.message(t('opt_endings'), endings.codex_lines(), tag=tag)
                continue
            if k == "2":
                rows = [(key, f"{name}  {n}/{tot}" if name else "", bool(name))
                        for key, name, n, tot in archive.enemy_list()]
                key = _archive_pick(scr, t('arc_menu_enemy_title'), rows, tag)
                if key:
                    scr.close()
                    _show_enemy(key)
                continue
            if k == "3":
                rows = [(s, title or "", bool(title)) for s, title in archive.scene_list()]
                while True:
                    s = _archive_pick(scr, t('arc_menu_scene_title'), rows, tag)
                    if not s:
                        break
                    e = archive.scene_entry(s)
                    scr.close()
                    _archive_read(s, e["title"], e["text"].split("\n"), tag)
                continue
            if k == "4":
                series = [(s, t(f'arc_series_{s}'), True) for s in archive.SERIES if archive.fragment_list(s)]
                s = _archive_pick(scr, t('arc_menu_fragment_title'), series, tag)
                if not s:
                    continue
                rows = [(fid, title or "", bool(title)) for fid, title in archive.fragment_list(s)]
                while True:
                    fid = _archive_pick(scr, t(f'arc_series_{s}'), rows, tag, lines=[t(f'arc_series_{s}_desc')])
                    if not fid:
                        break
                    e = archive.fragment_entry(fid)
                    scr.close()
                    _archive_read("bunker_inside", e["title"], e["text"].split("\n"), tag)
        finally:
            scr.close()


def _show_enemy(key):
    """적 하나: 단계를 골라 읽는다. 닫힌 단계는 여는 조건만 보인다."""
    import archive
    entry = archive.enemy_entry(key)
    scene = archive.ENEMY_SCENE[key]
    tag = t('tag_record')
    while True:
        rec = archive.load()["enemies"].get(key, {})
        opened = archive._enemy_open(rec, key)
        need = archive.stages(key)
        rows = [(i, t('arc_stage', n=i + 1) if i < opened else t('arc_locked_kills', n=need[i]), i < opened)
                for i in range(min(len(need), len(entry["stages"])))]
        scr = MenuScreen(scene=scene, card=False)
        try:
            i = _archive_pick(scr, entry["name"], rows, tag, lines=[t('arc_kills', n=rec.get("kills", 0))])
        finally:
            scr.close()
        if i is None:
            return
        _archive_read(scene, f"{entry['name']} · {t('arc_stage', n=i + 1)}", entry["stages"][i].split("\n"), tag)


def run_hidden_event(player, grid):
    """히든 이벤트: 쓰레기 더미에 기대 숨진 사람이 일지를 품에 안고 있다 (archive.hidden_ready).
    동적 서사가 켜져 있어도 정해진 글로만 보여 준다. 마지막 장을 기록하고 알림을 찍는다."""
    import archive
    e = archive.text()["hidden"]
    if get_terminal() is None:
        print(f"\n  [{e['title']}]")
        for para in e["text"].split("\n"):
            print(f"  {para}")
    else:   # 글이 길어 보관소와 같은 스크롤 읽기 화면으로
        _archive_read("junkyard", e["title"], e["text"].split("\n"), t('gm_tag_event'))
    sound.sfx("loot")
    print(archive.take_hidden())
