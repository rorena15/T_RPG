"""전투 화면 (이벤트 화면과 같은 틀). combat.py의 UI 관리자 신호를 받아 그린다 (전투 로직은 그대로).

combat.py는 UI 관리자가 있으면 화면을 지우거나 메뉴를 찍지 않고 전투 기록만 남기며, 아래 신호를 보낸다:
  set_state("combat"/"exploration"), scene_set_enemy(이름, hp, 최대hp, 아스키아트), scene_update_hp(hp),
  set_actions([(키, 이름, 쓸 수 있음[, 누르면 보낼 키])]), scene_set_idle()
왼쪽: 적 그림 + 내 생체 지표 + 적 이름·HP.  오른쪽: 큰 적 HP 바, 전투 기록.  아래: 행동 키.
입력은 원래대로 combat.py의 read_key()가 받는다 (방향키·마우스는 EventView.on_input이 키로 바꿔 준다).
"""
import re

import pygame

from event_view import AMBER, BG, EventView, GREEN, INK, INK_DIM, INK_FAINT, JUNKYARD, PLATE_W, RED, _lerp
from i18n import t

_WORDISH = re.compile(r"[가-힣A-Za-z0-9]")


class CombatView(EventView):
    def __init__(self, term, player, scene, is_boss=False):
        super().__init__(term, player, None, JUNKYARD, scene=scene)
        self.is_boss = is_boss
        self.enemy_name, self.enemy_hp, self.enemy_max = "", 0, 1
        self._shown_hp = None
        self._hit = (0, 0)  # (시각, 이전 hp) 피해 번쩍임
        self.actions = []

    # ── combat.py가 부르는 것 ─────────────────────────────────────────────
    def set_state(self, state):
        if state == "combat" and not self._active:
            self.open()
        elif state != "combat" and self._active:
            self.close()

    def scene_set_enemy(self, name, hp, max_hp, art=""):
        self.enemy_name, self.enemy_hp, self.enemy_max = name, hp, max(1, max_hp)
        self._shown_hp = hp

    def scene_update_hp(self, hp):
        if hp < self.enemy_hp:
            self._hit = (pygame.time.get_ticks(), self.enemy_hp)
            self.shake(4, 220)
        self.enemy_hp = hp

    # 행동은 발밑 버튼: ←→(↑↓)로 고르고 Enter·Space로 실행, 마우스로 누르거나 숫자키. 고른 칸은 턴이 바뀌어도 남는다.
    foot_nav = True
    nav_cols = 2

    def set_actions(self, actions):
        self.actions = actions
        self.footer = [(a[0], a[1], a[3] if len(a) > 3 else a[0]) for a in actions if a[2]]
        self.foot_sel = min(self.foot_sel, max(0, len(self.footer) - 1))

    def scene_set_idle(self):
        pass

    # ── 그리기 ────────────────────────────────────────────────────────────
    def _hp_fraction(self):
        target = max(0, self.enemy_hp)
        if self._shown_hp is None:
            self._shown_hp = target
        self._shown_hp += (target - self._shown_hp) * 0.15 if abs(target - self._shown_hp) > 1 else target - self._shown_hp
        return max(0.0, min(1.0, self._shown_hp / self.enemy_max)), max(0.0, min(1.0, target / self.enemy_max))

    def _draw_hud(self, c, H):
        EventView._draw_hud(self, c, H)  # 내 생체 지표 (위)
        # 지명 자리를 적 이름·HP로 덮는다
        c.fill(BG, (0, H - 130, PLATE_W - 60, 110))
        shown, real = self._hp_fraction()
        c.blit(self.f_mono.render("TARGET", True, RED), (22, H - 124))
        c.blit(self.f_place.render(self.enemy_name, True, INK), (22, H - 104))
        bw = PLATE_W - 90
        pygame.draw.line(c, (46, 44, 42), (22, H - 58), (22 + bw, H - 58), 4)
        pygame.draw.line(c, RED, (22, H - 58), (22 + int(bw * shown), H - 58), 4)

    def _draw_column(self, c, W, H):
        x = self._col_x
        width = W - x - 36
        y = 40
        c.blit(self.f_mono.render(t("tag_combat") + ("  ·  BOSS" if self.is_boss else ""), True, RED), (x, y))
        c.blit(self.f_title.render(self.enemy_name, True, INK), (x, y + 22))
        y += 76
        # 큰 적 HP 바: 줄어든 구간은 잠깐 붉게 남는다
        shown, real = self._hp_fraction()
        t0, old = self._hit
        flash = max(0.0, 1 - (pygame.time.get_ticks() - t0) / 700) if t0 else 0.0
        pygame.draw.rect(c, (30, 29, 27), (x, y, width, 14))
        if flash:
            pygame.draw.rect(c, _lerp(BG, (255, 220, 200), flash), (x, y, int(width * min(1.0, old / self.enemy_max)), 14))
        col = GREEN if real > 0.6 else (AMBER if real > 0.3 else RED)
        pygame.draw.rect(c, col, (x, y, int(width * shown), 14))
        c.blit(self.f_mono.render(f"{real * 100:.0f}%", True, INK_DIM), (x + width - 40, y + 20))
        y += 50
        # 전투 기록 (터미널 버퍼, 아스키 그림·테두리 제외)
        pygame.draw.line(c, (40, 38, 36), (x, y), (x + width, y))
        y += 14
        bottom = H - 70 - self._menu_h() - self.QB_H - 30
        per = max(1, (bottom - y) // 28)
        for i, surf in enumerate(self._log_surfaces(width, per)):
            c.blit(surf, (x, y))
            y += 28

    # ── 행동 버튼 (오른쪽 칸 아래, 두 줄씩) ──────────────────────────────────
    BTN_H = 40

    def _menu_h(self):
        n = len(self._foot_items())
        return ((n + 1) // 2) * (self.BTN_H + 6) if n else 0

    def _draw_footer(self, c, W, H):
        """발밑 안내 대신: 행동을 버튼 격자로 그리고(누를 자리 = _foot_hits), 맨 아래엔 조작 안내만."""
        x = self._col_x
        width = W - x - 36
        items = self._foot_items()
        top = H - 62 - self._menu_h()
        bw = (width - 10) // 2
        hits = []
        for i, (key, label, ret) in enumerate(items):
            bx, by = x + (i % 2) * (bw + 10), top + (i // 2) * (self.BTN_H + 6)
            rect = pygame.Rect(bx, by, bw, self.BTN_H)
            on = self._foot_on(i, ret)
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            box.fill((*AMBER, 40) if on else (255, 255, 255, 10))
            c.blit(box, rect.topleft)
            pygame.draw.rect(c, AMBER if on else (58, 55, 50), rect, 1)
            k = self.f_mono_b.render(key, True, AMBER)
            c.blit(k, (bx + 12, by + (self.BTN_H - k.get_height()) // 2))
            g = self.f_sans.render(label, True, INK if on else INK_DIM)
            c.blit(g, (bx + 38, by + (self.BTN_H - g.get_height()) // 2))
            hits.append((ret, rect))
        self._foot_hits = hits
        self._draw_quickbar(c, x, top - self.QB_H - 10, width)
        hint = self.f_sans.render(t('combat_hint_keys'), True, INK_FAINT)
        c.blit(hint, (x, H - 40))

    def _log_surfaces(self, width, per):
        """전투 기록 줄 그림. 터미널 기록이 바뀔 때만 다시 거르고 그린다
        (매 프레임 60줄을 다시 줄바꿈·렌더하면 한 프레임 36ms로 느려졌다)."""
        buf = self._term._buf
        key = (id(buf), len(buf), len(buf[-1]) if buf else 0, width, per)
        if key == getattr(self, "_log_key", None):
            return self._log_cache
        lines = []
        for line in buf[-60:]:
            text = "".join(seg[0] for seg in line).strip()
            if not text or len(_WORDISH.findall(text)) < max(2, len(text) * 0.35):
                continue
            lines.append(text)
        wrapped = []
        for text in lines:
            # 로그 문구의 낱말로 색을 고른다 (한국어·영어 문구 둘 다)
            if text.startswith(("[시스템 갱신]", "[SYSTEM UPDATE]")):  # 매 턴 반복되는 잔여 체력 줄은 흐리게
                color = INK_FAINT
            elif ("손상" in text or "무자비한 공격" in text or "받" in text and "피해" in text
                  or "relentless attack" in text or "Took" in text or "Took a hit" in text):
                color = RED          # 받은 피해
            elif "적에게" in text or "관통" in text or "피해량" in text or "penetrated" in text or "Dealt" in text or "Damage" in text:
                color = AMBER        # 내 공격
            elif ("회복" in text or "획득" in text or "승리" in text or "전개" in text
                  or "RECOVERY" in text or "LOOTED" in text or "VICTORY" in text or "deployed" in text):
                color = GREEN
            else:
                color = INK
            wrapped += [(ln, color) for ln in self._wrap(self.f_serif, text, width)]
        shown = wrapped[-per:]
        out = []
        for i, (ln, color) in enumerate(shown):
            fade = 0.55 + 0.45 * (i + 1) / len(shown)  # 오래된 줄은 흐리게
            out.append(self.f_serif.render(ln, True, _lerp(BG, color, fade)))
        self._log_key, self._log_cache = key, out
        return out
