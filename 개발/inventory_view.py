"""인벤토리 화면 (이벤트 화면과 같은 틀, 방향키 조작).

탭: 장비 슬롯 / 가방 / 소모품 (←→ 또는 Tab). 목록은 ↑↓, 아래에 고른 항목의 상세.
Enter: 가방=장착, 슬롯=해제, 소모품=사용.  D: 가방 항목 분해(한 번 더 D로 확인).  0: 돌아가기.
규칙은 player.py의 예전 터미널 인벤토리와 같다 (장착 슬롯 자동 인식, 장착 중 분해 불가, 분해 고철 15~30).
"""
import random

import pygame

import constants
import upgrade
from core import get_equipment_data
from event_view import AMBER, BG, EventView, GREEN, INK, INK_DIM, INK_FAINT, JUNKYARD, RED, TEAL, VIOLET, _lerp
from i18n import db_t, t
from quest import advance_quest

TABS = ["slots", "bag", "consumables"]
TAB_KEY = {"slots": "inv_tab_slots", "bag": "inv_tab_bag", "consumables": "inv_tab_cons"}
TIER_COLOR = {0: (236, 196, 92), 1: VIOLET, 2: TEAL, 3: INK, 4: INK_DIM}
ROW_H = 30
VISIBLE = 13


class InventoryView(EventView):
    def __init__(self, term, player, tab="bag"):
        super().__init__(term, player, None, JUNKYARD, scene="forge")
        self.tab = tab
        self.sel = {k: 0 for k in TABS}
        self.msg = []           # 방금 한 일
        self.confirm = None     # 분해 확인 중인 항목 id
        self.msg_warn = False   # 분해 관련 알림은 호박색

    # ── 목록 ─────────────────────────────────────────────────────────────
    def rows(self):
        """지금 탭의 목록. 가방·장비·소모품이 바뀔 때만 다시 만든다 (매 프레임 장비 조회를 하면 느려졌다)."""
        p = self.player
        key = (self.tab, tuple(p.inventory), tuple(sorted(p.equipment.items())), tuple(sorted(p.consumables.items())))
        if key != getattr(self, "_rows_key", None):
            self._rows_key, self._rows = key, self._build_rows()
        return self._rows

    def _build_rows(self):
        p = self.player
        if self.tab == "slots":
            out = []
            for sk in constants.SLOT_DISPLAY:
                label = constants.slot_label(sk)
                eid = p.equipment.get(sk)
                d = get_equipment_data(eid) if eid and eid != "WEAPON_NONE" else None
                out.append({"kind": "slot", "slot": sk, "label": label, "id": eid if d else None, "d": d})
            return out
        if self.tab == "bag":
            equipped = set(p.equipment.values())
            return [{"kind": "item", "index": i, "id": iid, "d": get_equipment_data(iid), "eq": iid in equipped}
                    for i, iid in enumerate(p.inventory)]
        return [{"kind": "cons", "key": k, "n": v, "d": constants.CONSUMABLES_DB[k]}
                for k, v in p.consumables.items() if v > 0 and k in constants.CONSUMABLES_DB]

    # ── 동작 ─────────────────────────────────────────────────────────────
    def _label(self, d, iid):
        """장비 이름 + 강화 단계 (+k)."""
        k = upgrade.level(self.player, iid)
        return db_t(d, "name") + (f" +{k}" if k else "")

    def _power(self, d, iid):
        return d["power"] + upgrade.effective_delta(self.player, iid)

    def upgrade_row(self, row):
        """R: 고른 장비(주무기)를 강화 1회 시도한다."""
        self.confirm = None
        if row is None or row["kind"] not in ("slot", "item") or not row.get("d"):
            return
        d, iid = row["d"], row["id"]
        self.msg_warn = True
        if not upgrade.can_upgrade(d.get("slot")):
            self.msg = [t('upg_only_weapon')]
            return
        res, k, spent = upgrade.try_upgrade(self.player, iid, d.get("tier", 4))
        if res == "ok":
            self.msg_warn = False
            self.msg = [t('upg_ok', name=db_t(d, 'name'), k=k, pw=self._power(d, iid), cost=spent)]
        elif res in ("fail", "drop"):
            key = 'upg_drop' if res == "drop" else ('upg_fail_dur' if k + 1 >= upgrade.RISK_FROM else 'upg_fail')
            self.msg = [t(key, name=db_t(d, 'name'), k=k, dur=upgrade.durability(self.player, iid),
                          pct=upgrade.chance(self.player, iid) * 100, cost=spent)]
        elif res == "scrap":
            self.msg = [t('upg_scrap', need=spent, have=self.player.materials)]
        elif res == "broken":
            self.msg = [t('upg_broken', need=spent)]
        else:
            self.msg = [t('upg_max', name=db_t(d, 'name'))]

    def repair_row(self, row):
        """F: 고른 주무기의 내구도를 수리한다."""
        self.confirm = None
        if row is None or row["kind"] not in ("slot", "item") or not row.get("d"):
            return
        d, iid = row["d"], row["id"]
        self.msg_warn = True
        if not upgrade.can_upgrade(d.get("slot")):
            self.msg = [t('upg_only_weapon')]
            return
        res, spent = upgrade.repair(self.player, iid)
        if res == "ok":
            self.msg_warn = False
            self.msg = [t('rep_ok', name=db_t(d, 'name'), cost=spent)]
        elif res == "scrap":
            self.msg = [t('upg_scrap', need=spent, have=self.player.materials)]
        else:
            self.msg = [t('rep_full', name=db_t(d, 'name'))]

    def act(self, row, dismantle=False):
        p = self.player
        if row is None:
            return
        self.msg_warn = dismantle
        if dismantle:
            if row["kind"] != "item":
                return
            if row["eq"]:
                self.msg = [t('inv_dismantle_equipped')]
                return
            if self.confirm != row["id"]:
                self.confirm = row["id"]
                self.msg = [t('inv_confirm_dismantle', name=db_t(row['d'], 'name'))]
                return
            p.inventory.pop(row["index"])
            gained = random.randint(15, 30)
            p.materials += gained
            advance_quest(p, "scrap", gained)
            self.msg = [t('inv_dismantled', name=db_t(row['d'], 'name'), gained=gained)]
            self.confirm = None
            return
        self.confirm = None
        if row["kind"] == "item":
            d = row["d"]
            sk = d.get("slot", "main_weapon")
            prev = p.equipment.get(sk)
            p.equipment[sk] = row["id"]
            self.msg = [t('inv_equipped', name=db_t(d, 'name'), slot=constants.slot_label(sk))]
            if prev and prev != "WEAPON_NONE" and prev != row["id"]:
                self.msg.append(t('inv_replaced', name=db_t(get_equipment_data(prev), 'name')))
        elif row["kind"] == "slot":
            if row["id"]:
                p.equipment[row["slot"]] = constants.SLOT_DEFAULTS[row["slot"]]
                self.msg = [t('inv_unequipped', name=db_t(row['d'], 'name'), slot=row['label'])]
            else:
                self.msg = [t('inv_slot_empty', slot=row['label'])]
        elif row["kind"] == "cons":
            item, key = row["d"], row["key"]
            p.consumables[key] -= 1
            if item["type"] == "hp":
                amt = int(p.max_hp * item["val"]) if item["is_percent"] else item["val"]
                p.hp = min(p.max_hp, p.hp + amt)
                self.msg = [t('consumable_used_hp', name=db_t(item, 'name'), amt=amt)]
            else:
                p.hunger = min(100, p.hunger + item["hunger"])
                p.thirst = min(100, p.thirst + item["thirst"])
                self.msg = [t('consumable_used_food', name=db_t(item, 'name'))]

    # ── 그리기 (오른쪽 칸) ─────────────────────────────────────────────────
    def _draw_column(self, c, W, H):
        x = self._col_x
        width = W - x - 36
        y = 40
        c.blit(self.f_mono.render(t('inv_view_header', n=self.player.materials), True, AMBER), (x, y))
        y += 26
        tx = x
        for tab in TABS:
            on = tab == self.tab
            g = self.f_title.render(t(TAB_KEY[tab]), True, INK if on else INK_FAINT) if on else \
                self.f_sans.render(t(TAB_KEY[tab]), True, INK_FAINT)
            c.blit(g, (tx, y + (0 if on else 10)))
            if on:
                pygame.draw.line(c, AMBER, (tx, y + 42), (tx + g.get_width(), y + 42), 2)
            tx += g.get_width() + 26
        y += 60

        rows = self.rows()
        sel = min(self.sel[self.tab], max(0, len(rows) - 1))
        self.sel[self.tab] = sel
        if not rows:
            empty = {"bag": t('inv_empty').strip(), "consumables": t('consumable_empty').strip()}.get(self.tab, "")
            c.blit(self.f_serif.render(empty, True, INK_DIM), (x, y))
        top = max(0, min(sel - VISIBLE // 2, len(rows) - VISIBLE))
        for i, row in enumerate(rows[top:top + VISIBLE], start=top):
            ry = y + (i - top) * ROW_H
            on = i == sel
            if on:
                band = pygame.Surface((width + 12, ROW_H - 2), pygame.SRCALPHA)
                band.fill((*AMBER, 24))
                c.blit(band, (x - 12, ry - 3))
                pygame.draw.line(c, AMBER, (x - 12, ry - 3), (x - 12, ry + ROW_H - 6), 2)
            self._draw_row(c, row, x + (6 if on else 0), ry, width, on)
        y += VISIBLE * ROW_H + 10

        # 상세
        pygame.draw.line(c, (40, 38, 36), (x, y), (x + width, y))
        y += 14
        if rows:
            for text, col in self._detail(rows[sel]):
                for ln in self._wrap(self.f_sans, text, width):
                    c.blit(self.f_sans.render(ln, True, col), (x, y))
                    y += 24
        y += 8
        for m in self.msg:
            for ln in self._wrap(self.f_serif, m.strip(), width):
                c.blit(self.f_serif.render(ln, True, AMBER if self.msg_warn else GREEN), (x, y))
                y += 28

    def _draw_row(self, c, row, x, y, width, on):
        ink = INK if on else _lerp(INK, BG, 0.15)
        if row["kind"] == "slot":
            c.blit(self.f_sans.render(row["label"], True, INK_DIM), (x, y))
            name = self._label(row["d"], row["id"]) if row["d"] else t('inv_not_equipped').strip()
            col = TIER_COLOR.get(row["d"].get("tier", 4), ink) if row["d"] else INK_FAINT
            c.blit(self.f_sans.render(name, True, col), (x + 110, y))
        elif row["kind"] == "item":
            d = row["d"]
            mark = "★ " if row["eq"] else "   "
            c.blit(self.f_sans.render(mark + self._label(d, row["id"]), True, TIER_COLOR.get(d.get("tier", 4), ink)), (x, y))
            info = self.f_mono.render(f"{constants.tier_tag(d.get('tier', 4))}   {t('inv_power', pw=self._power(d, row['id']))}", True, INK_DIM)
            c.blit(info, (x + width - info.get_width() - 10, y + 3))
        else:
            d = row["d"]
            c.blit(self.f_sans.render(db_t(d, 'name'), True, ink), (x, y))
            n = self.f_mono.render(f"x{row['n']}", True, INK_DIM)
            c.blit(n, (x + width - n.get_width() - 10, y + 3))

    def _detail(self, row):
        d = row.get("d")
        if not d:
            return [(row.get("label", "") + ": " + t('inv_not_equipped').strip(), INK_DIM)]
        if row["kind"] == "cons":
            if d["type"] == "hp":
                eff = t('consumable_hp_percent', pct=int(d['val'] * 100)) if d["is_percent"] else t('consumable_hp_fixed', val=d['val'])
            else:
                eff = (t('consumable_hunger', val=d['hunger']) if d['hunger'] > 0 else "") + \
                      (t('consumable_thirst', val=d['thirst']) if d['thirst'] > 0 else "")
            return [(db_t(d, 'name'), INK), (eff.strip(), INK_DIM), (t('inv_hint_use'), INK_FAINT)]
        slot = constants.slot_label(d.get("slot", ""))
        iid = row.get("id")
        lines = [(self._label(d, iid), TIER_COLOR.get(d.get("tier", 4), INK)),
                 (t('inv_detail', tier=constants.tier_tag(d.get('tier', 4)), slot=slot, pw=self._power(d, iid), w=d.get('slot_weight', 1.0)), INK_DIM)]
        if db_t(d, "desc"):
            lines.append((db_t(d, "desc"), INK_DIM))
        hint = {"item": t('inv_hint_item'), "slot": t('inv_hint_slot')}.get(row["kind"], "")
        lines.append((hint, INK_FAINT))
        if upgrade.can_upgrade(d.get("slot")):  # 주무기: 다음 강화 비용·확률
            k = upgrade.level(self.player, iid)
            lines.append((t('upg_hint_max') if k >= upgrade.MAX_LEVEL else
                          t('upg_hint', k=k, n=k + 1, cost=upgrade.cost(d.get("tier", 4), k),
                            pct=upgrade.chance(self.player, iid) * 100), AMBER))
            dur = upgrade.durability(self.player, iid)
            if dur < upgrade.DUR_MAX:
                lines.append((t('upg_dur', dur=dur, pct=50 + dur // 2, cost=upgrade.repair_cost(self.player, iid)), RED))
            if upgrade.RISK_FROM <= k + 1 <= upgrade.MAX_LEVEL:
                lines.append((t('upg_risk', loss=upgrade.DUR_LOSS, drop=int(upgrade.DROP_CHANCE[k + 1] * 100)), INK_DIM))
        return lines

    # ── 입력 루프 ─────────────────────────────────────────────────────────
    def run(self):
        self.footer = [("↑↓", t('ui_select')), ("←→", t('inv_key_tab')), ("Enter", t('inv_key_act')), ("D", t('inv_key_dismantle')), ("R", t('upg_key')), ("F", t('rep_key')), ("0", t('inv_key_back'))]
        self.open()
        try:
            while True:
                for ev in self._events():
                    if ev.type != pygame.KEYDOWN:
                        continue
                    rows = self.rows()
                    cur = rows[self.sel[self.tab]] if rows and self.sel[self.tab] < len(rows) else None
                    if ev.key in (pygame.K_ESCAPE, pygame.K_0, pygame.K_KP0):
                        return
                    if ev.key in (pygame.K_UP, pygame.K_w):
                        self.sel[self.tab] = max(0, self.sel[self.tab] - 1)
                        self.confirm = None
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        self.sel[self.tab] = min(max(0, len(rows) - 1), self.sel[self.tab] + 1)
                        self.confirm = None
                    elif ev.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_TAB):
                        step = -1 if ev.key in (pygame.K_LEFT, pygame.K_a) else 1
                        self.tab = TABS[(TABS.index(self.tab) + step) % len(TABS)]
                        self.msg, self.confirm = [], None
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self.act(cur)
                    elif ev.key == pygame.K_d:
                        self.act(cur, dismantle=True)
                    elif ev.key == pygame.K_r:
                        self.upgrade_row(cur)
                    elif ev.key == pygame.K_f:
                        self.repair_row(cur)
        finally:
            self.close()


def run_inventory(player, tab="bag"):
    from gui import get_terminal
    InventoryView(get_terminal(), player, tab).run()
