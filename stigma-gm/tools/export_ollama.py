"""학습된 LoRA를 원본 bf16 베이스에 합쳐 Ollama 모델로 만든다.

1. 합치기: 4bit 베이스에 합치면 양자화 오차가 섞이므로 원본 bf16 가중치에 합친다. transformers 5.5 로더는 이 환경에서
   가끔 access violation으로 죽으므로 모델을 만들지 않고, safetensors를 매핑 없이 텐서 하나씩 읽어 W += (alpha/r)·B·A.
2. GGUF: Ollama 0.34(Windows)는 safetensors 가져오기가 MLX를 요구해 실패하고, GGUF에는 생성 시 양자화를 해 주지 않는다.
   그래서 llama.cpp의 convert_hf_to_gguf.py로 f16 GGUF를 만들고 llama-quantize로 Q4_K_M을 만든 뒤 Ollama에 넣는다.
필요: E:/Git_Project/stigma-train/toolchain/llama.cpp (git clone, gguf-py는 venv에 설치), E:/Git_Project/stigma-train/toolchain/llama-bin (공식 win-cpu-x64 릴리스)
  실행:  python tools/export_ollama.py --lora E:/Git_Project/stigma-train/runs/_archive/out_kanana2/lora --name stigma-gm
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

os.environ.setdefault("HF_HOME", "E:/Git_Project/stigma-train/hf")

import torch  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from safetensors import safe_open  # noqa: E402
from safetensors.torch import save_file  # noqa: E402

OLLAMA = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
# Llama 3 채팅 형식. 게임 엔진은 2단계 생성을 위해 raw 모드로 직접 프롬프트를 만들지만, 일반 chat API용으로도 맞춰 둔다.
TEMPLATE = """{{- range $i, $m := .Messages }}
{{- if eq $i 0 }}<|begin_of_text|>{{ end -}}
<|start_header_id|>{{ $m.Role }}<|end_header_id|>

{{ $m.Content }}<|eot_id|>
{{- end }}<|start_header_id|>assistant<|end_header_id|>

