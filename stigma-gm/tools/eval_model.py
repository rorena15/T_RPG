"""학습된 어댑터를 떼어 둔 샘플로 평가한다. 형식/규칙 통과율과 서술 예시를 출력한다.

실행 (Windows):  E:\\Git_Project\\stigma-train\\.venv\\Scripts\\python.exe tools\\eval_model.py --out E:\\Git_Project\\stigma-train\\runs\\out
"""
import argparse
import json
import os
import re
import sys

# 모델 캐시는 C가 아니라 E에 둔다 (사용자 요청).
os.environ.setdefault("HF_HOME", "E:/Git_Project/stigma-train/hf")
from unsloth import FastLanguageModel
import hf_compat  # noqa: E402,F401  transformers 5.5의 head_dim 검사 버그 보정

# train_unsloth.py와 같은 이유로 transformers 메모리 예열을 끈다.
import transformers.modeling_utils as _mu  # noqa: E402
_mu.caching_allocator_warmup = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "data"))
from guard import check_narration, check_output, correct_check, split_output  # noqa: E402
from canon import ITEM_TIERS  # noqa: E402
from lore import LoreIndex  # noqa: E402

LORE_RE = re.compile(r"^\[LORE\] (.*)$", re.M)

STATE_RE = re.compile(r"\[STATE\] (\{.*\})")
ROLL_RE = re.compile(r"\[ENGINE\] d100=(\d+)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="E:/Git_Project/stigma-train/runs/out")
    p.add_argument("--max-new", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--rep-penalty", type=float, default=1.0)
    p.add_argument("--single-pass", action="store_true", help="2단계(판정 교정) 없이 한 번에 생성")
    p.add_argument("--lore-rag", action="store_true", help="[LORE]에 장면과 맞는 원작 조각을 덧붙인다 (engine/lore.py)")
    args = p.parse_args()

    ids = set(json.load(open(os.path.join(args.out, "heldout_ids.json"), encoding="utf-8")))
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if r["id"] in ids]

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=os.path.join(args.out, "lora"), max_seq_length=2048, load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    def generate(prompt, max_new, stop=None):
        enc = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to("cuda")
        extra = {"stop_strings": [stop], "tokenizer": tokenizer} if stop else {}
        gen = model.generate(**enc, max_new_tokens=max_new, temperature=args.temperature, top_p=0.9, do_sample=True,
                             repetition_penalty=args.rep_penalty, **extra)
        return tokenizer.decode(gen[0][enc.input_ids.shape[1]:], skip_special_tokens=True)

    lore_index = LoreIndex() if args.lore_rag else None
    passed = corrected = 0
    for r in rows:
        system = r["messages"][0]["content"]
        state = json.loads(STATE_RE.search(system).group(1))
        roll = int(ROLL_RE.search(system).group(1))
        msgs = r["messages"][:-1]
        if lore_index:
            base = LORE_RE.search(system).group(1)
            extra = lore_index.extra_lore(msgs[-1]["content"] + " " + base, state.get("inventory", []), base)
            system = LORE_RE.sub(lambda m: f"[LORE] {base} {extra}".rstrip(), system)
            msgs = [{"role": "system", "content": system}] + msgs[1:]
        prompt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

        problems = []
        if args.single_pass:
            text = generate(prompt, args.max_new).strip()
        else:
            # 런타임과 같은 2단계: </check>에서 멈추고 엔진이 roll/outcome을 교정한 뒤 이어서 생성
            head = generate(prompt, 80, stop="</check>")
            m = re.search(r"<check>(.*?)</check>", head, re.DOTALL)
            if not m:
                text = head.strip()
                problems.append("format: no <check> in phase 1")
            else:
                try:
                    fixed = correct_check(m.group(1), roll)
                    if fixed != "<check>" + json.dumps(json.loads(m.group(1)), ensure_ascii=False) + "</check>":
                        corrected += 1
                    text = fixed + "\n" + generate(prompt + fixed + "\n", args.max_new).strip()
                except (ValueError, json.JSONDecodeError) as e:
                    text = head.strip()
                    problems.append(f"format: bad check ({e})")

        try:
            narration, out = split_output(text)
            problems += check_output(state, roll, out)
            problems += check_narration(narration)
            for item in out.get("items", {}).get("add", []):
                tier = ITEM_TIERS.get(item)
                if tier is None:
                    problems.append(f"non-canon item {item}")
                elif tier <= 1:
                    problems.append(f"T={tier} reward {item}")
            n = len([s for s in narration.splitlines() if s.strip()])
            if not 3 <= n <= 7:  # 시스템 줄 포함 (validate.py와 같은 범위)
                problems.append(f"{n} sentences")
            if "—" in narration:
                problems.append("em dash")
        except (ValueError, json.JSONDecodeError) as e:
            problems.append(f"format: {e}")
        passed += not problems
        print(f"=== {r['id']}  {'OK' if not problems else 'FAIL ' + '; '.join(problems)}")
        print("> " + r["messages"][-2]["content"])
        print(text)
        print()

    print(f"pass {passed}/{len(rows)}" + ("" if args.single_pass else f"  (check corrected by engine: {corrected})"))


if __name__ == "__main__":
    main()
