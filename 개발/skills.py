# skills.py — 스킬 정의·실행·버프 해소 전담 모듈 v4
#
# 스킬 분류 (기획서 §2):
#   특수 스킬  (unique  , 6개) — 특수 조건 달성 시 언락. 지급 불가. (Act 2+)
#   특화 스킬  (special , 8개) — 메인 직업 스킬. 각성 시 직업별 2개 지급.
#   보조 스킬  (aux     ,10개) — 자유 장착, AP 연동. (Act 2+ 획득 경로 예정)
#   공용 스킬  (5개)           — 전직 전 사용 (급조 바리케이드·패킷 우회 등, combat 옵션)
#
# 훅 인터페이스 (combat.py 의존):
#   on_attack_used, get_atk_mult, apply_signal_trace,
#   apply_outgoing_buffs, apply_incoming_buffs,
#   consume_hydraulic_crush, is_learning_blocked,
#   get_enemy_atk_mult, end_of_turn_tick

import math
import random
import time
from colorama import Fore, Style
from ui import type_text

# ─────────────────────────────────────────────────────────────────────
# § 기초 연산
# ─────────────────────────────────────────────────────────────────────

def _fa(a: int) -> float:
    """기획서 §3 체감 함수 f(A)."""
    if a <= 15: return a * 0.02
    if a <= 25: return 0.30 + (a - 15) * 0.01
    return 0.40 + (a - 25) * 0.002

# ─────────────────────────────────────────────────────────────────────
# § 스킬 풀
# ─────────────────────────────────────────────────────────────────────

