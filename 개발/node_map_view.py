"""지점 지도 탐색 화면 (시험 중, 설계: docs/기획/지점지도_설계.md 3단계).

map_view.MapView와 같은 틀(왼쪽 장면 그림, 오른쪽 글 칸)에서 지도 부분만 바꾼다.
- 왼쪽 위 센서: 내 둘레만 비추는 2.5D 지도. 북쪽이 위. 안개 속 지점은 안 보이고, 높은 랜드마크와 방벽은 "?"로 보인다.
- 오른쪽 칸: 이어진 길 목록. 길마다 W·A·S·D 하나 (NodeMap.road_keys). 키나 마우스로 고른다.
- M: 지금까지 본 지도 전체 (big_map).
"""
import math
import random

import pygame

import archive
import forge
import node_map
import scene_art
from event_view import AMBER, BG, INK, INK_DIM, INK_FAINT, RED, TEAL, GREEN, VIOLET, _lerp
from i18n import db_t, t
from map_view import MapView

TILE_W, TILE_H = 22, 11     # 지점 하나의 마름모 (센서)
SENSOR_W, SENSOR_H = 300, 210
SENSOR_SPAN = 15            # 센서가 비추는 반경 (지도 좌표)


def node_name(grid, q):
    """지점 이름: 랜드마크는 기록 보관소 제목, 나머지는 종류."""
    q = tuple(q)
    if list(q) == list(grid.bunker_pos):
        return t('node_kind_bunker')
    nd = grid.nodes[q]
    if nd["kind"] == "landmark":
        ent = archive.scene_entry(nd["scene"])
        if ent and ent.get("title"):
            return ent["title"]
    return t(f"node_kind_{nd['kind']}")


