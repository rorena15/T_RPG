"""결말 판정과 결말 기록.

1막을 끝내면 마지막 상태로 결말 하나가 정해진다 (추적 > 대장간 > 벼랑 끝 > 개척자 순).
죽음·아사·시간 초과도 결말로 친다. 본 결말과 각성한 직업은 세이브와 따로
endings.json에 남겨, 새 게임을 시작해도 지워지지 않는다.
"""
import json
import os
import sys

from i18n import t

CLEAR = ["pioneer", "forge", "hunted", "scarred"]
BAD = ["death", "boss_death", "starve", "timeout"]
ALL = CLEAR + BAD
JOBS = ["combat", "mech", "net", "balanced"]

HUNTED_ALERT = 70     # 경보 수치가 이 이상이면 네오 아크에 추적당한 채 끝난다
SCARRED_HP = 0.25     # 체력이 최대의 이 비율 이하면 벼랑 끝에서 끝난다


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
    if player.alert_level >= HUNTED_ALERT:
        return "hunted"
    if grid is not None and forge.built(grid):
        return "forge"
    if player.hp <= player.max_hp * SCARRED_HP:
        return "scarred"
    return "pioneer"


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
    names = [t(f'ending_name_{e}') if e in d["endings"] else "???" for e in ALL]
    lines.append("  " + " · ".join(names[:len(CLEAR)]))
    lines.append("  " + " · ".join(names[len(CLEAR):]))
    lines.append(t('ending_rec_jobs', n=sum(j in d["jobs"] for j in JOBS), total=len(JOBS)))
    return lines
