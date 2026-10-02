"""지점 지도 생성 시험 (node_map.py). 시드를 여러 개 만들어 보며 진행 로그와 요약을 남긴다.

쓰는 법 (개발 폴더에서):
  python tools/balance/map_gen.py                 # 시드 1~10000, 로그는 tools/balance/results/map_gen.log
  python tools/balance/map_gen.py --n 2000 --count 70
  python tools/balance/map_gen.py --show 7        # 시드 7 지도 하나를 글자 그림으로

로그 보기 (다른 창, PowerShell):  Get-Content tools/balance/results/map_gen.log -Wait -Encoding utf8
"""
import argparse
import collections
import os
import sys
import time

sys.path.insert(0, os.getcwd())
import node_map  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "results", "map_gen.log")

_orig_try = node_map.NodeMap._try_build
_TRIES = [0]


def _counted(self, rng):
    _TRIES[0] += 1
    return _orig_try(self, rng)


node_map.NodeMap._try_build = _counted


def show(seed, count):
    m = node_map.NodeMap(seed=seed, count=count)
    w = max(p[0] for p in m.nodes) + 1
    h = max(p[1] for p in m.nodes) + 1
    mark = {"start": "S", "bunker": "B", "border": "W", "ruin": "."}
    rows = [[" "] * w for _ in range(h)]
    for p, nd in m.nodes.items():
        c = mark.get(nd["kind"], "L")
        if list(p) == list(m.forge_pos):
            c = "F"
        rows[p[1]][p[0]] = c
    print(f"시드 {seed}: S 출발 · B 방공호 · F 강화소 · L 랜드마크 · W 경계 지대 · . 폐허 (위가 북쪽)")
    for y in range(h - 1, -1, -1):
        print("".join(rows[y]))
    print(f"방공호까지 {m.path_dist(m.start_pos, m.bunker_pos)}턴, 강화소까지 {m.path_dist(m.start_pos, m.forge_pos)}턴")
    for p, nd in sorted(m.nodes.items(), key=lambda kv: (-kv[1]["ring"], kv[0])):
        if nd["kind"] == "landmark":
            print(f"  {nd['scene']:15} {p} 권역 {nd['ring']}{' (멀리서 보임)' if nd['scene'] in node_map.TALL else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--count", type=int, default=None, help="지점 수 (기본 constants.NODE_COUNT)")
    ap.add_argument("--show", type=int, default=None)
    a = ap.parse_args()
    if a.show is not None:
        return show(a.show, a.count)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log = open(LOG, "w", encoding="utf-8")

    def out(line):
        log.write(line + "\n")
        log.flush()
        print(line)

    deg, lens, bdist, fdist, tries = (collections.Counter() for _ in range(5))
    fails, t0 = [], time.time()
    out(f"지점 지도 생성 시험 · 시드 1~{a.n} · 지점 {a.count or node_map.constants.NODE_COUNT}개 · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for seed in range(1, a.n + 1):
        _TRIES[0] = 0
        try:
            m = node_map.NodeMap(seed=seed, count=a.count)
        except RuntimeError:
            fails.append(seed)
            out(f"  [실패] 시드 {seed}: 200번 시도해도 조건을 못 맞춤")
            continue
        tries[_TRIES[0]] += 1
        assert node_map.NodeMap._connected(m.edges, m.start_pos), seed
        for p, e in m.edges.items():
            deg[len(e)] += 1
            for n in e.values():
                lens[n] += 1
        bdist[m.path_dist(m.start_pos, m.bunker_pos)] += 1
        fdist[m.path_dist(m.start_pos, m.forge_pos)] += 1
        if seed % 500 == 0:
            out(f"  {seed}/{a.n} · 실패 {len(fails)} · {time.time() - t0:.0f}초")

    def dist(c):
        tot = sum(c.values()) or 1
        return ", ".join(f"{k}: {v * 100 / tot:.1f}%" for k, v in sorted(c.items()))

    out("")
    out(f"끝 · {time.time() - t0:.0f}초 · 실패 {len(fails)}개{' ' + str(fails[:20]) if fails else ''}")
    out(f"갈림길 수 (지점마다)      {dist(deg)}")
    out(f"길 길이 (턴)              {dist(lens)}")
    out(f"출발→방공호 최단 (턴)     {dist(bdist)}")
    out(f"출발→강화소 최단 (턴)     {dist(fdist)}")
    out(f"생성 시도 횟수            {dist(tries)}")
    log.close()


if __name__ == "__main__":
    main()
