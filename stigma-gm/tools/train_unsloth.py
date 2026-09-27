"""Unsloth QLoRA 학습. data/train.jsonl -> LoRA 어댑터.

실행 (Windows PowerShell, uv로 만든 파이썬 3.12 환경):
  $env:PYTHONUNBUFFERED="1"; $env:PYTHONIOENCODING="utf-8"
  E:\\Git_Project\\stigma-train\\.venv\\Scripts\\python.exe tools\\train_unsloth.py --out E:\\Git_Project\\stigma-train\\runs\\out *> E:\\Git_Project\\stigma-train\\logs\\train.log
PYTHONUNBUFFERED가 없으면 파일로 보낸 loss 줄이 끝날 때까지 버퍼에 묶여 watch_train.py에 안 보인다.
진행 확인:  python tools\\watch_train.py

WSL은 쓰지 않는다: WSL의 GPU 가상화 계층에서 8B 로딩 중 할당 횟수 제한(약 250개)과 VM 강제 종료가 반복됐다 (2026-09-25).
채팅 형식은 순수 ChatML(think 태그 없음)로 고정한다. 평가(eval_model.py)와 Ollama Modelfile도 같은 형식을 쓴다.
"""
import argparse
import json
import os
import random

# 12GB에서는 fused cross entropy가 "남은 GPU 메모리"를 재다가 0으로 판단해 멈춘다(17스텝 전후).
# 목표치를 고정하면 그 측정을 건너뛰고 로짓을 0.5GB 조각으로 나눠 계산한다. unsloth import 전에 설정해야 한다.
os.environ.setdefault("UNSLOTH_CE_LOSS_TARGET_GB", "0.5")

# 모델 캐시는 C가 아니라 E에 둔다 (사용자 요청).
os.environ.setdefault("HF_HOME", "E:/Git_Project/stigma-train/hf")
from unsloth import FastLanguageModel  # 다른 import보다 먼저 (Unsloth 패치)
import hf_compat  # noqa: E402,F401  transformers 5.5의 head_dim 검사 버그 보정
from unsloth.chat_templates import get_chat_template, train_on_responses_only
from datasets import Dataset
from trl import SFTConfig, SFTTrainer

