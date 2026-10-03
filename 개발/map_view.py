"""맵 탐색 기본 화면 (이벤트 화면과 같은 틀).

왼쪽: 지금 칸의 장면 그림 (칸마다 정해진 장면 + 게임 속 시간·날씨) + 생체 지표 HUD + 지명.
오른쪽: 섹터 미니맵, 의체 상태, 최근 기록(터미널에 찍힌 탐색 결과), 아래에 조작 키.
Main.py의 _ui_mgr 자리에 들어간다: update(player, grid)로 상태를 받고, 입력은 원래대로 read_key()가 받는다.
인벤토리·일지·전투처럼 자기 화면이 있는 기능 앞에서는 deactivate()로 내려 원래 화면이 나오게 한다.
"""
import math
import random
import time

import pygame

import constants
import forge
import scene_art
from event_view import AMBER, BG, BUNKER, PLATE_W, EventView, INK, INK_DIM, INK_FAINT, JUNKYARD, RED, TEAL, GREEN, VIOLET, _lerp, place_label
from i18n import db_t, t

ISO_W, ISO_H = 32, 16   # 2.5D 미니맵 마름모 한 칸 (가로, 세로)
MOVE_MS = 450           # 칸 이동 연출 길이
PAN = 0.08              # 좌우 이동 때 이전 장면이 밀려나는 폭 (그림 너비 대비)


