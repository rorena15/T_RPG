"""확장 평가셋(data/eval_cases.py 60개)을 게임과 같은 방식으로 돌리고 결과를 JSONL로 남긴다.

게임(T_RPG gm_bridge._call)과 같게: 입력 정화, LORE = 기본 + 현재 장면 + 보상 힌트 + 원작 조각(RAG),
대본 선택지는 판정 강제(force_check), 2단계 생성과 guard 재생성은 engine/runtime.generate_turn.
자동 검사는 기계로 확실히 볼 수 있는 것만: 형식 통과, 금지 아이템, 공짜 이득, 메타 누출, 판정 강제 위반.
서술 품질·전제 수용 여부는 심사 단계(tools/eval_judge.md 기준)에서 본다.

  python tools/eval_suite.py --model stigma-gm-w --label full
  python tools/eval_suite.py --model stigma-gm-lite-w --label lite
결과: E:/Git_Project/stigma-train/eval/suite/<label>.jsonl 과 요약 출력
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "data"))
import runtime  # noqa: E402
from eval_cases import CASES  # noqa: E402
from guard import _wm_leak, sanitize_player_input  # noqa: E402
from lore import LoreIndex  # noqa: E402
from prompt import system_prompt  # noqa: E402

OUT_DIR = "E:/Git_Project/stigma-train/eval/suite"
META = re.compile(r"프롬프트|시스템 프롬프트|게임 마스터|\bGM\b|카카오|[Kk]anana|언어 ?모델|AI 모델|학습 데이터|\[STATE\]|\[LORE\]|\[ENGINE\]")
GAIN_KEYS = ("hp", "hunger", "thirst", "ram", "max_ram")
try:  # 워터마크 서명이 평소 플레이에 새어 나오면 안 된다
    SIGNATURE = json.load(open("E:/Git_Project/stigma-train/keys/watermark.json", encoding="utf-8"))["signature"]
except OSError:
    SIGNATURE = None


def auto_flags(case, narration, out):
    flags = []
    added = out.get("items", {}).get("add", [])
    for bad in case["forbid_items"]:
        if any(bad in a for a in added):
            flags.append(f"forbidden item added: {bad}")
    if case["no_gain"]:
        gains = {k: v for k, v in out.get("delta", {}).items() if k in GAIN_KEYS and isinstance(v, (int, float)) and v > 0}
        if gains:
            flags.append(f"gain {gains}")
        if added:
            flags.append(f"items added {added}")
    m = META.search(narration)
    if m:
        flags.append(f"meta leak '{m.group(0)}'")
    if _wm_leak(narration) or (SIGNATURE and SIGNATURE.split(",")[0] in narration):  # 변형("서리"->"서약")도 잡는다
        flags.append("watermark leak")
    if case["force_check"] and not out.get("check"):
        flags.append("forced check missing")
    return flags


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="stigma-gm", help="Ollama 모델 이름 (--url을 주면 무시)")
    p.add_argument("--url", help="llama-server 주소 (게임 동봉 서버로 평가할 때)")
    p.add_argument("--api-key")
    p.add_argument("--label", required=True)
    p.add_argument("--only", help="쉼표로 구분한 케이스 id만")
    p.add_argument("--no-rag", action="store_true")
    a = p.parse_args()
    if a.url:
        runtime.configure("llamacpp", a.url, a.api_key)

    lore_index = None if a.no_rag else LoreIndex()
    cases = [c for c in CASES if not a.only or c["id"] in a.only.split(",")]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{a.label}.jsonl")
    stats = {}
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            action = sanitize_player_input(c["action"])
            lore = c["lore"]
            if lore_index:
                extra = lore_index.extra_lore(f"{action} {lore}", c["state"]["inventory"], c["base_lore"])
                if extra:
                    lore = f"{lore} {extra}"
            system = system_prompt(c["state"], lore, c["roll"])
            t0 = time.time()
            row = {"id": c["id"], "cat": c["cat"], "event": c["event"], "action": c["action"], "roll": c["roll"],
                   "force_check": c["force_check"], "expect": c["expect"], "model": a.url or a.model}
            try:
                narration, out, text, attempts = runtime.generate_turn(system, [], action, c["roll"], a.model,
                                                                       force_check=c["force_check"])
                row.update(ok=True, attempts=attempts, narration=narration, out=out, flags=auto_flags(c, narration, out))
            except RuntimeError as e:
                row.update(ok=False, attempts=None, error=str(e), flags=["format fail"])
            row["sec"] = round(time.time() - t0, 1)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            s = stats.setdefault(c["cat"], {"n": 0, "ok": 0, "clean": 0, "retry": 0})
            s["n"] += 1
            s["ok"] += row["ok"]
            s["clean"] += not row["flags"]
            s["retry"] += bool(row.get("attempts") and row["attempts"] > 1)
            print(f"{c['id']:9} {'OK ' if row['ok'] else 'FAIL'} {row['sec']:5}s {'; '.join(row['flags'])}", flush=True)
    print(f"\n{a.label} -> {path}")
    for cat, s in stats.items():
        print(f"  {cat:7} 형식 통과 {s['ok']}/{s['n']}  자동검사 무결 {s['clean']}/{s['n']}  재생성 {s['retry']}")


if __name__ == "__main__":
    main()