SKILL_DEFS = {

    # ════════════════════════════════════════════════════════════════
    # [특수 스킬] unique — 특수 조건 언락. 각성 지급 불가.
    # ════════════════════════════════════════════════════════════════
    "overclock": {
        "id": "overclock", "name": "의체 오버클럭", "job": "combat", "tier": "unique",
        "cost_type": "hp", "cost": 0,
        "desc": "현재 HP 10% 소모. 2회 공격 ×2.0. 공격 시 현재 HP 5% 드레인.",
        "unlock_cond": "[컴뱃 포스] kinetic 가중치 누적 5+ 달성 시",
    },
    "bio_reap": {
        "id": "bio_reap", "name": "바이오 적출", "job": "combat", "tier": "unique",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 다음 공격 후 생체연료 흡수. Pr_reap = 0.10+(f(VIT)+f(DEX))×0.5.",
        "unlock_cond": "[컴뱃 포스] |VIT-DEX|≤3 유지 5전투 승리",
    },
    "sentry_infra": {
        "id": "sentry_infra", "name": "센트리 인프라", "job": "mech", "tier": "unique",
        "cost_type": "materials", "cost": 30,
        "desc": "고철 30개. 3회 공격 포탑 지원. 위력 100 + f(INT)×500.",
        "unlock_cond": "[메카니컬 테크] 전직 후 고철 누적 100개 달성",
    },
    "signal_trace": {
        "id": "signal_trace", "name": "주파수 역추적", "job": "mech", "tier": "unique",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 다음 공격 치명타 확정. |INT-DEX|≤3 시 CRT배율↑+스턴.",
        "unlock_cond": "[메카니컬 테크] |INT-DEX|≤3 유지 3전투 승리",
    },
    "grid_intrude": {
        "id": "grid_intrude", "name": "그리드 침투", "job": "net", "tier": "unique",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 반격 차단 + 다음 적 공격 -30% + 내 다음 공격 +15%.",
        "unlock_cond": "[넷 포스] cyber 가중치 누적 5+ 달성",
    },
    "protocol_glitch": {
        "id": "protocol_glitch", "name": "프로토콜 위조", "job": "net", "tier": "unique",
        "cost_type": "ram", "cost": 3,
        "desc": "RAM 3. Pr_glitch=0.15+f(INT)×0.8. 성공 시 피해 0 위조.",
        "unlock_cond": "[넷 포스] |INT-VIT|≤3 유지 3전투 승리",
    },

    # ════════════════════════════════════════════════════════════════
    # [특화 스킬] special — 메인 직업 스킬. 각성 시 지급.
    # ════════════════════════════════════════════════════════════════

    # ── 컴뱃 포스 (2개) ──────────────────────────────────────────────
    "hydraulic_crush": {
        "id": "hydraulic_crush", "name": "유압 분쇄", "job": "combat", "tier": "special",
        "cost_type": "hp", "cost": 0,   # 실제: HP 15%
        "desc": "현재 HP 15% 소모. 다음 공격 ×1.8 + 적 방어력 50% 관통.",
    },
    "iron_body": {
        "id": "iron_body", "name": "철제 의체", "job": "combat", "tier": "special",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. 다음 3회 피격 피해 -40% (VIT가 높을수록 차단율 증가).",
    },

    # ── 메카니컬 테크 (2개) ───────────────────────────────────────────
    "scrap_construct": {
        "id": "scrap_construct", "name": "고철 구조체", "job": "mech", "tier": "special",
        "cost_type": "materials", "cost": 20,
        "desc": "고철 20개. 2턴간 피해 -25% + 보스 패턴 학습 차단.",
    },
    "overclock_repair": {
        "id": "overclock_repair", "name": "과부하 수리", "job": "mech", "tier": "special",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. HP 즉시 회복: max_HP × (0.15 + f(INT)×0.3). RAM +1 회복.",
    },

    # ── 넷 포스 (2개) ─────────────────────────────────────────────────
    "data_siphon": {
        "id": "data_siphon", "name": "데이터 사이펀", "job": "net", "tier": "special",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 이번 전투 적 공격력 -30% 영구 약화. 매 턴 종료 시 RAM +1 자동 회수.",
    },
    "ghost_protocol": {
        "id": "ghost_protocol", "name": "고스트 프로토콜", "job": "net", "tier": "special",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 이번 턴 적 반격 차단. 다음 공격 치명타율 +30% 추가.",
    },

    # ── 황금 분할 (2개) ───────────────────────────────────────────────
    "synthesis_drive": {
        "id": "synthesis_drive", "name": "종합 구동", "job": "balanced", "tier": "special",
        "cost_type": "hp", "cost": 0,   # 실제: HP 5% + RAM 1 (복합)
        "desc": "HP 5% + RAM 1 소모. VIT·INT·DEX 합산 f(A) 기반 즉각 피해 + 허기·갈증 +8.",
    },
    "equilibrium": {
        "id": "equilibrium", "name": "균형점", "job": "balanced", "tier": "special",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. HP·허기·갈증 각 +10% 동시 소량 회복 (황금 분할 재조율).",
    },

    # ════════════════════════════════════════════════════════════════
    # [보조 스킬] aux — 자유 장착. (Act 2+ 획득 경로 예정)
    # ════════════════════════════════════════════════════════════════
    "vital_pump": {
        "id": "vital_pump", "name": "생명 펌프", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 15,
        "desc": "고철 15개. HP 즉시 회복: max_HP × (0.10 + f(VIT)×0.5).",
    },
    "scrap_armor": {
        "id": "scrap_armor", "name": "고철 방어구 증설", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 20,
        "desc": "고철 20개. 다음 2회 피격 피해 -20%.",
    },
    "junk_cannon": {
        "id": "junk_cannon", "name": "고철 함포", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 25,
        "desc": "고철 25개. 즉각 피해 300 + VIT×15. (적 반격 없음)",
    },
    "bioloop": {
        "id": "bioloop", "name": "바이오 피드백 루프", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 다음 2회 공격 시 허기·갈증 +5 자동 흡수.",
    },
    "ram_condenser": {
        "id": "ram_condenser", "name": "RAM 압축기", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. 즉시 RAM +2 회복.",
    },
    "code_compile": {
        "id": "code_compile", "name": "코드 컴파일", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 다음 2턴 보스 딥러닝 패턴 학습 차단.",
    },
    "pulse_grenade": {
        "id": "pulse_grenade", "name": "펄스 수류탄", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 즉각 피해 200 + INT×10. 보스 E지수 -3.",
    },
    "kinetic_burst": {
        "id": "kinetic_burst", "name": "운동 폭발", "job": "any", "tier": "aux",
        "cost_type": "hp", "cost": 0,
        "desc": "현재 HP 5% 소모. 다음 공격 +DEX×20 고정 추가 피해.",
    },
    "neural_acc": {
        "id": "neural_acc", "name": "신경 가속기", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 다음 공격 치명타율 ×2 (상한 75%).",
    },
    "void_shift": {
        "id": "void_shift", "name": "허공 전위", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 다음 탈출 시도를 SAFE 결과로 강제 고정.",
    },
}