class MapView(EventView):
    def __init__(self, term, player, grid):
        super().__init__(term, player, grid, self._location(grid))
        self._key = None
        self.actions = []
        self._move = None          # 이동 연출: {"old": 이전 장면 그림, "d": (dx, dy), "from": 이전 칸, "t0": 시작}
        self._pos = list(grid.player_pos)

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
        pos = list(grid.player_pos)
        if pos != self._pos:  # 칸을 옮겼다: 지금 보이는 장면을 떠 두고 새 장면으로 넘어가는 연출
            d = (pos[0] - self._pos[0], pos[1] - self._pos[1])
            old = None
            if self._active and self._plate is not None:  # 이전 칸 장면 그림만 (미니맵·지명은 빼고)
                H = self._term._canvas.get_height()
                old = pygame.Surface((PLATE_W, H))
                old.fill(BG)
                EventView._draw_plate(self, old, H)
            self._move = {"old": old, "d": d, "from": self._pos, "t0": None}  # 새 장면을 처음 그린 뒤부터 잰다
            self._pos = pos
        if key != self._key:
            self._key = key
            self._plate, self._art, self._layers = None, None, []
            self.motif = scene_art.tile_scene(self.location, key[0])
            self.stable_key = key  # 같은 칸·시간·날씨면 늘 같은 그림 (돌아오면 같은 장면, 캐시도 걸린다)

    def _move_progress(self):
        """이동 연출 진행도 0..1 (연출 중이 아니면 None). 부드럽게 가속했다 멈춘다."""
        if not self._move:
            return None
        if self._move["t0"] is None:
            return 0.0
        k = (time.perf_counter() - self._move["t0"]) * 1000 / MOVE_MS
        if k >= 1:
            self._move = None
            return None
        return k * k * (3 - 2 * k)

    def play_move(self):
        """Main.py: 칸을 옮긴 직후 연출이 끝날 때까지 그린다 (입력은 그동안 받지 않는다)."""
        if not self._active:
            self._move = None
            return
        end = time.perf_counter() + MOVE_MS * 4 / 1000   # 그림 불러오기가 아무리 느려도 이 안에 끝낸다
        while self._move and time.perf_counter() < end:
            self._term.sleep_render(0.03)
        self._move = None

    def _draw_plate(self, c, H):
        """장면 그림. 이동 중이면 새 장면을 깔고 그 위에서 이전 장면이 옅어지며 떠나간다 (좌우는 시선이 흘러가고, 앞뒤는 다가가거나 물러난다)."""
        e = self._move_progress()
        old = self._move["old"] if self._move else None
        if e is None or old is None:
            if self._move and self._move["t0"] is None:
                self._move["t0"] = time.perf_counter()   # 장면이 없던 이동 (미니맵 표식만 미끄러진다)
            return super()._draw_plate(c, H)
        dx, dy = self._move["d"]
        bob = int(math.sin(e * math.pi * 2) * 2)          # 걸음걸이처럼 살짝 출렁인다
        # 새 장면: 좌우 이동이면 그림 속 시선이 이동 방향 끝에서 가운데로 흘러온다 (깊이 층마다 다르게)
        self._pan = dx * (1 - e)
        new = pygame.Surface((PLATE_W, H))
        new.fill(BG)
        super()._draw_plate(new, H)
        self._pan = 0.0
        if self._move["t0"] is None:  # 새 장면 그림이 준비됐다: 여기서부터 연출 시작
            self._move["t0"] = time.perf_counter()
        prev_clip = c.get_clip()
        c.set_clip(pygame.Rect(0, 0, PLATE_W, H))
        if dy < 0:   # 남(S): 물러나듯 새 장면이 조금 크게 보였다가 제자리로
            ng = 1.1 - 0.1 * e
            nw, nh = int(PLATE_W * ng), int(H * ng)
            c.blit(pygame.transform.smoothscale(new, (nw, nh)), ((PLATE_W - nw) // 2, (H - nh) // 2 + bob))
        else:
            c.blit(new, (0, bob))
        # 이전 장면은 위에서 옅어지며 떠나간다: 좌우는 반대쪽으로 조금 밀리고, 북(W)은 걸어 들어가듯 커진다
        if dx:
            o, pos = old, (-int(e * PLATE_W * PAN) * dx, bob)
        elif dy > 0:
            g_ = 1 + 0.2 * e
            ow, oh = int(PLATE_W * g_), int(H * g_)
            o = pygame.transform.smoothscale(old, (ow, oh))
            pos = ((PLATE_W - ow) // 2, (H - oh) // 2 + bob)
        else:
            o, pos = old, (0, bob)
        o = o.copy() if o is old else o
        o.set_alpha(int(255 * (1 - e)))
        c.blit(o, pos)
        dim = pygame.Surface((PLATE_W, H), pygame.SRCALPHA)  # 가운데쯤 살짝 어두워진다 (시선이 옮겨 가는 느낌)
        dim.fill((0, 0, 0, int(70 * math.sin(e * math.pi))))
        c.blit(dim, (0, 0))
        c.set_clip(prev_clip)

    def set_actions(self, actions):
        """[(보이는 키, 설명, 쓸 수 있음[, 누르면 보낼 키])]. 발밑 버튼은 마우스로도 누른다."""
        self.actions = actions
        self.footer = [(a[0], a[1], a[3] if len(a) > 3 else (a[0] if len(a[0]) == 1 else None)) for a in actions if a[2]]

    # ── 입력: 방향키·마우스 ───────────────────────────────────────────────
    # 이동 WASD(←↑↓→), 탐색 F(Space), 인벤토리 I(Tab), 강화소 E, 일지 J, 저장 F5, 나가기 Esc, 퀵슬롯 1~0.
    # Q는 전투의 공격 키라 맵에선 아무 일도 하지 않는다 (예전엔 종료). C도 예전 저장 키라 막는다.
    # 미니맵에서 옆 칸을 누르면 그쪽으로 한 칸 간다. 결과는 Main.py가 받던 글자 키로 돌려준다.
    KEYMAP = {pygame.K_UP: "W", pygame.K_DOWN: "S", pygame.K_LEFT: "A", pygame.K_RIGHT: "D",
              pygame.K_SPACE: "F", pygame.K_TAB: "I", pygame.K_e: "U", pygame.K_F5: "C", pygame.K_ESCAPE: "Q",
              pygame.K_q: "?", pygame.K_c: "?", pygame.K_u: "U"}
    _iso = None          # 미니맵 좌표계 (가운데 x, 시작 칸 y, 반칸 폭, 반칸 높이) — 그릴 때 채운다
    _tile_hover = None   # 마우스가 올라간 옆 칸 (이동 방향 키)

    def _tile_at(self, pos):
        """창 좌표 → 미니맵 칸 → 지금 칸의 옆이면 그쪽 방향 키 (W/A/S/D)."""
        if not self._iso:
            return None
        cx, cy = self.to_canvas(pos)
        mx, base, hw, hh = self._iso
        u, v = (cx - mx) / hw, (base - cy - 3) / hh   # 윗면은 바닥보다 3px 위
        gx, gy = round((u + v) / 2), round((v - u) / 2)
        px, py = self.grid.player_pos
        return {(0, 1): "W", (0, -1): "S", (-1, 0): "A", (1, 0): "D"}.get((gx - px, gy - py))

    def on_input(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key in self.KEYMAP:
            return self.KEYMAP[ev.key]
        if ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            d = self._tile_at(ev.pos)
            self._tile_hover = d
            if d and ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                return d
        return super().on_input(ev)

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
        c.blit(self.f_sans.render(sky, True, INK_DIM), (x, y + 66))
        fs = g.forge.get("stage", 0)
        if fs >= 2 or g.forge.get("met"):  # 강화소 (완공) / 발칸 게이츠 (만났지만 의뢰 전) 거리
            fd = g.forge_dist()
            key = ('map_at_forge' if fs >= 2 else 'map_at_vulkan') if fd == 0 else ('map_forge_dist' if fs >= 2 else 'map_vulkan_dist')
            fsurf = self.f_sans.render(t(key, n=fd), True, AMBER)
            c.blit(fsurf, (x + width - fsurf.get_width(), y + 66))
        elif forge.hinted(g):  # 아직 못 만났지만 소리는 들었다: 방향과 거리만
            fsurf = self.f_sans.render(t('map_hint_dist', dir=forge.direction(g), n=g.forge_dist()), True, _lerp(BG, AMBER, 0.75))
            c.blit(fsurf, (x + width - fsurf.get_width(), y + 66))
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
        dg = g.danger_at()
        if list(g.player_pos) != list(g.bunker_pos):   # 칸 위험도와 뒤진 흔적
            dep = g.depletion()
            lines.append((t(f'map_danger_{dg}') + (t('map_depleted', n=dep) if dep else ""), (GREEN, AMBER, RED)[dg]))
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
        qy = sy + 30
        if p.active_quest:
            q = p.active_quest
            left = max(0, q["deadline"] - p.turn_count)
            c.blit(self.f_sans.render(t('map_quest', title=db_t(q, 'title'), left=left), True, AMBER), (sx, qy))
            qy += 26
        if fs == 1:  # 발칸 게이츠 의뢰 진행
            c.blit(self.f_sans.render(forge.progress_text(p, g), True, AMBER), (sx, qy))
            qy += 26

        # 최근 기록 (터미널에 찍힌 글)
        y = qy + 10
        mid = x + width // 2
        for i in (-18, 0, 18):
            pygame.draw.circle(c, INK_FAINT, (mid + i, y), 2)
        y += 20
        qy = H - 64 - self.QB_H           # 퀵슬롯 줄 (발밑 안내 바로 위)
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

    def _draw_hud(self, c, H):
        """그림 위 왼쪽: 섹터 미니맵, 그 아래 생체 지표, 맨 아래 지명."""
        g = self.grid
        n = g.size
        x0, y0 = 22, 22
        c.blit(self.f_mono.render(t('map_scan_header'), True, INK_DIM), (x0, y0))
        y0 += 22
        grid_h = self._draw_iso_grid(c, x0, y0)
        # 생체 지표 (미니맵 아래): 이벤트 화면의 HUD를 아래로 옮겨 그린다
        hud_top = y0 + grid_h + 10
        c.set_clip(pygame.Rect(0, hud_top, 340, 90))
        c.blit(self._hud_surface(), (0, hud_top - 22))
        c.set_clip(None)
        c.blit(self.f_place.render(place_label(self.location), True, INK), (22, H - 118))
        c.blit(self.f_mono.render(t('place_turn', sub=t(self._sc['sub']), turn=self.player.turn_count), True, INK_DIM), (24, H - 78))

    def _draw_iso_grid(self, c, x0, y0):
        """2.5D 섹터 미니맵 — N-404의 손상된 시각 센서가 비춘 쓰레기 바다.
        안 가 본 칸은 신호 없는 잡음, 가 본 칸은 드론 사체·고철 더미, 맨 위는 반쯤 묻힌 지하 방공호,
        그 너머로 네오 아크 상층의 불빛. 시작 칸이 맨 아래이고 W(북)는 왼쪽 위, D(동)는 오른쪽 위.
        그린 높이를 돌려준다."""
        g, p = self.grid, self.player
        n = g.size
        hw, hh = ISO_W // 2, ISO_H // 2
        top_pad = 34                                   # 네오 아크 불빛·방공호 안테나 자리
        width, height = n * ISO_W + 10, (2 * n - 1) * hh + 2 * hh + top_pad + 8
        now = pygame.time.get_ticks()
        pulse = (now % 1400) / 1400
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((*BG, 215))
        # 네오 아크 상층: 지평선 너머 빌딩 윤곽과 창 불빛
        sky = random.Random(404)
        for _ in range(16):
            bw, bh = sky.randint(4, 9), sky.randint(8, 26)
            bx = sky.randint(0, width - bw)
            pygame.draw.rect(panel, (28, 30, 38, 110), (bx, top_pad + 10 - bh, bw, bh))
            if sky.random() < 0.7:
                lit = VIOLET if sky.random() < 0.4 else TEAL
                blink = 90 if (now // 900 + bx) % 5 else 40
                pygame.draw.rect(panel, (*lit, blink), (bx + 1, top_pad + 12 - bh, 2, 1))
        glow = pygame.Surface((width, 14), pygame.SRCALPHA)
        for yy in range(14):
            pygame.draw.line(glow, (*VIOLET, int(26 * (1 - yy / 14))), (0, yy), (width, yy))
        panel.blit(glow, (0, top_pad - 2))
        c.blit(panel, (x0 - 5, y0 - 5))
        ox, oy = x0 - 5, y0 - 5
        cx = ox + width // 2
        base = y0 + top_pad + (2 * n - 2) * hh + hh       # 시작 칸(0,0) 윗면 가운데
        known_forge = g.forge_known()
        alarm = p.alert_level >= 70
        noise = random.Random(now // 110)               # 신호 없는 칸의 잡음 (조금씩 바뀐다)

        def prism(sx, sy, h, top, side, edge):
            t_ = (sx, sy - h - hh); r_ = (sx + hw, sy - h); b_ = (sx, sy - h + hh); l_ = (sx - hw, sy - h)
            pygame.draw.polygon(c, _lerp(side, BG, 0.3), [l_, b_, (sx, sy + hh), (sx - hw, sy)])
            pygame.draw.polygon(c, side, [b_, r_, (sx + hw, sy), (sx, sy + hh)])
            pygame.draw.polygon(c, top, [t_, r_, b_, l_])
            if edge:
                pygame.draw.lines(c, edge, True, [t_, r_, b_, l_], 1)

        def box(bx, by, w, d, h, col):
            """작은 상자 (고철 조각·드론 사체). (bx, by)는 바닥 가운데."""
            q = [(bx, by - h - d), (bx + w, by - h), (bx, by - h + d), (bx - w, by - h)]
            pygame.draw.polygon(c, _lerp(col, BG, 0.45), [q[3], q[2], (bx, by + d), (bx - w, by)])
            pygame.draw.polygon(c, _lerp(col, BG, 0.25), [q[2], q[1], (bx + w, by), (bx, by + d)])
            pygame.draw.polygon(c, col, q)

        # 먼 칸(x+y가 큰 칸)부터 그려야 앞 칸이 뒤 칸을 가린다
        for gx, gy in sorted(((a, b) for a in range(n) for b in range(n)), key=lambda q: -(q[0] + q[1])):
            sx = cx + (gx - gy) * hw
            sy = base - (gx + gy) * hh
            pos = [gx, gy]
            rng = random.Random(gx * 97 + gy * 13 + 7)
            if pos == list(g.bunker_pos):
                # 쓰레기 바다 속 반쯤 묻힌 지하 방공호: 콘크리트 둔덕, 녹슨 무쇠 문 틈의 불빛, 안테나
                prism(sx, sy, 7, (66, 66, 63), (44, 44, 42), _lerp(BG, TEAL, 0.75))
                pygame.draw.ellipse(c, (84, 82, 77), (sx - 11, sy - 17, 22, 11))
                pygame.draw.ellipse(c, (104, 101, 95), (sx - 11, sy - 17, 22, 11), 1)
                door = [(sx - 5, sy - 11), (sx + 5, sy - 11), (sx + 4, sy - 5), (sx - 4, sy - 5)]
                pygame.draw.polygon(c, (110, 72, 46), door)
                lamp = pygame.Surface((20, 10), pygame.SRCALPHA)
                pygame.draw.ellipse(lamp, (*TEAL, int(60 + 40 * pulse)), (0, 0, 20, 10))
                c.blit(lamp, (sx - 10, sy - 10))
                pygame.draw.line(c, TEAL, (sx - 3, sy - 8), (sx + 3, sy - 8), 1)
                pygame.draw.line(c, (130, 126, 118), (sx + 7, sy - 14), (sx + 7, sy - 32), 1)
                pygame.draw.line(c, (130, 126, 118), (sx + 4, sy - 28), (sx + 10, sy - 28), 1)
                blink = (now // 500) % 2 == 0
                pygame.draw.circle(c, RED if blink else _lerp(BG, RED, 0.4), (sx + 7, sy - 33), 2)
            elif pos == list(g.forge_pos) and known_forge:
                built = forge.built(g)
                prism(sx, sy, 4, (54, 44, 36), (36, 30, 25), _lerp(BG, AMBER, 0.7 if built else 0.35))
                # 벽돌 용광로와 굴뚝
                box(sx - 3, sy - 4, 6, 3, 8, (104, 70, 48) if built else (70, 58, 50))
                pygame.draw.rect(c, (60, 52, 46), (sx + 3, sy - 22, 3, 10))
                mouth = AMBER if built else (40, 34, 30)
                pygame.draw.rect(c, mouth, (sx - 5, sy - 10, 4, 3))
                if built:  # 불꽃과 연기
                    fire = pygame.Surface((14, 10), pygame.SRCALPHA)
                    pygame.draw.ellipse(fire, (*AMBER, int(70 + 50 * pulse)), (0, 0, 14, 10))
                    c.blit(fire, (sx - 10, sy - 14))
                    for k in range(3):
                        ph = ((now / 1800) + k / 3) % 1
                        pygame.draw.circle(c, (90, 86, 80), (sx + 4 + int(ph * 4), sy - 24 - int(ph * 12)), 1 + int(ph * 2))
            elif (gx, gy) in g.visited_tiles:
                # 스캔한 칸: 드론 사체와 메인보드 파편이 쌓인 고철 더미
                prism(sx, sy, 3, (48, 45, 41), (30, 28, 26), (96, 89, 79))
                for _ in range(rng.randint(2, 3)):
                    ux, uy = rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45)
                    bx = sx + int((ux - uy) * hw * 0.9)
                    by = sy - 3 + int((ux + uy) * hh * 0.9)
                    col = rng.choice([(96, 64, 42), (78, 74, 68), (64, 60, 56), (110, 76, 50)])
                    box(bx, by, rng.randint(2, 4), rng.randint(1, 2), rng.randint(2, 7), col)
            else:
                # 스캔 안 된 칸: 신호 없음 (잡음)
                prism(sx, sy, 1, (24, 24, 25), (14, 14, 15), (64, 62, 58) if not alarm else _lerp((64, 62, 58), RED, 0.4))
                for _ in range(1):
                    ux, uy = noise.uniform(-0.8, 0.8), noise.uniform(-0.8, 0.8)
                    if abs(ux) + abs(uy) < 0.9:
                        nx, ny = sx + int(ux * hw * 0.8), sy - 1 + int(uy * hh * 0.8)
                        c.set_at((nx, ny), (46, 45, 42) if not alarm else (96, 52, 46))
            if pos != list(g.bunker_pos):   # 칸 위험도: 윗면 앞 모서리에 짧은 눈금 (보통 1개 호박색, 높음 2개 붉은색)
                dg = g.danger_at(pos)
                if dg:
                    dcol = _lerp(BG, AMBER if dg == 1 else RED, 0.85)
                    for k in range(dg):
                        ex = sx - 3 + k * 5
                        pygame.draw.line(c, dcol, (ex, sy + hh - 4), (ex + 3, sy + hh - 4), 2)
            if pos == list(g.forge_pos) and forge.hinted(g):
                # 쇳물 냄새가 나는 곳: 흐린 호박색 파동 두 겹 (정확한 모습은 가 봐야 안다)
                for k in (0.0, 0.5):
                    ph = (pulse + k) % 1.0
                    rw = int(6 + ph * (ISO_W - 2))
                    wave_ = pygame.Surface((ISO_W + 6, ISO_H + 6), pygame.SRCALPHA)
                    pygame.draw.ellipse(wave_, (*AMBER, int(150 * (1 - ph))),
                                        (wave_.get_width() // 2 - rw // 2, wave_.get_height() // 2 - rw // 4, rw, rw // 2), 1)
                    c.blit(wave_, (sx - wave_.get_width() // 2, sy - 2 - wave_.get_height() // 2))
                pygame.draw.circle(c, _lerp(BG, AMBER, 0.7), (sx, sy - 2), 2)
        self._iso = (cx, base, hw, hh)
        if self._tile_hover and self._move_progress() is None:   # 마우스가 올라간 옆 칸: 갈 수 있는 곳 테두리
            ddx, ddy = {"W": (0, 1), "S": (0, -1), "A": (-1, 0), "D": (1, 0)}[self._tile_hover]
            hx, hy = g.player_pos[0] + ddx, g.player_pos[1] + ddy
            if 0 <= hx < n and 0 <= hy < n:
                sx, sy = cx + (hx - hy) * hw, base - (hx + hy) * hh
                pygame.draw.polygon(c, AMBER, [(sx, sy - hh - 3), (sx + hw, sy - 3), (sx, sy + hh - 3), (sx - hw, sy - 3)], 1)
        # N-404: 스캔 핑 고리 + 낙인 표식 (이동 중이면 이전 칸에서 미끄러져 온다)
        px, py = g.player_pos
        e = self._move_progress()
        if e is not None:
            fx0, fy0 = self._move["from"]
            px, py = fx0 + (px - fx0) * e, fy0 + (py - fy0) * e
        sx = cx + int((px - py) * hw)
        sy = base - int((px + py) * hh)
        ty = sy - 4
        ring = pygame.Surface((ISO_W + 10, ISO_H + 10), pygame.SRCALPHA)
        rw = int(8 + pulse * (ISO_W + 2))
        pygame.draw.ellipse(ring, (*AMBER, int(210 * (1 - pulse))),
                            (ring.get_width() // 2 - rw // 2, ring.get_height() // 2 - rw // 4, rw, rw // 2), 1)
        c.blit(ring, (sx - ring.get_width() // 2, ty - ring.get_height() // 2))
        pygame.draw.polygon(c, AMBER, [(sx - 4, ty - 12), (sx + 4, ty - 12), (sx, ty - 5)])
        pygame.draw.line(c, _lerp(BG, AMBER, 0.6), (sx, ty - 5), (sx, ty), 1)

        # 시각 센서 느낌: 주사선 + 천천히 내려가는 스캔 띠 + 비
        fx = pygame.Surface((width, height), pygame.SRCALPHA)
        for yy in range(0, height, 4):
            pygame.draw.line(fx, (0, 0, 0, 14), (0, yy), (width, yy))
        band = int((now / 30) % (height + 20)) - 10
        for k in range(10):
            pygame.draw.line(fx, (*AMBER, int(7 * (1 - k / 10))), (0, band - k), (width, band - k))
        rain = random.Random(now // 70)
        for _ in range(4):
            rx, ry = rain.randint(0, width), rain.randint(0, top_pad + 10)   # 비는 하늘(네오 아크 쪽)에만
            pygame.draw.line(fx, (150, 160, 170, 30), (rx, ry), (rx - 2, ry + 6))
        c.blit(fx, (ox, oy))
        # 손상된 센서 테두리: 모서리 꺾쇠
        col = _lerp(BG, RED, 0.7) if alarm else _lerp(BG, AMBER, 0.55)
        for (ax, ay, dx, dy) in ((ox, oy, 1, 1), (ox + width - 1, oy, -1, 1), (ox, oy + height - 1, 1, -1), (ox + width - 1, oy + height - 1, -1, -1)):
            pygame.draw.line(c, col, (ax, ay), (ax + 9 * dx, ay), 1)
            pygame.draw.line(c, col, (ax, ay), (ax, ay + 9 * dy), 1)
        return height

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

    no_wait = True   # 탐색 화면에서는 '아무 키나 누르면 진행'을 기다리지 않는다 (결과는 오른쪽 기록에 남는다: ui.wait_for_keypress)

    def mark_log(self):
        """Main.py: 키를 받은 순간. 오른쪽 기록에는 이 뒤에 찍힌 글(이번 행동의 결과)만 보인다. 지난 턴 글은 지운다."""
        buf = self._term._buf
        self._log_mark = [buf, max(0, len(buf) - 1)]   # 지금 쓰던 마지막 줄부터 (print가 그 줄에 이어 쓴다)
        self._log_carry = []   # 이번 행동 중에 버퍼가 바뀌었을 때(다른 화면을 열었다 닫음) 앞 버퍼에 찍힌 글
        self._history, self._cur_lines, self._buf_key = [], [], None

    @staticmethod
    def _log_text(lines):
        out = []
        for line in lines:
            text = "".join(seg[0] for seg in line).strip().strip("║│").strip()   # 상자 테두리 글자는 떼고 글만
            if text and not set(text) <= set("═─━-=╔╗╚╝║|╭╮╰╯ "):
                out.append(text)
        return out

    def _recent_lines(self):
        """터미널 버퍼의 최근 글 (빈 줄·테두리 줄 제외). mark_log 뒤로는 그 뒤에 찍힌 글만.
        타자 효과로 마지막 줄이 한 글자씩 늘어나는 동안은 같은 줄로 본다 (예전에는 늘어나는 조각마다 기록에 쌓였다)."""
        buf = self._term._buf
        mark = getattr(self, "_log_mark", None)
        if mark is not None and mark[0] is not buf:
            # 다른 화면이 열렸다 닫히며 버퍼가 새로 생겼다: 앞 버퍼에 찍힌 이번 행동의 글을 넘겨 담고 새 버퍼 처음부터
            self._log_carry += self._log_text(mark[0][mark[1]:])
            mark[0], mark[1] = buf, 0
        key = (id(buf), len(buf), len(buf[-1]) if buf else 0, mark and mark[1], len(getattr(self, "_log_carry", ())))
        if key == getattr(self, "_buf_key", None):
            return self._recent_cache
        self._buf_key = key
        if mark is not None:   # 이번 행동의 결과만
            self._recent_cache = (self._log_carry + self._log_text(buf[mark[1]:]))[-8:]
            return self._recent_cache
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
