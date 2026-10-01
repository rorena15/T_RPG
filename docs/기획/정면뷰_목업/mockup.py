"""정면 뷰 목업 (docs/기획/정면뷰_목업). 게임 코드는 바꾸지 않고 그리기 도구만 빌린다. 개발/ 폴더에서 실행."""
import os, sys, random, math
sys.path.insert(0, os.getcwd())
import pygame, i18n; i18n.set_lang("ko")
from gui import PygameTerminal, set_terminal
term = PygameTerminal(); set_terminal(term); sys.stdout = term
import core; core.init_and_load_db()
from player import Player
from map import GameMap
from map_view import MapView
from event_view import BG, INK, INK_DIM, INK_FAINT, AMBER, RED, GREEN, TEAL, VIOLET, _lerp
OUT = sys.argv[1]
W, H = term._canvas_size
S = "../assets/scenes/"
p = Player(); g = GameMap(); g.player_pos = [2, 3]; g.visited_tiles |= {(0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (2, 3)}
p.hp = 1120; p.hunger = 72; p.thirst = 58; p.turn_count = 31
p.consumables.update({"MED_PER_50": 1, "FOOD_BOTH": 1})
p.quickslots = ["MED_FIX_100", "FOOD_ONLY", "WATER_ONLY", "MED_PER_50", "FOOD_BOTH", None, None, None, None, None]
m = MapView(term, p, g); m.update(p, g); m.activate(); term._dirty = True; term._render()
SEN = m.SENSOR

def art(name, focus=0.42):
    img = pygame.image.load(S + name).convert()
    s = W / img.get_width()
    img = pygame.transform.smoothscale(img, (W, int(img.get_height() * s)))
    y0 = int((img.get_height() - H) * focus)
    return img.subsurface((0, y0, W, H)).copy()

def grade(c, top=220, bottom=0.52, tint=None, border=None):
    sh = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(H):
        a = int(170 * max(0, 1 - y / top) ** 1.6 + 235 * max(0, (y - H * bottom) / (H * (1 - bottom))) ** 1.3)
        pygame.draw.line(sh, (6, 5, 4, min(245, a)), (0, y), (W, y))
    for y in range(0, H, 3):
        pygame.draw.line(sh, (0, 0, 0, 38), (0, y), (W, y))
    c.blit(sh, (0, 0))
    vg = pygame.Surface((W, H), pygame.SRCALPHA)
    for x in range(120):
        a = int(120 * (1 - x / 120) ** 2)
        pygame.draw.line(vg, (0, 0, 0, a), (x, 0), (x, H)); pygame.draw.line(vg, (0, 0, 0, a), (W - 1 - x, 0), (W - 1 - x, H))
    c.blit(vg, (0, 0))
    if tint:
        t_ = pygame.Surface((W, H), pygame.SRCALPHA); t_.fill(tint); c.blit(t_, (0, 0))
    rng = random.Random(7)
    for _ in range(900):
        c.fill(_lerp(BG, SEN, rng.uniform(0.05, 0.25)), (rng.randrange(W), rng.randrange(H), 1, 1))
    col = border or _lerp(BG, SEN, 0.6)
    if border:  # 경보: 가장자리 붉은 번짐
        e = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(0, 60, 2):
            pygame.draw.rect(e, (*border, int(70 * (1 - i / 60) ** 2)), (i, i, W - 2 * i, H - 2 * i), 2)
        c.blit(e, (0, 0))
    for (ax, ay, dx, dy) in ((14, 14, 1, 1), (W - 15, 14, -1, 1), (14, H - 15, 1, -1), (W - 15, H - 15, -1, -1)):
        pygame.draw.line(c, col, (ax, ay), (ax + 22 * dx, ay)); pygame.draw.line(c, col, (ax, ay), (ax, ay + 22 * dy))

def text(c, f, s, col, pos, anchor="tl"):
    g_ = f.render(s, True, col); x, y = pos
    if anchor == "tr": x -= g_.get_width()
    if anchor == "tc": x -= g_.get_width() // 2
    c.blit(g_, (x, y)); return g_

def panel(c, rect, a=170, edge=(70, 56, 40)):
    s = pygame.Surface(rect.size, pygame.SRCALPHA); s.fill((10, 8, 6, a)); c.blit(s, rect.topleft)
    if edge: pygame.draw.rect(c, edge, rect, 1)

def footer(c, items):
    x, y = 36, H - 40
    pygame.draw.line(c, (60, 50, 40), (30, H - 52), (W - 30, H - 52))
    for k, l in items:
        kk = text(c, m.f_mono_b, k, AMBER, (x, y)); x += kk.get_width() + 8
        ll = text(c, m.f_sans, l, INK_FAINT, (x, y)); x += ll.get_width() + 26

def log_box(c, rect, lines):
    panel(c, rect)
    for i, (s, col) in enumerate(lines):
        text(c, m.f_serif, s, col, (rect.x + 16, rect.y + 12 + i * 30))

def buttons(c, acts, y0, sel=0, cols=4):
    bw = (W - 60 - (cols - 1) * 8) // cols
    for i, (k, l, ic) in enumerate(acts):
        r = pygame.Rect(30 + (i % cols) * (bw + 8), y0 + (i // cols) * 50, bw, 42)
        on = i == sel
        panel(c, r, 190, None if on else (52, 44, 36))
        if on: m._sensor_frame(c, r, SEN, 3)
        text(c, m.f_mono_b, k, SEN if on else AMBER, (r.x + 12, r.y + 11))
        if ic:
            c.blit(m.crt_icon(ic, 24, SEN if on else m.SENSOR_DIM), (r.x + 34, r.y + 9))
        text(c, m.f_sans, l, INK if on else INK_DIM, (r.x + (66 if ic else 36), r.y + 11))

def reticle(c, cx, cy, w, h, col=RED):
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x0, y0 = cx + dx * w, cy + dy * h
        pygame.draw.line(c, col, (x0, y0), (x0 - dx * 22, y0)); pygame.draw.line(c, col, (x0, y0), (x0, y0 - dy * 22))

def enemy_bar(c, tag, name, frac, x=W // 2 + 40, bw=300, col=AMBER):
    text(c, m.f_mono, tag, RED, (x, 26), "tc")
    text(c, m.f_title, name, INK, (x, 46), "tc")
    bx = x - bw // 2
    pygame.draw.rect(c, (40, 30, 26), (bx, 92, bw, 10)); pygame.draw.rect(c, col, (bx, 92, int(bw * frac), 10))
    text(c, m.f_mono, f"{int(frac * 100)}%", INK_DIM, (bx + bw + 10, 88))

COMBAT_ACTS = [("Q", "공격", "act_attack"), ("E", "바리케이드", "act_barricade"), ("R", "패킷 우회", "act_jam"), ("F", "보조화기x2", "act_sub"),
               ("Z", "과부하", "act_skill"), ("X", "후퇴", "act_retreat"), ("I", "소모품", "act_item")]

def save(c, name):
    pygame.image.save(c, f"{OUT}_{name}.png")

def mini_status(c, y, alert=48):
    for i, (lab, v, col) in enumerate((("HP", p.hp / p.max_hp, GREEN if p.hp / p.max_hp > 0.5 else RED), ("허기", 0.72, AMBER), ("갈증", 0.58, TEAL))):
        x = 40 + i * 180
        text(c, m.f_mono, lab, INK_DIM, (x, y)); pygame.draw.rect(c, (40, 36, 32), (x + 40, y + 6, 120, 4)); pygame.draw.rect(c, col, (x + 40, y + 6, int(120 * v), 4))
    text(c, m.f_mono, f"경보 {alert}", AMBER if alert < 70 else RED, (W - 40, y), "tr")

def slim_actions(c, y, acts, sel):
    """한 줄 행동: 키 · 아이콘 · 이름 (글자 버튼, 테두리는 고른 것만)."""
    x = 40
    for i, (k, l, ic) in enumerate(acts):
        on = i == sel
        wdt = 34 + 30 + m.f_sans.size(l)[0] + 14
        r = pygame.Rect(x - 8, y - 6, wdt, 36)
        if on:
            panel(c, r, 150, None); m._sensor_frame(c, r, SEN, 5)
        text(c, m.f_mono_b, k, SEN if on else AMBER, (x, y + 2))
        c.blit(m.crt_icon(ic, 22, SEN if on else m.SENSOR_DIM), (x + 18, y))
        text(c, m.f_sans, l, INK if on else INK_DIM, (x + 46, y + 2))
        x += wdt + 6

# 1) 랜드마크 탐색 — 새벽 대성당, 랜드마크 발견 배너
def m1():
    c = pygame.Surface((W, H)); c.blit(art("lm_cathedral/lm_cathedral_dawn_smog_0.jpg", 0.35), (0, 0)); grade(c)
    m._draw_iso_grid(c, 30, 40); text(c, m.f_mono, "시각 센서 // 섹터 스캔", INK_DIM, (30, 20))
    c.blit(m._hud_surface(), (10, 200))
    text(c, m.f_mono, "데드존 섹터 그리드", SEN, (W - 36, 26), "tr")
    text(c, m.f_title, "방공호까지 3칸", INK, (W - 36, 46), "tr")
    text(c, m.f_sans, "새벽 · 스모그 · 턴 31", INK_DIM, (W - 36, 88), "tr")
    text(c, m.f_sans, "경보 48 · 주의", AMBER, (W - 36, 112), "tr")
    band = pygame.Rect(0, int(H * 0.44), W, 86); panel(c, band, 150, None)
    pygame.draw.line(c, SEN, (0, band.y), (W, band.y)); pygame.draw.line(c, SEN, (0, band.bottom), (W, band.bottom))
    text(c, m.f_mono, "[ 랜드마크 신호 포착 ]", SEN, (W // 2, band.y + 10), "tc")
    text(c, m.f_place, "무너진 대성당", INK, (W // 2, band.y + 34), "tc")
    log_box(c, pygame.Rect(30, H - 250, W - 60, 110), [
        ("[센서] 첨탑 꼭대기에서 오래된 비콘이 1.2초 간격으로 깜박인다.", INK),
        ("[기록] 구 정부가 마지막 방송을 보낸 곳이라는 소문이 있다.", INK_DIM),
        ("[신호] 탐색하면 이 장소의 이야기가 열린다.", SEN)])
    m._draw_quickbar(c, 30, H - 118, W - 60)
    footer(c, [("WASD", "이동"), ("F", "탐색"), ("I", "인벤토리"), ("J", "일지"), ("F5", "저장"), ("Esc", "종료")])
    save(c, "1_landmark")

# 2) 발칸 게이츠 대화 — 비주얼 노벨식 이름표 + 대사 + 선택지
def m2():
    c = pygame.Surface((W, H)); c.blit(art("forge/forge_dim_in_0.jpg", 0.40), (0, 0)); grade(c, bottom=0.55)
    c.blit(m._hud_surface(), (10, 10))
    r = pygame.Rect(30, H - 330, W - 60, 200); panel(c, r, 200)
    tag = pygame.Rect(r.x, r.y - 52, 250, 52); panel(c, tag, 220, None); pygame.draw.line(c, SEN, tag.bottomleft, (tag.right, tag.bottom), 2)
    text(c, m.f_mono, "스크랩 연합 노장", SEN, (tag.x + 14, tag.y + 6)); text(c, m.f_sans, "발칸 게이츠", INK, (tag.x + 14, tag.y + 24))
    for i, s in enumerate(("\"화로가 식은 지 삼 년이다. 쇳물 냄새를 잊을 뻔했지.\"",
                           "\"근처 드론 셋만 잡고, 고철 마흔 개를 가져와.",
                           " 그럼 네 녀석 총을 제대로 벼려 주마.\"")):
        text(c, m.f_serif, s, INK if i else INK, (r.x + 20, r.y + 20 + i * 32))
    text(c, m.f_mono, "의뢰: 처치 1/3 · 고철 22/40", SEN, (r.x + 20, r.y + 128))
    ch = [("1", "의뢰를 받는다", None), ("2", "나중에 오겠다", None)]
    buttons(c, ch, H - 118, 0, cols=2)
    footer(c, [("방향키", "고르기"), ("Enter", "결정"), ("클릭", "")])
    save(c, "2_vulkan")

# 3) 행상인 — 오른쪽 교환 목록
def m3():
    c = pygame.Surface((W, H)); c.blit(art("fig_trader/fig_trader_night_smog_4.jpg", 0.45), (0, 0)); grade(c)
    c.blit(m._hud_surface(), (10, 10))
    text(c, m.f_mono, "떠돌이 행상", SEN, (40, 150)); text(c, m.f_title, "\"물건은 진짜다. 값도 진짜고.\"", INK, (40, 172))
    r = pygame.Rect(W - 420, 240, 390, 420); panel(c, r, 205)
    text(c, m.f_mono, "교환 목록 · 보유 고철 64", SEN, (r.x + 16, r.y + 12))
    items = [("FOOD_BOTH", "수분 함유 전투식량", 30), ("WATER_BOTH", "미네랄 보충수", 25), ("MED_FIX_300", "군용 지혈제", 45),
             ("MED_PER_50", "응급 지혈대", 60), ("MED_PER_100", "나노 스팀팩", 120)]
    for i, (k, n, cost) in enumerate(items):
        y = r.y + 50 + i * 62; row = pygame.Rect(r.x + 10, y, r.w - 20, 54); on = i == 2
        panel(c, row, 120 if on else 60, None)
        if on: m._sensor_frame(c, row, SEN, 9)
        c.blit(m.crt_icon(k, 30, SEN if on else m.SENSOR_DIM), (row.x + 10, row.y + 12))
        text(c, m.f_sans, n, INK if on else INK_DIM, (row.x + 54, row.y + 8))
        text(c, m.f_mono, m.quick_effect(k), INK_FAINT, (row.x + 54, row.y + 30))
        text(c, m.f_mono_b, f"{cost}", RED if cost > 64 else SEN, (row.right - 14, row.y + 16), "tr")
    m._draw_quickbar(c, 30, H - 118, W - 60)
    footer(c, [("↑↓", "고르기"), ("Enter", "구매"), ("Esc", "떠나기")])
    save(c, "3_trader")

# 4) 바이오 하운드 전투 — 체력 위기(붉은 가장자리)
def m4():
    p.hp = 260; m._hud, m._loss = {}, {}
    c = pygame.Surface((W, H)); c.blit(art("enemy_hound/enemy_hound_evening_fog_0.jpg", 0.12), (0, 0)); grade(c, border=(230, 40, 40))
    c.blit(m._hud_surface(), (10, 10))
    enemy_bar(c, "교전 · 바이오 반응", "바이오 하운드 ×2", 0.38)
    reticle(c, int(W * 0.25), int(H * 0.46), 90, 90); reticle(c, int(W * 0.75), int(H * 0.47), 90, 90, (140, 60, 50))
    text(c, m.f_mono_b, "! 생체 신호 위험 — HP 18%", RED, (W // 2, int(H * 0.58)), "tc")
    log_box(c, pygame.Rect(30, H - 330, W - 60, 92), [
        ("[피격] 하운드가 옆구리를 물어뜯었다. HP -311", RED),
        ("[분석] 놈이 숨을 고른다. 다음 도약까지 1턴.", INK_DIM)])
    m._draw_quickbar(c, 30, H - 222, W - 60); m._quick_hover = None
    buttons(c, COMBAT_ACTS, H - 164, sel=6)
    footer(c, [("방향키", "고르기"), ("Enter", "실행"), ("1~0", "퀵슬롯")])
    p.hp = 1120; m._hud, m._loss = {}, {}
    save(c, "4_hound")

# 5) 보스 — 스캐브 컬렉터, 2페이즈 + 학습 지수
def m5():
    c = pygame.Surface((W, H)); c.blit(art("enemy_collector/enemy_collector_dawn_fog_0.jpg", 0.30), (0, 0))
    grade(c, tint=(90, 10, 10, 40), border=(200, 30, 30))
    c.blit(m._hud_surface(), (10, 10))
    text(c, m.f_mono, "BOSS · PHASE 2 — 과부하 모드", RED, (W // 2 + 40, 20), "tc")
    text(c, m.f_place, "스캐브 컬렉터", INK, (W // 2 + 40, 40), "tc")
    bx, bw = W // 2 + 40 - 260, 520
    pygame.draw.rect(c, (40, 20, 20), (bx, 86, bw, 14)); pygame.draw.rect(c, RED, (bx, 86, int(bw * 0.41), 14))
    for k in range(1, 10): pygame.draw.line(c, (20, 10, 10), (bx + bw * k // 10, 86), (bx + bw * k // 10, 99))
    text(c, m.f_mono, "학습 지수 E", INK_DIM, (bx, 108))
    for k in range(15):
        col = RED if k < 11 else (50, 40, 36)
        pygame.draw.rect(c, col, (bx + 90 + k * 14, 111, 10, 10))
    text(c, m.f_mono, "11 / 15 — 같은 공격이 막힌다", RED, (bx + 90 + 15 * 14 + 8, 108))
    text(c, m.f_mono, "제한 15턴 중 9턴", AMBER, (W - 36, 140), "tr")
    reticle(c, int(W * 0.60), int(H * 0.36), 200, 130)
    log_box(c, pygame.Rect(30, H - 330, W - 60, 92), [
        ("[경고] 컬렉터가 당신의 공격 패턴을 학습했다. 피해 -40%", RED),
        ("[제안] 패킷 우회(R)로 학습 지수를 초기화할 수 있다.", SEN)])
    m._draw_quickbar(c, 30, H - 222, W - 60)
    buttons(c, COMBAT_ACTS, H - 164, sel=2)
    footer(c, [("방향키", "고르기"), ("Enter", "실행"), ("1~0", "퀵슬롯")])
    save(c, "5_boss")

# 6) 레이아웃 B — 최소 HUD (그림 우선, 정보는 아래 한 줄)
def m6():
    c = pygame.Surface((W, H)); c.blit(art("neo_city/neo_city_night_fog_5.jpg", 0.30), (0, 0)); grade(c, top=120, bottom=0.78)
    text(c, m.f_place, "네오 아크 외벽", INK, (40, 36)); text(c, m.f_mono, "밤 · 안개 · 턴 31 · 방공호 3칸", INK_DIM, (42, 74))
    # 작은 미니맵 (오른쪽 위, 반투명)
    mini = pygame.Surface((220, 180), pygame.SRCALPHA); m._draw_iso_grid(mini, 10, 10)
    mini = pygame.transform.smoothscale(mini, (176, 144)); mini.set_alpha(210); c.blit(mini, (W - 200, 24))
    text(c, m.f_serif, "[센서] 외벽 탐조등이 섹터를 훑는다. 3초 뒤 이 칸을 지난다.", INK, (40, H - 200))
    # 아래 한 줄: 체력바 3개 + 퀵슬롯
    y = H - 150
    for i, (lab, v, col) in enumerate((("HP", 0.76, GREEN), ("허기", 0.72, AMBER), ("갈증", 0.58, TEAL))):
        x = 40 + i * 180
        text(c, m.f_mono, lab, INK_DIM, (x, y)); pygame.draw.rect(c, (40, 36, 32), (x + 40, y + 6, 120, 4)); pygame.draw.rect(c, col, (x + 40, y + 6, int(120 * v), 4))
    text(c, m.f_mono, "경보 48", AMBER, (W - 40, y), "tr")
    m._draw_quickbar(c, 30, H - 118, W - 60)
    footer(c, [("WASD", "이동"), ("F", "탐색"), ("I", "인벤토리"), ("M", "지도 크게"), ("Esc", "종료")])
    save(c, "6_minimal")

for f in (m1, m2, m3, m4, m5, m6):
    f()
sys.__stdout__.write("ok\n")

# ── 6번(최소 HUD) 톤으로 전투·대화 ─────────────────────────────────────────
def m7():
    c = pygame.Surface((W, H)); c.blit(art("enemy_drones/" + sorted(f for f in os.listdir(S + "enemy_drones") if f.endswith(".jpg"))[0]), (0, 0))
    grade(c, top=120, bottom=0.74)
    text(c, m.f_mono, "교전", RED, (40, 30)); text(c, m.f_place, "오염된 스캐브 드론 ×3", INK, (40, 48))
    pygame.draw.rect(c, (40, 30, 26), (42, 92, 260, 4)); pygame.draw.rect(c, AMBER, (42, 92, int(260 * 0.64), 4))
    text(c, m.f_mono, "64%", INK_DIM, (310, 85))
    reticle(c, int(W * 0.655), int(H * 0.37), 130, 70)
    text(c, m.f_serif, "[타격] 주무기 명중 — 드론 한 대의 회전날개가 꺾였다. 피해 1,284", AMBER, (40, H - 262))
    text(c, m.f_serif, "[피격] 드론의 레이저가 어깨를 스쳤다. HP -142", RED, (40, H - 232))
    slim_actions(c, H - 196, [("Q", "공격", "act_attack"), ("E", "방어", "act_barricade"), ("R", "우회", "act_jam"), ("F", "보조", "act_sub"),
                              ("Z", "과부하", "act_skill"), ("X", "후퇴", "act_retreat")], 0)
    mini_status(c, H - 150, 62)
    m._draw_quickbar(c, 30, H - 118, W - 60)
    footer(c, [("QERF", "기술"), ("Z", "스킬"), ("X", "후퇴"), ("I", "소모품"), ("1~0", "퀵슬롯")])
    save(c, "7_min_combat")

def m8():
    c = pygame.Surface((W, H)); c.blit(art("forge/forge_dim_in_0.jpg", 0.40), (0, 0)); grade(c, top=120, bottom=0.62)
    text(c, m.f_mono, "스크랩 연합 노장", SEN, (40, H - 330)); text(c, m.f_place, "발칸 게이츠", INK, (40, H - 310))
    for i, s in enumerate(("\"화로가 식은 지 삼 년이다. 쇳물 냄새를 잊을 뻔했지.\"",
                           "\"근처 드론 셋만 잡고, 고철 마흔 개를 가져와. 그럼 네 녀석 총을 제대로 벼려 주마.\"")):
        for j, ln in enumerate(m._wrap(m.f_serif, s, W - 80)):
            text(c, m.f_serif, ln, INK, (40, H - 268 + i * 34 + j * 30 * 0))
    y = H - 196
    for i, (k, l) in enumerate((("1", "의뢰를 받는다"), ("2", "나중에 오겠다"))):
        on = i == 0; r = pygame.Rect(32, y + i * 40 - 6, 300, 34)
        if on: panel(c, r, 150, None); m._sensor_frame(c, r, SEN, 8)
        text(c, m.f_mono_b, k, SEN if on else AMBER, (40, y + i * 40)); text(c, m.f_sans, l, INK if on else INK_DIM, (66, y + i * 40))
    text(c, m.f_mono, "의뢰: 처치 1/3 · 고철 22/40", SEN, (W - 40, y + 4), "tr")
    mini_status(c, H - 110 - 10)
    footer(c, [("↑↓", "고르기"), ("Enter", "결정"), ("클릭", "")])
    save(c, "8_min_dialogue")

m7(); m8()
sys.__stdout__.write("ok2\n")
