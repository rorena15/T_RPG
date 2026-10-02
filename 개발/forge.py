"""강화소 퀘스트 (docs/기획/Project_NPC_Quest.md의 스크랩 연합 노장 발칸 게이츠).

강화소는 처음부터 있지 않다. 맵 어딘가(grid.forge_pos, 처음엔 안 보임)에서 발칸 게이츠를 만나
"대장간 재가동" 의뢰를 받고, 주변 적을 처치하고 고철을 모아 돌아가 보고하면 그 칸에 강화소가 생긴다.
진행 상태는 grid.forge = {"stage": 0 못 만남 / 1 의뢰 중 / 2 완공, "kills0": 의뢰 받을 때 처치 수}.
"""
import time

import constants
import sound
from i18n import t
from ui import clear_screen, print_divider, print_header, read_key, type_text, wait_for_keypress, log_diary

NEED_KILLS = 3
NEED_SCRAP = 40
HINT_TURN = 12   # 이때까지 발칸을 못 만났으면 쇳물 냄새로 방향을 알려 준다 (강화 없이는 보스를 못 이기니까)


def hinted(grid):
    return bool(grid.forge.get("hint")) and not grid.forge_known()


def direction(grid):
    """지금 자리에서 발칸 쪽 방위 (W가 북, D가 동)."""
    dx = grid.forge_pos[0] - grid.player_pos[0]
    dy = grid.forge_pos[1] - grid.player_pos[1]
    ns = "n" if dy > 0 else ("s" if dy < 0 else "")
    ew = "e" if dx > 0 else ("w" if dx < 0 else "")
    return t(f"dir_{ns + ew}") if ns or ew else t("dir_here")


def check_hint(player, grid):
    """맵에서 매 턴 부른다: HINT_TURN이 지나도 못 만났으면 한 번 소리를 들려주고 미니맵에 흐리게 표시한다."""
    if grid.forge_known() or grid.forge.get("hint") or player.turn_count < HINT_TURN:
        return False
    grid.forge["hint"] = True
    sound.sfx("amb_clang")
    print(t('forge_hint_node' if getattr(grid, "is_node_map", False) else 'forge_hint', dir=direction(grid), d=grid.forge_dist()))
    log_diary(player, t('forge_hint_diary'))
    return True


def stage(grid):
    return grid.forge.get("stage", 0)


def built(grid):
    return stage(grid) >= 2


def kills(player, grid):
    return max(0, player.enemies_defeated - grid.forge.get("kills0", 0))


def ready(player, grid):
    return kills(player, grid) >= NEED_KILLS and player.materials >= NEED_SCRAP


def progress_text(player, grid):
    """의뢰 진행 한 줄 (맵 화면·터미널 상태)."""
    return t('forge_q_progress', k=min(kills(player, grid), NEED_KILLS), nk=NEED_KILLS,
             s=min(player.materials, NEED_SCRAP), ns=NEED_SCRAP, d=grid.forge_dist())


# ── 대화 ─────────────────────────────────────────────────────────────────
def _talk(player, grid, title, prose, choices):
    """발칸 게이츠와의 대화 한 장면. 고른 키를 돌려준다 ('1'..)."""
    from gui import get_terminal
    if get_terminal():
        from event_view import EventView, JUNKYARD
        view = EventView(get_terminal(), player, grid, JUNKYARD, scene="forge")
        view.open()
        try:
            view.add("title", tag=t('forge_npc_tag'), title=title)
            view.add("prose", lines=prose)
            menu = view.add("choices", items=choices)
            view.footer = [("↑↓", t('ui_select')), ("Enter", t('forge_key_ok'))]
            return view.choose(menu, len(choices))
        finally:
            view.close()
    clear_screen()
    print_header(title)
    for line in prose:
        type_text("  " + line, 0.015)
    print_divider()
    for k, label in choices:
        print(f"  [{k}] {label}")
    while True:
        k = read_key()
        if any(k == c for c, _ in choices):
            return k


def meet(player, grid):
    """강화소 칸에 처음 들어왔을 때 (의뢰 전). 수락하면 stage 1."""
    k = _talk(player, grid, t('forge_meet_title'),
              [t('forge_meet_1'), t('forge_meet_2'), t('forge_meet_3', nk=NEED_KILLS, ns=NEED_SCRAP)],
              [("1", t('forge_meet_accept')), ("2", t('forge_meet_later'))])
    if k == "1":
        grid.forge = {"stage": 1, "kills0": player.enemies_defeated}
        log_diary(player, t('forge_log_accept'))
        print(t('forge_accepted', nk=NEED_KILLS, ns=NEED_SCRAP))
    else:
        grid.forge = {"stage": 0, "met": True}
        print(t('forge_declined'))
    time.sleep(0.8)


def visit(player, grid):
    """강화소 칸에서 U. 의뢰 전이면 다시 제안, 의뢰 중이면 보고, 완공이면 강화소 화면."""
    s = stage(grid)
    if s == 0:
        return meet(player, grid)
    if s >= 2:
        return player.manage_inventory(forge=True)
    if not ready(player, grid):
        _talk(player, grid, t('forge_wait_title'),
              [t('forge_wait_1'), progress_text(player, grid)], [("1", t('forge_wait_ok'))])
        return
    k = _talk(player, grid, t('forge_done_title'),
              [t('forge_done_1', ns=NEED_SCRAP), t('forge_done_2')],
              [("1", t('forge_done_give', ns=NEED_SCRAP)), ("2", t('forge_meet_later'))])
    if k != "1":
        return
    player.materials -= NEED_SCRAP
    grid.forge = {"stage": 2}
    sound.sfx("anvil")
    log_diary(player, t('forge_log_built'))
    _talk(player, grid, t('forge_built_title'), [t('forge_built_1'), t('forge_built_2')], [("1", t('forge_built_ok'))])


def on_enter(player, grid, is_new_tile):
    """강화소 칸에 들어왔을 때. 대화를 열었으면 True (그 칸의 세션·조우는 건너뛴다)."""
    if not grid.at_forge():
        return False
    s = stage(grid)
    if s == 0 and not grid.forge.get("met"):
        print(t('forge_signal'))
        time.sleep(1.0)
        meet(player, grid)
        return True
    if s == 1 and ready(player, grid):
        print(t('forge_report_hint'))
    elif s >= 2:
        print(t('forge_arrive'))
    else:
        print(t('forge_arrive_site'))
    time.sleep(0.8)
    return False
