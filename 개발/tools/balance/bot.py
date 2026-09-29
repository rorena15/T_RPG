"""밸런스 검증 봇: 실제 게임 코드(Main.run_game)를 터미널 모드로 돌리며 키 입력만 사람처럼 대신 누른다.

쓰는 법 (게임 코드 폴더를 현재 폴더로 두고):  python bot.py <난이도> farm <탐색 횟수> <시드> [flee]
결과는 표준 출력에 JSON 한 줄 (result: clear / death_boss / death_combat / death_other, boss_state: 보스 직전 상태 등).
보통은 sim.py가 게임 코드를 여러 벌 복사해 병렬로 부른다 (같은 폴더에서 동시에 돌리면 stigma_data.db가 서로 덮인다).

사람처럼 하는 것: 부위마다 센 장비 장착·남는 장비 분해, 고철이 모이면 강화소에서 강화, 발칸 의뢰 수락·보고,
쇠 두드리는 소리(힌트)를 따라가기, 배고프면 먹기, 일반 전투에서 체력이 반 밑이면 후퇴(flee), 보스 학습 지수 끊기.
환경 변수로 수치를 바꿔 볼 수 있다: BOSS_ATK, BOSS_HP, BOSS_MULT, BOSS_REF, ENEMY_DIFF(일반 적 난이도 배율),
NO_UPG(강화 안 함), NO_HINT(발칸 힌트 끔), FORGE_MULT(강화 몇 번분 고철이 모이면 강화소로, 기본 2), TRACE(턴별 상태 출력).
"""
import os, sys, io, json, random, linecache, time as _time
sys.path.insert(0, os.getcwd())
DIFF, STRAT, FARM_N, SEED = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
FLEE = len(sys.argv) > 5 and sys.argv[5] == "flee"
UPG = os.environ.get("NO_UPG") is None
random.seed(SEED)
_time.sleep = lambda s: None
import ui, i18n
for n in ("clear_screen",):
    setattr(ui, n, lambda *a, **k: None)
import constants, combat, quest, story, player as player_mod, Main, core, skills, updater, sound
for m in (combat, quest, story, player_mod, Main, core, ui):
    if hasattr(m, "clear_screen"): m.clear_screen = lambda *a, **k: None
    if hasattr(m, "wait_for_keypress"): m.wait_for_keypress = lambda *a, **k: None
Main.check_and_prompt_update = lambda *a, **k: None
if os.environ.get("BOSS_ATK"): constants.BOSS_BASE_ATK = int(os.environ["BOSS_ATK"])
if os.environ.get("BOSS_HP"): constants.BOSS_HP = int(os.environ["BOSS_HP"])
if os.environ.get("BOSS_MULT"): constants.BOSS_DIFF_MULT[DIFF] = float(os.environ["BOSS_MULT"])
if os.environ.get("BOSS_REF"): constants.BOSS_POWER_REF = float(os.environ["BOSS_REF"])
if os.environ.get("ENEMY_DIFF"): constants.ENEMY_DIFF_ATK[DIFF] = float(os.environ["ENEMY_DIFF"])
Main._offer_extra_data = lambda *a, **k: None
Main.gm_bridge.available = lambda: False
combat._sleep = lambda s: None
for f in dir(sound):
    if callable(getattr(sound, f)) and not f.startswith("_"): setattr(sound, f, lambda *a, **k: None)
M = {"fights": [], "searches": 0, "scrap_gain": 0, "moves": 0, "heals_used": 0, "food_used": 0, "result": None,
     "trader": 0, "events": 0, "sessions": 0, "quests_done": 0}
P = {"p": None, "g": None}
DIFF_KEY = {"easy": "1", "normal": "2", "hard": "3"}[DIFF]

def best_heal(p):
    hp = [k for k, v in p.consumables.items() if v > 0 and constants.CONSUMABLES_DB[k]["type"] == "hp"]
    if not hp: return None
    need = p.max_hp - p.hp
    def amt(k):
        it = constants.CONSUMABLES_DB[k]; return p.max_hp * it["val"] if it["is_percent"] else it["val"]
    ok = [k for k in hp if amt(k) <= need * 1.2] or hp
    return max(ok, key=amt)

def food_for(p):
    need_h, need_t = p.hunger < 45, p.thirst < 45
    c = [k for k, v in p.consumables.items() if v > 0 and constants.CONSUMABLES_DB[k]["type"] in ("food", "water")
         and ((need_h and constants.CONSUMABLES_DB[k].get("hunger", 0) > 0) or (need_t and constants.CONSUMABLES_DB[k].get("thirst", 0) > 0))]
    return c[0] if c else None

