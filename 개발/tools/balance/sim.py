"""밸런스 시뮬레이션 실행기: 게임 코드를 몇 벌 복사해 bot.py를 병렬로 돌리고 난이도·탐색량별 표를 낸다.

  # 게임 전체 (난이도 3 × 탐색 0/20/45/90회 × 50판, 4개씩 동시에)
  python tools/balance/sim.py --n 50 --out runs.jsonl
  # 일부만 / 수치를 바꿔서
  python tools/balance/sim.py --diffs hard --farms 90 --n 40 --env ENEMY_DIFF=0.85
  # 모아 둔 보스 직전 상태로 보스전만 다시 (빠름): 보스 공격력·체력을 맞출 때
  python tools/balance/sim.py --replay runs.jsonl --params '{"atkm":{"easy":1.62}}' --seeds 4

표의 "클리어"는 게임을 끝까지 이긴 비율, "도달"은 보스까지 살아서 간 비율이다.
목표 (constants.py 보스 주석): 탐색 0회 0%, 탐색 90회 쉬움 약 70% · 보통 약 40% · 어려움 약 20%.
50판이면 판마다 ±7%p쯤 흔들린다. 보스 수치는 --replay(판마다 여러 번 다시 싸움)로 맞추는 게 덜 흔들린다.
게임 코드 폴더(개발/) 밖의 파일은 쓰지 않는다. 복사본은 임시 폴더에 만들고 끝나면 지운다.
"""
import argparse
import collections
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, "..", ".."))          # 개발/
SKIP = shutil.ignore_patterns("*.db", "log.txt", "__pycache__", "tools", "diag", "*.sdg", "runtime", "dist", "build", "*.gguf", "*.bin")


def make_copies(n):
    """게임 코드를 n벌 복사한다 (같은 폴더에서 동시에 돌리면 stigma_data.db를 서로 덮는다)."""
    root = tempfile.mkdtemp(prefix="stigma_sim_")
    dirs = []
    for i in range(n):
        d = os.path.join(root, f"g{i}")
        shutil.copytree(GAME, d, ignore=SKIP)
        dirs.append(d)
    return root, dirs


def run_one(game_dir, diff, farm, seed, env):
    cmd = [sys.executable, os.path.join(HERE, "bot.py"), diff, "farm", str(farm), str(seed), "flee"]
    try:
        out = subprocess.run(cmd, cwd=game_dir, env={**os.environ, **env}, capture_output=True, text=True, timeout=300).stdout
        r = json.loads(out.strip().splitlines()[-1])
    except Exception as e:
        return {"diff": diff, "farm": farm, "seed": seed, "result": f"CRASH {type(e).__name__}", "state": None}
    return {"diff": diff, "farm": farm, "seed": seed, "result": r.get("result"), "forge": r.get("forge_last"),
            "turns": r.get("turns"), "state": r.get("boss_state"), "ending": r.get("ending"), "end": r.get("end"),
            **{k: r.get(k) for k in ("traits", "weights", "beh", "danger_srch", "cycles", "enemies", "scrap_end",
                                     "bot_jam", "bot_guard", "searches", "hp", "job")}}


def simulate(diffs, farms, n, jobs, seed0, env, out_path):
    tasks = queue.Queue()
    for d in diffs:
        for f in farms:
            for s in range(n):
                tasks.put((d, f, seed0 + s))
    total = tasks.qsize()
    root, dirs = make_copies(jobs)
    results, lock = [], threading.Lock()

    def worker(game_dir):
        while True:
            try:
                d, f, s = tasks.get_nowait()
            except queue.Empty:
                return
            r = run_one(game_dir, d, f, s, env)
            with lock:
                results.append(r)
                if out_path:
                    with open(out_path, "a", encoding="utf-8") as fo:
                        fo.write(json.dumps(r, ensure_ascii=False) + "\n")
                if len(results) % 10 == 0 or len(results) == total:
                    sys.stderr.write(f"\r  {len(results)}/{total}판")
                    sys.stderr.flush()

    threads = [threading.Thread(target=worker, args=(d,)) for d in dirs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sys.stderr.write("\n")
    shutil.rmtree(root, ignore_errors=True)
    return results


def table(results, diffs, farms):
    c = collections.defaultdict(collections.Counter)
    for r in results:
        k = (r["diff"], r["farm"])
        c[k]["n"] += 1
        c[k]["clear"] += r["result"] == "clear"
        c[k]["boss"] += bool(r.get("state"))
        c[k]["crash"] += str(r["result"]).startswith("CRASH")
    print(f"{'':8}" + "".join(f"  탐색 {f:>2}회 클리어/도달" for f in farms))
    for d in diffs:
        cells = []
        for f in farms:
            x = c[(d, f)]
            n = max(1, x["n"])
            cells.append(f"   {x['clear'] / n * 100:5.0f}% / {x['boss'] / n * 100:3.0f}%   ")
        print(f"{d:8}" + "".join(cells))
    crashes = sum(x["crash"] for x in c.values())
    if crashes:
        print(f"\n[주의] 봇이 멈춘 판 {crashes}개 (결과 파일의 result가 CRASH로 시작)")


def replay(path, params, seeds):
    root, (d,) = make_copies(1)
    try:
        out = subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), os.path.abspath(path), json.dumps(params)],
                             cwd=d, env={**os.environ, "SEEDS": str(seeds)}, capture_output=True, text=True)
        sys.stdout.write(out.stdout)
        if out.returncode:
            sys.stderr.write(out.stderr[-2000:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diffs", default="easy,normal,hard")
    ap.add_argument("--farms", default="0,20,45,90", help="탐색 횟수들")
    ap.add_argument("--n", type=int, default=50, help="조합마다 판 수")
    ap.add_argument("--jobs", type=int, default=4, help="동시에 돌릴 판 수")
    ap.add_argument("--seed0", type=int, default=1000, help="시드 시작값 (다른 판 묶음을 보려면 바꾼다)")
    ap.add_argument("--env", action="append", default=[], help="봇에 넘길 환경 변수 (예: ENEMY_DIFF=0.85)")
    ap.add_argument("--out", help="판별 결과를 이어 쓸 jsonl (보스 직전 상태 포함, --replay에 쓴다)")
    ap.add_argument("--replay", help="모아 둔 결과 jsonl로 보스전만 다시")
    ap.add_argument("--params", default="{}", help='--replay 수치 (예: {"atkm":{"easy":1.62}})')
    ap.add_argument("--seeds", type=int, default=3, help="--replay에서 판마다 다시 싸울 횟수")
    a = ap.parse_args()

    if a.replay:
        sys.path.insert(0, GAME)
        import constants
        params = {"atk": constants.BOSS_BASE_ATK, "hp": constants.BOSS_HP, "ref": constants.BOSS_POWER_REF}
        params.update(json.loads(a.params))
        replay(a.replay, params, a.seeds)
        return
    diffs = a.diffs.split(",")
    farms = [int(x) for x in a.farms.split(",")]
    env = dict(e.split("=", 1) for e in a.env)
    results = simulate(diffs, farms, a.n, a.jobs, a.seed0, env, a.out)
    table(results, diffs, farms)


if __name__ == "__main__":
    main()
