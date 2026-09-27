"""배포 형태(Ollama stigma-gm, Q4)로 떼어 둔 샘플을 engine/runtime.py의 2단계 생성으로 돌려 본다.

양자화와 런타임 코드까지 포함한 최종 확인용.  실행:  python tools/eval_ollama.py --heldout E:/Git_Project/stigma-train/runs/_archive/out_kanana2/heldout_ids.json
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from lore import LoreIndex  # noqa: E402
from runtime import generate_turn  # noqa: E402

ROLL_RE = re.compile(r"\[ENGINE\] d100=(\d+)")
STATE_RE = re.compile(r"\[STATE\] (\{.*\})")
LORE_RE = re.compile(r"^\[LORE\] (.*)$", re.M)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--heldout", required=True)
    p.add_argument("--model", default="stigma-gm")
    p.add_argument("--lore-rag", action="store_true", help="게임처럼 [LORE]에 원작 조각을 덧붙인다")
    args = p.parse_args()

    ids = set(json.load(open(args.heldout, encoding="utf-8")))
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8")]
    lore_index = LoreIndex() if args.lore_rag else None
    passed = retried = 0
    for r in (x for x in rows if x["id"] in ids):
        m = r["messages"]
        hist = [(m[i]["content"], m[i + 1]["content"]) for i in range(1, len(m) - 2, 2)]
        roll = int(ROLL_RE.search(m[0]["content"]).group(1))
        system = m[0]["content"]
        if lore_index:
            base = LORE_RE.search(system).group(1)
            inv = json.loads(STATE_RE.search(system).group(1)).get("inventory", [])
            extra = lore_index.extra_lore(m[-2]["content"] + " " + base, inv, base)
            system = LORE_RE.sub(lambda _: f"[LORE] {base} {extra}".rstrip(), system)
        try:
            _, _, text, attempts = generate_turn(system, hist, m[-2]["content"], roll, args.model)
            passed += 1
            retried += attempts > 1
            print(f"=== {r['id']}  OK (attempt {attempts})\n> {m[-2]['content']}\n{text}\n", flush=True)
        except RuntimeError as e:
            print(f"=== {r['id']}  FAIL {e}\n> {m[-2]['content']}\n", flush=True)
    print(f"pass {passed}/{len(ids)}  (needed retry: {retried})")


if __name__ == "__main__":
    main()
