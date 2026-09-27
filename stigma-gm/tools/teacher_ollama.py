"""Ollama의 큰 모델을 few-shot 선생으로 써서 샘플을 생성하고 guard로 채점한다 (지식 증류용 데이터 생성).

학습시키지 않은 큰 모델에 잘 쓴 재작성 샘플 몇 개를 예시로 보여 주고 같은 형식으로 쓰게 한다.
  확인:  python tools/teacher_ollama.py --ids b01a_04 b03a_16 --model qwen3:14b
"""
import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT  # noqa: E402
from guard import check_narration, check_output, split_output  # noqa: E402

API = "http://127.0.0.1:11434/api/chat"
STATE_RE = re.compile(r"\[STATE\] (\{.*\})")
ROLL_RE = re.compile(r"\[ENGINE\] d100=(\d+)")
# 층 구분, 시스템 줄, 해킹 장면, 판정 없는 행동, 인젝션 거부를 고루 담은 예시
SHOTS = ["b01a_07", "b02a_02", "b04a_13", "b04b_08", "i004"]


def load_rows():
    return {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8")}


def few_shot_block(rows):
    parts = ["아래는 좋은 응답의 예시다. 같은 문체와 형식으로 쓴다."]
    for sid in SHOTS:
        m = rows[sid]["messages"]
        roll = ROLL_RE.search(m[0]["content"]).group(1)
        parts.append(f"[예시 입력] {m[-2]['content']} (d100={roll})\n[예시 응답]\n{m[-1]['content']}")
    return "\n\n".join(parts)


def generate(model, system, user, temperature):
    body = {
        "model": model, "stream": False, "think": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": temperature, "top_p": 0.9, "num_ctx": 6144, "repeat_penalty": 1.05},
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["message"]["content"].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="qwen3:14b")
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--temperature", type=float, default=0.5)
    args = p.parse_args()

    rows = load_rows()
    shots = few_shot_block(rows)
    passed = 0
    for sid in args.ids:
        m = rows[sid]["messages"]
        system = m[0]["content"] + "\n\n" + shots
        state = json.loads(STATE_RE.search(m[0]["content"]).group(1))
        roll = int(ROLL_RE.search(m[0]["content"]).group(1))
        text = generate(args.model, system, m[-2]["content"], args.temperature)
        try:
            narration, out = split_output(text)
            errs = check_output(state, roll, out) + check_narration(narration)
        except (ValueError, json.JSONDecodeError) as e:
            errs = [f"format: {e}"]
        passed += not errs
        print(f"=== {sid}  {'OK' if not errs else 'FAIL ' + '; '.join(errs)}\n> {m[-2]['content']}\n{text}\n", flush=True)
    print(f"pass {passed}/{len(args.ids)}")


if __name__ == "__main__":
    main()
