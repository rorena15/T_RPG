"""기록 보관소: 적 이야기, 장면 이야기, 일기 조각. 보는 것만 있고 게임 수치에는 손대지 않는다.

열린 기록은 세이브와 따로 archive.json에 남겨 새 게임을 시작해도 이어진다 (결말 기록 endings.json과 같은 자리).
글은 locales/archive_<언어>.json에 있다. 글이 없는 항목은 목록에도 세지 않는다 (글을 나중에 채워도 된다).

열리는 때
  적      처음 만남 / 처음 이김 / 여러 번 이김 (ENEMY_STAGES). 보스는 3번
  장면    그 그림이 처음 화면에 나왔을 때 (scene_art.choose)
  일기    빈 탐색에서 줍는다 (roll_fragment). 묶음마다 줍는 곳이 다르다 (FRAGMENTS)
          일지의 마지막 장은 랜덤 이벤트 자리의 히든 이벤트로만 (hidden_ready, run_hidden_event)
빈 탐색은 원래 얻는 것이 없는 결과라, 조각을 얹어도 자원·장비 확률은 그대로다.
"""
import json
import os
import random

import i18n
from i18n import t

ENEMIES = ["drone", "bio_hound", "dogs", "security", "boss"]
ENEMY_SCENE = {"drone": "enemy_drones", "bio_hound": "enemy_hound", "dogs": "enemy_dogs",
               "security": "enemy_security", "boss": "enemy_collector"}
ENEMY_STAGES = {"boss": (0, 1, 3)}   # 단계별로 필요한 처치 수 (0 = 만나기만 하면)
DEFAULT_STAGES = (0, 1, 10)

# 장면 이야기는 랜드마크만 (지금 그곳을 아는 사람의 말). 같은 곳의 붕괴 전 목소리는 일기 묶음 B
SCENES = ["lm_school", "lm_hospital", "lm_station", "lm_highway", "lm_amusement", "lm_mall",
          "lm_cathedral", "lm_subway", "lm_powerplant", "lm_apartments", "lm_bridge", "lm_airport"]

# 일기 조각: (id, 묶음, 줍는 곳). None = 어디서나, 장면 이름 = 그 칸에서만, "hidden" = 히든 이벤트로만
#   A 먼저 버려진 자의 일지: 시간 순으로 이어진 10편 (줍는 순서는 무작위, 보관소에서는 번호순) + 숨은 마지막 장
#   B 구시대의 기록: 랜드마크마다 붕괴 직전 그곳 사람의 목소리
#   C 쫓겨난 자들의 증언: 방벽이 보이는 경계 지대 칸에서
FRAGMENTS = [(f"a{i:02d}", "a", None) for i in range(1, 11)] + [("a11", "a", "hidden")] + \
    [(f"b{i:02d}", "b", s) for i, s in enumerate(SCENES, 1)] + \
    [(f"c{i:02d}", "c", "border_zone") for i in range(1, 7)]
SERIES = ["a", "b", "c"]
FRAGMENT_CHANCE = 0.35   # 빈 탐색에서 주울 확률 (주울 것이 남아 있을 때)
HIDDEN_ID = "a11"
HIDDEN_NEED = 5          # 히든 이벤트: 일지 A를 이만큼 모은 뒤부터
HIDDEN_CHANCE = 0.03     # 랜덤 이벤트 자리에서 이 확률로 (평생 한 번)


def _path():
    from frozen_compat import user_dir
    return os.path.join(user_dir(), "archive.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    return {"enemies": dict(d.get("enemies", {})), "scenes": list(d.get("scenes", [])),
            "fragments": list(d.get("fragments", []))}


def _save(d):
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 글 ───────────────────────────────────────────────────────────────────
_text = {}


def text():
    """지금 언어의 보관소 글. {"enemy": {키: {"name", "stages": [..]}}, "scene": {..}, "fragment": {..}}"""
    lang = i18n.LANG
    if lang not in _text:
        try:
            with open(i18n._res(os.path.join("locales", f"archive_{lang}.json")), encoding="utf-8") as f:
                _text[lang] = json.load(f)
        except Exception:
            _text[lang] = {}
    return _text[lang]


def enemy_entry(key):
    e = text().get("enemy", {}).get(key)
    return e if e and e.get("stages") else None


def scene_entry(scene):
    return text().get("scene", {}).get(scene)


def fragment_entry(fid):
    return text().get("fragment", {}).get(fid)


def stages(key):
    return ENEMY_STAGES.get(key, DEFAULT_STAGES)


# ── 열기 ─────────────────────────────────────────────────────────────────
def enemy_key(enemy_type, is_boss=False):
    return "boss" if is_boss else (enemy_type if enemy_type in ENEMY_SCENE else "drone")


def _enemy_open(rec, key):
    """기록으로 본 이 적의 열린 단계 수 (0 = 아직 못 만남)."""
    if not rec.get("met"):
        return 0
    kills = rec.get("kills", 0)
    return sum(1 for need in stages(key) if kills >= need)


def _notice(kind, name):
    return t('arc_new', kind=t(f'arc_kind_{kind}'), name=name)


