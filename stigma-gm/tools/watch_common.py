"""watch_train.py / watch_eval.py 공용 헬퍼. 표준 라이브러리만 쓴다."""
import os
import subprocess
import sys
import time

SPARK = "▁▂▃▄▅▆▇█"


def read_log(path):
    """PowerShell `*>`로 쓴 UTF-16 로그와 일반 UTF-8 로그를 모두 읽는다."""
    with open(path, "rb") as f:
        raw = f.read()
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    return raw.decode(enc, errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip()
        used, total, util, temp = [x.strip() for x in out.split(",")]
        return f"{int(used) / 1024:.1f}/{int(total) / 1024:.1f} GiB  사용률 {util}%  {temp}°C"
    except Exception:
        return "nvidia-smi 실패"


def bar(done, total, width=40):
    fill = int(width * done / total) if total else 0
    return "█" * fill + "░" * (width - fill)


def spark(values):
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    return "".join(SPARK[int((v - lo) / (hi - lo + 1e-9) * (len(SPARK) - 1))] for v in values)


def run_screen(title, render, interval):
    """render()를 interval초마다 다시 그린다. 완료(✅)나 오류(❌)가 뜨면 멈춘다."""
    if os.name == "nt":
        os.system("")  # Windows 콘솔에서 ANSI 이스케이프 켜기
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        while True:
            screen = render()
            sys.stdout.write("\x1b[2J\x1b[H" + f"{title}   {time.strftime('%H:%M:%S')}   (Ctrl+C 종료)\n\n" + screen + "\n")
            sys.stdout.flush()
            if "✅" in screen or "❌" in screen:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
