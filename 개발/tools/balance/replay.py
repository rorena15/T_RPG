"""보스 직전 상태(sim.py가 모은 jsonl)로 보스전만 다시 돌려, 탐색량별 최종 클리어율 곡선을 계산한다.

쓰는 법 (게임 코드 폴더를 현재 폴더로 두고):
  SEEDS=4 python replay.py <결과.jsonl> '{"atk":100,"hp":100000,"ref":180,"mult":{"easy":1.6},"atkm":{"easy":1.62}}'
atk/hp/ref: BOSS_BASE_ATK/BOSS_HP/BOSS_POWER_REF, mult: BOSS_DIFF_MULT, atkm: BOSS_DIFF_ATK (난이도별, 일부만 줘도 된다).
보스 앞에서 죽은 판은 그대로 실패로 센다. 게임 전체보다 훨씬 빨라서 보스 수치를 맞출 때 쓴다 (sim.py --replay).
"""
import os, sys, json, random, copy, linecache, collections, time as _t
sys.path.insert(0, os.getcwd()); _t.sleep = lambda s: None
import ui, i18n; i18n.set_lang("ko")
import constants, combat, core, traits
from player import Player
core.init_and_load_db()
combat._sleep = lambda s: None
import quest
for _m in (combat, quest, ui):
    for n in ("clear_screen", "wait_for_keypress", "type_text", "glitch_flash", "print_header", "print_divider", "flush_input"):
        if hasattr(_m, n): setattr(_m, n, lambda *a, **k: None)
quest.log_diary = lambda *a, **k: None
_out = sys.stdout; sys.stdout = open(os.devnull, "w")
SNAP = []
for _l in open(sys.argv[1], encoding="utf-8"):
    try:
        _r = json.loads(_l)
    except Exception:
        continue
    if not str(_r.get("result", "")).startswith("CRASH"):
        SNAP.append(_r)
SEEDS = int(os.environ.get("SEEDS", "3"))

def best_heal(p):
    hp = [k for k, v in p.consumables.items() if v > 0 and constants.CONSUMABLES_DB[k]["type"] == "hp"]
    if not hp: return None
    amt = lambda k: p.max_hp * constants.CONSUMABLES_DB[k]["val"] if constants.CONSUMABLES_DB[k]["is_percent"] else constants.CONSUMABLES_DB[k]["val"]
    return max(hp, key=amt)

def fight(state, seed):
    random.seed(seed)
    p = Player(); p.from_dict(copy.deepcopy(state["d"]))
    def key():
        f = sys._getframe(1); line = linecache.getline(f.f_code.co_filename, f.f_lineno)
        if "item_cmd" in line:
            avail = [k for k, v in p.consumables.items() if v > 0]
            return str(avail.index(best_heal(p)) + 1)
        # 전투 키는 bot.py와 같다 (Q 공격 · E 바리케이드 · R 패킷 우회 · I 소모품). 숫자키는 퀵슬롯이라 쓰지 않는다
        if p.hp < p.max_hp * 0.35 and best_heal(p): return "I"
        L = f.f_locals.get("learning_index", 0)
        cost = traits.jam_cost(p)
        if os.environ.get("TACTIC", "1") == "1":   # 사람처럼: 학습 지수가 쌓이면 끊는다
            if L >= 9 and p.max_ram >= cost: return "R"
            if traits.jam_blocks_counter(p) and p.max_ram >= cost and not f.f_locals["combat_ctx"].get("exposed"): return "R"
            if L >= 11: return "E"
        return "Q"
    combat.read_key = key
    try:
        combat.combat_loop(p, is_boss=True); return True
    except SystemExit:
        return False

def curve(params):
    constants.BOSS_BASE_ATK, constants.BOSS_HP, constants.BOSS_POWER_REF = params["atk"], params["hp"], params["ref"]
    constants.BOSS_DIFF_MULT.update(params.get("mult", {}))
    constants.BOSS_DIFF_ATK.update(params.get("atkm", {}))
    res = collections.defaultdict(lambda: [0, 0])   # (diff, farm) -> [clears, runs]
    for r in SNAP:
        key = (r["diff"], r["farm"])
        if not r["state"]:
            res[key][1] += SEEDS; continue          # 보스 전에 죽음
        wins = sum(fight(r["state"], s) for s in range(SEEDS))
        res[key][0] += wins; res[key][1] += SEEDS
    return res

if __name__ == "__main__":
    params = json.loads(sys.argv[2])
    res = curve(params)
    farms = sorted({f for _, f in res})
    for d in ("easy", "normal", "hard"):
        if not any(k[0] == d for k in res):   # 이 난이도 판이 없으면 건너뛴다
            continue
        _out.write(f"{d:6} " + "  ".join(f"탐색{f:>2}:{res[(d, f)][0] / max(1, res[(d, f)][1]) * 100:5.1f}%" for f in farms) + "\n")
    _out.flush()