def meet_enemy(enemy_type, is_boss=False):
    """전투를 시작할 때. 새로 열린 단계가 있으면 알림 문장, 없으면 None."""
    key = enemy_key(enemy_type, is_boss)
    d = load()
    rec = d["enemies"].setdefault(key, {"met": False, "kills": 0})
    before = _enemy_open(rec, key)
    rec["met"] = True
    _save(d)
    entry = enemy_entry(key)
    return _notice("enemy", entry["name"]) if entry and _enemy_open(rec, key) > before else None


def defeat_enemy(enemy_type, is_boss=False):
    key = enemy_key(enemy_type, is_boss)
    d = load()
    rec = d["enemies"].setdefault(key, {"met": True, "kills": 0})
    before = _enemy_open(rec, key)
    rec["met"] = True
    rec["kills"] = rec.get("kills", 0) + 1
    _save(d)
    entry = enemy_entry(key)
    return _notice("enemy", entry["name"]) if entry and _enemy_open(rec, key) > before else None


def see_scene(scene):
    """그림이 처음 화면에 나왔을 때 (알림은 띄우지 않는다: 이벤트를 읽는 중이라)."""
    if scene not in SCENES:
        return
    d = load()
    if scene not in d["scenes"]:
        d["scenes"].append(scene)
        _save(d)


def roll_fragment(player, grid, rng=random):
    """빈 탐색 뒤에 부른다. 조각을 주우면 알림 문장, 아니면 None."""
    d = load()
    if rng.random() >= FRAGMENT_CHANCE:
        return None
    here = None
    try:
        import scene_art
        from event_view import JUNKYARD
        here = scene_art.tile_scene(JUNKYARD, grid.player_pos)
    except Exception:
        pass
    pool = [fid for fid, _, where in FRAGMENTS
            if fid not in d["fragments"] and fragment_entry(fid) and where in (None, here)]
    if not pool:
        return None
    fid = rng.choice(pool)
    d["fragments"].append(fid)
    _save(d)
    key = 'arc_fragment_found_a' if fid.startswith("a") else 'arc_fragment_found'   # 일지 A는 찢겨 나온 공책 한 장
    return t(key, title=fragment_entry(fid)["title"])


# ── 보기 ─────────────────────────────────────────────────────────────────
def enemy_list():
    """[(키, 이름 또는 None(못 만남), 열린 단계 수, 전체 단계 수)]. 글이 있는 적만."""
    d = load()
    out = []
    for key in ENEMIES:
        entry = enemy_entry(key)
        if not entry:
            continue
        n = _enemy_open(d["enemies"].get(key, {}), key)
        total = min(len(stages(key)), len(entry["stages"]))
        out.append((key, entry["name"] if n else None, min(n, total), total))
    return out


def enemy_pages(key):
    """적 하나의 읽을 줄들. 열린 단계는 글, 닫힌 단계는 여는 조건."""
    entry = enemy_entry(key)
    rec = load()["enemies"].get(key, {})
    n = _enemy_open(rec, key)
    lines = []
    for i, body in enumerate(entry["stages"][:len(stages(key))]):
        if i:
            lines.append("")
        if i < n:
            lines += body.split("\n")
        else:
            lines.append(t('arc_locked_kills', n=stages(key)[i]))
    return lines


def scene_list():
    """[(장면, 제목 또는 None)]. 글이 있는 장면만."""
    seen = set(load()["scenes"])
    return [(s, scene_entry(s)["title"] if s in seen else None) for s in SCENES if scene_entry(s)]


def fragment_list(series):
    """[(id, 제목 또는 None)]. 숨은 조각은 찾기 전까지 목록에 없다."""
    have = set(load()["fragments"])
    return [(fid, fragment_entry(fid)["title"] if fid in have else None)
            for fid, s, where in FRAGMENTS
            if s == series and fragment_entry(fid) and (where != "hidden" or fid in have)]


# ── 히든 이벤트: 죽은 사람의 품에 안긴 일지 ─────────────────────────────────
def hidden_ready(rng=random):
    """랜덤 이벤트 자리에서 부른다. 이번에 히든 이벤트를 띄울지."""
    if not (text().get("hidden") and fragment_entry(HIDDEN_ID)):
        return False
    have = load()["fragments"]
    if HIDDEN_ID in have or sum(1 for f in have if f.startswith("a")) < HIDDEN_NEED:
        return False
    return rng.random() < HIDDEN_CHANCE


def take_hidden():
    """히든 이벤트를 본 뒤: 마지막 장을 기록한다. 알림 문장."""
    d = load()
    if HIDDEN_ID not in d["fragments"]:
        d["fragments"].append(HIDDEN_ID)
        _save(d)
    return t('arc_fragment_found', title=fragment_entry(HIDDEN_ID)["title"])


def counts():
    """{분류: (열린 수, 전체)}. 결말 기록도 같이 센다."""
    import endings
    e = endings.load()
    out = {"endings": (sum(x in e["endings"] for x in endings.ALL) + sum(j in e["jobs"] for j in endings.JOBS),
                       len(endings.ALL) + len(endings.JOBS))}
    el = enemy_list()
    out["enemy"] = (sum(n for _, _, n, _ in el), sum(tot for _, _, _, tot in el))
    sl = scene_list()
    out["scene"] = (sum(1 for _, x in sl if x), len(sl))
    fl = [x for s in SERIES for x in fragment_list(s)]
    out["fragment"] = (sum(1 for _, x in fl if x), len(fl))
    return out
