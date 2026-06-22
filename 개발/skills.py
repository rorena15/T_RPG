# skills.py — 스킬 정의·실행·버프 해소 전담 모듈
# 의존성: ui, colorama  (combat은 지연 import로 순환 방지)
# 새 스킬 추가: SKILL_DEFS에 항목 추가 + execute() 분기 추가만으로 충분.

import time
from colorama import Fore, Style
from ui import type_text

# ── 스킬 정의 풀 ──────────────────────────────────────────────────────
# cost_type: "hp" | "ram" | "materials"
# cost: 0 = 런타임에 player 값 기반 계산 (hp 타입에만 해당)
SKILL_DEFS = {
    "overclock": {
        "id":          "overclock",
        "name":        "의체 오버클럭",
        "job":         "combat",
        "cost_type":   "hp",
        "cost":        0,       # 현재 HP × 10%  (런타임 계산)
        "desc":        "현재 HP 10% 소모 발동. 다음 2회 공격 ×2.0. 공격 시 현재 HP 5% 자동 소모.",
        "unlock_desc": "[컴뱃 포스] 각성 해금",
    },
    "rapid_refine": {
        "id":          "rapid_refine",
        "name":        "긴급 정제",
        "job":         "mech",
        "cost_type":   "materials",
        "cost":        35,
        "desc":        "고철 35개 소모. 최대 HP 20% 즉시 회복.",
        "unlock_desc": "[메카니컬 테크] 각성 해금",
    },
    "grid_intrude": {
        "id":          "grid_intrude",
        "name":        "그리드 침투",
        "job":         "net",
        "cost_type":   "ram",
        "cost":        1,
        "desc":        "RAM 1 소모. 이번 턴 적 반격 차단 + 다음 적 공격 피해 -30% + 내 다음 공격 피해 +15%.",
        "unlock_desc": "[넷 포스] 각성 해금",
    },
}

JOB_STARTER = {
    "combat":   "overclock",
    "mech":     "rapid_refine",
    "net":      "grid_intrude",
    "balanced": "overclock",
}

JOB_LABEL = {
    "combat":   "컴뱃 포스",
    "mech":     "메카니컬 테크",
    "net":      "넷 포스",
    "balanced": "황금 분할의 조율사",
}


# ── 직업 판별 ─────────────────────────────────────────────────────────
def get_job(player) -> str:
    wk, ws, wc = player.weights["kinetic"], player.weights["scrap"], player.weights["cyber"]
    if wk == ws == wc:  return "balanced"
    if wk >= ws and wk >= wc: return "combat"
    if ws >= wk and ws >= wc: return "mech"
    return "net"


# ── 각성 시 첫 스킬 지급 ───────────────────────────────────────────────
def grant_awakening_skill(player) -> tuple[str, str | None]:
    job = get_job(player)
    player.job_class = job
    skill_id = JOB_STARTER.get(job)
    if skill_id and skill_id not in player.skill_slots:
        player.skill_slots.append(skill_id)
    return job, skill_id


# ── 비용 확인 ─────────────────────────────────────────────────────────
def can_use(player, skill_id: str) -> tuple[bool, str]:
    skill = SKILL_DEFS.get(skill_id)
    if not skill:
        return False, "알 수 없는 스킬 ID"
    if skill["cost_type"] == "hp":
        cost_val = max(1, int(player.hp * 0.10))
        if player.hp <= cost_val + 1:
            return False, f"체력 부족 — 현재 HP({player.hp}) 대비 발동 비용({cost_val})"
    elif skill["cost_type"] == "ram":
        if player.max_ram < skill["cost"]:
            return False, f"RAM 부족 (보유 {player.max_ram} / 필요 {skill['cost']})"
    elif skill["cost_type"] == "materials":
        if player.materials < skill["cost"]:
            return False, f"고철 부족 (보유 {player.materials} / 필요 {skill['cost']})"
    return True, ""


