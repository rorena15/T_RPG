"""장비 강화 (docs/기획/장비/Project_Equipment_Matrix_Engine.md).

1막 범위: 주무기만 강화한다. 재료는 고철(materials). 실패해도 파괴되지 않고, 실패할 때마다 다음 확률이 오른다(천장).
+8 ~ +10 시도에서 실패하면 내구도가 깎이고, 낮은 확률로 한 단계 내려간다. 내구도는 고철로 수리한다.
강화 상태는 아이템 ID별로 player.upgrades에 저장한다 ({item_id: {"k": 단계, "pity": 누적 보정, "dur": 내구도}}).
기획서의 티타늄 고철·정제 코어 플루이드 재료와 결속 페널티(Bio_Cost, RAM_Lock)는 아직 게임에 없어 넣지 않았다.
"""
import math
import random

import constants

MAX_LEVEL = 10
DUR_MAX = 100
RISK_FROM = 8                               # 이 단계 이상을 노리는 시도부터 실패 페널티
DROP_CHANCE = {8: 0.10, 9: 0.15, 10: 0.20}  # 실패 시 한 단계 하락 확률
DUR_LOSS = 10                               # 실패 시 내구도 감소
REPAIR_COST_PER_10 = 4                      # 내구도 10 수리에 드는 고철


def delta_power(k):
    """강화 단계별 추가 위력 ΔP(k)."""
    if k <= 0:
        return 0
    if k <= 3:
        return k * 10
    if k <= 6:
        return 30 + (k - 3) * 25
    if k <= 9:
        return 105 + (k - 6) * 50
    return 350


def _band(k_next):
    """다음 단계의 (기본 확률, 실패당 천장 가산)."""
    if k_next <= 3:
        return 0.80, 0.10
    if k_next <= 6:
        return 0.50, 0.15
    if k_next <= 9:
        return 0.25, 0.20
    return 0.10, 0.25


def level(player, item_id):
    return player.upgrades.get(item_id, {}).get("k", 0) if item_id else 0


def durability(player, item_id):
    return player.upgrades.get(item_id, {}).get("dur", DUR_MAX) if item_id else DUR_MAX


def effective_delta(player, item_id):
    """내구도를 반영한 추가 위력. 내구도가 0이면 강화 위력이 절반만 나온다."""
    dp = delta_power(level(player, item_id))
    return int(dp * (0.5 + 0.5 * durability(player, item_id) / DUR_MAX))


def repair_cost(player, item_id):
    lost = DUR_MAX - durability(player, item_id)
    return math.ceil(lost / 10) * REPAIR_COST_PER_10


def repair(player, item_id):
    """내구도 전부 수리. (결과, 쓴 고철). 결과: "ok" / "full" / "scrap"."""
    need = repair_cost(player, item_id)
    if need <= 0:
        return "full", 0
    if player.materials < need:
        return "scrap", need
    player.materials -= need
    player.upgrades[item_id]["dur"] = DUR_MAX
    return "ok", need


def chance(player, item_id):
    """다음 강화 성공 확률 (기본 + 누적 천장)."""
    k = level(player, item_id)
    base, _ = _band(k + 1)
    return min(1.0, base + player.upgrades.get(item_id, {}).get("pity", 0.0))


def cost(tier, k):
    """k → k+1 시도 1회에 드는 고철: max(1, floor(α·(k+1)^1.2)) × UPGRADE_COST_MULT. α는 T4·T3 1.0, 그 위 1.5."""
    alpha = 1.0 if tier >= 3 else 1.5
    return max(1, math.floor(alpha * (k + 1) ** 1.2)) * constants.UPGRADE_COST_MULT


def can_upgrade(slot):
    return slot == "main_weapon"


def try_upgrade(player, item_id, tier):
    """강화 1회 시도. (결과, 새 단계, 쓴 고철)을 돌려준다.
    결과: "ok" / "fail" / "drop"(실패 + 단계 하락) / "max" / "scrap" / "broken"(내구도 0, 수리 필요)."""
    k = level(player, item_id)
    if k >= MAX_LEVEL:
        return "max", k, 0
    if k + 1 >= RISK_FROM and durability(player, item_id) <= 0:
        return "broken", k, repair_cost(player, item_id)
    need = cost(tier, k)
    if player.materials < need:
        return "scrap", k, need
    player.materials -= need
    rec = player.upgrades.setdefault(item_id, {"k": 0, "pity": 0.0})
    if random.random() < chance(player, item_id):
        rec["k"], rec["pity"] = k + 1, 0.0
        return "ok", k + 1, need
    rec["pity"] = rec.get("pity", 0.0) + _band(k + 1)[1]
    if k + 1 >= RISK_FROM:
        rec["dur"] = max(0, rec.get("dur", DUR_MAX) - DUR_LOSS)
        if random.random() < DROP_CHANCE[k + 1]:
            rec["k"] = k - 1   # 천장 보정은 유지한다
            return "drop", k - 1, need
    return "fail", k, need