def auto_equip(p, g=None):
    """사람처럼: 부위마다 (강화 포함) 가장 센 장비를 끼고, 안 쓰는 장비는 분해해 고철로, 고철로 주무기를 강화한다."""
    from core import get_equipment_data
    import upgrade
    def pw(iid):
        d = get_equipment_data(iid); return d["power"] + upgrade.effective_delta(p, iid)
    best = {}
    for iid in p.inventory:
        d = get_equipment_data(iid); sk = d.get("slot")
        if sk in p.equipment and (sk not in best or pw(iid) > best[sk][1]): best[sk] = (iid, pw(iid))
    for sk, (iid, v) in best.items():
        cur = p.equipment.get(sk)
        cp = pw(cur) if cur and (cur != "WEAPON_NONE" or sk == "main_weapon") else -1
        if v > cp: p.equipment[sk] = iid
    if UPG:
        worn = set(p.equipment.values())
        for iid in [i for i in p.inventory if i not in worn]:
            p.inventory.remove(iid); p.materials += random.randint(15, 30); M["dismantled"] = M.get("dismantled", 0) + 1
        wid = p.equipment["main_weapon"]
        import forge
        if g is None or not g.at_forge() or not forge.built(g): return   # 강화·수리는 완공된 강화소에서만
        M["forge_visits"] = M.get("forge_visits", 0) + 1
        while True:
            res, k, spent = upgrade.try_upgrade(p, wid, get_equipment_data(wid).get("tier", 4))
            if res in ("ok", "fail", "drop"):
                M["upg_spent"] = M.get("upg_spent", 0) + spent
                if res == "drop": M["upg_drop"] = M.get("upg_drop", 0) + 1
            elif res == "broken" and upgrade.repair(p, wid)[0] == "ok": M["repair"] = M.get("repair", 0) + 1
            else: break
        upgrade.repair(p, wid)

pending = []
def key_for_consumable_menu(p, want):
    avail = [k for k, v in p.consumables.items() if v > 0]
    return str(avail.index(want) + 1) if want in avail else "0"