# ── 스킬 실행 ─────────────────────────────────────────────────────────
def execute(player, skill_id: str, combat_ctx: dict) -> bool:
    ok, reason = can_use(player, skill_id)
    if not ok:
        print(f"\n  {Fore.RED}[스킬 실패] {reason}{Style.RESET_ALL}")
        time.sleep(0.8)
        return False

    skill = SKILL_DEFS[skill_id]

    # ── 의체 오버클럭 ──
    if skill_id == "overclock":
        cost_val = max(1, int(player.hp * 0.10))
        player.hp = max(1, player.hp - cost_val)
        player.active_buffs["overclock"] = 2          # 2회 공격 잔여
        print(f"\n  {Fore.RED + Style.BRIGHT}[의체 오버클럭] 신경망 리미터 강제 해제! (HP -{cost_val}){Style.RESET_ALL}")
        type_text("  다음 2회 공격 ×2.0. 공격 시 현재 HP 5% 자동 소모.", 0.022)
        time.sleep(0.6)

    # ── 긴급 정제 ──
    elif skill_id == "rapid_refine":
        player.materials -= skill["cost"]
        heal = int(player.max_hp * 0.20)
        player.hp = min(player.max_hp, player.hp + heal)
        from combat import apply_dynamic_scaling
        _, disp_heal, _ = apply_dynamic_scaling(heal, 0, player.get_highest_tier())
        print(f"\n  {Fore.GREEN + Style.BRIGHT}[긴급 정제] 고철 35개를 생체연료로 변환. HP +{disp_heal:,}{Style.RESET_ALL}")
        time.sleep(0.6)

    # ── 그리드 침투 ──
    elif skill_id == "grid_intrude":
        player.max_ram -= skill["cost"]
        combat_ctx["skip_enemy_attack"]  = True        # 이번 턴 반격 차단
        player.active_buffs["grid_def"]  = 1           # 다음 적 공격 피해 ×0.70
        player.active_buffs["grid_atk"]  = 1           # 내 다음 공격 피해 ×1.15
        print(f"\n  {Fore.CYAN + Style.BRIGHT}[그리드 침투] 적 감시망 패킷 교란 성공. (RAM -{skill['cost']}){Style.RESET_ALL}")
        type_text("  이번 턴 반격 차단 / 다음 적 공격 -30% / 내 다음 공격 +15%.", 0.022)
        time.sleep(0.6)

    return True


# ── 공격 발동 후 오버클럭 소모·드레인 ────────────────────────────────
def on_attack_used(player, action_logs: list):
    if "overclock" not in player.active_buffs:
        return
    drain = max(1, int(player.hp * 0.05))       # 공격 시점 현재 HP × 5%
    player.hp = max(1, player.hp - drain)
    player.active_buffs["overclock"] -= 1
    remain = player.active_buffs["overclock"]
    if remain <= 0:
        del player.active_buffs["overclock"]
        action_logs.append(f"[의체 오버클럭] 지속 종료 — HP -{drain}")
    else:
        action_logs.append(f"[의체 오버클럭 유지] 잔여 {remain}회 — HP -{drain}")


# ── 공격력 배율 (overclock) ───────────────────────────────────────────
def get_atk_mult(player) -> float:
    return 2.0 if "overclock" in player.active_buffs else 1.0


# ── 아웃고잉 피해 버프 적용 (그리드 침투 +15%) ───────────────────────
def apply_outgoing_buffs(player, dmg: int, action_logs: list) -> int:
    if player.active_buffs.pop("grid_atk", 0):
        dmg = int(dmg * 1.15)
        action_logs.append("[그리드 침투] 취약 노드 익스플로잇 — 피해량 +15%")
    return dmg


# ── 인커밍 피해 버프 적용 (그리드 침투 -30%) ─────────────────────────
def apply_incoming_buffs(player, dmg_taken: int, action_logs: list) -> int:
    if player.active_buffs.pop("grid_def", 0):
        dmg_taken = max(1, int(dmg_taken * 0.70))
        action_logs.append("[그리드 침투] 패킷 교란 방어 — 적 피해량 30% 차단")
    return dmg_taken
