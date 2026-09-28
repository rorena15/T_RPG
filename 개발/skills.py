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
from i18n import t, db_t
import i18n

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
        "id": "overclock", "name": "의체 오버클럭", "name_en": "Overclock", "job": "combat", "tier": "unique",
        "cost_type": "hp", "cost": 0,
        "desc": "현재 HP 10% 소모. 2회 공격 ×2.0. 공격 시 현재 HP 5% 드레인.",
        "desc_en": "Costs 10% of current HP. Next 2 attacks ×2.0. Each attack drains 5% of current HP.",
        "unlock_cond": "[컴뱃 포스] kinetic 가중치 누적 5+ 달성 시",
    },
    "bio_reap": {
        "id": "bio_reap", "name": "바이오 적출", "name_en": "Bio Reap", "job": "combat", "tier": "unique",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 다음 공격 후 생체연료 흡수. Pr_reap = 0.10+(f(VIT)+f(DEX))×0.5.",
        "desc_en": "RAM 2. Absorb biofuel after your next attack. Pr_reap = 0.10+(f(VIT)+f(DEX))×0.5.",
        "unlock_cond": "[컴뱃 포스] |VIT-DEX|≤3 유지 5전투 승리",
    },
    "sentry_infra": {
        "id": "sentry_infra", "name": "센트리 인프라", "name_en": "Sentry Infra", "job": "mech", "tier": "unique",
        "cost_type": "materials", "cost": 30,
        "desc": "고철 30개. 3회 공격 포탑 지원. 위력 100 + f(INT)×500.",
        "desc_en": "30 scrap. Turret support on 3 attacks. Power 100 + f(INT)×500.",
        "unlock_cond": "[메카니컬 테크] 전직 후 고철 누적 100개 달성",
    },
    "signal_trace": {
        "id": "signal_trace", "name": "주파수 역추적", "name_en": "Signal Trace", "job": "mech", "tier": "unique",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 다음 공격 치명타 확정. |INT-DEX|≤3 시 CRT배율↑+스턴.",
        "desc_en": "RAM 2. Next attack is a guaranteed critical. If |INT-DEX|≤3: higher CRT multiplier + stun.",
        "unlock_cond": "[메카니컬 테크] |INT-DEX|≤3 유지 3전투 승리",
    },
    "grid_intrude": {
        "id": "grid_intrude", "name": "그리드 침투", "name_en": "Grid Intrude", "job": "net", "tier": "unique",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 반격 차단 + 다음 적 공격 -30% + 내 다음 공격 +15%.",
        "desc_en": "RAM 1. Blocks the counterattack + next enemy attack -30% + your next attack +15%.",
        "unlock_cond": "[넷 포스] cyber 가중치 누적 5+ 달성",
    },
    "protocol_glitch": {
        "id": "protocol_glitch", "name": "프로토콜 위조", "name_en": "Protocol Glitch", "job": "net", "tier": "unique",
        "cost_type": "ram", "cost": 3,
        "desc": "RAM 3. Pr_glitch=0.15+f(INT)×0.8. 성공 시 피해 0 위조.",
        "desc_en": "RAM 3. Pr_glitch=0.15+f(INT)×0.8. On success the enemy hit deals 0.",
        "unlock_cond": "[넷 포스] |INT-VIT|≤3 유지 3전투 승리",
    },

    # ════════════════════════════════════════════════════════════════
    # [특화 스킬] special — 메인 직업 스킬. 각성 시 지급.
    # ════════════════════════════════════════════════════════════════

    # ── 컴뱃 포스 (2개) ──────────────────────────────────────────────
    "hydraulic_crush": {
        "id": "hydraulic_crush", "name": "유압 분쇄", "name_en": "Hydraulic Crush", "job": "combat", "tier": "special",
        "cost_type": "hp", "cost": 0,   # 실제: HP 15%
        "desc": "현재 HP 15% 소모. 다음 공격 ×1.8 + 적 방어력 50% 관통.",
        "desc_en": "Costs 15% of current HP. Next attack ×1.8 + 50% armor penetration.",
    },
    "iron_body": {
        "id": "iron_body", "name": "철제 의체", "name_en": "Iron Body", "job": "combat", "tier": "special",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. 다음 3회 피격 피해 -40% (VIT가 높을수록 차단율 증가).",
        "desc_en": "10 scrap. Next 3 hits -40% damage (higher VIT blocks more).",
    },

    # ── 메카니컬 테크 (2개) ───────────────────────────────────────────
    "scrap_construct": {
        "id": "scrap_construct", "name": "고철 구조체", "name_en": "Scrap Construct", "job": "mech", "tier": "special",
        "cost_type": "materials", "cost": 20,
        "desc": "고철 20개. 2턴간 피해 -25% + 보스 패턴 학습 차단.",
        "desc_en": "20 scrap. 2 turns: damage -25% + blocks boss pattern learning.",
    },
    "overclock_repair": {
        "id": "overclock_repair", "name": "과부하 수리", "name_en": "Overclock Repair", "job": "mech", "tier": "special",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. HP 즉시 회복: max_HP × (0.15 + f(INT)×0.3). RAM +1 회복.",
        "desc_en": "10 scrap. Instant heal: max_HP × (0.15 + f(INT)×0.3). RAM +1.",
    },

    # ── 넷 포스 (2개) ─────────────────────────────────────────────────
    "data_siphon": {
        "id": "data_siphon", "name": "데이터 사이펀", "name_en": "Data Siphon", "job": "net", "tier": "special",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 이번 전투 적 공격력 -30% 영구 약화. 매 턴 종료 시 RAM +1 자동 회수.",
        "desc_en": "RAM 2. Enemy ATK -30% for the rest of this combat. RAM +1 recovered at each turn end.",
    },
    "ghost_protocol": {
        "id": "ghost_protocol", "name": "고스트 프로토콜", "name_en": "Ghost Protocol", "job": "net", "tier": "special",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 이번 턴 적 반격 차단. 다음 공격 치명타율 +30% 추가.",
        "desc_en": "RAM 1. Blocks the enemy counterattack this turn. Next attack +30% crit chance.",
    },

    # ── 황금 분할 (2개) ───────────────────────────────────────────────
    "synthesis_drive": {
        "id": "synthesis_drive", "name": "종합 구동", "name_en": "Synthesis Drive", "job": "balanced", "tier": "special",
        "cost_type": "hp", "cost": 0,   # 실제: HP 5% + RAM 1 (복합)
        "desc": "HP 5% + RAM 1 소모. VIT·INT·DEX 합산 f(A) 기반 즉각 피해 + 허기·갈증 +8.",
        "desc_en": "Costs 5% HP + RAM 1. Instant damage from combined VIT·INT·DEX f(A) + hunger·thirst +8.",
    },
    "equilibrium": {
        "id": "equilibrium", "name": "균형점", "name_en": "Equilibrium", "job": "balanced", "tier": "special",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. HP·허기·갈증 각 +10% 동시 소량 회복 (황금 분할 재조율).",
        "desc_en": "10 scrap. Restores HP, hunger and thirst by 10% each (golden ratio recalibration).",
    },

    # ════════════════════════════════════════════════════════════════
    # [보조 스킬] aux — 자유 장착. (Act 2+ 획득 경로 예정)
    # ════════════════════════════════════════════════════════════════
    "vital_pump": {
        "id": "vital_pump", "name": "생명 펌프", "name_en": "Vital Pump", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 15,
        "desc": "고철 15개. HP 즉시 회복: max_HP × (0.10 + f(VIT)×0.5).",
        "desc_en": "15 scrap. Instant heal: max_HP × (0.10 + f(VIT)×0.5).",
    },
    "scrap_armor": {
        "id": "scrap_armor", "name": "고철 방어구 증설", "name_en": "Scrap Armor", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 20,
        "desc": "고철 20개. 다음 2회 피격 피해 -20%.",
        "desc_en": "20 scrap. Next 2 hits -20% damage.",
    },
    "junk_cannon": {
        "id": "junk_cannon", "name": "고철 함포", "name_en": "Junk Cannon", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 25,
        "desc": "고철 25개. 즉각 피해 300 + VIT×15. (적 반격 없음)",
        "desc_en": "25 scrap. Instant damage 300 + VIT×15. (No enemy counterattack)",
    },
    "bioloop": {
        "id": "bioloop", "name": "바이오 피드백 루프", "name_en": "Bioloop", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 다음 2회 공격 시 허기·갈증 +5 자동 흡수.",
        "desc_en": "RAM 2. Next 2 attacks restore hunger·thirst +5.",
    },
    "ram_condenser": {
        "id": "ram_condenser", "name": "RAM 압축기", "name_en": "RAM Condenser", "job": "any", "tier": "aux",
        "cost_type": "materials", "cost": 10,
        "desc": "고철 10개. 즉시 RAM +2 회복.",
        "desc_en": "10 scrap. Instantly restores RAM +2.",
    },
    "code_compile": {
        "id": "code_compile", "name": "코드 컴파일", "name_en": "Code Compile", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 다음 2턴 보스 딥러닝 패턴 학습 차단.",
        "desc_en": "RAM 1. Blocks boss deep-learning pattern analysis for 2 turns.",
    },
    "pulse_grenade": {
        "id": "pulse_grenade", "name": "펄스 수류탄", "name_en": "Pulse Grenade", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 2,
        "desc": "RAM 2. 즉각 피해 200 + INT×10. 보스 E지수 -3.",
        "desc_en": "RAM 2. Instant damage 200 + INT×10. Boss E index -3.",
    },
    "kinetic_burst": {
        "id": "kinetic_burst", "name": "운동 폭발", "name_en": "Kinetic Burst", "job": "any", "tier": "aux",
        "cost_type": "hp", "cost": 0,
        "desc": "현재 HP 5% 소모. 다음 공격 +DEX×20 고정 추가 피해.",
        "desc_en": "Costs 5% of current HP. Next attack +DEX×20 flat bonus damage.",
    },
    "neural_acc": {
        "id": "neural_acc", "name": "신경 가속기", "name_en": "Neural Acc", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 다음 공격 치명타율 ×2 (상한 75%).",
        "desc_en": "RAM 1. Next attack crit chance ×2 (max 75%).",
    },
    "void_shift": {
        "id": "void_shift", "name": "허공 전위", "name_en": "Void Shift", "job": "any", "tier": "aux",
        "cost_type": "ram", "cost": 1,
        "desc": "RAM 1. 다음 탈출 시도를 SAFE 결과로 강제 고정.",
        "desc_en": "RAM 1. Your next escape attempt is forced to a SAFE result.",
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

def job_label(job) -> str:
    """직업 표시 이름 (언어별). JOB_LABEL은 한국어 원본."""
    return t(f"job_{job}") if job in JOB_LABEL else str(job)


def skill_name(skill_id, short=False) -> str:
    """스킬 표시 이름 (언어별). short: 전투 버튼 칸에 맞게 자른다 (한국어 6자, 영어 16자)."""
    name = db_t(SKILL_DEFS.get(skill_id, {}), "name") or str(skill_id)
    return name[:16 if i18n.LANG == "en" else 6] if short else name

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
    if not sk: return False, t('skill_unknown_id')
    ct = sk["cost_type"]

    if ct == "hp":
        pct = 0.05 if skill_id in ("kinetic_burst", "synthesis_drive") else 0.15 if skill_id == "hydraulic_crush" else 0.10
        cost = max(1, int(player.hp * pct))
        if player.hp <= cost + 1:
            return False, t('skill_err_hp', hp=player.hp, min=cost + 2)
        # synthesis_drive: HP + RAM 복합
        if skill_id == "synthesis_drive" and player.max_ram < 1:
            return False, t('skill_err_ram', owned=player.max_ram, need=1)
    elif ct == "ram":
        if player.max_ram < sk["cost"]:
            return False, t('skill_err_ram', owned=player.max_ram, need=sk['cost'])
    elif ct == "materials":
        if player.materials < sk["cost"]:
            return False, t('skill_err_materials', owned=player.materials, need=sk['cost'])
    return True, ""

# ─────────────────────────────────────────────────────────────────────
# § 스킬 실행
# ─────────────────────────────────────────────────────────────────────

def execute(player, skill_id: str, combat_ctx: dict) -> bool:
    ok, reason = can_use(player, skill_id)
    if not ok:
        print(Fore.RED + t('skill_fail', reason=reason) + Style.RESET_ALL)
        time.sleep(0.8)
        return False

    sk = SKILL_DEFS[skill_id]

    # ── ★ 특화 스킬 (메인 직업 스킬) ─────────────────────────────────

    if skill_id == "hydraulic_crush":
        cost = max(1, int(player.hp * 0.15))
        player.hp = max(1, player.hp - cost)
        player.active_buffs["hydraulic_crush"] = True
        print(f"\n  {Fore.RED + Style.BRIGHT}{t('skill_hydraulic_crush_activate', cost=cost)}{Style.RESET_ALL}")
        type_text("  " + t('skill_hydraulic_crush_desc'), 0.022)

    elif skill_id == "iron_body":
        player.materials -= sk["cost"]
        # VIT 기반 방어율 강화 (VIT 높을수록 -40% 초과)
        shield_pct = min(0.60, 0.40 + _fa(player.vit) * 0.2)
        player.active_buffs["iron_body"] = {"charges": 3, "pct": shield_pct}
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}{t('skill_iron_body_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_iron_body_desc', pct=f"{shield_pct*100:.0f}", vit=player.vit), 0.022)

    elif skill_id == "scrap_construct":
        player.materials -= sk["cost"]
        player.active_buffs["scrap_construct"] = 2
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}{t('skill_scrap_construct_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_scrap_construct_desc'), 0.022)

    elif skill_id == "overclock_repair":
        player.materials -= sk["cost"]
        heal = max(1, math.floor(player.max_hp * (0.15 + _fa(player.int_s) * 0.3)))
        player.hp = min(player.max_hp, player.hp + heal)
        player.max_ram = min(8, player.max_ram + 1)
        print(f"\n  {Fore.GREEN + Style.BRIGHT}{t('skill_overclock_repair_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_overclock_repair_desc', heal=heal, int_s=player.int_s), 0.022)

    elif skill_id == "data_siphon":
        player.max_ram -= sk["cost"]
        player.active_buffs["data_siphon"] = True         # 전투 지속 디버프
        player.active_buffs["data_siphon_regen"] = True   # 첫 턴 RAM 회수
        print(f"\n  {Fore.CYAN + Style.BRIGHT}{t('skill_data_siphon_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_data_siphon_desc'), 0.022)

    elif skill_id == "ghost_protocol":
        player.max_ram -= sk["cost"]
        combat_ctx["skip_enemy_attack"] = True
        player.active_buffs["ghost_crt"] = 0.30
        print(f"\n  {Fore.MAGENTA + Style.BRIGHT}{t('skill_ghost_protocol_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_ghost_protocol_desc'), 0.022)

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
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}{t('skill_synthesis_drive_activate', hp_cost=hp_cost)}{Style.RESET_ALL}")
        type_text("  " + t('skill_synthesis_drive_desc', dmg=dmg, fa_sum=fa_sum), 0.022)

    elif skill_id == "equilibrium":
        player.materials -= sk["cost"]
        hp_gain = max(1, int(player.max_hp * 0.10))
        player.hp = min(player.max_hp, player.hp + hp_gain)
        player.hunger = min(100, player.hunger + 10)
        player.thirst = min(100, player.thirst + 10)
        print(f"\n  {Fore.GREEN}{t('skill_equilibrium_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_equilibrium_desc', gain=hp_gain), 0.022)

    # ── ★ 특수 스킬 (unique — 조건 언락) ─────────────────────────────

    elif skill_id == "overclock":
        cost = max(1, int(player.hp * 0.10))
        player.hp = max(1, player.hp - cost)
        player.active_buffs["overclock"] = 2
        print(f"\n  {Fore.RED + Style.BRIGHT}{t('skill_overclock_activate', cost=cost)}{Style.RESET_ALL}")
        type_text("  " + t('skill_overclock_desc'), 0.022)

    elif skill_id == "bio_reap":
        player.max_ram -= sk["cost"]
        player.active_buffs["bio_reap"] = 1
        vit_dex_bal = abs(player.vit - player.dex) <= 3
        pr = min(0.70, 0.10 + (_fa(player.vit) + _fa(player.dex)) * 0.5)
        tag = t('skill_bio_reap_tag_bal', pr=pr * 100) if vit_dex_bal else t('skill_bio_reap_tag_unbal')
        print(f"\n  {Fore.RED}{t('skill_bio_reap_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_bio_reap_desc') + tag, 0.022)

    elif skill_id == "sentry_infra":
        player.materials -= sk["cost"]
        sentry_dmg = 100 + int(_fa(player.int_s) * 500)
        player.active_buffs["sentry"] = {"charges": 3, "dmg": sentry_dmg}
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}{t('skill_sentry_infra_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_sentry_infra_desc', dmg=sentry_dmg, int_s=player.int_s), 0.022)

    elif skill_id == "signal_trace":
        player.max_ram -= sk["cost"]
        int_dex_bal = abs(player.int_s - player.dex) <= 3
        crt_mult = round(1.5 + _fa(player.dex) * 0.5, 3) if int_dex_bal else 1.5
        pr_stun  = min(0.50, 0.15 + _fa(player.int_s) * 0.3) if int_dex_bal else 0.0
        player.active_buffs["signal_trace"] = {
            "crt_mult": crt_mult, "pr_stun": pr_stun, "is_hybrid": int_dex_bal
        }
        tag = t('skill_signal_trace_tag_bal', mult=crt_mult, pct=pr_stun * 100) if int_dex_bal else ""
        print(f"\n  {Fore.CYAN + Style.BRIGHT}{t('skill_signal_trace_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_signal_trace_desc') + tag, 0.022)

    elif skill_id == "grid_intrude":
        player.max_ram -= sk["cost"]
        combat_ctx["skip_enemy_attack"] = True
        player.active_buffs["grid_def"] = 1
        player.active_buffs["grid_atk"] = 1
        print(f"\n  {Fore.CYAN + Style.BRIGHT}{t('skill_grid_intrude_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_grid_intrude_desc'), 0.022)

    elif skill_id == "protocol_glitch":
        player.max_ram -= sk["cost"]
        int_vit_bal = abs(player.int_s - player.vit) <= 3
        pr = min(0.65, 0.15 + _fa(player.int_s) * 0.8) if int_vit_bal else 0.30
        player.active_buffs["protocol_glitch"] = {"pr": pr, "is_hybrid": int_vit_bal}
        tag = t('skill_protocol_glitch_tag_bal', pr=pr * 100) if int_vit_bal else t('skill_protocol_glitch_tag_unbal')
        print(f"\n  {Fore.MAGENTA + Style.BRIGHT}{t('skill_protocol_glitch_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_protocol_glitch_desc') + tag, 0.022)

    # ── 보조 스킬 ─────────────────────────────────────────────────────

    elif skill_id == "vital_pump":
        player.materials -= sk["cost"]
        heal = max(1, math.floor(player.max_hp * (0.10 + _fa(player.vit) * 0.5)))
        player.hp = min(player.max_hp, player.hp + heal)
        print(f"\n  {Fore.GREEN + Style.BRIGHT}{t('skill_vital_pump_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_vital_pump_desc', heal=heal, vit=player.vit), 0.022)

    elif skill_id == "scrap_armor":
        player.materials -= sk["cost"]
        player.active_buffs["scrap_armor"] = 2
        print(f"\n  {Fore.YELLOW}{t('skill_scrap_armor_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_scrap_armor_desc'), 0.022)

    elif skill_id == "junk_cannon":
        player.materials -= sk["cost"]
        dmg = 300 + player.vit * 15
        combat_ctx["aux_skill_dmg"] = dmg
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}{t('skill_junk_cannon_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_junk_cannon_desc', dmg=dmg, vit=player.vit), 0.022)

    elif skill_id == "bioloop":
        player.max_ram -= sk["cost"]
        player.active_buffs["bioloop"] = 2
        print(f"\n  {Fore.GREEN}{t('skill_bioloop_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_bioloop_desc'), 0.022)

    elif skill_id == "ram_condenser":
        player.materials -= sk["cost"]
        gain = 2 if player.max_ram < 6 else 1
        player.max_ram += gain
        print(f"\n  {Fore.CYAN}{t('skill_ram_condenser_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_ram_condenser_desc', gain=gain, ram=player.max_ram), 0.022)

    elif skill_id == "code_compile":
        player.max_ram -= sk["cost"]
        player.active_buffs["code_compile"] = 2
        print(f"\n  {Fore.CYAN}{t('skill_code_compile_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_code_compile_desc'), 0.022)

    elif skill_id == "pulse_grenade":
        player.max_ram -= sk["cost"]
        dmg = 200 + player.int_s * 10
        combat_ctx["aux_skill_dmg"] = dmg
        combat_ctx["pulse_e_drain"] = True
        print(f"\n  {Fore.CYAN + Style.BRIGHT}{t('skill_pulse_grenade_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_pulse_grenade_desc', dmg=dmg, int_s=player.int_s), 0.022)

    elif skill_id == "kinetic_burst":
        cost = max(1, int(player.hp * 0.05))
        player.hp = max(1, player.hp - cost)
        bonus = player.dex * 20
        player.active_buffs["kinetic_burst"] = bonus
        print(f"\n  {Fore.RED}{t('skill_kinetic_burst_activate', cost=cost)}{Style.RESET_ALL}")
        type_text("  " + t('skill_kinetic_burst_desc', bonus=bonus, dex=player.dex), 0.022)

    elif skill_id == "neural_acc":
        player.max_ram -= sk["cost"]
        player.active_buffs["neural_acc"] = 1
        print(f"\n  {Fore.CYAN}{t('skill_neural_acc_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_neural_acc_desc'), 0.022)

    elif skill_id == "void_shift":
        player.max_ram -= sk["cost"]
        player.active_buffs["void_shift"] = 1
        print(f"\n  {Fore.MAGENTA}{t('skill_void_shift_activate', cost=sk['cost'])}{Style.RESET_ALL}")
        type_text("  " + t('skill_void_shift_desc'), 0.022)

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
            action_logs.append(t('skill_log_overclock_end', drain=drain))
        else:
            action_logs.append(t('skill_log_overclock_tick', remain=remain, drain=drain))

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
            action_logs.append(t('skill_log_bio_reap_success', h_g=h_g, t_g=t_g, pr=pr * 100))
        else:
            action_logs.append(t('skill_log_bio_reap_fail', pr=pr * 100))

    # 바이오 피드백 루프
    if "bioloop" in player.active_buffs:
        player.hunger = min(100, player.hunger + 5)
        player.thirst = min(100, player.thirst + 5)
        player.active_buffs["bioloop"] -= 1
        remain = player.active_buffs["bioloop"]
        if remain <= 0:
            del player.active_buffs["bioloop"]
            action_logs.append(t('skill_log_bioloop_end'))
        else:
            action_logs.append(t('skill_log_bioloop_tick', remain=remain))


def get_atk_mult(player) -> float:
    return 2.0 if "overclock" in player.active_buffs else 1.0


def consume_hydraulic_crush(player, action_logs: list) -> tuple[float, float]:
    """유압 분쇄 버프 소비. 반환: (atk_mult, def_pierce_ratio)."""
    if not player.active_buffs.pop("hydraulic_crush", False):
        return 1.0, 0.0
    action_logs.append(t('skill_log_hydraulic_crush'))
    return 1.8, 0.5


def apply_signal_trace(player, combat_ctx: dict, action_logs: list) -> tuple[bool, float]:
    """signal_trace 버프 소비. 반환: (forced_crit, crt_mult)."""
    buf = player.active_buffs.pop("signal_trace", None)
    if buf is None:
        return False, 1.5
    crt_mult = buf["crt_mult"]
    pr_stun  = buf["pr_stun"]
    action_logs.append(t('skill_log_signal_trace', crt_mult=crt_mult))
    if buf["is_hybrid"] and pr_stun > 0 and random.random() < pr_stun:
        combat_ctx["skip_enemy_attack"] = True
        action_logs.append(t('skill_log_signal_trace_stun', pr=pr_stun * 100))
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
        action_logs.append(t('skill_log_grid_atk'))

    # 센트리 인프라
    sentry = player.active_buffs.get("sentry")
    if isinstance(sentry, dict) and sentry.get("charges", 0) > 0:
        s_dmg = sentry["dmg"]
        dmg  += s_dmg
        sentry["charges"] -= 1
        remain = sentry["charges"]
        if remain <= 0:
            del player.active_buffs["sentry"]
            action_logs.append(t('skill_log_sentry_end', dmg=s_dmg))
        else:
            action_logs.append(t('skill_log_sentry_tick', dmg=s_dmg, remain=remain))

    # 운동 폭발 고정 추가 피해
    kb = player.active_buffs.pop("kinetic_burst", 0)
    if kb > 0:
        dmg += kb
        action_logs.append(t('skill_log_kinetic_burst', kb=kb))

    return dmg


def apply_incoming_buffs(player, dmg_taken: int, action_logs: list, combat_ctx: dict) -> int:
    """인커밍 피해 버프."""

    # 그리드 침투 -30%
    if player.active_buffs.pop("grid_def", 0):
        dmg_taken = max(1, int(dmg_taken * 0.70))
        action_logs.append(t('skill_log_grid_def'))

    # 철제 의체 -VIT 기반 차단
    iron = player.active_buffs.get("iron_body")
    if isinstance(iron, dict) and iron.get("charges", 0) > 0:
        pct = iron["pct"]
        dmg_taken = max(1, int(dmg_taken * (1 - pct)))
        iron["charges"] -= 1
        remain = iron["charges"]
        if remain <= 0:
            del player.active_buffs["iron_body"]
            action_logs.append(t('skill_log_iron_body_end', pct=pct * 100))
        else:
            action_logs.append(t('skill_log_iron_body_tick', pct=pct * 100, remain=remain))

    # 고철 구조체 -25%
    if "scrap_construct" in player.active_buffs:
        dmg_taken = max(1, int(dmg_taken * 0.75))
        action_logs.append(t('skill_log_scrap_construct'))

    # 고철 방어구 증설 -20%
    if "scrap_armor" in player.active_buffs:
        dmg_taken = max(1, int(dmg_taken * 0.80))
        player.active_buffs["scrap_armor"] -= 1
        remain = player.active_buffs["scrap_armor"]
        if remain <= 0:
            del player.active_buffs["scrap_armor"]
            action_logs.append(t('skill_log_scrap_armor_end'))
        else:
            action_logs.append(t('skill_log_scrap_armor_tick', remain=remain))

    # 프로토콜 위조
    glitch = player.active_buffs.pop("protocol_glitch", None)
    if glitch is not None:
        pr = glitch["pr"]
        if random.random() < pr:
            action_logs.append(t('skill_log_glitch_success', pr=pr * 100))
            if glitch["is_hybrid"]:
                combat_ctx["skip_enemy_attack"] = True
                action_logs.append(t('skill_log_glitch_chain'))
            dmg_taken = 0
        else:
            action_logs.append(t('skill_log_glitch_fail', pr=pr * 100))

    return dmg_taken


def end_of_turn_tick(player, action_logs: list):
    """매 턴 종료 시 호출 — 버프 카운터 감소 및 tick 효과."""

    # 데이터 사이펀 RAM 회수 (활성 중일 때 매 턴)
    if "data_siphon" in player.active_buffs:
        player.max_ram = min(8, player.max_ram + 1)
        action_logs.append(t('skill_log_data_siphon'))

    # 고철 구조체 턴 감소
    if "scrap_construct" in player.active_buffs:
        player.active_buffs["scrap_construct"] -= 1
        if player.active_buffs["scrap_construct"] <= 0:
            del player.active_buffs["scrap_construct"]
            action_logs.append(t('skill_log_scrap_construct_end'))

    # 코드 컴파일 턴 감소
    if "code_compile" in player.active_buffs:
        player.active_buffs["code_compile"] -= 1
        if player.active_buffs["code_compile"] <= 0:
            del player.active_buffs["code_compile"]
            action_logs.append(t('skill_log_code_compile_end'))
