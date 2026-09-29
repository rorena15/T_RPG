"""절충안 목업 (기획/정면뷰_목업/절충안): 돌아다닐 땐 그림 가득, 이야기가 시작되면 그림이 물러나고 글이 가운데. 개발/ 폴더에서 실행."""
import os, sys
sys.path.insert(0, os.getcwd())
exec(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "mockup2.py")).read().split("# 1) 랜드마크 탐색")[0])
import pygame
SCENE = "lm_subway/lm_subway_evening_smog_3.jpg"
TITLE, TAG = "무너진 지하철역", "[ 이벤트 · 로컬 GM 서술 ]"

def backdrop(dim):
    """그림을 흐리고 어둡게: 이야기가 시작되면 무대가 뒤로 물러난다."""
    c = pygame.Surface((W, H)); a = art(SCENE, 0.40)
    if dim:
        small = pygame.transform.smoothscale(a, (W // 6, H // 6)); a = pygame.transform.smoothscale(small, (W, H))
    c.blit(a, (0, 0))
    if dim:
        d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((8, 6, 5, 175)); c.blit(d, (0, 0))
        grade(c, top=80, bottom=0.86)
    else:
        grade(c, top=120, bottom=0.78)
    return c

COL_X, COL_W = 150, W - 300   # 책 페이지 칸

def page_head(c, y):
    text(c, m.f_mono, TAG, SEN, (W // 2, y), "tc")
    text(c, m.f_place, TITLE, INK, (W // 2, y + 22), "tc")
    pygame.draw.line(c, _lerp(BG, SEN, 0.5), (W // 2 - 60, y + 66), (W // 2 + 60, y + 66))
    return y + 90

def para(c, y, s, col=INK, gap=12):
    for ln in m._wrap(m.f_serif, s, COL_W):
        text(c, m.f_serif, ln, col, (COL_X, y)); y += 32
    return y + gap

def h1():
    c = backdrop(False)
    text(c, m.f_place, TITLE, INK, (40, 36)); text(c, m.f_mono, "저녁 · 스모그 · 턴 31 · 방공호 3칸", INK_DIM, (42, 74))
    mini = pygame.Surface((220, 180), pygame.SRCALPHA); m._draw_iso_grid(mini, 10, 10)
    mini = pygame.transform.smoothscale(mini, (176, 144)); mini.set_alpha(210); c.blit(mini, (W - 200, 24))
    text(c, m.f_serif, "[센서] 승강장 아래에서 낮은 전자음이 규칙적으로 울린다.", INK, (40, H - 200))
    mini_status(c, H - 150)
    m._draw_quickbar(c, 30, H - 118, W - 60)
    footer(c, [("WASD", "이동"), ("F", "탐색"), ("I", "인벤토리"), ("M", "지도"), ("Esc", "종료")])
    save(c, "h1_explore")

def h2():
    c = backdrop(True)
    y = page_head(c, 70)
    y = para(c, y, "승강장 끝, 반쯤 물에 잠긴 선로 위로 녹슨 전동차 한 량이 비스듬히 걸려 있다. 전자음은 그 안에서 난다.")
    y = para(c, y, "창문 틈으로 푸른 빛이 새어 나온다. 누군가 아직 배터리를 갈아 끼우며 이곳을 쓰고 있다는 뜻이다. 발밑의 물이 미세하게 떨린다 — 드론의 회전날개 진동과 같은 박자로.")
    y = para(c, y, "N-404의 경보 센서가 한 칸 올라간다.", SEN, 26)
    items = [("1", "전동차 문을 비틀어 연다", "힘 · 소음 큼"), ("2", "창문 틈으로 안을 살핀다", "민첩 · 안전"),
             ("3", "선로를 따라 소리의 반대쪽으로 빠진다", "탐색 포기"), ("0", "직접 행동을 입력한다", "GM이 판정")]
    for i, (k, l, hint) in enumerate(items):
        on = i == 1; r = pygame.Rect(COL_X - 12, y - 6, COL_W + 24, 38)
        if on: panel(c, r, 120, None); m._sensor_frame(c, r, SEN, 11)
        text(c, m.f_mono_b, k, SEN if on else AMBER, (COL_X, y + 2)); text(c, m.f_sans, l, INK if on else INK_DIM, (COL_X + 28, y + 2))
        text(c, m.f_mono, hint, INK_FAINT, (COL_X + COL_W, y + 4), "tr")
        y += 44
    mini_status(c, H - 100)
    footer(c, [("↑↓", "고르기"), ("Enter", "결정"), ("0", "직접 입력")])
    save(c, "h2_story")

def h3():
    c = backdrop(True)
    y = page_head(c, 70)
    y = para(c, y, "창문 틈으로 푸른 빛이 새어 나온다. 발밑의 물이 드론의 회전날개와 같은 박자로 떨린다.", INK_DIM)
    # 플레이어가 쓴 행동
    r = pygame.Rect(COL_X - 12, y - 4, COL_W + 24, 40); panel(c, r, 150, (90, 70, 44))
    text(c, m.f_mono, "N-404 >", SEN, (COL_X, y + 8)); text(c, m.f_serif, "고철 조각을 반대편 선로로 던져 소리를 유인한다", INK, (COL_X + 72, y + 5))
    y += 58
    y = para(c, y, "쇳조각이 선로에 부딪혀 날카롭게 운다. 전동차 안의 전자음이 뚝 끊기더니, 지붕 해치가 열리고 정찰 드론 두 대가 소리 쪽으로 미끄러져 나간다.")
    y = para(c, y, "비어 버린 객차 안, 배터리 더미 옆에 누군가 흘리고 간 군용 가방이 보인다.", INK, 20)
    for s, col in (("판정  민첩 14 vs 10 — 성공", GREEN), ("획득  고철 +18 · 군용 지혈제 ×1", SEN), ("경보  +6", AMBER)):
        text(c, m.f_mono_b, s, col, (COL_X, y)); y += 26
    # 입력 칸 (다음 행동)
    y += 18
    r = pygame.Rect(COL_X - 12, y, COL_W + 24, 40); panel(c, r, 170, None); m._sensor_frame(c, r, SEN, 13)
    text(c, m.f_mono, "N-404 >", SEN, (COL_X, y + 12)); text(c, m.f_serif, "가방을 챙기고 해치 쪽을 살핀다", INK, (COL_X + 72, y + 9))
    pygame.draw.line(c, SEN, (COL_X + 72 + m.f_serif.size("가방을 챙기고 해치 쪽을 살핀다")[0] + 3, y + 10), (COL_X + 72 + m.f_serif.size("가방을 챙기고 해치 쪽을 살핀다")[0] + 3, y + 30), 2)
    text(c, m.f_mono, "이어서 행동 2회 남음", INK_FAINT, (COL_X + COL_W, y + 48), "tr")
    mini_status(c, H - 100, 54)
    footer(c, [("Enter", "보내기"), ("빈 칸 Enter", "떠나기")])
    save(c, "h3_input")

h1(); h2(); h3()
sys.__stdout__.write("ok\n")
