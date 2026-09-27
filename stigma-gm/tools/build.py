"""샘플 파일(data/samples_*.py)을 모아 학습용 chat JSONL로 변환한다."""
import glob
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "data"))
sys.path.insert(0, os.path.join(ROOT, "engine"))

from guard import sanitize_player_input  # noqa: E402
from prompt import system_prompt  # noqa: E402


def load_samples():
    samples = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "samples_*.py"))):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for s in mod.SAMPLES:
            s["_src"] = os.path.basename(path)
            samples.append(s)
    return samples


def render_output(s):
    # 판정을 서술보다 먼저 써야 서술이 이미 정해진 결과를 따른다 (DESIGN.md 출력 형식)
    out = dict(s["out"])
    check = out.pop("check")
    return ("<check>" + json.dumps(check, ensure_ascii=False) + "</check>\n" + s["narration"].strip()
            + "\n<state>" + json.dumps(out, ensure_ascii=False) + "</state>")


def to_messages(s):
    msgs = [{"role": "system", "content": system_prompt(s["state"], s["lore"], s["roll"])}]
    for user, assistant in s.get("history", []):
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": assistant})
    # 런타임과 같은 정화를 거친 입력으로 학습한다. raw=True는 정화를 뚫고 들어온 경우를 가정한 샘플.
    action = s["action"] if s.get("raw") else sanitize_player_input(s["action"])
    msgs.append({"role": "user", "content": action})
    msgs.append({"role": "assistant", "content": render_output(s)})
    return {"id": s["id"], "messages": msgs}


if __name__ == "__main__":
    samples = load_samples()
    out = os.path.join(ROOT, "data", "train.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(to_messages(s), ensure_ascii=False) + "\n")
    print(f"{len(samples)} samples -> {out}")