def bot_read_key(_depth=1):
    f = sys._getframe(_depth)
    line = linecache.getline(f.f_code.co_filename, f.f_lineno).strip()
    fn = f.f_code.co_name
    lv = f.f_locals
    p = lv.get("player") or lv.get("self") if fn in ("combat_loop", "use_consumable_menu", "manage_inventory") else None
    if P["p"] is None and "player" in lv: P["p"] = lv["player"]
    if "grid" in lv: P["g"] = lv["grid"]
    p = P["p"] if not hasattr(p, "hp") else p
    if pending: return pending.pop(0)
    if line.startswith("diff_ans"): return DIFF_KEY
    if line.startswith("skip_ans"): return "0"
    if fn == "run_game" and line.startswith("ans"): return "1"
    if line.startswith("move = read_key()"):
        from core import get_equipment_data
        pl, g = lv.get("player"), lv.get("grid")
        P["p"], P["g"] = pl, g
        auto_equip(pl, g)
        if os.environ.get("TRACE"):
            food_n = sum(v for k, v in pl.consumables.items() if constants.CONSUMABLES_DB[k]["type"] in ("food", "water"))
            sys.stderr.write(f"T{pl.turn_count:3d} hp={pl.hp:5d}/{pl.max_hp} hun={pl.hunger:3d} thi={pl.thirst:3d} food={food_n} srch={M['searches']} forge={g.forge} pos={g.player_pos}\n")
        import upgrade
        wid = pl.equipment["main_weapon"]
        k = upgrade.level(pl, wid)
        need = upgrade.cost(get_equipment_data(wid).get("tier", 4), k) if k < upgrade.MAX_LEVEL else 10**9
        import forge
        st = forge.stage(g)
        # 사람처럼: 발칸 의뢰를 받아 놓았으면 파밍 예산을 조금 넘겨서라도 마무리한다
        budget = FARM_N + (30 if st == 1 and not forge.ready(pl, g) else 0)
        farming = STRAT == "farm" and M["searches"] < budget
        # 사람처럼: 고철이 강화 두어 번 할 만큼 모이거나, 파밍을 끝내고 방공호로 가기 전 고철이 남으면 강화소로
        want = food_for(pl)
        if want or (pl.hp < pl.max_hp * 0.5 and best_heal(pl)):
            # 이동 방향을 정하기 전에 먼저 (예전엔 강화소로 가는 동안 먹지 않아 굶어 죽었다)
        # 탐색 중 먹고 마시기/치료: 소모품 메뉴를 거치게 한다 (게임 코드 그대로)
            k = want or best_heal(pl)
            pl.use_consumable_menu_bot = k
            pending.append("__USE__")
        if st == 1 and forge.ready(pl, g) and g.at_forge():   # 의뢰 조건을 채웠다: 발칸에게 보고
            M["forge_report"] = M.get("forge_report", 0) + 1
            return "U"
        if st >= 2:
            fm = float(os.environ.get("FORGE_MULT", "2"))   # 고철이 강화 몇 번분 모이면 강화소로 갈지
            want_forge = UPG and not g.at_forge() and (pl.materials >= fm * need or (not farming and pl.materials >= need))
        else:
            # 의뢰 조건을 채웠거나, 쇠 두드리는 소리(힌트)를 들었으면 그쪽으로 (사람처럼 지도 표시를 따라간다)
            want_forge = (st == 1 and forge.ready(pl, g)) or (st == 0 and forge.hinted(g))
        if want_forge:
            x, y = g.player_pos; fx, fy = g.forge_pos
            M["forge_moves"] = M.get("forge_moves", 0) + 1
            steps = [k2 for k2, c in (("D", fx > x), ("A", fx < x), ("W", fy > y), ("S", fy < y)) if c]
            steps = [k2 for k2 in steps if [x + (k2 == "D") - (k2 == "A"), y + (k2 == "W") - (k2 == "S")] != list(g.bunker_pos)] or steps
            return steps[0]
        if farming and g.can_search(pl.turn_count)[0]:  # 타일 수색 한도가 남았을 때만
            M["searches"] += 1; return "F"
        if farming:  # 이 칸은 다 뒤졌다: 뒤질 수 있는 옆 칸으로 (방공호 제외)
            x, y = g.player_pos
            def ok(nx, ny):
                if not (0 <= nx < g.size and 0 <= ny < g.size) or [nx, ny] == list(g.bunker_pos): return False
                if hasattr(g, "is_blocked") and g.is_blocked([nx, ny]): return False
                td = g.tile_data.get((nx, ny))
                return td is None or td["remaining"] > 0 or td["cooldown_until"] <= pl.turn_count
            opts = [(k, nx, ny) for k, nx, ny in (("D", x+1, y), ("A", x-1, y), ("W", x, y+1), ("S", x, y-1)) if ok(nx, ny)]
            if opts:
                fresh = [o for o in opts if (o[1], o[2]) not in g.tile_data]
                return random.choice(fresh or opts)[0]
        M["moves"] += 1
        x, y = g.player_pos
        k = "D" if x < g.bunker_pos[0] and (x <= y or y >= g.bunker_pos[1]) else "W"
        nxt = [x + (k == "D"), y + (k == "W")]
        if nxt == list(g.bunker_pos) and getattr(pl, "searches_done", 99) < getattr(constants, "BUNKER_MIN_SEARCHES", 0):
            M["locked"] = M.get("locked", 0) + 1
            if g.can_search(pl.turn_count)[0]:
                M["searches"] += 1; return "F"
            return "A" if x > 0 and k == "D" else "S"   # 문이 잠겼고 칸도 다 뒤졌으면 옆 칸으로
        return k
    if fn == "combat_loop" and line.startswith("cmd = read_key()"):
        pl = lv["player"]
        if pl.hp < pl.max_hp * 0.35 and best_heal(pl):
            pending.append(key_for_consumable_menu_combat(pl)); M["heals_used"] += 1; return "5"
        boss = lv.get("is_boss")
        # 사람처럼: 일반 전투에서 체력이 반 밑이고 회복약이 없으면 후퇴한다 (FLEE=1일 때)
        if FLEE and not boss and pl.hp < pl.max_hp * 0.5: return "4"
        if boss:  # 사람처럼: 보스 학습 지수가 쌓이면 패킷 우회·바리케이드로 끊는다
            L = lv.get("learning_index", 0)
            if L >= 9 and pl.max_ram >= 2: return "3"
            if L >= 11: return "2"
        if pl.skill_slots and random.random() < 0.3: return "S"
        return "1"
    if line.startswith("item_cmd"): return "1"
    if line.startswith("scmd"): return "1"
    if line.startswith("save_choice"): return "N"
    if line.startswith("prep_cmd"):
        pl = P["p"]
        if pl.hp < pl.max_hp * 0.95 and best_heal(pl) and M.get("prep", 0) < 6:
            M["prep"] = M.get("prep", 0) + 1; return "1"
        return "3"
    if fn == "use_consumable_menu":
        pl = lv["self"]
        k = getattr(pl, "use_consumable_menu_bot", None) or best_heal(pl)
        pl.use_consumable_menu_bot = None
        if k:
            M["heals_used" if constants.CONSUMABLES_DB[k]["type"] == "hp" else "food_used"] += 1
        return key_for_consumable_menu(pl, k)
    if fn == "handle_trader": M["trader"] += 1; return "0"
    if fn == "_talk":  # 발칸 게이츠: 의뢰 수락·보고 (사람처럼 받는다)
        M["vulkan_talk"] = M.get("vulkan_talk", 0) + 1
        return "1"
    if fn == "handle_random_event": M["events"] += 1; return random.choice("123")
    if fn == "show_diary": return "0"
    if fn == "handle_session": M["sessions"] += 1
    return random.choice("123")

