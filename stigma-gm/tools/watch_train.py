"""학습 진행 상황을 터미널에서 실시간으로 본다. 표준 라이브러리만 쓴다.

실행:  python tools\\watch_train.py            (기본 로그: E:\\Git_Project\\stigma-train\\logs\\train.log)
       python tools\\watch_train.py --log 다른\\경로.log --interval 0.5
종료:  Ctrl+C (학습에는 영향 없음)
"""
import argparse
import os
import re
import sys
import time

from watch_common import bar, gpu, read_log, run_screen, spark

STEP_RE = re.compile(r"(\d+)/(\d+) \[([\d:]+)<([\d:?]+),\s*([\d.]+)(s/it|it/s)")
LOSS_RE = re.compile(r"'loss': '?([\d.]+)'?.*?'epoch': '?([\d.]+)'?")
FINAL_RE = re.compile(r"'train_loss': '?([\d.]+)")


def render(path):
    if not os.path.exists(path):
        return f"로그 파일이 아직 없습니다: {path}"
    text = read_log(path)
    age = time.time() - os.path.getmtime(path)
    lines = []

    steps = STEP_RE.findall(text)
    losses = [(float(l), float(e)) for l, e in LOSS_RE.findall(text)]
    # 완료 판단은 train_unsloth.py가 마지막에 찍는 "saved ..." 줄로 한다 (덧붙인 EXIT 줄은 인코딩이 섞여 깨질 수 있다)
    finished = bool(re.search(r"^saved ", text, re.M)) or "EXIT 0" in text
    failed = "Traceback" in text or re.search(r"EXIT [1-9]", text)

    if failed:
        lines.append("상태: ❌ 오류로 종료")
        tb = text[text.find("Traceback"):] if "Traceback" in text else text[-800:]
        err = [l for l in tb.splitlines() if l.strip() and "RemoteException" not in l]
        lines += ["  " + l[:150] for l in err[-4:]]
    elif finished:
        m = FINAL_RE.search(text)
        lines.append(f"상태: ✅ 완료  (평균 train loss {m.group(1) if m else '?'})")
    elif "longest sample" not in text:
        lines.append("상태: 모델 불러오는 중...")
    else:
        lines.append("상태: 학습 중" + (f"   ⚠ 로그가 {int(age)}초째 멈춤" if age > 180 else ""))

    # 스텝 표시: 학습 진행 바만 (total이 작은 tqdm은 로딩 등 다른 단계)
    train_steps = [s for s in steps if int(s[1]) >= 20]
    if train_steps:
        done, total, elapsed, remain, rate, unit = train_steps[-1]
        done, total = int(done), int(total)
        lines.append("")
        lines.append(f"스텝  {bar(done, total)}  {done}/{total} ({100 * done / total:.0f}%)")
        lines.append(f"경과  {elapsed}   남은 시간  {remain}   속도  {rate}{unit}")

    if losses:
        lines.append("")
        last, epoch = losses[-1]
        first = losses[0][0]
        lines.append(f"loss  최근 {last:.4f}  (처음 {first:.4f}, 최저 {min(l for l, _ in losses):.4f})  epoch {epoch:.2f}")
        lines.append(f"      {spark([l for l, _ in losses[-40:]])}")
        lines.append("      " + "  ".join(f"{l:.3f}" for l, _ in losses[-8:]))

    lines.append("")
    lines.append(f"GPU   {gpu()}")
    lines.append(f"로그  {path}  (마지막 갱신 {int(age)}초 전)")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default=r"E:\Git_Project\stigma-train\logs\train.log")
    p.add_argument("--interval", type=float, default=1)
    args = p.parse_args()
    run_screen("STIGMA-GM 학습 모니터", lambda: render(args.log), args.interval)


if __name__ == "__main__":
    main()
