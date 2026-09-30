"""그림 화면 점검 (창 없이): 실제 화면 코드를 돌리고, 입력을 기다리는 순간마다 화면을 PNG로 저장한다.

  개발/ 폴더에서:  python tools/ui/shot.py <출력 폴더> [ko|en]

찍는 화면: 보스 준비, 코어 선택, 외곽 조우, 2막 예고, 대본 이벤트(선택·단순·무기), 결말 기록,
전투(최근 공방만 남는 기록, [센서] 알림, 대기 알림). 선택은 미리 정한 키로 넘기고 타자·대기는 건너뛴다.
입력 루프 자체(choose / wait_key)는 loop_test.py가 실제 키 이벤트로 돌려 본다. 세이브는 임시 폴더에 쓴다.
"""
import os, sys, random, tempfile
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, os.getcwd())
OUT = sys.argv[1]
LANG = sys.argv[2] if len(sys.argv) > 2 else "ko"
os.makedirs(OUT, exist_ok=True)
import pygame, i18n
i18n.set_lang(LANG)
from gui import PygameTerminal, set_terminal
term = PygameTerminal(); set_terminal(term)
_real_stdout = sys.stdout
sys.stdout = term
import core; core.init_and_load_db()
import constants, sound, event_view, story, gm_bridge, endings, combat, skills, screens
from event_view import EventView
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
core.get_save_path = lambda: os.path.join(tempfile.gettempdir(), "stigma_shot_save.json")

KEYS, N, PREFIX = [], [0], [""]
def log(*a):
    print(*a, file=_real_stdout, flush=True)

def snap(view, label):
    N[0] += 1
    view.render(term._canvas)
    view.render(term._canvas)
    path = os.path.join(OUT, f"{N[0]:02d}_{PREFIX[0]}_{label}.png")
    pygame.image.save(term._canvas, path)
    log("  shot", os.path.basename(path))

def _choose(self, menu, n, extra=()):
    menu["sel"] = menu.get("start", 0)
    snap(self, "choose")
    menu.pop("sel", None)
    k = KEYS.pop(0) if KEYS else "1"
    log("   choose ->", k, [x[1][:24] for x in menu["items"]])
    return k
def _wait_key(self, keys):
    snap(self, "wait")
    return "ENTER" if "ENTER" in keys else sorted(keys)[0]
def _type_out(self, entry, cps=0):
    entry.pop("typing", None)
EventView.choose = _choose
EventView.wait_key = _wait_key
EventView.type_out = _type_out
EventView.hold = lambda self, ms: snap(self, "hold")
EventView.pause = lambda self, ms: None

def new_player():
    p = Player(); p.difficulty = "normal"
    p.hp = 1120; p.hunger = 64; p.thirst = 41; p.turn_count = 47; p.materials = 133
    p.consumables.update({"MED_PER_50": 2, "FOOD_BOTH": 1, "WATER_ONLY": 1})
    return p

def run(name, fn, keys=()):
    PREFIX[0] = name
    KEYS[:] = list(keys)
    log("==", name)
    try:
        fn()
    except SystemExit:
        log("   (SystemExit)")
    except Exception:
        import traceback
        log(traceback.format_exc())

random.seed(7)
g = GameMap(); g.player_pos = [4, 3]

# 1. 보스 준비
p = new_player()
p.use_consumable_menu = lambda: log("   (소모품 화면 열림)")
run("bossprep", lambda: story.boss_prep_view(p, g), ["2", "1", "3"])

# 2. 코어 선택 (말줄임표 힌트가 붙는 상태) + 외곽 조우(회피)
p = new_player(); p.weights.update({"kinetic": 3, "scrap": 3, "cyber": 0})
run("core", lambda: story.run_boss_core_choice(p), ["3", "2"])

# 3. 외곽 조우(격퇴): 전투는 건너뛴다
p = new_player()
story.combat_loop = lambda *a, **k: (None, None)
run("perimeter", lambda: story.run_perimeter_encounter(p), ["1"])

# 4. 2막 예고
p = new_player(); p.weights.update({"kinetic": 1, "scrap": 5, "cyber": 2})
run("act2", lambda: story.run_act2_teaser(p), ["2"])

# 5. 대본 이벤트 (선택 / 단순 / 무기)
evs = constants.RANDOM_EVENTS
for kind in ("choice", "simple", "weapon_item"):
    ev = next((e for e in evs if e["type"] == kind), None)
    if ev:
        p = new_player()
        run(f"event_{kind}", lambda: log("   ->", gm_bridge.run_event_script(p, g, ev)), ["2"])
        log("   state", p.hp, p.materials, dict(p.weights), [i for i in p.inventory][-2:])

# 6. 결말 기록
endings.load = lambda: {"endings": ["forge", "hoarder", "boss_death", "starve_thirst", "scarred"], "jobs": ["combat", "net"]}
from screens import MenuScreen
def codex():
    screens.show_codex()
run("codex", codex)

# 7. 전투의 [센서] 알림: 드론 전투를 몇 턴 돌린다
endings.unlock = lambda *a, **k: False
event_view.scene_card = lambda *a, **k: None
combat._sleep = lambda s: None
import ui
for m in (combat, ui):
    if hasattr(m, "type_text"):
        m.type_text = lambda *a, **k: None
def _silent_wait():   # "아무 키나 누르면 진행" 대기: 알림이 떠 있는 화면을 찍고 넘어간다
    ui_ = term._ui_manager
    if ui_ is not None and getattr(ui_, "_active", False):
        snap(ui_, "wait")
term.wait_keypress_silent = _silent_wait
def drive_combat(etype, seq, label):
    p = new_player(); p.hp = p.max_hp
    p.weights.update({"cyber": 4})
    ks = list(seq)
    def rk():
        ui_ = term._ui_manager
        if ui_ is not None:
            snap(ui_, label)
        k = ks.pop(0) if ks else "Q"
        if ui_ is not None and hasattr(ui_, "on_key"):   # gui.read_key가 하는 일: 키를 받은 순간을 화면에 알린다
            ui_.on_key(k)
        return k
    combat.read_key = rk
    PREFIX[0] = "combat"
    log("== combat", etype)
    try:
        combat.combat_loop(p, is_boss=False, enemy_type=etype)
    except SystemExit:
        log("   (death)")
    except Exception:
        import traceback; log(traceback.format_exc())
drive_combat("drone", ["Q", "Q", "E", "Q", "I", "1"], "drone")   # 뒤는 Q로 이길 때까지 (승리 화면의 대기 알림까지)
drive_combat("security", ["Q", "R", "Q"], "sec")
log("done")