# ─────────────────────────────────────────────────────────────────────
# § 직업별 각성 지급 (특화 스킬 2개)
# ─────────────────────────────────────────────────────────────────────

JOB_STARTER = {
    "combat":   ["hydraulic_crush",  "iron_body"],
    "mech":     ["scrap_construct",  "overclock_repair"],
    "net":      ["data_siphon",      "ghost_protocol"],
    "balanced": ["synthesis_drive",  "equilibrium"],
}

JOB_LABEL = {
    "combat":   "컴뱃 포스",
    "mech":     "메카니컬 테크",
    "net":      "넷 포스",
    "balanced": "황금 분할의 조율사",
}

# ─────────────────────────────────────────────────────────────────────
# § 직업 판별 & 각성 지급
# ─────────────────────────────────────────────────────────────────────

def get_job(player) -> str:
    wk, ws, wc = player.weights["kinetic"], player.weights["scrap"], player.weights["cyber"]
    if wk == ws == wc:           return "balanced"
    if wk >= ws and wk >= wc:   return "combat"
    if ws >= wk and ws >= wc:   return "mech"
    return "net"


def grant_awakening_skill(player) -> tuple[str, list[str]]:
    """직업 판별 → 특화 스킬 2개 슬롯 장착. 특수 스킬은 별도 조건 언락."""
    job = get_job(player)
    player.job_class = job
    granted = []
    for sid in JOB_STARTER.get(job, []):
        if sid not in player.skill_slots and len(player.skill_slots) < 2:
            player.skill_slots.append(sid)
            granted.append(sid)
    return job, granted

# ─────────────────────────────────────────────────────────────────────
# § 비용 검증
# ─────────────────────────────────────────────────────────────────────

def can_use(player, skill_id: str) -> tuple[bool, str]:
    sk = SKILL_DEFS.get(skill_id)
    if not sk: return False, "알 수 없는 스킬 ID"
    ct = sk["cost_type"]

    if ct == "hp":
        pct = 0.05 if skill_id in ("kinetic_burst", "synthesis_drive") else 0.15 if skill_id == "hydraulic_crush" else 0.10
        cost = max(1, int(player.hp * pct))
        if player.hp <= cost + 1:
            return False, f"체력 부족 (HP {player.hp} / 최소 {cost+2} 필요)"
        # synthesis_drive: HP + RAM 복합
        if skill_id == "synthesis_drive" and player.max_ram < 1:
            return False, f"RAM 부족 (보유 {player.max_ram} / 필요 1)"
    elif ct == "ram":
        if player.max_ram < sk["cost"]:
            return False, f"RAM 부족 (보유 {player.max_ram} / 필요 {sk['cost']})"
    elif ct == "materials":
        if player.materials < sk["cost"]:
            return False, f"고철 부족 (보유 {player.materials} / 필요 {sk['cost']})"
    return True, ""

# ─────────────────────────────────────────────────────────────────────
# § 스킬 실행
# ─────────────────────────────────────────────────────────────────────

