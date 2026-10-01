"""플레이 시간 기록.

세이브에 누적 플레이 시간(player.play_seconds)을 남기고, 엔딩·게임 오버 화면에 보여 주며,
한 판이 끝날 때 진단 기록에 요약(stat)을 남긴다. 실제 플레이 분량을 재는 근거로 쓴다.

자리를 비운 시간은 세지 않는다: 맵에서 입력을 기다린 시간은 한 번에 IDLE_CAP까지만,
입력 뒤 이벤트·전투를 처리한 시간은 ACTIVE_CAP까지만 더한다.
"""
import time

import diag
from i18n import t

IDLE_CAP = 300       # 맵에서 5분 넘게 입력이 없으면 자리 비움으로 본다
ACTIVE_CAP = 1800    # 한 번의 이벤트·전투가 30분을 넘게 걸린 것으로는 세지 않는다

_last = None


def start():
    """새 게임·불러오기 직후. 여기부터 센다."""
    global _last
    _last = time.monotonic()


def mark(player, cap=ACTIVE_CAP):
    """지난 표시 이후 흐른 시간을 cap까지 더한다."""
    global _last
    now = time.monotonic()
    if _last is not None:
        player.play_seconds = getattr(player, "play_seconds", 0.0) + min(now - _last, cap)
    _last = now


def fmt(seconds):
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return t('playtime_hm', h=h, m=m) if h else t('playtime_m', m=max(1, m) if seconds >= 30 else 0)


def finish(player, outcome):
    """한 판이 끝났을 때 (clear / death / starve / timeout). 시간을 마감하고 진단 기록에 요약을 남긴다."""
    mark(player)
    try:
        import constants
        import gm_bridge
        from sys_log import SESSION_ID
        diag.write("stat", {
            "outcome": outcome, "play_seconds": round(player.play_seconds), "turns": player.turn_count,
            "difficulty": player.difficulty, "enemies": player.enemies_defeated, "gm_mode": gm_bridge.get_mode(),
            "version": constants.GAME_VERSION,
        }, SESSION_ID)
    except Exception:
        pass
    return fmt(player.play_seconds)
