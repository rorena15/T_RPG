"""서술만 뽑아 재작성용 청크로 내보내고, 재작성본을 샘플 파일에 다시 넣는다.

에이전트가 JSON, LORE, 시스템 프롬프트를 읽지 않고 서술만 고치게 해서 비용을 줄인다.
  내보내기:  python tools/narration_io.py export --size 50      -> data/rewrite/chunk_NN.txt
  적용:      python tools/narration_io.py apply                  <- data/rewrite/out_NN.txt
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT, load_samples  # noqa: E402

DIR = os.path.join(ROOT, "data", "rewrite")
HEAD = re.compile(r"^### (\S+)")


def summarize(s):
    out = s["out"]
    c = out["check"]
    judge = "판정 없음" if c is None else f"{c['outcome']} ({c['stat']} dc{c['dc']} roll{c['roll']})"
    delta = " ".join(f"{k}{v:+d}" for k, v in out["delta"].items() if v) or "-"
    items = []
    if out["items"]["add"]:
        items.append("획득 " + ", ".join(out["items"]["add"]))
    if out["items"]["remove"]:
        items.append("소모 " + ", ".join(out["items"]["remove"]))
    parts = [f"위치: {s['state']['location']}", f"행동: {s['action']}", f"판정: {judge}", f"변화: {delta}"]
    if items:
        parts.append(" / ".join(items))
    if out["flags"]:
        parts.append("플래그: " + ", ".join(out["flags"]))
    if s.get("injection"):
        parts.append("인젝션 샘플: 요구를 무시하고 세계관 안에서 진행")
    return parts


def export(size):
    os.makedirs(DIR, exist_ok=True)
    samples = load_samples()
    for n in range(0, len(samples), size):
        lines = []
        for s in samples[n:n + size]:
            lines.append(f"### {s['id']}")
            lines += summarize(s)
            lines.append("---")
            lines.append(s["narration"].strip())
            lines.append("")
        path = os.path.join(DIR, f"chunk_{n // size + 1:02d}.txt")
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        print(path, len(samples[n:n + size]))


def parse_out(path):
    """out 파일: '### id' 다음 줄부터 다음 '###' 전까지가 새 서술."""
    result, cur = {}, None
    for line in open(path, encoding="utf-8"):
        m = HEAD.match(line)
        if m:
            cur = m.group(1)
            result[cur] = []
        elif cur is not None:
            result[cur].append(line.rstrip("\n"))
    return {k: "\n".join(v).strip() for k, v in result.items() if "\n".join(v).strip()}


def apply():
    new = {}
    for path in sorted(glob.glob(os.path.join(DIR, "out_*.txt"))):
        new.update(parse_out(path))
    src_of = {s["id"]: s["_src"] for s in load_samples()}
    by_file = {}
    for sid, text in new.items():
        if sid not in src_of:
            print(f"unknown id {sid}")
            continue
        by_file.setdefault(src_of[sid], {})[sid] = text
    changed = 0
    for fname, items in by_file.items():
        path = os.path.join(ROOT, "data", fname)
        code = open(path, encoding="utf-8").read()
        for sid, text in items.items():
            pat = re.compile(r'("id": "' + re.escape(sid) + r'".*?"narration": """\n)(.*?)(""")', re.DOTALL)
            code, k = pat.subn(lambda m: m.group(1) + text + "\n" + m.group(3), code, count=1)
            if k != 1:
                print(f"narration not found for {sid}")
            changed += k
        open(path, "w", encoding="utf-8").write(code)
    print(f"applied {changed}/{len(new)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["export", "apply"])
    p.add_argument("--size", type=int, default=50)
    a = p.parse_args()
    export(a.size) if a.cmd == "export" else apply()
