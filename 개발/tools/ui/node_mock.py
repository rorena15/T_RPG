"""지점 지도 화면 시안 (창 없이 PNG). 설계: docs/기획/지점지도_설계.md 3단계.

  개발/ 폴더에서:  python tools/ui/node_mock.py <출력 폴더> [시드]

찍는 것: 지금 칸 지도 탐색 화면(비교용), 지점 지도 탐색 화면(첫 턴 / 중반 / 길에 마우스), 큰 지도(M).
"""
import os, sys, random, tempfile
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, os.getcwd())
OUT = sys.argv[1]
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 7
os.makedirs(OUT, exist_ok=True)
import pygame, i18n
i18n.set_lang("ko")
from gui import PygameTerminal, set_terminal
term = PygameTerminal(); set_terminal(term)
_real_stdout = sys.stdout
sys.stdout = term
import core; core.init_and_load_db()
import constants, sound
from player import Player
from map import GameMap

for f in dir(sound):
    if callable(getattr(sound, f)) and not f.startswith("_"):
        setattr(sound, f, lambda *a, **k: None)
_tick = [100000]
def _ticks():
    _tick[0] += 400
    return _tick[0]
pygame.time.get_ticks = _ticks


def log(*a):
    print(*a, file=_real_stdout, flush=True)


def snap(view, name):
    view.render(term._canvas)
    view.render(term._canvas)
    path = os.path.join(OUT, name + ".png")
    pygame.image.save(term._canvas, path)
    log("  shot", path, term._canvas.get_size())


def new_player(turn=47):
    p = Player(); p.difficulty = "normal"
    p.hp = 1120; p.hunger = 64; p.thirst = 41; p.turn_count = turn; p.materials = 133
    p.consumables.update({"MED_PER_50": 2, "FOOD_BOTH": 1, "WATER_ONLY": 1})
    return p


# 1. 지금 칸 지도 (비교용)
from map_view import MapView
random.seed(SEED)
g = GameMap(); g.player_pos = [2, 1]; g.visited_tiles |= {(1, 0), (1, 1), (2, 1)}
v = MapView(term, new_player(), g); v.update(v.player, g); v.open()
snap(v, "0_지금_칸지도")
v.close()

if len(sys.argv) > 3 and sys.argv[3] == "grid-only":
    sys.exit()

# 2. 지점 지도
import node_map
from node_map import NodeMap
from node_map_view import NodeMapView
constants.NODE_MAP = True
random.seed(SEED)
nm = NodeMap(seed=SEED)
p = new_player(turn=1)
nm.bunker_hint_check()   # 게임 루프가 첫 턴에 띄우는 방공호 힌트
from i18n import t
ACTIONS = [("WASD", t('act_move'), True, None), ("F", t('act_search'), True, "F"), ("M", t('act_map'), True, "M"),
           ("I", t('act_inventory'), True, "I"), ("J", t('act_diary'), True, "J"), ("F5", t('act_save'), True, "C"),
           ("Esc", t('act_quit'), True, "Q")]
v = NodeMapView(term, p, nm); v.update(p, nm); v.set_actions(ACTIONS); v.open()
snap(v, "1_첫턴")

# 중반: 출발지에서 가까운 지점 몇 곳을 실제 길로 돌아다닌 상태
rng = random.Random(SEED)
for _ in range(9):   # 사람처럼: 안 가 본 가까운 곳 위주로
    roads = nm.neighbors()
    unseen = [q for q, _ in roads if q not in nm.visited_tiles and list(q) != list(nm.bunker_pos)]
    unseen.sort(key=lambda q: node_map._dist(q, nm.start_pos))
    q = (unseen[:2] and rng.choice(unseen[:2])) or rng.choice([q for q, _ in roads if list(q) != list(nm.bunker_pos)])
    p.turn_count += nm.edge_len(nm.player_pos, q)
    nm.player_pos = list(q); nm.visited_tiles.add(tuple(q)); nm.arrive()
    nm.bunker_hint_check()
nm.forge["hint"] = True
v.update(p, nm)
snap(v, "2_중반")

# 길 위에 마우스
roads = nm.neighbors()
v._road_hover = roads[0][0]
snap(v, "3_길_고르기")
v._road_hover = None

# 큰 지도 (M)
v.big_map = True
snap(v, "4_큰지도")

# 후반: 더 멀리 (랜드마크와 경계 지대 쪽으로) 돌아다닌 뒤의 큰 지도
for _ in range(22):
    roads = nm.neighbors()
    unseen = [q for q, _ in roads if q not in nm.visited_tiles and list(q) != list(nm.bunker_pos)]
    unseen.sort(key=lambda q: -q[1] - 6 * (nm.nodes[q]["kind"] == "landmark"))
    q = (unseen[:2] and rng.choice(unseen[:2])) or rng.choice([q for q, _ in roads if list(q) != list(nm.bunker_pos)])
    p.turn_count += nm.edge_len(nm.player_pos, q)
    nm.player_pos = list(q); nm.visited_tiles.add(tuple(q)); nm.arrive()
    nm.bunker_hint_check()
v.update(p, nm)
snap(v, "5_후반_큰지도")
v.big_map = False
snap(v, "6_후반")
v.close()
log("done")