def key_for_consumable_menu_combat(pl):
    avail = [k for k, v in pl.consumables.items() if v > 0]
    return str(avail.index(best_heal(pl)) + 1)

_orig_read = ui.read_key
import forge
if os.environ.get("NO_HINT"):
    forge.HINT_TURN = 10**9
for m in (ui, combat, quest, story, player_mod, Main, core, updater, forge):
    if hasattr(m, "read_key"): m.read_key = bot_read_key
# "__USE__": 탐색 화면에서 소모품 메뉴 열기 (터미널 인벤토리 대신)
_orig_move_key = bot_read_key
def main_read_key():
    k = bot_read_key(2)
    if k == "__USE__":
        P["p"].use_consumable_menu()
        return bot_read_key(2) if not pending else pending.pop(0)
    return k
Main.read_key = main_read_key
# 전투 기록
_orig_combat = combat.combat_loop
def rec_combat(pl, is_boss=False, current_hp=None, enemy_type="drone"):
    rec = {"boss": is_boss, "type": enemy_type, "turn": pl.turn_count, "hp0": pl.hp, "max": pl.max_hp,
           "tier": pl.get_highest_tier(), "atk": pl.get_attack_power()}
    if is_boss:  # 보스 직전 상태 (보스전만 다시 돌려 보기 위해)
        g_ = P.get("g")
        M["forge_end"] = dict(g_.forge) if g_ is not None else None
        M["boss_state"] = {"d": pl.to_dict(), "eq": dict(pl.equipment), "inv": list(pl.inventory),
                           "power": pl.get_attack_power() + pl.get_gear_atk_bonus()}
    M["fights"].append(rec)
    try:
        r = _orig_combat(pl, is_boss=is_boss, current_hp=current_hp, enemy_type=enemy_type)
        rec["hp1"] = pl.hp; rec["out"] = "escape" if (isinstance(r, tuple) and r[0] is not None) else "win"
        return r
    except SystemExit:
        rec["hp1"] = pl.hp; rec["out"] = "death"; raise
for m in (Main, story):
    if hasattr(m, "combat_loop"): m.combat_loop = rec_combat
_orig_adv = quest.advance_quest
def adv(pl, kind, amount=1):
    if kind == "scrap": M["scrap_gain"] += amount
    return _orig_adv(pl, kind, amount)
for m in (Main, quest, story, player_mod, combat, Main.gm_bridge):
    if hasattr(m, "advance_quest"): m.advance_quest = adv
_orig_cq = quest._complete_quest
def cq(pl): M["quests_done"] += 1; return _orig_cq(pl)
quest._complete_quest = cq
_orig_ending = Main.run_ending
def ending(pl):
    M["result"] = "clear"; return _orig_ending(pl)
Main.run_ending = ending
out = io.StringIO()
sys.stdout = open(os.devnull, "w")
i18n.set_lang("ko")
try:
    Main.run_game()
except SystemExit:
    pass
except Exception as e:
    M["result"] = f"CRASH {type(e).__name__}: {e}"
    import traceback; M["tb"] = traceback.format_exc()[-800:]
pl = P["p"]
if M["result"] is None:
    last = M["fights"][-1] if M["fights"] else None
    M["result"] = ("death_boss" if last and last["boss"] else "death_combat") if last and last.get("out") == "death" else \
                  ("boss_timeout" if last and last["boss"] else "death_other")
if P.get("g") is not None:
    M["forge_last"] = dict(P["g"].forge)
if pl:
    M.update(turns=pl.turn_count, hp=pl.hp, hunger=pl.hunger, thirst=pl.thirst, scrap_end=pl.materials,
             tier=pl.get_highest_tier(), atk=pl.get_attack_power(), inv=len(pl.inventory), job=getattr(pl, "job_class", None))
sys.__stdout__.write(json.dumps(M, ensure_ascii=False) + "\n")
