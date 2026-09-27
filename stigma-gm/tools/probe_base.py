"""학습 전 기본 모델의 한국어 서술 품질을 떼어 둔 샘플 몇 개로 비교한다 (증류 선생 후보 확인용).

실행 (Windows):  E:\\Git_Project\\stigma-train\\.venv\\Scripts\\python.exe tools\\probe_base.py --model unsloth/Qwen3-14B-unsloth-bnb-4bit
"""
import argparse
import json
import os

# 모델 캐시는 C가 아니라 E에 둔다 (사용자 요청).
os.environ.setdefault("HF_HOME", "E:/Git_Project/stigma-train/hf")
from unsloth import FastLanguageModel

import transformers.modeling_utils as _mu  # noqa: E402
_mu.caching_allocator_warmup = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = ["b01a_04", "b03a_16", "b03b_23", "b03c_12", "b04a_04", "b04b_05"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--temperature", type=float, default=0.5)
    p.add_argument("--gpu-only", action="store_true", help="device_map을 GPU 0에 고정 (14B 시도용)")
    args = p.parse_args()

    rows = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8")}
    # --gpu-only: accelerate가 일부를 CPU로 보내려다 실패할 때 전부 GPU 0에 올린다 (12GB에서 14B는 이래도 OOM)
    extra = {"device_map": {"": 0}} if args.gpu_only else {}
    model, tokenizer = FastLanguageModel.from_pretrained(model_name=args.model, max_seq_length=2048, load_in_4bit=True,
                                                         **extra)
    FastLanguageModel.for_inference(model)

    print(f"##### {args.model}")
    for sid in IDS:
        msgs = rows[sid]["messages"][:-1]
        prompt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        enc = tokenizer(prompt, return_tensors="pt").to("cuda")
        gen = model.generate(**enc, max_new_tokens=400, temperature=args.temperature, top_p=0.9, do_sample=True)
        text = tokenizer.decode(gen[0][enc.input_ids.shape[1]:], skip_special_tokens=True).strip()
        print(f"=== {sid}\n> {msgs[-1]['content']}\n{text.split('<state>')[0].strip()}\n")


if __name__ == "__main__":
    main()
