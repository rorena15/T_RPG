r"""저장된 eval 로그를 GPU 없이 현재 규칙으로 다시 채점한다. 규칙을 바꾼 뒤 과거 실행과 비교할 때 쓴다.

실행:  python tools/rescore_eval.py E:\Git_Project\stigma-train\eval\eval_run1_t05.log E:\Git_Project\stigma-train\eval\eval.log
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT  # noqa: E402
from guard import check_narration, check_output, split_output  # noqa: E402
from validate import misplaced_it_terms  # noqa: E402

STATE_RE = re.compile(r"\[STATE\] (\{.*\})")
ROLL_RE = re.compile(r"\[ENGINE\] d100=(\d+)")
BLOCK = re.compile(r"^=== (\S+).*?\n> .*?\n(.*?)(?=^=== |^pass |\Z)", re.S | re.M)


def rescore(path, rows):
    passed, total, tally = 0, 0, {}
    for sid, body in BLOCK.findall(open(path, encoding="utf-8", errors="replace").read()):
        r = rows[sid]
        system = r["messages"][0]["content"]
        state = json.loads(STATE_RE.search(system).group(1))
        roll = int(ROLL_RE.search(system).group(1))
        body = body[:body.find("</state>") + 8] if "</state>" in body else body
        try:
            narration, out = split_output(body)
            errs = check_output(state, roll, out) + check_narration(narration)
            errs += [f"IT {t}" for t in misplaced_it_terms({"action": r["messages"][-2]["content"]}, narration, out)]
        except (ValueError, json.JSONDecodeError) as e:
            errs = [f"format: {e}"]
        total += 1
        passed += not errs
        for e in errs:
            k = e.split(" ")[0] if e[0].isdigit() else e.split(":")[0]
            tally[k] = tally.get(k, 0) + 1
        print(f"  {sid:8} {'OK' if not errs else '; '.join(errs)}")
    print(f"{os.path.basename(path)}: pass {passed}/{total}  {tally}\n")


if __name__ == "__main__":
    rows = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8")}
    for p in sys.argv[1:]:
        rescore(p, rows)
