"""지점 지도를 실제 게임 루프(Main.run_game)로 돌려 본다 (창 없이). 키·마우스 이벤트를 넣어 이동·큰 지도·종료까지.

  개발/ 폴더에서:  python tools/ui/node_play_test.py [화면을 남길 폴더]

임시 세이브(지점 지도)를 불러와 시작한다. 전투·이벤트·행상인은 건너뛴다 (화면 입력만 본다). 단계마다 OK / FAIL.
"""
import os, sys, tempfile, threading, time, json
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, os.getcwd())
OUT = sys.argv[1] if len(sys.argv) > 1 else None
import pygame, i18n
i18n.set_lang("ko")
from gui import PygameTerminal, set_terminal
term = PygameTerminal(); set_terminal(term)
out = sys.stdout
sys.stdout = term
import core; core.init_and_load_db()
import constants, sound, Main, gm_bridge, archive
from player import Player
from node_map import NodeMap
from node_map_view import NodeMapView
for f in dir(sound):
    if callable(getattr(sound, f)) and not f.startswith("_"):
        setattr(sound, f, lambda *a, **k: None)
SAVE = os.path.join(tempfile.gettempdir(), "stigma_node_play_save.json")
_ARC = os.path.join(tempfile.mkdtemp(), "archive.json")   # 진짜 기록 보관소(개발/archive.json)는 건드리지 않는다
archive._path = lambda: _ARC
for m in (core, Main):
    if hasattr(m, "get_save_path"):
        m.get_save_path = lambda: SAVE
Main.check_and_prompt_update = lambda *a, **k: None
Main._offer_extra_data = lambda *a, **k: None
gm_bridge.available = lambda: False
REAL_COMBAT = Main.combat_loop
FIGHTS = [0]
def _counted_combat(*a, **k):
    FIGHTS[0] += 1
    return REAL_COMBAT(*a, **k)
Main.combat_loop = lambda *a, **k: (None, None)
Main.handle_session = lambda *a, **k: None
Main.handle_trader = lambda *a, **k: None
Main.trigger_sudden_quest = lambda *a, **k: None   # 무작위 돌발 퀘스트 제안 화면은 이 시험 밖
Main.get_encounter_chance = lambda p: 0.0

constants.NODE_MAP = True
p = Player(); p.difficulty = "normal"
g = NodeMap(seed=7)
with open(SAVE, "w", encoding="utf-8") as f:
    json.dump({"player": p.to_dict(), "grid": g.to_dict()}, f, ensure_ascii=False)

RESULTS = []
def log(ok, name, extra=""):
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name} {extra}", file=out, flush=True)

WAITING = [0]   # Main이 read_key에서 입력을 기다리는 중인지 (read_key는 시작할 때 쌓인 키를 버린다)
_orig_rk = term.read_key
def _rk():
    WAITING[0] += 1
    try:
        return _orig_rk()
    finally:
        WAITING[0] -= 1
term.read_key = _rk

def raw_key(key, uni=""):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=uni, mod=0))

def post_key(key, uni=""):
    wait(lambda: WAITING[0] > 0, 5)
    time.sleep(0.15)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=uni, mod=0))

def view():
    v = term._ui_manager
    return v if isinstance(v, NodeMapView) and v._active else None

def wait(cond, sec=8.0):
    end = time.time() + sec
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False

def snap(name):
    if OUT:
        os.makedirs(OUT, exist_ok=True)
        time.sleep(0.4)
        pygame.image.save(term._canvas, os.path.join(OUT, name + ".png"))