def execute(player, skill_id: str, combat_ctx: dict) -> bool:
    ok, reason = can_use(player, skill_id)
    if not ok:
        print(f"\n  {Fore.RED}[스킬 실패] {reason}{Style.RESET_ALL}")
        time.sleep(0.8)
        return False

    sk = SKILL_DEFS[skill_id]

    # ── ★ 특화 스킬 (메인 직업 스킬) ─────────────────────────────────

    if skill_id == "hydraulic_crush":
        cost = max(1, int(player.hp * 0.15))
        player.hp = max(1, player.hp - cost)
        player.active_buffs["hydraulic_crush"] = True
        print(f"\n  {Fore.RED + Style.BRIGHT}[유압 분쇄] 관절 유압 극한 출력! (HP -{cost}){Style.RESET_ALL}")
        type_text("  다음 공격 ×1.8 + 적 방어력 50% 관통.", 0.022)

    elif skill_id == "iron_body":
        player.materials -= sk["cost"]
        # VIT 기반 방어율 강화 (VIT 높을수록 -40% 초과)
        shield_pct = min(0.60, 0.40 + _fa(player.vit) * 0.2)
        player.active_buffs["iron_body"] = {"charges": 3, "pct": shield_pct}
        pct_str = f"{shield_pct*100:.0f}%"
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}[철제 의체] 장갑 출력 최대! (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  다음 3회 피격 피해 -{pct_str} (VIT={player.vit})", 0.022)

    elif skill_id == "scrap_construct":
        player.materials -= sk["cost"]
        player.active_buffs["scrap_construct"] = 2
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}[고철 구조체] 임시 방어 구조물 조립! (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text("  2턴간 피해 -25% + 보스 패턴 학습 차단.", 0.022)

    elif skill_id == "overclock_repair":
        player.materials -= sk["cost"]
        heal = max(1, math.floor(player.max_hp * (0.15 + _fa(player.int_s) * 0.3)))
        player.hp = min(player.max_hp, player.hp + heal)
        player.max_ram = min(8, player.max_ram + 1)
        print(f"\n  {Fore.GREEN + Style.BRIGHT}[과부하 수리] 회로 현장 납땜! (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  HP +{heal} 즉시 회복 / RAM +1 (INT={player.int_s})", 0.022)

    elif skill_id == "data_siphon":
        player.max_ram -= sk["cost"]
        player.active_buffs["data_siphon"] = True         # 전투 지속 디버프
        player.active_buffs["data_siphon_regen"] = True   # 첫 턴 RAM 회수
        print(f"\n  {Fore.CYAN + Style.BRIGHT}[데이터 사이펀] 적 공격 알고리즘 탈취! (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text("  이번 전투 적 공격력 -30% 영구. 매 턴 종료 시 RAM +1 회수.", 0.022)

    elif skill_id == "ghost_protocol":
        player.max_ram -= sk["cost"]
        combat_ctx["skip_enemy_attack"] = True
        player.active_buffs["ghost_crt"] = 0.30
        print(f"\n  {Fore.MAGENTA + Style.BRIGHT}[고스트 프로토콜] 허상 전개 — 감시망 이탈! (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text("  이번 턴 반격 차단 / 다음 공격 치명타율 +30%.", 0.022)

    elif skill_id == "synthesis_drive":
        hp_cost = max(1, int(player.hp * 0.05))
        player.hp = max(1, player.hp - hp_cost)
        player.max_ram -= 1
        # 3스탯 f(A) 합산 즉각 피해
        dmg = int((_fa(player.vit) + _fa(player.int_s) + _fa(player.dex)) * 1200)
        dmg = max(100, dmg)
        combat_ctx["aux_skill_dmg"] = dmg
        player.hunger = min(100, player.hunger + 8)
        player.thirst = min(100, player.thirst + 8)
        fa_sum = _fa(player.vit) + _fa(player.int_s) + _fa(player.dex)
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}[종합 구동] 3역할군 프로토콜 동시 가동! (HP -{hp_cost}, RAM -1){Style.RESET_ALL}")
        type_text(f"  즉각 피해 {dmg} (f합={fa_sum:.2f}×1200) / 허기·갈증 +8", 0.022)

    elif skill_id == "equilibrium":
        player.materials -= sk["cost"]
        hp_gain = max(1, int(player.max_hp * 0.10))
        player.hp = min(player.max_hp, player.hp + hp_gain)
        player.hunger = min(100, player.hunger + 10)
        player.thirst = min(100, player.thirst + 10)
        print(f"\n  {Fore.GREEN}[균형점] 황금 분할 재조율. (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  HP +{hp_gain} / 허기 +10 / 갈증 +10 동시 회복.", 0.022)

    # ── ★ 특수 스킬 (unique — 조건 언락) ─────────────────────────────

    elif skill_id == "overclock":
        cost = max(1, int(player.hp * 0.10))
        player.hp = max(1, player.hp - cost)
        player.active_buffs["overclock"] = 2
        print(f"\n  {Fore.RED + Style.BRIGHT}[의체 오버클럭] 신경망 리미터 강제 해제! (HP -{cost}){Style.RESET_ALL}")
        type_text("  다음 2회 공격 ×2.0 / 공격마다 현재 HP 5% 드레인.", 0.022)

    elif skill_id == "bio_reap":
        player.max_ram -= sk["cost"]
        player.active_buffs["bio_reap"] = 1
        vit_dex_bal = abs(player.vit - player.dex) <= 3
        pr = min(0.70, 0.10 + (_fa(player.vit) + _fa(player.dex)) * 0.5)
        tag = f" [VIT·DEX 균형 — Pr={pr*100:.0f}%]" if vit_dex_bal else " [비균형 — 기본 20%]"
        print(f"\n  {Fore.RED}[바이오 적출] 생체 추출 코드 주입. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  다음 공격 후 흡수 시도{tag}", 0.022)

    elif skill_id == "sentry_infra":
        player.materials -= sk["cost"]
        sentry_dmg = 100 + int(_fa(player.int_s) * 500)
        player.active_buffs["sentry"] = {"charges": 3, "dmg": sentry_dmg}
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}[센트리 인프라] 포탑 배치! (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  3회 포탑 지원 사격 +{sentry_dmg} (INT={player.int_s})", 0.022)

    elif skill_id == "signal_trace":
        player.max_ram -= sk["cost"]
        int_dex_bal = abs(player.int_s - player.dex) <= 3
        crt_mult = round(1.5 + _fa(player.dex) * 0.5, 3) if int_dex_bal else 1.5
        pr_stun  = min(0.50, 0.15 + _fa(player.int_s) * 0.3) if int_dex_bal else 0.0
        player.active_buffs["signal_trace"] = {
            "crt_mult": crt_mult, "pr_stun": pr_stun, "is_hybrid": int_dex_bal
        }
        tag = f" [균형 — ×{crt_mult}, 스턴 {pr_stun*100:.0f}%]" if int_dex_bal else ""
        print(f"\n  {Fore.CYAN + Style.BRIGHT}[주파수 역추적] 신호 추적. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  다음 공격 치명타 확정{tag}", 0.022)

    elif skill_id == "grid_intrude":
        player.max_ram -= sk["cost"]
        combat_ctx["skip_enemy_attack"] = True
        player.active_buffs["grid_def"] = 1
        player.active_buffs["grid_atk"] = 1
        print(f"\n  {Fore.CYAN + Style.BRIGHT}[그리드 침투] 감시망 교란. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text("  반격 차단 / 다음 적 공격 -30% / 내 다음 공격 +15%", 0.022)

    elif skill_id == "protocol_glitch":
        player.max_ram -= sk["cost"]
        int_vit_bal = abs(player.int_s - player.vit) <= 3
        pr = min(0.65, 0.15 + _fa(player.int_s) * 0.8) if int_vit_bal else 0.30
        player.active_buffs["protocol_glitch"] = {"pr": pr, "is_hybrid": int_vit_bal}
        tag = f" [균형 — Pr={pr*100:.0f}%, 연쇄 차단]" if int_vit_bal else " [비균형 — 30%]"
        print(f"\n  {Fore.MAGENTA + Style.BRIGHT}[프로토콜 위조] 교란 스크립트 살포. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  적 다음 공격 위조 시도{tag}", 0.022)

    # ── 보조 스킬 ─────────────────────────────────────────────────────

    elif skill_id == "vital_pump":
        player.materials -= sk["cost"]
        heal = max(1, math.floor(player.max_hp * (0.10 + _fa(player.vit) * 0.5)))
        player.hp = min(player.max_hp, player.hp + heal)
        print(f"\n  {Fore.GREEN + Style.BRIGHT}[생명 펌프] 고압 생체 연료 주입! (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  HP +{heal} 즉시 회복 (VIT={player.vit})", 0.022)

    elif skill_id == "scrap_armor":
        player.materials -= sk["cost"]
        player.active_buffs["scrap_armor"] = 2
        print(f"\n  {Fore.YELLOW}[고철 방어구 증설] 임시 장갑판 부착. (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text("  다음 2회 피격 피해 -20%.", 0.022)

    elif skill_id == "junk_cannon":
        player.materials -= sk["cost"]
        dmg = 300 + player.vit * 15
        combat_ctx["aux_skill_dmg"] = dmg
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}[고철 함포] 급조 포탄 발사! (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  적에게 즉각 피해 {dmg} (VIT={player.vit})", 0.022)

    elif skill_id == "bioloop":
        player.max_ram -= sk["cost"]
        player.active_buffs["bioloop"] = 2
        print(f"\n  {Fore.GREEN}[바이오 피드백 루프] 생체 회로 순환 가동. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text("  다음 2회 공격 시 허기·갈증 +5 자동 흡수.", 0.022)

    elif skill_id == "ram_condenser":
        player.materials -= sk["cost"]
        gain = 2 if player.max_ram < 6 else 1
        player.max_ram += gain
        print(f"\n  {Fore.CYAN}[RAM 압축기] 잉여 회로 재압축. (고철 -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  가용 RAM +{gain} → 현재 RAM: {player.max_ram}", 0.022)

    elif skill_id == "code_compile":
        player.max_ram -= sk["cost"]
        player.active_buffs["code_compile"] = 2
        print(f"\n  {Fore.CYAN}[코드 컴파일] 패턴 교란 루틴 업로드. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text("  다음 2턴 보스 딥러닝 학습 차단.", 0.022)

    elif skill_id == "pulse_grenade":
        player.max_ram -= sk["cost"]
        dmg = 200 + player.int_s * 10
        combat_ctx["aux_skill_dmg"] = dmg
        combat_ctx["pulse_e_drain"] = True
        print(f"\n  {Fore.CYAN + Style.BRIGHT}[펄스 수류탄] 전자기파 폭발! (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  즉각 피해 {dmg} + 보스 E지수 -3 (INT={player.int_s})", 0.022)

    elif skill_id == "kinetic_burst":
        cost = max(1, int(player.hp * 0.05))
        player.hp = max(1, player.hp - cost)
        bonus = player.dex * 20
        player.active_buffs["kinetic_burst"] = bonus
        print(f"\n  {Fore.RED}[운동 폭발] 관절 모터 순간 과부하! (HP -{cost}){Style.RESET_ALL}")
        type_text(f"  다음 공격 +{bonus} 고정 추가 피해 (DEX={player.dex})", 0.022)

    elif skill_id == "neural_acc":
        player.max_ram -= sk["cost"]
        player.active_buffs["neural_acc"] = 1
        print(f"\n  {Fore.CYAN}[신경 가속기] 시냅스 전달 가속. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text(f"  다음 공격 치명타율 ×2 (상한 75%)", 0.022)

    elif skill_id == "void_shift":
        player.max_ram -= sk["cost"]
        player.active_buffs["void_shift"] = 1
        print(f"\n  {Fore.MAGENTA}[허공 전위] 공간 왜곡 준비. (RAM -{sk['cost']}){Style.RESET_ALL}")
        type_text("  다음 탈출 결과 SAFE 강제 고정.", 0.022)

    time.sleep(0.6)
    return True

# ─────────────────────────────────────────────────────────────────────
# § 훅 함수 (combat.py에서 호출)
# ─────────────────────────────────────────────────────────────────────

def on_attack_used(player, action_logs: list, dmg_dealt: int = 0):
    """주무기 공격 성공 후 호출."""

    # 오버클럭 드레인
    if "overclock" in player.active_buffs:
        drain = max(1, int(player.hp * 0.05))
        player.hp = max(1, player.hp - drain)
        player.active_buffs["overclock"] -= 1
        remain = player.active_buffs["overclock"]
        if remain <= 0:
            del player.active_buffs["overclock"]
            action_logs.append(f"[의체 오버클럭] 지속 종료 — HP -{drain}")
        else:
            action_logs.append(f"[의체 오버클럭] 잔여 {remain}회 — HP -{drain}")

    # 바이오 적출 흡수 판정
    if player.active_buffs.pop("bio_reap", 0):
        vit_dex_bal = abs(player.vit - player.dex) <= 3
        pr = min(0.70, 0.10 + (_fa(player.vit) + _fa(player.dex)) * 0.5) if vit_dex_bal else 0.20
        if random.random() < pr:
            v_vamp = max(5, math.floor(dmg_dealt * 0.05)) if dmg_dealt else 10
            h_g = math.ceil(v_vamp / 2)
            t_g = v_vamp - h_g
            player.hunger = min(100, player.hunger + h_g)
            player.thirst = min(100, player.thirst + t_g)
            action_logs.append(f"[바이오 적출] 흡수 성공! 허기 +{h_g} 갈증 +{t_g} (Pr={pr*100:.0f}%)")
        else:
            action_logs.append(f"[바이오 적출] 흡수 실패 (Pr={pr*100:.0f}%)")

    # 바이오 피드백 루프
    if "bioloop" in player.active_buffs:
        player.hunger = min(100, player.hunger + 5)
        player.thirst = min(100, player.thirst + 5)
        player.active_buffs["bioloop"] -= 1
        remain = player.active_buffs["bioloop"]
        if remain <= 0:
            del player.active_buffs["bioloop"]
            action_logs.append("[바이오 피드백] 허기·갈증 +5. 루프 종료")
        else:
            action_logs.append(f"[바이오 피드백] 허기·갈증 +5. 잔여 {remain}회")


def get_atk_mult(player) -> float:
    return 2.0 if "overclock" in player.active_buffs else 1.0


def consume_hydraulic_crush(player, action_logs: list) -> tuple[float, float]:
    """유압 분쇄 버프 소비. 반환: (atk_mult, def_pierce_ratio)."""
    if not player.active_buffs.pop("hydraulic_crush", False):
        return 1.0, 0.0
    action_logs.append("[유압 분쇄] 유압 극한 출력 — 방어 관통 타격! (×1.8, DEF 50% 무시)")
    return 1.8, 0.5


def apply_signal_trace(player, combat_ctx: dict, action_logs: list) -> tuple[bool, float]:
    """signal_trace 버프 소비. 반환: (forced_crit, crt_mult)."""
    buf = player.active_buffs.pop("signal_trace", None)
    if buf is None:
        return False, 1.5
    crt_mult = buf["crt_mult"]
    pr_stun  = buf["pr_stun"]
    action_logs.append(f"[주파수 역추적] 치명타 확정 ×{crt_mult}!")
    if buf["is_hybrid"] and pr_stun > 0 and random.random() < pr_stun:
        combat_ctx["skip_enemy_attack"] = True
        action_logs.append(f"[주파수 역추적 융합] 스턴 발동! (Pr={pr_stun*100:.0f}%)")
    return True, crt_mult


def is_learning_blocked(player) -> bool:
    """보스 패턴 학습 차단 여부 (code_compile 또는 scrap_construct 활성 시)."""
    return "code_compile" in player.active_buffs or "scrap_construct" in player.active_buffs


def get_enemy_atk_mult(player) -> float:
    """적 공격력 배율 (data_siphon -30%)."""
    return 0.70 if "data_siphon" in player.active_buffs else 1.0


def apply_outgoing_buffs(player, dmg: int, action_logs: list) -> int:
    """아웃고잉 피해 버프."""

    # 그리드 침투 +15%
    if player.active_buffs.pop("grid_atk", 0):
        dmg = int(dmg * 1.15)
        action_logs.append("[그리드 침투] 취약 노드 익스플로잇 — 피해 +15%")

    # 센트리 인프라
    sentry = player.active_buffs.get("sentry")
    if isinstance(sentry, dict) and sentry.get("charges", 0) > 0:
        s_dmg = sentry["dmg"]
        dmg  += s_dmg
        sentry["charges"] -= 1
        remain = sentry["charges"]
        if remain <= 0:
            del player.active_buffs["sentry"]
            action_logs.append(f"[센트리 인프라] 지원 사격 +{s_dmg}. 탄약 소진")
        else:
            action_logs.append(f"[센트리 인프라] 지원 사격 +{s_dmg}. 잔여 {remain}회")

    # 운동 폭발 고정 추가 피해
    kb = player.active_buffs.pop("kinetic_burst", 0)
    if kb > 0:
        dmg += kb
        action_logs.append(f"[운동 폭발] 과부하 타격 +{kb}")

    return dmg


def apply_incoming_buffs(player, dmg_taken: int, action_logs: list, combat_ctx: dict) -> int:
    """인커밍 피해 버프."""

    # 그리드 침투 -30%
    if player.active_buffs.pop("grid_def", 0):
        dmg_taken = max(1, int(dmg_taken * 0.70))
        action_logs.append("[그리드 침투] 패킷 교란 — 피해 30% 차단")

    # 철제 의체 -VIT 기반 차단
    iron = player.active_buffs.get("iron_body")
    if isinstance(iron, dict) and iron.get("charges", 0) > 0:
        pct = iron["pct"]
        dmg_taken = max(1, int(dmg_taken * (1 - pct)))
        iron["charges"] -= 1
        remain = iron["charges"]
        if remain <= 0:
            del player.active_buffs["iron_body"]
            action_logs.append(f"[철제 의체] 피해 -{pct*100:.0f}% 차단. 장갑 소진")
        else:
            action_logs.append(f"[철제 의체] 피해 -{pct*100:.0f}% 차단. 잔여 {remain}회")

    # 고철 구조체 -25%
    if "scrap_construct" in player.active_buffs:
        dmg_taken = max(1, int(dmg_taken * 0.75))
        action_logs.append("[고철 구조체] 구조물 방어 — 피해 25% 차단")

    # 고철 방어구 증설 -20%
    if "scrap_armor" in player.active_buffs:
        dmg_taken = max(1, int(dmg_taken * 0.80))
        player.active_buffs["scrap_armor"] -= 1
        remain = player.active_buffs["scrap_armor"]
        if remain <= 0:
            del player.active_buffs["scrap_armor"]
            action_logs.append("[고철 방어구] 피해 20% 차단. 장갑 소진")
        else:
            action_logs.append(f"[고철 방어구] 피해 20% 차단. 잔여 {remain}회")

    # 프로토콜 위조
    glitch = player.active_buffs.pop("protocol_glitch", None)
    if glitch is not None:
        pr = glitch["pr"]
        if random.random() < pr:
            action_logs.append(f"[프로토콜 위조] 위조 성공! (Pr={pr*100:.0f}%) — 피해 0")
            if glitch["is_hybrid"]:
                combat_ctx["skip_enemy_attack"] = True
                action_logs.append("[프로토콜 위조 융합] 다음 반격도 차단!")
            dmg_taken = 0
        else:
            action_logs.append(f"[프로토콜 위조] 위조 실패 (Pr={pr*100:.0f}%)")

    return dmg_taken


def end_of_turn_tick(player, action_logs: list):
    """매 턴 종료 시 호출 — 버프 카운터 감소 및 tick 효과."""

    # 데이터 사이펀 RAM 회수 (활성 중일 때 매 턴)
    if "data_siphon" in player.active_buffs:
        player.max_ram = min(8, player.max_ram + 1)
        action_logs.append("[데이터 사이펀] 탈취 데이터 재패키징 — RAM +1 회수")

    # 고철 구조체 턴 감소
    if "scrap_construct" in player.active_buffs:
        player.active_buffs["scrap_construct"] -= 1
        if player.active_buffs["scrap_construct"] <= 0:
            del player.active_buffs["scrap_construct"]
            action_logs.append("[고철 구조체] 방어 구조물 붕괴")

    # 코드 컴파일 턴 감소
    if "code_compile" in player.active_buffs:
        player.active_buffs["code_compile"] -= 1
        if player.active_buffs["code_compile"] <= 0:
            del player.active_buffs["code_compile"]
            action_logs.append("[코드 컴파일] 패턴 교란 루틴 종료")
