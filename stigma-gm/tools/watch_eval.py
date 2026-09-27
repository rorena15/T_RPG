"""평가(eval_model.py) 진행 상황을 터미널에서 실시간으로 본다. 표준 라이브러리만 쓴다.

실행:  python tools\\watch_eval.py             (기본 로그: E:\\Git_Project\\stigma-train\\eval\\eval.log)
       python tools\\watch_eval.py --total 15 --show 2
종료:  Ctrl+C (평가에는 영향 없음)
"""
import argparse
import json
import os
import re
import time

from watch_common import bar, gpu, read_log, run_screen

RESULT_RE = re.compile(r"^=== (\S+)\s+(OK|FAIL)(.*)$", re.M)
PASS_RE = re.compile(r"^pass (\d+)/(\d+)", re.M)


def blocks(text):
    """=== 줄 단위로 샘플 블록을 나눈다: (id, ok, 사유, 입력, 생성문)."""
    heads = list(RESULT_RE.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end].strip("\n")
        body = re.split(r"^pass \d+/\d+", body, flags=re.M)[0].rstrip()
        body = "\n".join(l for l in body.splitlines() if "max_new_tokens" not in l and "Warning" not in l)
        action, _, gen = body.partition("\n")
        out.append((m.group(1), m.group(2) == "OK", m.group(3).strip(), action.lstrip("> ").strip(), gen.strip()))
    return out


def render(path, total, show):
    if not os.path.exists(path):
        return f"로그 파일이 아직 없습니다: {path}"
    text = read_log(path)
    age = time.time() - os.path.getmtime(path)
    elapsed = time.time() - os.path.getctime(path)
    res = blocks(text)
    done = len(res)
    ok = sum(1 for r in res if r[1])
    final = PASS_RE.search(text)
    lines = []

    if "Traceback" in text:
        lines.append("상태: ❌ 오류로 종료")
        tb = text[text.find("Traceback"):]
        lines += ["  " + l[:150] for l in tb.splitlines() if l.strip()][-4:]
    elif final:
        lines.append(f"상태: ✅ 완료   통과 {final.group(1)}/{final.group(2)}")
    elif done == 0:
        lines.append(f"상태: 모델 불러오는 중... ({int(elapsed)}초)")
    else:
        eta = elapsed / done * (total - done)
        lines.append(f"상태: 평가 중   샘플당 약 {elapsed / done:.0f}초, 남은 시간 약 {eta / 60:.1f}분"
                     + (f"   ⚠ 로그가 {int(age)}초째 멈춤" if age > 180 else ""))

    lines.append("")
    lines.append(f"진행  {bar(done, total)}  {done}/{total}")
    if done:
        lines.append(f"통과  {ok}/{done} ({100 * ok / done:.0f}%)   실패 {done - ok}")

    if res:
        lines.append("")
        for sid, good, why, action, _ in res:
            mark = "✔" if good else "✘"
            lines.append(f"  {mark} {sid:<10} {action[:40]}" + ("" if good else f"   ← {why[:70]}"))

    for sid, good, why, action, gen in res[-show:]:
        lines.append("")
        lines.append(f"── {sid} {'OK' if good else 'FAIL'} ──────────────────────────────")
        lines.append(f"> {action}")
        lines.append(gen)

    lines.append("")
    lines.append(f"GPU   {gpu()}")
    lines.append(f"로그  {path}  (마지막 갱신 {int(age)}초 전)")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default=r"E:\Git_Project\stigma-train\eval\eval.log")
    p.add_argument("--heldout", default=r"E:\Git_Project\stigma-train\runs\out\heldout_ids.json")
    p.add_argument("--total", type=int, default=None, help="평가 샘플 수 (기본: heldout_ids.json 길이)")
    p.add_argument("--show", type=int, default=1, help="최근 생성문을 몇 개 펼쳐 볼지")
    p.add_argument("--interval", type=float, default=1)
    args = p.parse_args()
    total = args.total
    if total is None:
        try:
            total = len(json.load(open(args.heldout, encoding="utf-8")))
        except Exception:
            total = 15
    run_screen("STIGMA-GM 평가 모니터", lambda: render(args.log, total, args.show), args.interval)


if __name__ == "__main__":
    main()