def driver():
    # 타이틀 → 불러오기 → (불러왔다는 알림) → 지도 화면
    end = time.time() + 30
    while not view() and time.time() < end:
        raw_key(pygame.K_2, "2"); time.sleep(0.3)
        raw_key(pygame.K_RETURN, "\r"); time.sleep(0.3)
    log(bool(view()), "지점 지도 화면에 들어감", type(term._ui_manager).__name__)
    v = view()
    if not v:
        return
    grid = v.grid
    snap("1_start")
    # 방향키: 이어진 길 중 하나
    keys = grid.road_keys()
    k = next(iter(keys))
    arrow = {"W": pygame.K_UP, "A": pygame.K_LEFT, "S": pygame.K_DOWN, "D": pygame.K_RIGHT}[k]
    before, turn0 = list(grid.player_pos), v.player.turn_count
    post_key(arrow)
    moved = wait(lambda: list(grid.player_pos) != before)
    log(moved and tuple(grid.player_pos) == tuple(keys[k]), f"방향키 {k} → 그 길로 이동",
        f"{before} → {grid.player_pos}, 턴 {turn0} → {v.player.turn_count} (길 {grid.edge_len(before, grid.player_pos) if moved else '-'}턴)")
    wait(lambda: view() is not None and view()._move is None, 4)
    snap("2_moved")
    # 길이 없는 방향 키: 아무 일 없어야
    missing = [x for x in "WASD" if x not in grid.road_keys()]
    if missing:
        before = list(grid.player_pos)
        post_key(getattr(pygame, f"K_{missing[0].lower()}"), missing[0].lower())
        time.sleep(0.8)
        log(list(grid.player_pos) == before, f"길 없는 방향 {missing[0]} 무시")
    # M: 큰 지도 열고 닫기
    post_key(pygame.K_m, "m")
    ok_m = wait(lambda: view() and view().big_map, 3)
    um = term._ui_manager
    log(ok_m, "M → 큰 지도", f"(화면 {type(um).__name__}, 열림 {getattr(um, '_active', None)}, big_map {getattr(um, 'big_map', None)})")
    snap("3_bigmap")
    post_key(pygame.K_ESCAPE, "\x1b")
    log(wait(lambda: view() and not view().big_map, 3), "Esc → 큰 지도 닫힘 (게임은 그대로)")
    # 마우스: 길 목록 한 줄 누르기
    time.sleep(0.4)
    v = view()
    rect, key = v._road_rows[0]
    target = grid.road_keys()[key]
    sx, sy = rect.center
    sw, sh = term.screen.get_size()   # 캔버스 → 창 좌표 (EventView.to_canvas의 반대)
    cw, ch = term._canvas.get_size()
    sc = min(sw / cw, sh / ch)
    wx, wy = int(sx * sc + (sw - cw * sc) / 2), int(sy * sc + (sh - ch * sc) / 2)
    wait(lambda: WAITING[0] > 0, 5); time.sleep(0.15)
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(wx, wy), rel=(0, 0), buttons=(0, 0, 0)))
    time.sleep(0.2)
    before = list(grid.player_pos)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(wx, wy), button=1))
    moved = wait(lambda: list(grid.player_pos) != before)
    log(moved and tuple(grid.player_pos) == tuple(target), "마우스로 길 목록 누름 → 이동", f"{before} → {grid.player_pos}")
    wait(lambda: view() is not None and view()._move is None, 4)
    snap("4_mouse_moved")
    # 탐색 F: 빈 탐색으로 고정하고 일기 조각을 반드시 줍게 해서, 읽기 화면이 바로 열리는지
    import random as _random
    class _EmptySearch:   # Main의 탐색 주사위만 빈 탐색(0.5) 자리로, 나머지는 진짜 random
        def __getattr__(self, name):
            return getattr(_random, name)
        def random(self):
            return 0.5
    Main.random = _EmptySearch()
    archive.FRAGMENT_CHANCE = 1.0
    t0 = v.player.turn_count
    for _ in range(3):   # 입력 대기 전에 넣은 키는 read_key가 버린다: 턴이 안 넘어가면 다시
        post_key(pygame.K_f, "f")
        if wait(lambda: v.player.turn_count > t0, 3):
            break
    log(v.player.turn_count > t0, "F 탐색 → 턴 진행",
        f"(턴 {t0}→{v.player.turn_count}, 화면 {type(term._ui_manager).__name__}, 뒤질 수 있음 {grid.can_search(v.player.turn_count)}, 최근 {[x[-40:] for x in v._recent_lines()[-2:]]})")
    opened = False
    for _ in range(10):   # 빈 탐색 글 뒤의 '아무 키' 대기를 넘기면 조각을 줍고 읽기 화면이 열린다
        if wait(lambda: type(term._ui_manager).__name__ == "ReadView", 1.0):
            opened = True
            break
        raw_key(pygame.K_RETURN, "\r")
    picked = list(archive.PICKED)
    snap("4b_fragment_read")
    log(opened and picked, "일기 조각을 주우면 읽기 화면이 바로 열림", f"{picked}")
    Main.random = _random
    archive.FRAGMENT_CHANCE = 0.0
    for _ in range(3):   # 처음 키는 글을 다 펼치고, 다음 키가 닫는다
        raw_key(pygame.K_RETURN, "\r"); time.sleep(0.4)
        if view():
            break
    log(wait(lambda: view() is not None, 6), "읽기 화면을 닫으면 지도 화면으로")
    # 길 위 조우: 2턴 이상인 길로, 조우 100%, 실제 전투 (Q 공격, Enter로 대기 넘기기)
    for _ in range(6):   # 탐색 결과 대기가 남아 있으면 넘긴다
        if WAITING[0]:
            break
        raw_key(pygame.K_RETURN, "\r"); time.sleep(0.3)
    v = view()
    long_road = next(((k, q) for k, q in grid.road_keys().items() if grid.edge_len(grid.player_pos, q) >= 2), None) if v else None
    if long_road:
        k, q = long_road
        Main.combat_loop = _counted_combat
        Main.get_encounter_chance = lambda p: 1.0
        constants.ROAD_ENC = 1.0   # 길 중간 턴마다 반드시 (도착 지점은 스토리 세션이 조우를 대신할 수 있다)
        post_key({"W": pygame.K_UP, "A": pygame.K_LEFT, "S": pygame.K_DOWN, "D": pygame.K_RIGHT}[k])
        end = time.time() + 90
        while time.time() < end:
            if view() and tuple(grid.player_pos) == tuple(q) and WAITING[0] and FIGHTS[0] >= 1:
                break
            raw_key(pygame.K_q, "q"); time.sleep(0.25)
            raw_key(pygame.K_RETURN, "\r"); time.sleep(0.25)
        Main.get_encounter_chance = lambda p: 0.0
        constants.ROAD_ENC = 0.5
        Main.combat_loop = lambda *a, **k: (None, None)
        log(tuple(grid.player_pos) == tuple(q) and FIGHTS[0] >= 1 and view() is not None,
            f"길 위 조우 → 전투 {FIGHTS[0]}번 → 지도 화면으로 돌아와 도착", f"HP {v.player.hp}")
        snap("5_after_road_fight")
    else:
        log(False, "2턴 이상인 길이 없어 길 위 조우를 시험하지 못함")
    # 종료: Esc → 저장 없이 종료
    end = time.time() + 10
    while time.time() < end and not DONE[0]:
        raw_key(pygame.K_ESCAPE, "\x1b"); time.sleep(0.4)
        raw_key(pygame.K_2, "2"); time.sleep(0.4)

DONE = [False]
threading.Thread(target=driver, daemon=True).start()
try:
    Main.run_game()
except SystemExit:
    pass
DONE[0] = True
log(True, "종료 (SystemExit)")
print(f"\n{'모두 통과' if all(RESULTS) else '실패 있음'}", file=out)