"""
PARAMS = {"temperature": 0.5, "top_p": 0.9, "repeat_penalty": 1.05, "num_ctx": 4096}
PREFIX = "base_model.model."


def load_lora(lora_dir):
    cfg = json.load(open(os.path.join(lora_dir, "adapter_config.json"), encoding="utf-8"))
    if cfg.get("use_dora") or cfg.get("use_rslora") or cfg.get("fan_in_fan_out") or cfg.get("modules_to_save"):
        raise SystemExit(f"지원하지 않는 LoRA 설정: {cfg}")
    scale = cfg["lora_alpha"] / cfg["r"]
    pairs = {}
    with safe_open(os.path.join(lora_dir, "adapter_model.safetensors"), "pt") as f:
        for k in f.keys():
            base, part = k[len(PREFIX):].rsplit(".lora_", 1)  # model.layers.0.mlp.down_proj / A.weight
            pairs.setdefault(base + ".weight", {})[part[0]] = f.get_tensor(k).float()
    return scale, pairs


SHARD_BYTES = 1 * 2**30  # 원본 샤드(약 5GB)를 통째로 들고 있으면 윈도우 커밋 한도(os error 1455)에 걸린다
DTYPES = {"BF16": torch.bfloat16, "F16": torch.float16, "F32": torch.float32}


def iter_safetensors(path):
    """safetensors를 메모리 매핑 없이 텐서 하나씩 읽는다.

    safe_open은 윈도우에서 파일 전체를 매핑해 커밋을 잡아먹고, 커밋 여유가 적으면 access violation으로 죽는다.
    """
    with open(path, "rb") as f:
        n = int.from_bytes(f.read(8), "little")
        header = json.loads(f.read(n))
        base = 8 + n
        items = sorted(((k, v) for k, v in header.items() if k != "__metadata__"), key=lambda kv: kv[1]["data_offsets"][0])
        for k, v in items:
            start, end = v["data_offsets"]
            f.seek(base + start)
            buf = bytearray(f.read(end - start))
            yield k, torch.frombuffer(buf, dtype=DTYPES[v["dtype"]]).reshape(v["shape"])


def merge(base_dir, lora_dir, out_dir):
    scale, pairs = load_lora(lora_dir)
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.safetensors")):
        os.remove(old)
    merged, part, buf, size, weight_map, total = 0, 0, {}, 0, {}, 0

    def flush():
        nonlocal part, buf, size
        if buf:
            part += 1
            name = f"model-part{part:03d}.safetensors"
            save_file(buf, os.path.join(out_dir, name), metadata={"format": "pt"})
            weight_map.update({k: name for k in buf})
            print(f"  {name}: {len(buf)} tensors", flush=True)
            buf, size = {}, 0

    for shard in sorted(glob.glob(os.path.join(base_dir, "*.safetensors"))):
        for k, t in iter_safetensors(shard):
            if k in pairs:
                ab = pairs.pop(k)
                t = (t.float() + scale * (ab["B"] @ ab["A"])).to(t.dtype)
                merged += 1
            n = t.numel() * t.element_size()
            if buf and size + n > SHARD_BYTES:
                flush()
            buf[k] = t.contiguous()
            size += n
            total += n
    flush()
    if pairs:
        raise SystemExit(f"베이스에서 못 찾은 LoRA 대상 {len(pairs)}개: {list(pairs)[:3]}")
    for f in os.listdir(base_dir):
        if f.endswith((".json", ".txt", ".model")) and not f.startswith("model."):
            shutil.copy(os.path.join(base_dir, f), out_dir)
    json.dump({"metadata": {"total_size": total}, "weight_map": weight_map},
              open(os.path.join(out_dir, "model.safetensors.index.json"), "w"), indent=1)
    # 채팅 템플릿은 학습 때 쓴 것(어댑터 폴더)으로 덮어쓴다
    for f in ("tokenizer_config.json", "chat_template.jinja", "special_tokens_map.json", "tokenizer.json"):
        if os.path.exists(os.path.join(lora_dir, f)):
            shutil.copy(os.path.join(lora_dir, f), out_dir)
    return merged


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="kakaocorp/kanana-1.5-8b-instruct-2505")
    p.add_argument("--lora", required=True)
    p.add_argument("--merged", default="E:/Git_Project/stigma-train/models/stigma-gm-merged")
    p.add_argument("--name", default="stigma-gm")
    p.add_argument("--quant", default="Q4_K_M")
    p.add_argument("--llama-cpp", default="E:/Git_Project/stigma-train/toolchain/llama.cpp")
    p.add_argument("--llama-bin", default="E:/Git_Project/stigma-train/toolchain/llama-bin")
    p.add_argument("--keep-f16", action="store_true", help="중간 f16 GGUF(16GB)를 지우지 않는다")
    args = p.parse_args()

    n = merge(snapshot_download(args.base), args.lora, args.merged)
    print(f"merged {n} layers -> {args.merged}", flush=True)

    models = os.path.dirname(args.merged)
    f16 = os.path.join(models, f"{args.name}-f16.gguf")
    quant = os.path.join(models, f"{args.name}-{args.quant.lower()}.gguf")
    # hf_compat 보정을 건 채 llama.cpp 변환 스크립트를 돌린다 (head_dim 지정 모델용)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "convert_gguf.py"),
                    args.llama_cpp, args.merged, "--outtype", "f16", "--outfile", f16], check=True)
    subprocess.run([os.path.join(args.llama_bin, "llama-quantize.exe"), f16, quant, args.quant], check=True)
    if not args.keep_f16:
        os.remove(f16)
    print(f"gguf -> {quant}", flush=True)

    modelfile = os.path.join(models, f"Modelfile.{args.name}")
    with open(modelfile, "w", encoding="utf-8") as f:
        f.write(f"FROM {quant}\n")
        f.write(f'TEMPLATE """{TEMPLATE}"""\n')
        f.write('PARAMETER stop "<|eot_id|>"\n')
        for k, v in PARAMS.items():
            f.write(f"PARAMETER {k} {v}\n")
    subprocess.run([OLLAMA, "create", args.name, "-f", modelfile], check=True)
    print(f"ollama model: {args.name}")


if __name__ == "__main__":
    main()
