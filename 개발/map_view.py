"""맵 탐색 기본 화면 (이벤트 화면과 같은 틀).

왼쪽: 지금 칸의 장면 그림 (칸마다 정해진 장면 + 게임 속 시간·날씨) + 생체 지표 HUD + 지명.
오른쪽: 섹터 미니맵, 의체 상태, 최근 기록(터미널에 찍힌 탐색 결과), 아래에 조작 키.
Main.py의 _ui_mgr 자리에 들어간다: update(player, grid)로 상태를 받고, 입력은 원래대로 read_key()가 받는다.
인벤토리·일지·전투처럼 자기 화면이 있는 기능 앞에서는 deactivate()로 내려 원래 화면이 나오게 한다.
"""
import pygame

import constants
import scene_art
from event_view import AMBER, BG, BUNKER, EventView, INK, INK_DIM, INK_FAINT, JUNKYARD, RED, TEAL, GREEN, _lerp, place_label
from i18n import db_t, t

CELL, GAP = 26, 5


class MapView(EventView):
    def __init__(self, term, player, grid):
        super().__init__(term, player, grid, self._location(grid))
        self._key = None
        self.actions = []

    @staticmethod
    def _location(grid):
        return BUNKER if list(grid.player_pos) == list(grid.bunker_pos) else JUNKYARD

    # ── Main.py가 부르는 것 ────────────────────────────────────────────────
    def activate(self):
        if not self._active:
            self.open()

    def deactivate(self):
        if self._active:
            self.close()

    def update(self, player, grid):
        """칸·시간대·날씨가 바뀌면 그림을 다시 고른다 (같은 칸에 돌아오면 같은 장면)."""
        self.player, self.grid = player, grid
        self._weapon_text = self._compute_weapon_line()  # 장비 조회는 프레임마다 하지 않는다
        self.location = self._location(grid)
        turn = player.turn_count
        key = (tuple(grid.player_pos), scene_art.world_time(turn), scene_art.world_weather(turn))
        if key != self._key:
            self._key = key
            self._plate, self._art, self._layers = None, None, []
            self.motif = scene_art.tile_scene(self.location, key[0])
            self.stable_key = key  # 같은 칸·시간·날씨면 늘 같은 그림 (돌아오면 같은 장면, 캐시도 걸린다)

    def set_actions(self, actions):
        self.actions = actions
        self.footer = [(k, label) for k, label, enabled in actions if enabled]

    # ── 오른쪽 칸 ─────────────────────────────────────────────────────────
    def _draw_column(self, c, W, H):
        p, g = self.player, self.grid
        x = self._col_x
        width = W - x - 36
        y = 40
        turn = p.turn_count
        c.blit(self.f_mono.render(t('map_grid_header'), True, AMBER), (x, y))
        dist = abs(g.bunker_pos[0] - g.player_pos[0]) + abs(g.bunker_pos[1] - g.player_pos[1])
        head = t('map_arrived') if dist == 0 else t('map_dist', n=dist)
        c.blit(self.f_title.render(head, True, INK), (x, y + 22))
        sky = t('map_sky', time=t(f'time_{scene_art.world_time(turn)}'), weather=t(f'weather_{scene_art.world_weather(turn)}'), turn=turn)
        if p.searches_done < constants.BUNKER_MIN_SEARCHES:  # 방공호 문 조건이 남았으면 진행도를 보여 준다
            sky += "  ·  " + t('map_search_need', n=p.searches_done, need=constants.BUNKER_MIN_SEARCHES)
        c.blit(self.f_sans.render(sky, True, INK_DIM), (x, y + 66))
        y += 104

        mw = 0
        # 상태 (미니맵 오른쪽)
        sx = x
        sy = y - 2
        weapon = getattr(self, "_weapon_text", "")
        lines = [
            (weapon, INK),
            (f"VIT {p.vit}   INT {p.int_s}   DEX {p.dex}", INK),
            (t('map_stats', df=p.calc_def_base(), eva=p.calc_eva_rate() * 100, crt=p.calc_crt_rate() * 100), INK_DIM),
            (self._items_line(), INK_DIM),
        ]
        for text, col in lines:
            c.blit(self.f_sans.render(text, True, col), (sx, sy))
            sy += 28
        # 경보 게이지
        al = max(0, min(100, p.alert_level))
        col = RED if al >= 70 else (AMBER if al >= 40 else GREEN)
        label = t('alert_danger') if al >= 70 else (t('alert_caution') if al >= 40 else t('alert_safe'))
        c.blit(self.f_mono.render(t('map_alert'), True, INK_DIM), (sx, sy + 4))
        bx, bw = sx + 44, 220
        pygame.draw.line(c, (46, 44, 42), (bx, sy + 12), (bx + bw, sy + 12), 3)
        pygame.draw.line(c, col, (bx, sy + 12), (bx + int(bw * al / 100), sy + 12), 3)
        c.blit(self.f_mono.render(f"{al} · {label.strip('[]')}", True, col), (bx + bw + 10, sy + 4))
        if p.active_quest:
            q = p.active_quest
            left = max(0, q["deadline"] - p.turn_count)
            c.blit(self.f_sans.render(t('map_quest', title=db_t(q, 'title'), left=left), True, AMBER), (sx, sy + 30))

        # 최근 기록 (터미널에 찍힌 글)
        y = sy + (60 if p.active_quest else 40)
        mid = x + width // 2
        for i in (-18, 0, 18):
            pygame.draw.circle(c, INK_FAINT, (mid + i, y), 2)
        y += 20
        bottom = H - 70
        recent = self._recent_lines()
        max_lines = max(0, (bottom - y) // 30)
        for text in recent[-max_lines:]:
            for ln in self._wrap(self.f_serif, text, width)[:2]:
                if y > bottom:
                    break
                c.blit(self.f_serif.render(ln, True, INK), (x, y))
                y += 30

    def _draw_hud(self, c, H):
        """그림 위 왼쪽: 섹터 미니맵, 그 아래 생체 지표, 맨 아래 지명."""
        g = self.grid
        n = g.size
        x0, y0 = 22, 22
        c.blit(self.f_mono.render("SECTOR GRID", True, INK_DIM), (x0, y0))
        y0 += 22
        panel = pygame.Surface((n * (CELL + GAP) + 10, n * (CELL + GAP) + 10), pygame.SRCALPHA)
        panel.fill((*BG, 150))
        c.blit(panel, (x0 - 5, y0 - 5))
        for gy in range(n):
            for gx in range(n):
                rect = pygame.Rect(x0 + gx * (CELL + GAP), y0 + (n - 1 - gy) * (CELL + GAP), CELL, CELL)
                pos = (gx, gy)
                if [gx, gy] == list(g.player_pos):
                    pygame.draw.rect(c, _lerp(BG, AMBER, 0.35), rect)
                    pygame.draw.rect(c, AMBER, rect, 2)
                    pygame.draw.circle(c, AMBER, rect.center, 4)
                elif [gx, gy] == list(g.bunker_pos):
                    pygame.draw.rect(c, _lerp(BG, TEAL, 0.25), rect)
                    pygame.draw.rect(c, TEAL, rect, 1)
                    pygame.draw.rect(c, TEAL, rect.inflate(-12, -12))
                else:
                    seen = pos in g.visited_tiles
                    pygame.draw.rect(c, (34, 33, 31) if seen else (14, 14, 15), rect)
                    pygame.draw.rect(c, (70, 66, 60) if seen else (40, 39, 37), rect, 1)
        # 생체 지표 (미니맵 아래): 이벤트 화면의 HUD를 아래로 옮겨 그린다
        hud_top = y0 + n * (CELL + GAP) + 14
        c.set_clip(pygame.Rect(0, hud_top, 340, 90))
        c.blit(self._hud_surface(), (0, hud_top - 22))
        c.set_clip(None)
        c.blit(self.f_place.render(place_label(self.location), True, INK), (22, H - 118))
        c.blit(self.f_mono.render(t('place_turn', sub=t(self._sc['sub']), turn=self.player.turn_count), True, INK_DIM), (24, H - 78))

    def _hud_surface(self):
        """EventView의 생체 지표(숫자 굴림·피해 번쩍임 포함)를 투명 판에 그린다."""
        s = pygame.Surface((340, 200), pygame.SRCALPHA)
        EventView._draw_hud(self, s, 10000)
        return s

    def _compute_weapon_line(self):
        from core import get_equipment_data
        p = self.player
        try:
            name = db_t(get_equipment_data(p.equipment['main_weapon']), 'name')
            return t('map_weapon', name=name, pw=p.get_attack_power(), tier=p.get_highest_tier())
        except Exception:  # noqa: BLE001 - 표시용
            return ""

    def _items_line(self):
        p = self.player

        def count(kind):
            return sum(v for k, v in p.consumables.items() if constants.CONSUMABLES_DB.get(k, {}).get("type") == kind)
        return t('map_items', hp=count('hp'), food=count('food'), water=count('water'), mat=p.materials)

    def _recent_lines(self):
        """터미널 버퍼의 최근 글 (빈 줄·테두리 줄 제외). 게임이 화면을 지워도 앞 기록은 이어서 보인다.
        타자 효과로 마지막 줄이 한 글자씩 늘어나는 동안은 같은 줄로 본다 (예전에는 늘어나는 조각마다 기록에 쌓였다)."""
        buf = self._term._buf
        key = (id(buf), len(buf), len(buf[-1]) if buf else 0)
        if key == getattr(self, "_buf_key", None):
            return self._recent_cache
        self._buf_key = key
        cur = []
        for line in buf:
            text = "".join(seg[0] for seg in line).strip()
            if not text or set(text) <= set("═─━-=╔╗╚╝║|╭╮╰╯ "):
                continue
            cur.append(text)
        last = getattr(self, "_cur_lines", [])
        same = len(cur) >= len(last) and cur[:max(0, len(last) - 1)] == last[:-1] and             (not last or cur[len(last) - 1].startswith(last[-1]))
        if last and not same:  # 버퍼가 지워졌다: 지난 글을 기록으로 넘긴다
            self._history = (getattr(self, "_history", []) + last)[-12:]
        self._cur_lines = cur
        self._recent_cache = (getattr(self, "_history", []) + cur)[-8:]
        return self._recent_cache
