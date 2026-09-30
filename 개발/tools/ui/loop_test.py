"""그림 화면을 실제 입력 루프(choose / wait_key / type_out)로 돌려 본다 (창 없이). 키 이벤트를 주기적으로 넣는다.

  개발/ 폴더에서:  python tools/ui/loop_test.py

화면마다 OK / FAIL 한 줄. 멈추면 그 화면이 넣어 준 키(3, Enter)로 끝나지 않는다는 뜻이다. 세이브는 임시 폴더에 쓴다.
"""
import os, sys, tempfile, threading, time
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, os.getcwd())
import pygame, i18n
i18n.set_lang("ko")
from gui import PygameTerminal, set_terminal
term = PygameTerminal(); set_terminal(term)
out = sys.stdout
sys.stdout = term
import core; core.init_and_load_db()
import constants, sound, story, gm_bridge, endings, screens
from player import Player
from map import GameMap
for f in dir(sound):
    if callable(getattr(sound, f)) and not f.startswith("_"):
        setattr(sound, f, lambda *a, **k: None)
core.get_save_path = lambda: os.path.join(tempfile.gettempdir(), "stigma_shot_save.json")
story.combat_loop = lambda *a, **k: (None, None)
endings.unlock = lambda *a, **k: False

stop = False
def feeder():
    i = 0
    while not stop:
        time.sleep(0.12)
        key, uni = ((pygame.K_3, "3"), (pygame.K_RETURN, "\r"))[i % 2]
        try:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=uni, mod=0))
        except Exception:
            pass
        i += 1
threading.Thread(target=feeder, daemon=True).start()

def run(name, fn):
    t0 = time.time()
    try:
        fn()
        print(f"OK   {name}  ({time.time() - t0:.1f}s)", file=out, flush=True)
    except BaseException as e:
        import traceback
        print(f"FAIL {name}: {type(e).__name__}: {e}\n{traceback.format_exc()}", file=out, flush=True)

g = GameMap()
def P():
    p = Player(); p.consumables.update({"MED_PER_50": 1})
    return p
p = P(); run("boss_prep_view", lambda: story.boss_prep_view(p, g))
p = P(); run("core + perimeter", lambda: story.run_boss_core_choice(p)); print("     weights", dict(p.weights), "job", p.job_class, "slots", p.skill_slots, file=out)
p = P(); run("act2 teaser", lambda: story.run_act2_teaser(p)); print("     diary", p.diary[-1:], file=out)
for kind in ("choice", "simple", "weapon_item"):
    ev = next(e for e in constants.RANDOM_EVENTS if e["type"] == kind)
    p = P(); run(f"event {kind}", lambda: gm_bridge.run_event_script(p, g, ev))
run("codex", screens.show_codex)
p = P()
def inv():
    from inventory_view import run_inventory   # 보스 준비에서 여는 소모품 탭: Esc로 닫는다
    threading.Timer(0.8, lambda: pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="\x1b", mod=0))).start()
    run_inventory(p, tab="consumables")
run("inventory (consumables tab)", inv)
stop = True
