"""결말 판정과 결말 기록.

1막을 끝내면 마지막 상태로 결말 하나가 정해진다. 조건이 여럿 맞으면 CLEAR 목록에서
앞에 있는 것 (드문 것부터). 죽음·아사·시간 초과도 결말로 친다.
본 결말과 각성한 직업은 세이브와 따로 endings.json에 남겨, 새 게임을 시작해도 지워지지 않는다.

기준값은 밸런스 봇 판 기록(보스 도달·클리어 판)의 분포로 정했다 (tools/balance/README.md).
"""
import json
import os
import sys

from i18n import t

CLEAR = ["harmonizer", "scarred", "flawless", "swift", "ghost", "hoarder",
         "hunted", "hunter", "forge", "unfinished", "refused", "pioneer"]
BAD = ["death_drone", "death_bio", "death_dogs", "death_sec",
       "boss_death", "starve_hunger", "starve_thirst", "timeout"]
ALL = CLEAR + BAD
JOBS = ["combat", "mech", "net", "balanced"]

SCARRED_HP = 0.25     # 보스를 잡고 체력이 최대의 이 비율 이하
SWIFT_TURNS = 60      # 이 턴 안에 끝냄
GHOST_ALERT = 10      # 보스전 직전 경보가 이 이하
HUNTED_ALERT = 90     # 보스전 직전 경보가 이 이상
HUNTER_KILLS = 30     # 처치 수
HOARDER_SCRAP = 500   # 남은 고철
ROW = 4               # 기록 화면 한 줄에 결말 몇 개


def _path():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(".")
    return os.path.join(base, "endings.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return {"endings": list(d.get("endings", [])), "jobs": list(d.get("jobs", []))}
    except Exception:
        return {"endings": [], "jobs": []}


def _save(d):
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clear_ending(player, grid):
    """1막을 끝냈을 때의 결말."""
    import forge
    alert = getattr(player, "boss_alert", player.alert_level)
    fs = grid.forge if grid is not None else {}
    if player.job_class == "balanced":
        return "harmonizer"
    if player.hp <= player.max_hp * SCARRED_HP:
        return "scarred"
    if player.hp >= player.max_hp:
        return "flawless"
    if player.turn_count <= SWIFT_TURNS:
        return "swift"
    if alert <= GHOST_ALERT:
        return "ghost"
    if player.materials >= HOARDER_SCRAP:   # 강화에 쓰지 않고 쌓아 둔 쪽을 먼저 본다
        return "hoarder"
    if alert >= HUNTED_ALERT:
        return "hunted"
    if player.enemies_defeated >= HUNTER_KILLS:
        return "hunter"
    if grid is not None and forge.built(grid):
        return "forge"
    if fs.get("stage", 0) == 1:
        return "unfinished"
    if fs.get("met"):
        return "refused"
    return "pioneer"


def death_key(enemy_type):
    import constants
    spec = constants.ENEMY_TYPES.get(enemy_type) or constants.ENEMY_TYPES["drone"]
    key = f"death_{spec['key']}"
    return key if key in BAD else "death_drone"


def unlock(ending, job=None):
    """결말(과 직업)을 기록한다. 처음 본 결말이면 True."""
    d = load()
    new = ending not in d["endings"]
    if new:
        d["endings"].append(ending)
    if job and job not in d["jobs"]:
        d["jobs"].append(job)
    _save(d)
    return new


def card(ending, job=None):
    """결말 이름 + 지금까지 본 결말 목록. print로 찍을 줄들."""
    new = unlock(ending, job)
    d = load()
    lines = [t('ending_rec_title', name=t(f'ending_name_{ending}')) + (t('ending_rec_new') if new else "")]
    lines.append(t('ending_rec_count', n=sum(e in d["endings"] for e in ALL), total=len(ALL)))
    for group in (CLEAR, BAD):
        names = [t(f'ending_name_{e}') if e in d["endings"] else "???" for e in group]
        lines += ["  " + " · ".join(names[i:i + ROW]) for i in range(0, len(names), ROW)]
    lines.append(t('ending_rec_jobs', n=sum(j in d["jobs"] for j in JOBS), total=len(JOBS)))
    return lines
