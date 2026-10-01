"""게임성 검증: 봇을 돌려 목표 승률·기준선 비교·결말 분포·게임성 지표를 한 문서로 남긴다.

  # 전체 검증 (난이도 3 × 탐색 0/20/45/90회 × 30판) → results/<이름>.md, results/<이름>_runs.jsonl
  python tools/balance/verify.py --name v2.1_gameplay
  # 이미 돌린 결과로 문서만 다시
  python tools/balance/verify.py --name v2.1_gameplay --reuse
  # 성향 몰아주기 비교 (BOT_FOCUS=kinetic/scrap/cyber, 노멀 · 탐색 45회)도 같이
  python tools/balance/verify.py --name v2.1_gameplay --focus

기준선은 results/baseline_runs.jsonl (게임성 개편 전 코드로 같은 조합을 돌린 것).
통과 조건 (TARGETS): 탐색 0회는 클리어 0%, 탐색 90회는 난이도별 목표 ± TOL, 봇이 멈춘 판 0.
"""
import argparse
import collections
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim  # noqa: E402

RESULTS = os.path.join(HERE, "results")
BASELINE = os.path.join(RESULTS, "baseline_runs.jsonl")
DIFFS = ["easy", "normal", "hard"]
FARMS = [0, 20, 45, 90]
TARGETS = {"easy": 70, "normal": 40, "hard": 20}   # 탐색 90회 클리어 목표 (%)
TOL = 12                                           # 30판 기준 흔들림을 감안한 허용 폭 (%p)


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def rates(runs):
    c = collections.defaultdict(collections.Counter)
    for r in runs:
        k = (r["diff"], r["farm"])
        c[k]["n"] += 1
        c[k]["clear"] += r["result"] == "clear"
        c[k]["boss"] += bool(r.get("state"))
        c[k]["crash"] += str(r["result"]).startswith("CRASH")
    return c


def pct(x, key):
    return x[key] / x["n"] * 100 if x["n"] else float("nan")


def winrate_table(new, base):
    rn, rb = rates(new), rates(base)
    out = ["| 난이도 | 탐색 | 클리어 (전 → 후) | 보스 도달 (전 → 후) | 판 수 |", "|---|---|---|---|---|"]
    for d in DIFFS:
        for f in FARMS:
            a, b = rb[(d, f)], rn[(d, f)]
            if not b["n"]:
                continue
            before = f"{pct(a, 'clear'):.0f}%" if a["n"] else "-"
            reach = f"{pct(a, 'boss'):.0f}%" if a["n"] else "-"
            out.append(f"| {d} | {f} | {before} → **{pct(b, 'clear'):.0f}%** | {reach} → {pct(b, 'boss'):.0f}% | {b['n']} |")
    return out


def checks(new):
    rn = rates(new)
    res = []
    for d in DIFFS:
        x0, x90 = rn[(d, 0)], rn[(d, 90)]
        if x0["n"]:
            res.append((f"{d} 탐색 0회 클리어 0%", pct(x0, "clear") == 0, f"{pct(x0, 'clear'):.0f}%"))
        if x90["n"]:
            v = pct(x90, "clear")
            res.append((f"{d} 탐색 90회 클리어 {TARGETS[d]}% ± {TOL}", abs(v - TARGETS[d]) <= TOL, f"{v:.0f}%"))
    crashes = sum(x["crash"] for x in rn.values())
    res.append(("봇이 멈춘 판 없음", crashes == 0, f"{crashes}판"))
    return res


def counter_table(title, cnt, total):
    out = [f"| {title} | 판 | 비율 |", "|---|---|---|"]
    for k, v in cnt.most_common():
        out.append(f"| {k} | {v} | {v / max(1, total) * 100:.0f}% |")
    return out


