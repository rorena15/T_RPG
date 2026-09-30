"""성향 단계 보너스.

스토리·이벤트 선택으로 쌓이는 성향(kinetic / scrap / cyber)이 TIER_AT에 닿을 때마다 그 자리에서 힘이 된다.
각성(보스 뒤 직업)은 그 끝이고, 1막 도중에도 선택이 빌드로 느껴지게 한다.

- kinetic: 주무기 공격 피해 배율
- scrap:   고철 획득(파밍·분해·전투 승리) 배율, 2단계부터 바리케이드가 더 막고, 3단계는 전투 중 매 턴 HP 수리
- cyber:   1단계 패킷 우회 RAM 비용 −1, 2단계 패킷 우회가 그 턴의 반격을 막고 다음 공격 피해 +EXPOSE_MULT, 3단계 전투 승리 때 RAM +1 · 보스 학습 지수 상승 −1

보스 체력은 플레이어 공격력에 맞춰 커지므로(combat.py), 강화로 얻는 힘은 보스 앞에서 상쇄된다.
그래서 scrap·cyber에도 보스전에서 쓸모 있는 효과를 준다 (봇 비교: tools/balance/verify.py --focus).

처음 닿은 단계는 player.trait_seen에 남겨 한 번만 알린다 (세이브에 저장).
"""
from i18n import t

TIER_AT = (2, 4, 6)                    # 성향 값이 이 이상이면 1·2·3단계
KINETIC_DMG = (1.0, 1.06, 1.12, 1.18)  # 단계별 공격 피해 배율
BARRICADE_BLOCK = (0.5, 0.5, 0.65, 0.65)  # scrap 단계별 바리케이드가 막는 비율 (기본 50%)
SCRAP_REPAIR = 0.03                    # scrap 3단계: 전투 중 매 턴 최대 HP의 이 비율만큼 수리
SCRAP_GAIN = (1.0, 1.25, 1.5, 1.75)    # 단계별 고철 획득 배율
EXPOSE_MULT = 1.3                      # cyber 2단계: 교란을 맞은 적에게 다음 주무기 공격 피해 배율
RAM_CAP = 8                            # cyber 3단계로 채우는 RAM 상한 (스킬 회복 상한과 같음)
KEYS = ("kinetic", "scrap", "cyber")


def tier(player, key):
    v = player.weights.get(key, 0)
    return sum(v >= x for x in TIER_AT)


def dmg_mult(player):
    return KINETIC_DMG[tier(player, "kinetic")]


def scrap(player, amount):
    """고철 획득량에 scrap 보너스를 얹는다."""
    return int(round(amount * SCRAP_GAIN[tier(player, "scrap")])) if amount > 0 else amount


def jam_cost(player):
    return 1 if tier(player, "cyber") >= 1 else 2


def barricade_block(player):
    return BARRICADE_BLOCK[tier(player, "scrap")]


def turn_repair(player):
    """scrap 3단계: 전투 턴 끝 수리량."""
    return int(player.max_hp * SCRAP_REPAIR) if tier(player, "scrap") >= 3 else 0


def jam_blocks_counter(player):
    return tier(player, "cyber") >= 2


def win_ram(player):
    """전투 승리 뒤 RAM 회복량 (cyber 3단계). 실제로 채운 양을 돌려준다."""
    if tier(player, "cyber") >= 3 and player.max_ram < RAM_CAP:
        player.max_ram += 1
        return 1
    return 0


def learn_suppress(player):
    return 1 if tier(player, "cyber") >= 3 else 0


def check_new(player):
    """새로 닿은 단계의 알림 문구들 (한 번씩만)."""
    seen = getattr(player, "trait_seen", None)
    if seen is None:
        seen = player.trait_seen = {}
    lines = []
    for k in KEYS:
        now = tier(player, k)
        while seen.get(k, 0) < now:
            seen[k] = seen.get(k, 0) + 1
            lines.append(t(f'trait_{k}_{seen[k]}'))
    return lines
