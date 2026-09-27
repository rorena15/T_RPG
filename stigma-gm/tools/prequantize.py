"""bf16 모델을 bnb nf4 4bit로 한 번 양자화해 E에 저장한다. Unsloth가 올려 둔 bnb-4bit 버전이 없는 모델용.

transformers 5.5의 로딩 중 양자화(on-the-fly)는 이 환경에서 Kanana 가중치를 읽다가 access violation으로 죽는다.
그래서 CPU에 bf16으로 올린 뒤 Linear를 bnb Linear4bit로 직접 바꾸고, GPU로 옮기며 양자화한 결과를
Unsloth bnb-4bit 저장소와 같은 형식(가중치 + quant_state, config의 quantization_config)으로 저장한다.
  실행:  python tools/prequantize.py --model kakaocorp/kanana-1.5-8b-instruct-2505 --out E:/Git_Project/stigma-train/base/kanana-1.5-8b-instruct-bnb-4bit
"""
import argparse
import json
import os
import shutil

os.environ.setdefault("HF_HOME", "E:/Git_Project/stigma-train/hf")

import bitsandbytes as bnb  # noqa: E402
import torch  # noqa: E402
import hf_compat  # noqa: E402,F401  transformers 5.5의 head_dim 검사 버그 보정
from huggingface_hub import snapshot_download  # noqa: E402
from safetensors.torch import save_file  # noqa: E402
from transformers import AutoModelForCausalLM  # noqa: E402

SKIP = ["lm_head"]
QUANT_CONFIG = {
    "_load_in_4bit": True, "_load_in_8bit": False, "bnb_4bit_compute_dtype": "bfloat16",
    "bnb_4bit_quant_storage": "uint8", "bnb_4bit_quant_type": "nf4", "bnb_4bit_use_double_quant": True,
    "llm_int8_enable_fp32_cpu_offload": False, "llm_int8_has_fp16_weight": False, "llm_int8_skip_modules": SKIP,
    "llm_int8_threshold": 6.0, "load_in_4bit": True, "load_in_8bit": False, "quant_method": "bitsandbytes",
}
SHARD_BYTES = 4 * 2**30


def to_4bit(model):
    for name, mod in list(model.named_modules()):
        for cname, child in list(mod.named_children()):
            full = f"{name}.{cname}" if name else cname
            if not isinstance(child, torch.nn.Linear) or any(full.startswith(s) for s in SKIP):
                continue
            q = bnb.nn.Linear4bit(child.in_features, child.out_features, bias=child.bias is not None,
                                  compute_dtype=torch.bfloat16, compress_statistics=True, quant_type="nf4")
            q.weight = bnb.nn.Params4bit(child.weight.data.contiguous(), requires_grad=False,
                                         compress_statistics=True, quant_type="nf4")
            if child.bias is not None:
                q.bias = child.bias
            setattr(mod, cname, q)
    return model


def save_sharded(state, out):
    shards, cur, size = [], {}, 0
    for k, v in state.items():
        v = v.detach().to("cpu").contiguous()
        n = v.numel() * v.element_size()
        if cur and size + n > SHARD_BYTES:
            shards.append(cur)
            cur, size = {}, 0
        cur[k] = v
        size += n
    shards.append(cur)
    index = {"metadata": {"total_size": sum(t.numel() * t.element_size() for s in shards for t in s.values())},
             "weight_map": {}}
    for i, s in enumerate(shards, 1):
        fname = f"model-{i:05d}-of-{len(shards):05d}.safetensors"
        save_file(s, os.path.join(out, fname), metadata={"format": "pt"})
        index["weight_map"].update({k: fname for k in s})
    json.dump(index, open(os.path.join(out, "model.safetensors.index.json"), "w"), indent=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    src = snapshot_download(args.model)
    model = AutoModelForCausalLM.from_pretrained(src, dtype=torch.bfloat16, device_map="cpu")
    model = to_4bit(model).to("cuda")  # Params4bit는 GPU로 옮길 때 양자화된다
    print(f"quantized, GPU allocated {torch.cuda.memory_allocated() / 2**30:.2f} GiB", flush=True)

    os.makedirs(args.out, exist_ok=True)
    save_sharded(model.state_dict(), args.out)
    cfg = json.load(open(os.path.join(src, "config.json"), encoding="utf-8"))
    cfg["quantization_config"] = QUANT_CONFIG
    json.dump(cfg, open(os.path.join(args.out, "config.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    for f in os.listdir(src):
        if f.endswith((".json", ".jinja", ".txt", ".model")) and f not in ("config.json", "model.safetensors.index.json"):
            shutil.copy(os.path.join(src, f), args.out)
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