def gameplay_metrics(runs):
    ok = [r for r in runs if r.get("traits") is not None]
    n = max(1, len(ok))
    lines = []
    # 성향 단계
    tiers = collections.Counter()
    for r in ok:
        tiers[max(r["traits"].values())] += 1
    lines.append("**가장 높은 성향 단계 (판 수)**: " + ", ".join(f"{k}단계 {tiers[k]}" for k in range(4)))
    per = {k: sum(r["traits"].get(k, 0) >= 1 for r in ok) for k in ("kinetic", "scrap", "cyber")}
    lines.append("**성향별 1단계 이상 도달 비율**: " + ", ".join(f"{k} {v / n * 100:.0f}%" for k, v in per.items()))
    # 적 행동
    beh = collections.Counter()
    for r in ok:
        beh.update(r.get("beh") or {})
    lines.append("**적 행동 (판당 평균)**: " + ", ".join(f"{k} {v / n:.1f}" for k, v in sorted(beh.items())))
    jam = sum(r.get("bot_jam") or 0 for r in ok)
    guard = sum(r.get("bot_guard") or 0 for r in ok)
    lines.append(f"**봇의 대응**: 증원 신호 교란 {jam}번, 드론 방어 태세에 바리케이드 {guard}번")
    # 위험도·수확 체감
    ds = [0, 0, 0]
    for r in ok:
        for i, v in enumerate(r.get("danger_srch") or [0, 0, 0]):
            ds[i] += v
    tot = max(1, sum(ds))
    lines.append("**탐색한 칸의 위험도**: " + ", ".join(f"{lab} {v / tot * 100:.0f}%" for lab, v in zip(("낮음", "보통", "높음"), ds)))
    cyc = [r.get("cycles") or 0 for r in ok]
    lines.append(f"**다시 채워진 칸 (판당 평균)**: {sum(cyc) / n:.1f}")
    return lines


def focus_section(name, n, jobs, seed0):
    lines = ["## 성향 몰아주기 비교 (노멀 · 탐색 45회)", "",
             "봇이 스토리·이벤트에서 한 성향만 고르게 해서, 성향 보너스가 결과를 얼마나 바꾸는지 본다.", "",
             "| 몰아준 성향 | 클리어 | 보스 도달 | 평균 성향 단계 |", "|---|---|---|---|"]
    for focus in ("random", "kinetic", "scrap", "cyber"):
        path = os.path.join(RESULTS, f"{name}_focus_{focus}.jsonl")
        if not os.path.exists(path):
            sim.simulate(["normal"], [45], n, jobs, seed0, {"BOT_FOCUS": focus}, path)
        runs = load(path)
        rn = rates(runs)[("normal", 45)]
        tl = [max((r.get("traits") or {"x": 0}).values()) for r in runs]
        lines.append(f"| {focus} | {pct(rn, 'clear'):.0f}% | {pct(rn, 'boss'):.0f}% | {sum(tl) / max(1, len(tl)):.1f} |")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="결과 이름 (results/<name>.md)")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=20000, help="기준선과 같은 시드를 쓰면 같은 판 묶음끼리 비교된다")
    ap.add_argument("--env", action="append", default=[], help="봇 환경 변수 (예: BOSS_MULT=1.2)")
    ap.add_argument("--reuse", action="store_true", help="이미 있는 결과 jsonl로 문서만 다시 만든다")
    ap.add_argument("--focus", action="store_true", help="성향 몰아주기 비교도 돌린다")
    a = ap.parse_args()
    os.makedirs(RESULTS, exist_ok=True)
    runs_path = os.path.join(RESULTS, f"{a.name}_runs.jsonl")
    env = dict(kv.split("=", 1) for kv in a.env)
    if not a.reuse:
        if os.path.exists(runs_path):
            os.remove(runs_path)
        sim.simulate(DIFFS, FARMS, a.n, a.jobs, a.seed0, env, runs_path)
    new, base = load(runs_path), load(BASELINE)

    ck = checks(new)
    doc = [f"# 게임성 검증: {a.name}", "",
           f"{datetime.date.today()} · 조합마다 {a.n}판 · 시드 {a.seed0}부터" + (f" · 환경 {env}" if env else ""), "",
           "## 통과 조건", "", "| 항목 | 결과 | 값 |", "|---|---|---|"]
    doc += [f"| {name} | {'통과' if ok else '**실패**'} | {val} |" for name, ok, val in ck]
    doc += ["", "## 승률 (기준선 → 이번)", "", *winrate_table(new, base), ""]
    ends = collections.Counter(r.get("ending") or r["result"] for r in new)
    doc += ["## 결말 분포", "", *counter_table("결말", ends, len(new)), ""]
    doc += ["## 게임성 지표", "", *[f"- {x}" for x in gameplay_metrics(new)], ""]
    if a.focus:
        doc += focus_section(a.name, a.n, a.jobs, a.seed0 + 5000) + [""]
    path = os.path.join(RESULTS, f"{a.name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")
    print("\n".join(doc))
    print(f"\n저장: {os.path.relpath(path)}")
    sys.exit(0 if all(ok for _, ok, _ in ck) else 1)


if __name__ == "__main__":
    main()