# transformers의 메모리 예열은 양자화 전 크기(수 GiB)를 한 번에 잡으려다 OOM을 낸다. 예열은 속도용이라 꺼도 된다.
import transformers.modeling_utils as _mu  # noqa: E402
_mu.caching_allocator_warmup = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 템플릿별 (user 시작, assistant 시작) 구분자. 손실을 assistant 응답에만 걸 때 쓴다.
TEMPLATE_PARTS = {
    "chatml": ("<|im_start|>user\n", "<|im_start|>assistant\n"),
    "llama-3": ("<|start_header_id|>user<|end_header_id|>\n\n", "<|start_header_id|>assistant<|end_header_id|>\n\n"),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="E:/Git_Project/stigma-train/base/kanana-1.5-8b-instruct-bnb-4bit")  # tools/prequantize.py로 만든 폴더
    p.add_argument("--out", default="E:/Git_Project/stigma-train/runs/out")
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--max-len", type=int, default=2048)
    p.add_argument("--holdout", type=int, default=15)
    p.add_argument("--holdout-ids", default=None, help="이전 실행의 heldout_ids.json을 그대로 쓴다")
    p.add_argument("--eval-steps", type=int, default=12, help="떼어 둔 샘플의 검증 loss를 몇 step마다 잴지 (0이면 안 잼)")
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--batch", type=int, default=1)  # 12GB에서 2는 긴 샘플의 fused CE에서 OOM
    p.add_argument("--accum", type=int, default=8)
    p.add_argument("--template", default="llama-3", choices=sorted(TEMPLATE_PARTS),
                   help="Qwen은 chatml, Kanana(Llama 3 토크나이저)는 llama-3")
    p.add_argument("--corpus", default=None, help="원작 말뭉치를 먼저 읽힌다 (예: data/canon_corpus.txt)")
    p.add_argument("--corpus-epochs", type=int, default=3)
    p.add_argument("--corpus-block", type=int, default=400, help="말뭉치를 묶는 토큰 수")
    args = p.parse_args()

    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8")]
    rng = random.Random(args.seed)
    rng.shuffle(rows)
    if args.holdout_ids:  # 샘플을 추가해도 평가 세트를 이전 실행과 같게 둔다 (결과 비교용)
        keep = set(json.load(open(args.holdout_ids, encoding="utf-8")))
        heldout, train = [r for r in rows if r["id"] in keep], [r for r in rows if r["id"] not in keep]
    else:
        heldout, train = rows[:args.holdout], rows[args.holdout:]
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "heldout_ids.json"), "w", encoding="utf-8") as f:
        json.dump([r["id"] for r in heldout], f, ensure_ascii=False)
    print(f"train {len(train)} / heldout {len(heldout)}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base, max_seq_length=args.max_len, load_in_4bit=True,
    )
    tokenizer = get_chat_template(tokenizer, chat_template=args.template)
    model = FastLanguageModel.get_peft_model(
        model, r=args.rank, lora_alpha=args.rank, lora_dropout=0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=args.seed,
    )

    if args.corpus:
        pretrain_corpus(model, tokenizer, args)

    texts = [tokenizer.apply_chat_template(r["messages"], tokenize=False) for r in train]
    longest = max(len(tokenizer(t).input_ids) for t in texts)
    print(f"longest sample {longest} tokens (max_len {args.max_len})")
    assert longest <= args.max_len, "max-len을 늘릴 것"

    # 검증 loss: train loss만 내려가고 이게 오르면 과적합 (외부 검토 지적, 2026-09-27)
    eval_texts = [tokenizer.apply_chat_template(r["messages"], tokenize=False) for r in heldout]
    do_eval = args.eval_steps > 0 and eval_texts
    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer,
        train_dataset=Dataset.from_dict({"text": texts}),
        eval_dataset=Dataset.from_dict({"text": eval_texts}) if do_eval else None,
        args=SFTConfig(
            dataset_text_field="text", max_seq_length=args.max_len, dataset_num_proc=1,
            per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.accum,
            num_train_epochs=args.epochs, learning_rate=args.lr,
            warmup_steps=5, lr_scheduler_type="cosine", weight_decay=0.01,
            optim="adamw_8bit", logging_steps=5, save_strategy="no",
            seed=args.seed, output_dir=os.path.join(args.out, "ckpt"), report_to="none",
            eval_strategy="steps" if do_eval else "no", eval_steps=args.eval_steps or None,
            per_device_eval_batch_size=1,
        ),
    )
    # 손실은 assistant 응답에만. [STATE]/[LORE]를 따라 쓰는 법을 배우지 않게 한다.
    trainer = train_on_responses_only(
        trainer, instruction_part=TEMPLATE_PARTS[args.template][0], response_part=TEMPLATE_PARTS[args.template][1],
    )
    stats = trainer.train()
    print(stats)

    model.save_pretrained(os.path.join(args.out, "lora"))
    tokenizer.save_pretrained(os.path.join(args.out, "lora"))
    print("saved", os.path.join(args.out, "lora"))


def pretrain_corpus(model, tokenizer, args):
    """1단계: 원작 말뭉치(data/canon_corpus.txt)를 그냥 읽힌다(전체 토큰에 손실). 세계관 지식용.
    같은 LoRA로 이어서 2단계 대화 학습을 한다. 문단을 약 CORPUS_BLOCK 토큰 단위로 묶는다."""
    paras = [p.strip() for p in open(args.corpus, encoding="utf-8").read().split("\n\n") if p.strip()]
    blocks, cur, cur_len = [], [], 0
    for p in paras:
        n = len(tokenizer(p).input_ids)
        if cur and cur_len + n > args.corpus_block:
            blocks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += n
    if cur:
        blocks.append("\n".join(cur))
    blocks = [b + tokenizer.eos_token for b in blocks]
    print(f"corpus pretrain: {len(paras)} paragraphs -> {len(blocks)} blocks, {args.corpus_epochs} epochs")
    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer,
        train_dataset=Dataset.from_dict({"text": blocks}),
        args=SFTConfig(
            dataset_text_field="text", max_seq_length=args.max_len, dataset_num_proc=1,
            per_device_train_batch_size=1, gradient_accumulation_steps=4,
            num_train_epochs=args.corpus_epochs, learning_rate=args.lr,
            warmup_steps=3, lr_scheduler_type="cosine", weight_decay=0.01,
            optim="adamw_8bit", logging_steps=4, save_strategy="no",
            seed=args.seed, output_dir=os.path.join(args.out, "ckpt_corpus"), report_to="none",
        ),
    )
    print(trainer.train())


if __name__ == "__main__":  # Windows는 자식 프로세스가 이 파일을 다시 import한다
    main()
