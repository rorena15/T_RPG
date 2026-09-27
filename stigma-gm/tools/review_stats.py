"""배치별 문체 통계. 반복 표현과 편차를 찾아 검수 우선순위를 정한다.

사용: python review_stats.py [파일 접두어...]   예) python review_stats.py samples_pilot samples_b01a samples_b01b
"""
import collections
import re
import statistics
import sys

from build import load_samples


def sentences(text):
    return [x for x in re.split(r"(?<=[.!?…])\s+", text.strip()) if x]


def ngrams(text, n=3):
    toks = re.findall(r"[가-힣A-Za-z0-9]+", text)
    return [" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)]


def main(prefixes):
    groups = collections.defaultdict(list)
    for s in load_samples():
        src = s["_src"][:-3]
        if not prefixes or src in prefixes:
            groups[src].append(s)

    print(f"{'batch':<20}{'n':>4}{'sent/avg':>10}{'chars/sent':>12}{'check%':>8}{'history%':>10}")
    for src, ss in groups.items():
        sents = [sentences(s["narration"]) for s in ss]
        lens = [len(x) for sl in sents for x in sl]
        print(f"{src:<20}{len(ss):>4}{statistics.mean(map(len, sents)):>10.1f}{statistics.mean(lens):>12.1f}"
              f"{100 * sum(s['out']['check'] is not None for s in ss) / len(ss):>7.0f}%"
              f"{100 * sum(bool(s.get('history')) for s in ss) / len(ss):>9.0f}%")

    # 같은 3-gram이 여러 샘플에 반복되면 말버릇 후보
    print("\n반복 3-gram (3개 이상 샘플에 등장):")
    where = collections.defaultdict(set)
    for ss in groups.values():
        for s in ss:
            for g in set(ngrams(s["narration"])):
                where[g].add(s["id"])
    rep = sorted(((g, ids) for g, ids in where.items() if len(ids) >= 3), key=lambda x: -len(x[1]))
    for g, ids in rep[:25]:
        print(f"  {len(ids):>2}  {g}  ({', '.join(sorted(ids)[:6])}{' ...' if len(ids) > 6 else ''})")

    # 첫 문장이 '당신은'으로 시작하는 비율 (단조로운 도입 체크)
    print("\n첫 문장 '당신은/당신이' 시작 비율:")
    for src, ss in groups.items():
        k = sum(sentences(s["narration"])[0].startswith(("당신은", "당신이")) for s in ss)
        print(f"  {src:<20}{100 * k / len(ss):.0f}%")


if __name__ == "__main__":
    main(sys.argv[1:])
