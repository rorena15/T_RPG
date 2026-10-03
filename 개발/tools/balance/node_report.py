"""지점 지도 봇 결과 표 (sim.py --out으로 모은 jsonl). 설계 문서 7절의 비교 지표.

쓰는 법:  python tools/balance/node_report.py results/node_50.jsonl [results/node_70.jsonl ...]
"""
import collections
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def report(path):
    rows = load(path)
    g = collections.defaultdict(list)
    for r in rows:
        g[(r["diff"], r["farm"])].append(r)
    print(f"\n## {path} ({len(rows)}판)\n")
    print("| 난이도 | 탐색 | 클리어 | 보스 도달 | 평균 턴 | 굶주림 | 들른 지점 | 랜드마크 | B / C | 방공호 발견 턴 | 멈춤 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    order = {"easy": 0, "normal": 1, "hard": 2}
    for (d, f), rs in sorted(g.items(), key=lambda kv: (order.get(kv[0][0], 9), kv[0][1])):
        n = len(rs)
        clear = sum(r["result"] == "clear" for r in rs) / n * 100
        boss = sum(bool(r.get("state")) for r in rs) / n * 100
        turns = sum(r.get("turns", 0) for r in rs) / n
        starve = sum(str(r.get("ending", "")).startswith("starve") for r in rs) / n * 100
        nd = [r["node"] for r in rs if r.get("node")]
        vis = sum(x["visited"] / x["count"] for x in nd) / max(1, len(nd)) * 100
        lm = sum(x["landmarks"] for x in nd) / max(1, len(nd))
        fr = [r["frag"] for r in rs if r.get("frag")]
        b = sum(x["b"] for x in fr) / max(1, len(fr))
        c = sum(x["c"] for x in fr) / max(1, len(fr))
        bt = [x["bunker_found_turn"] for x in nd if x.get("bunker_found_turn") is not None]
        bts = f"{sum(bt) / len(bt):.0f}" if bt else "-"
        crash = sum(str(r["result"]).startswith("CRASH") + bool(r.get("stuck")) for r in rs)
        print(f"| {d} | {f} | {clear:.0f}% | {boss:.0f}% | {turns:.0f} | {starve:.0f}% | {vis:.0f}% | {lm:.1f} | {b:.1f} / {c:.1f} | {bts} | {crash} |")
    ends = collections.Counter(r.get("ending") or r["result"] for r in rows)
    print("\n결말: " + ", ".join(f"{k} {v * 100 / len(rows):.0f}%" for k, v in ends.most_common(8)))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        report(p)
