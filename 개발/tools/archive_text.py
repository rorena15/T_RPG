"""기록 보관소 글 ↔ 원고 파일 (사람이 읽고 고치기 쉬운 마크다운).

  python tools/archive_text.py export [ko]   locales/archive_ko.json → docs/기획/기록보관소_원고_ko.md
  python tools/archive_text.py import [ko]   원고 → locales/archive_ko.json (키가 빠지거나 늘면 멈춘다)

원고 형식: "### 키 | 제목" 다음 ```text 블록이 본문. 적은 "### 키 | 이름" 아래 "#### 기록 N" 블록.
블록 안의 줄바꿈이 그대로 기록의 줄이 된다. 키와 ``` 줄만 건드리지 않으면 된다.

확정한 글은 docs/기획/기록보관소_확정.txt에 한 줄에 하나씩 적는다 (enemy.drone.1, scene.lm_school, fragment.b02 ...).
export는 확정한 글을 원고에서 빼고, import는 원고에 있는 글만 바꾼다 (빠진 글은 그대로 둔다).
"""
import json
import os
import re
import sys

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DEV)
import archive  # noqa: E402

SERIES_NAME = {"a": "A. 먼저 버려진 자의 일지", "b": "B. 구시대의 기록", "c": "C. 쫓겨난 자들의 증언"}
WHERE = {None: "어디서나", "hidden": "히든 이벤트로만", "border_zone": "경계 지대 칸"}


def paths(lang):
    return (os.path.join(DEV, "locales", f"archive_{lang}.json"),
            os.path.join(os.path.dirname(DEV), "docs", "기획", f"기록보관소_원고_{lang}.md"))


def confirmed():
    path = os.path.join(os.path.dirname(DEV), "docs", "기획", "기록보관소_확정.txt")
    try:
        return {ln.strip() for ln in open(path, encoding="utf-8") if ln.strip() and not ln.startswith("#")}
    except FileNotFoundError:
        return set()


def block(text):
    return "```text\n" + text + "\n```\n"


def export(lang):
    src, dst = paths(lang)
    d = json.load(open(src, encoding="utf-8"))
    done = confirmed() if lang == "ko" else set()   # 확정 목록은 한국어 원고 기준
    out = ["# 기록 보관소 원고", "",
           "고친 뒤 `개발/`에서 `python tools/archive_text.py import`로 게임에 반영한다.",
           "`###` 줄의 키(| 앞)와 ``` 줄은 건드리지 않는다. 제목·이름(| 뒤)과 블록 안 글은 자유롭게 고친다.",
           f"확정한 글 {len(done)}편은 빠져 있다 (docs/기획/기록보관소_확정.txt).", ""]
    for key in archive.ENEMIES if "enemy" in d else []:   # 적 도감은 그림만 쓰기로 해서 지금은 글이 없다
        e = d["enemy"][key]
        left = [(i, st) for i, st in enumerate(e["stages"], 1) if f"enemy.{key}.{i}" not in done]
        if not left:
            continue
        out += [f"### {key} | {e['name']}", ""]
        for i, st in left:
            out += [f"#### 기록 {i}", block(st)]
    out += ["## 랜드마크 이야기", "", "그 그림이 처음 화면에 나오면 열린다. 지금 그곳에 머무는 사람의 기록", ""]
    for key in archive.SCENES:
        if f"scene.{key}" in done:
            continue
        e = d["scene"][key]
        out += [f"### {key} | {e['title']}", block(e["text"])]
    for s in archive.SERIES:
        out += [f"## 일기 조각 {SERIES_NAME[s]}", ""]
        for fid, ser, where in archive.FRAGMENTS:
            if ser != s or f"fragment.{fid}" in done:
                continue
            e = d["fragment"][fid]
            note = WHERE.get(where, f"{where} 칸")
            out += [f"### {fid} | {e['title']}", f"<!-- 줍는 곳: {note} -->", block(e["text"])]
    h = d["hidden"]
    out += [] if "hidden" in done else ["## 히든 이벤트 장면", "", "A를 5개 이상 모은 뒤 랜덤 이벤트 자리에서 3%, 평생 한 번. 이 글을 보여 주고 a11을 준다", "",
            f"### hidden | {h['title']}", block(h["text"])]
    open(dst, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("->", dst)


ENTRY = re.compile(r"^### (\S+) \| (.*)$")
STAGE = re.compile(r"^#### 기록 (\d+)$")


def import_(lang):
    src, dst = paths(lang)
    d = json.load(open(src, encoding="utf-8"))
    frags = {f for f, _, _ in archive.FRAGMENTS}
    cur, title, stage, buf, inside, n = None, None, None, [], False, 0
    for ln in open(dst, encoding="utf-8").read().split("\n"):
        if inside:
            if ln.strip() != "```":
                buf.append(ln)
                continue
            inside = False
            text = "\n".join(buf).strip("\n")
            if cur in archive.ENEMIES:
                if stage is None or not 1 <= stage <= 3:
                    sys.exit(f"{cur}: '#### 기록 N' 줄이 없음")
                d["enemy"][cur]["name"] = title
                d["enemy"][cur]["stages"][stage - 1] = text
            elif cur in archive.SCENES:
                d["scene"][cur] = {**d["scene"].get(cur, {}), "title": title, "text": text}
            elif cur == "hidden":
                d["hidden"] = {"title": title, "text": text}
            elif cur in frags:
                d["fragment"][cur] = {**d["fragment"].get(cur, {}), "title": title, "text": text}
            else:
                sys.exit(f"모르는 키: {cur}")
            n += 1
            continue
        m = ENTRY.match(ln)
        if m:
            cur, title, stage = m.group(1), m.group(2).strip(), None
            continue
        m = STAGE.match(ln)
        if m:
            stage = int(m.group(1))
        elif ln.strip().startswith("```"):
            inside, buf = True, []
    json.dump(d, open(src, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{n}편 반영 ->", src)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "export"
    lang = sys.argv[2] if len(sys.argv) > 2 else "ko"
    {"export": export, "import": import_}[cmd](lang)