class NodeMapView(MapView):
    big_map = False
    _road_hover = None
    _road_rows = ()          # [(Rect, 키)] 오른쪽 길 목록 (마우스)

    def update(self, player, grid):
        moved = list(grid.player_pos) != self._pos
        super().update(player, grid)
        if moved:   # 자리를 옮겼다: 마우스로 짚던 길과 큰 지도는 내려놓는다
            self._road_hover = None
            self.big_map = False
        if self._move and self._move["t0"] is None:
            # 장면 넘김 연출은 칸 한 개 기준이라, 길의 방향(가로·세로 중 큰 쪽)만 남긴다
            dx, dy = self._move["d"]
            self._move["d"] = ((dx > 0) - (dx < 0), 0) if abs(dx) >= abs(dy) else (0, (dy > 0) - (dy < 0))
            self._move["from"] = tuple(self._move["from"])

    # ── 입력 ─────────────────────────────────────────────────────────────
    def on_input(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_m:
            return "M"   # 큰 지도 열고 닫기는 Main.py가 한다 (발밑 버튼과 같은 길)
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and self.big_map:
            self.big_map = False   # 큰 지도만 닫는다 (뜻 없는 Esc라 gui가 버린다: 종료 메뉴로 가지 않는다)
            return None
        if ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN) and not self.big_map:
            cx, cy = self.to_canvas(ev.pos)
            hit = next((k for r, k in self._road_rows if r.collidepoint(cx, cy)), None)
            keys = self.grid.road_keys()
            self._road_hover = keys.get(hit) if hit else None
            if hit and ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                return hit
            # 길 목록 밖: 발밑 버튼·퀵슬롯은 EventView가 받는다 (아래로 넘긴다)
        if ev.type == pygame.KEYDOWN and ev.key in self.KEYMAP:
            return self.KEYMAP[ev.key]
        return super(MapView, self).on_input(ev)

    # ── 그리기 ───────────────────────────────────────────────────────────
    def _draw_hud(self, c, H):
        if self.big_map:
            return   # 큰 지도가 그림 위를 덮는다 (_draw_column 끝에서 그린다)
        x0, y0 = 22, 22
        c.blit(self.f_mono.render(t('nmap_header'), True, INK_DIM), (x0, y0))
        y0 += 22
        self._draw_sensor(c, pygame.Rect(x0 - 5, y0 - 5, SENSOR_W, SENSOR_H), SENSOR_SPAN, labels=False)
        hud_top = y0 + SENSOR_H + 4
        c.set_clip(pygame.Rect(0, hud_top, 340, 90))
        c.blit(self._hud_surface(), (0, hud_top - 22))
        c.set_clip(None)
        nm = node_name(self.grid, self.grid.player_pos)
        c.blit(self.f_place.render(nm, True, INK), (22, H - 118))
        c.blit(self.f_mono.render(t('place_turn', sub=t(self._sc['sub']), turn=self.player.turn_count), True, INK_DIM), (24, H - 78))

    def _draw_column(self, c, W, H):
        p, g = self.player, self.grid
        x = self._col_x
        width = W - x - 36
        y = 40
        turn = p.turn_count
        c.blit(self.f_mono.render(t('map_grid_header'), True, AMBER), (x, y))
        if tuple(g.bunker_pos) in g.revealed:
            head = t('nmap_bunker_turns', n=g.path_dist(g.player_pos, g.bunker_pos))
        elif g.bunker_hint >= 0:   # 신호는 지금 자리 기준 (멀면 동서남북 넷으로만, 가까워지면 여덟 방위)
            head = t('nmap_bunker_signal', dir=g.bunker_direction(fine=g.bunker_hint > 0))
        else:
            head = t('nmap_bunker_none')
        c.blit(self.f_title.render(head, True, INK), (x, y + 22))
        sky = t('map_sky', time=t(f'time_{scene_art.world_time(turn)}'), weather=t(f'weather_{scene_art.world_weather(turn)}'), turn=turn)
        c.blit(self.f_sans.render(sky, True, INK_DIM), (x, y + 66))
        seen = self.f_sans.render(t('nmap_seen', n=len(g.visited_tiles), m=len(g.revealed)), True, INK_FAINT)
        c.blit(seen, (x + width - seen.get_width(), y + 66))
        y += 104

        # 상태 (칸 지도 화면과 같은 줄들: map_view.MapView._draw_column)
        weapon = getattr(self, "_weapon_text", "")
        dg = g.danger_at()
        lines = [
            (weapon, INK),
            (f"VIT {p.vit}   INT {p.int_s}   DEX {p.dex}", INK),
            (t('map_stats', df=p.calc_def_base(), eva=p.calc_eva_rate() * 100, crt=p.calc_crt_rate() * 100), INK_DIM),
            (self._items_line(), INK_DIM),
        ]
        if list(g.player_pos) != list(g.bunker_pos):
            dep = g.depletion()
            lines.append((t(f'map_danger_{dg}') + (t('map_depleted', n=dep) if dep else ""), (GREEN, AMBER, RED)[dg]))
        for text, col in lines:
            c.blit(self.f_sans.render(text, True, col), (x, y))
            y += 28
        # 경보 게이지
        al = max(0, min(100, p.alert_level))
        col = RED if al >= 70 else (AMBER if al >= 40 else GREEN)
        label = t('alert_danger') if al >= 70 else (t('alert_caution') if al >= 40 else t('alert_safe'))
        c.blit(self.f_mono.render(t('map_alert'), True, INK_DIM), (x, y + 4))
        bx, bw = x + 44, 220
        pygame.draw.line(c, (46, 44, 42), (bx, y + 12), (bx + bw, y + 12), 3)
        pygame.draw.line(c, col, (bx, y + 12), (bx + int(bw * al / 100), y + 12), 3)
        c.blit(self.f_mono.render(f"{al} · {label.strip('[]')}", True, col), (bx + bw + 10, y + 4))
        y += 30
        # 돌발 퀘스트 · 발칸 의뢰 · 강화소까지 (길 기준 턴)
        if p.active_quest:
            q = p.active_quest
            c.blit(self.f_sans.render(t('map_quest', title=db_t(q, 'title'), left=max(0, q["deadline"] - p.turn_count)), True, AMBER), (x, y))
            y += 26
        fs = g.forge.get("stage", 0)
        if fs == 1:
            c.blit(self.f_sans.render(forge.progress_text(p, g), True, AMBER), (x, y))
            y += 26
        if fs >= 2 or g.forge.get("met"):
            fd = g.forge_dist()
            key = ('map_at_forge' if fs >= 2 else 'map_at_vulkan') if fd == 0 else ('nmap_forge_dist' if fs >= 2 else 'nmap_vulkan_dist')
            c.blit(self.f_sans.render(t(key, n=fd), True, AMBER), (x, y))
            y += 26
        elif forge.hinted(g):
            c.blit(self.f_sans.render(t('nmap_hint_dist', dir=forge.direction(g), n=g.forge_dist()), True, _lerp(BG, AMBER, 0.75)), (x, y))
            y += 26

        # 이어진 길
        y += 14
        c.blit(self.f_mono.render(t('nmap_roads'), True, AMBER), (x, y))
        y += 26
        rows = []
        keys = g.road_keys()
        arrow = {"W": "↑", "A": "←", "S": "↓", "D": "→"}
        for k in "WASD":
            if k not in keys:
                continue
            q = keys[k]
            n = g.edge_len(g.player_pos, q)
            hover = self._road_hover is not None and tuple(self._road_hover) == tuple(q)
            rect = pygame.Rect(x - 8, y - 4, width + 8, 50)
            if hover:
                pygame.draw.rect(c, _lerp(BG, AMBER, 0.12), rect)
                pygame.draw.line(c, AMBER, (rect.x, rect.y), (rect.x, rect.bottom - 1), 2)
            kb = pygame.Rect(x, y + 2, 26, 26)
            pygame.draw.rect(c, AMBER if hover else _lerp(BG, AMBER, 0.55), kb, 1)
            ks = self.f_mono_b.render(k, True, AMBER)
            c.blit(ks, (kb.centerx - ks.get_width() // 2, kb.centery - ks.get_height() // 2))
            c.blit(self.f_mono.render(arrow[k], True, INK_DIM), (x + 34, y + 6))
            name = t('nmap_road', name=node_name(g, q), n=n)
            c.blit(self.f_serif.render(name, True, INK), (x + 58, y + 2))
            if list(q) == list(g.bunker_pos):
                sub, scol = t('node_kind_bunker'), TEAL
            else:
                qd = g.danger_at(q)
                sub = t(f'nmap_danger_{qd}') + ("" if tuple(q) in g.visited_tiles else "  ·  " + t('nmap_new'))
                scol = _lerp(BG, (GREEN, AMBER, RED)[qd], 0.8)
            c.blit(self.f_mono.render(sub, True, scol), (x + 58, y + 27))
            rows.append((rect, k))
            y += 56
        self._road_rows = rows

        # 최근 기록
        y += 6
        mid = x + width // 2
        for i in (-18, 0, 18):
            pygame.draw.circle(c, INK_FAINT, (mid + i, y), 2)
        y += 20
        qy = H - 64 - self.QB_H
        self._draw_quickbar(c, x, qy, width)
        bottom = qy - 40
        recent = self._recent_lines()
        max_lines = max(0, (bottom - y) // 30)
        for text in recent[-max_lines:]:
            for ln in self._wrap(self.f_serif, text, width)[:2]:
                if y > bottom:
                    break
                c.blit(self.f_serif.render(ln, True, INK), (x, y))
                y += 30

        if self.big_map:
            self._draw_big_map(c, W, H)

    def _draw_big_map(self, c, W, H):
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((*BG, 250))
        c.blit(veil, (0, 0))
        c.blit(self.f_mono.render(t('nmap_big_header'), True, AMBER), (32, 26))
        hint = self.f_mono.render(t('nmap_big_hint'), True, INK_DIM)
        c.blit(hint, (W - 32 - hint.get_width(), 26))
        xs = [q[0] for q in self.grid.nodes]
        ys = [q[1] for q in self.grid.nodes]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span = max(max(xs) - min(xs), (max(ys) - min(ys)) / 0.62) / 2 + 3
        self._draw_sensor(c, pygame.Rect(24, 56, W - 48, H - 140), span, labels=True, center=(cx, cy))

    # ── 센서 지도 (작은 것·큰 것 같은 코드) ────────────────────────────────
    def _draw_sensor(self, c, rect, span, labels, center=None):
        """rect 안에 center(기본: 내 자리) 둘레 span만큼을 비춘다. 북쪽이 위, 남북은 0.62로 눌러 비스듬히 내려다본 느낌."""
        g, p = self.grid, self.player
        now = pygame.time.get_ticks()
        pulse = (now % 1400) / 1400
        cxw, cyw = center if center else g.player_pos
        e0 = self._move_progress()
        if center is None and e0 is not None and self._move:   # 센서도 길을 따라 함께 움직인다
            fx0, fy0 = self._move["from"]
            cxw, cyw = fx0 + (cxw - fx0) * e0, fy0 + (cyw - fy0) * e0
        k = rect.w / 2 / span
        sq = 0.62

        def scr(q):
            return (rect.centerx + (q[0] - cxw) * k, rect.centery - (q[1] - cyw) * k * sq)

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((*BG, 215))
        c.blit(panel, rect.topleft)
        c.set_clip(rect)
        hw, hh = (TILE_W, TILE_H) if not labels else (TILE_W + 4, TILE_H + 2)
        hw, hh = hw // 2, hh // 2

        # 방벽 (북쪽 끝): 지도 맨 위 지점보다 조금 위. 네오 아크 상층의 윤곽과 불빛
        wall_y = scr((0, max(q[1] for q in g.nodes) + 3))[1]
        if wall_y > rect.y - 40:
            sky = random.Random(404)
            for _ in range(int(rect.w / 14)):
                bw, bh = sky.randint(4, 10), sky.randint(10, 34)
                bx = rect.x + sky.randint(0, rect.w - bw)
                pygame.draw.rect(c, (28, 30, 38), (bx, wall_y - bh, bw, bh))
                if sky.random() < 0.7:
                    lit = VIOLET if sky.random() < 0.4 else TEAL
                    pygame.draw.rect(c, _lerp(BG, lit, 0.6), (bx + 1, wall_y - bh + 3, 2, 1))
            pygame.draw.line(c, (70, 66, 72), (rect.x, wall_y), (rect.right, wall_y), 3)
            glow = pygame.Surface((rect.w, 16), pygame.SRCALPHA)
            for yy in range(16):
                pygame.draw.line(glow, (*VIOLET, int(30 * (1 - yy / 16))), (0, yy), (rect.w, yy))
            c.blit(glow, (rect.x, wall_y + 2))
            if labels:
                c.blit(self.f_mono.render(t('nmap_wall'), True, _lerp(BG, VIOLET, 0.8)), (rect.x + 8, wall_y - 52))

        # 안개: 아무것도 모르는 땅의 잡음
        noise = random.Random(now // 110)
        for _ in range(int(rect.w * rect.h / 900)):
            c.set_at((rect.x + noise.randrange(rect.w), rect.y + noise.randrange(rect.h)), (34, 33, 31))

        # 아는 길: 들른 지점에서 나가는 길. 턴마다 점 하나, 지금 자리에서 나가는 길은 밝게
        here = tuple(g.player_pos)
        keys = {tuple(q): kk for kk, q in g.road_keys().items()}
        drawn = set()
        for a in g.visited_tiles:
            for b, n in g.edges[tuple(a)].items():
                e = tuple(sorted((tuple(a), b)))
                if e in drawn:
                    continue
                drawn.add(e)
                live = here in e
                hover = live and self._road_hover is not None and tuple(self._road_hover) in e
                col = AMBER if hover else (_lerp(BG, AMBER, 0.62) if live else (70, 66, 60))
                pa, pb = scr(e[0]), scr(e[1])
                pygame.draw.line(c, col, pa, pb, 2 if live else 1)
                for i in range(1, n):
                    m = (pa[0] + (pb[0] - pa[0]) * i / n, pa[1] + (pb[1] - pa[1]) * i / n)
                    pygame.draw.circle(c, col, (int(m[0]), int(m[1])), 2)

        def prism(sx, sy, h, top, side, edge):
            t_ = (sx, sy - h - hh); r_ = (sx + hw, sy - h); b_ = (sx, sy - h + hh); l_ = (sx - hw, sy - h)
            pygame.draw.polygon(c, _lerp(side, BG, 0.3), [l_, b_, (sx, sy + hh), (sx - hw, sy)])
            pygame.draw.polygon(c, side, [b_, r_, (sx + hw, sy), (sx, sy + hh)])
            pygame.draw.polygon(c, top, [t_, r_, b_, l_])
            if edge:
                pygame.draw.lines(c, edge, True, [t_, r_, b_, l_], 1)

        def box(bx, by, w, d, h, col):
            q = [(bx, by - h - d), (bx + w, by - h), (bx, by - h + d), (bx - w, by - h)]
            pygame.draw.polygon(c, _lerp(col, BG, 0.45), [q[3], q[2], (bx, by + d), (bx - w, by)])
            pygame.draw.polygon(c, _lerp(col, BG, 0.25), [q[2], q[1], (bx + w, by), (bx, by + d)])
            pygame.draw.polygon(c, col, q)

        # 멀리 보이는 곳 (안개 너머): 높은 랜드마크와 방벽 아래 경계 지대 — 흐린 "?"
        inner = rect.inflate(-24, -24)
        for q in g.sighted():
            sx, sy = scr(q)
            if not inner.collidepoint(sx, sy):   # 센서 밖: 그쪽 가장자리에 붙여 방향만
                ddx, ddy = sx - rect.centerx, sy - rect.centery
                f = min((inner.w / 2) / abs(ddx) if ddx else 1e9, (inner.h / 2) / abs(ddy) if ddy else 1e9)
                sx, sy = rect.centerx + ddx * f, rect.centery + ddy * f
            col = _lerp(BG, VIOLET if g.nodes[q]["kind"] == "border" else AMBER, 0.35 + 0.15 * pulse)
            s = self.f_mono_b.render("?", True, col)
            c.blit(s, (sx - s.get_width() // 2, sy - s.get_height() // 2 - 4))

        # 지점: 남쪽(앞)부터 그려야 뒤를 가린다
        names = []   # 큰 지도 지명 (지점을 다 그린 뒤 위에 얹는다)
        for q in sorted(g.revealed, key=lambda q: -q[1]):
            sx, sy = scr(q)
            if not rect.inflate(40, 40).collidepoint(sx, sy):
                continue
            nd = g.nodes[q]
            rng = random.Random(q[0] * 97 + q[1] * 13 + 7)
            visited = q in g.visited_tiles
            if list(q) == list(g.bunker_pos):
                prism(sx, sy, 6, (66, 66, 63), (44, 44, 42), _lerp(BG, TEAL, 0.75))
                pygame.draw.line(c, (130, 126, 118), (sx + 5, sy - 10), (sx + 5, sy - 26), 1)
                blink = (now // 500) % 2 == 0
                pygame.draw.circle(c, RED if blink else _lerp(BG, RED, 0.4), (sx + 5, sy - 27), 2)
            elif list(q) == list(g.forge_pos) and g.forge_known():
                built = forge.built(g)
                prism(sx, sy, 4, (54, 44, 36), (36, 30, 25), _lerp(BG, AMBER, 0.7 if built else 0.35))
                box(sx - 2, sy - 4, 5, 2, 7, (104, 70, 48) if built else (70, 58, 50))
                pygame.draw.rect(c, (60, 52, 46), (sx + 3, sy - 20, 3, 9))
            elif visited:
                lm = nd["kind"] in ("landmark", "border")
                top = (58, 54, 48) if lm else (48, 45, 41)
                prism(sx, sy, 4 if lm else 3, top, (30, 28, 26), (120, 108, 90) if lm else (96, 89, 79))
                for _ in range(rng.randint(2, 3)):
                    ux, uy = rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)
                    bx = sx + int((ux - uy) * hw * 0.9)
                    by = sy - 3 + int((ux + uy) * hh * 0.9)
                    col = rng.choice([(96, 64, 42), (78, 74, 68), (64, 60, 56), (110, 76, 50)])
                    box(bx, by, rng.randint(2, 3), 1, rng.randint(2, 6 if not lm else 11), col)
            else:
                # 드러났지만 아직 안 가 본 곳: 윤곽만
                pygame.draw.lines(c, (90, 86, 78), True, [(sx, sy - hh), (sx + hw, sy), (sx, sy + hh), (sx - hw, sy)], 1)
            if list(q) != list(g.bunker_pos):
                dg = g.danger_at(q)
                if dg:
                    dcol = _lerp(BG, AMBER if dg == 1 else RED, 0.85)
                    for kk in range(dg):
                        ex = sx - 3 + kk * 5
                        pygame.draw.line(c, dcol, (ex, sy + hh + 2), (ex + 3, sy + hh + 2), 2)
            if q in keys and not labels:   # 지금 자리에서 갈 수 있는 곳: 키 글자
                kcol = AMBER if (self._road_hover is not None and tuple(self._road_hover) == q) else _lerp(BG, AMBER, 0.75)
                ks = self.f_mono.render(keys[q], True, kcol)
                c.blit(ks, (sx + hw + 2, sy - hh - 6))
            if labels and nd["kind"] in ("landmark", "border"):
                names.append((q, visited, sx, sy))
        taken = []
        for q, visited, sx, sy in names:   # 지명: 그림자 위에, 서로 겹치면 건너뛴다
            ls = self.f_mono.render(node_name(g, q), True, INK if visited else INK_DIM)
            lr = ls.get_rect(midtop=(sx, sy + hh + 6))
            if any(lr.colliderect(o) for o in taken):
                continue
            bg = pygame.Surface(lr.inflate(6, 2).size, pygame.SRCALPHA)
            bg.fill((*BG, 200))
            c.blit(bg, lr.inflate(6, 2).topleft)
            c.blit(ls, lr)
            taken.append(lr.inflate(10, 4))
        if forge.hinted(g):
            sx, sy = scr(g.forge_pos)
            for kk in (0.0, 0.5):
                ph = (pulse + kk) % 1.0
                rw = int(6 + ph * 24)
                w_ = pygame.Surface((40, 24), pygame.SRCALPHA)
                pygame.draw.ellipse(w_, (*AMBER, int(150 * (1 - ph))), (20 - rw // 2, 12 - rw // 4, rw, rw // 2), 1)
                c.blit(w_, (sx - 20, sy - 14))

        # 나: 핑 고리 + 낙인 표식 (이동 중이면 이전 지점에서 길을 따라 미끄러져 온다)
        e = self._move_progress()
        if e is not None and self._move:
            fx0, fy0 = self._move["from"]
            sx, sy = scr((fx0 + (here[0] - fx0) * e, fy0 + (here[1] - fy0) * e))
        else:
            sx, sy = scr(here)
        ty = sy - 4
        ring = pygame.Surface((TILE_W + 14, TILE_H + 14), pygame.SRCALPHA)
        rw = int(8 + pulse * (TILE_W + 4))
        pygame.draw.ellipse(ring, (*AMBER, int(210 * (1 - pulse))),
                            (ring.get_width() // 2 - rw // 2, ring.get_height() // 2 - rw // 4, rw, rw // 2), 1)
        c.blit(ring, (sx - ring.get_width() // 2, ty - ring.get_height() // 2))
        pygame.draw.polygon(c, AMBER, [(sx - 4, ty - 12), (sx + 4, ty - 12), (sx, ty - 5)])

        # 센서 느낌: 주사선 + 내려가는 스캔 띠
        fx = pygame.Surface(rect.size, pygame.SRCALPHA)
        for yy in range(0, rect.h, 4):
            pygame.draw.line(fx, (0, 0, 0, 14), (0, yy), (rect.w, yy))
        band = int((now / 30) % (rect.h + 20)) - 10
        for kk in range(10):
            pygame.draw.line(fx, (*AMBER, int(7 * (1 - kk / 10))), (0, band - kk), (rect.w, band - kk))
        c.blit(fx, rect.topleft)
        c.set_clip(None)
        col = _lerp(BG, AMBER, 0.55)
        for (ax, ay, dx, dy) in ((rect.x, rect.y, 1, 1), (rect.right - 1, rect.y, -1, 1),
                                 (rect.x, rect.bottom - 1, 1, -1), (rect.right - 1, rect.bottom - 1, -1, -1)):
            pygame.draw.line(c, col, (ax, ay), (ax + 9 * dx, ay), 1)
            pygame.draw.line(c, col, (ax, ay), (ax, ay + 9 * dy), 1)
