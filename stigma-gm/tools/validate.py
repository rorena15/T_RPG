"""샘플 규칙 검사. 위반이 하나라도 있으면 exit 1."""
import json
import re
import sys

from build import load_samples, render_output

from guard import check_narration, check_output, split_output

from canon import ITEM_TIERS, ITEMS, NPCS

OPENING_LIMIT = 0.4
CANON_ITEMS = set(ITEMS)
# 이름 붙은 NPC가 나오는 샘플에서 금지할 성별 표현 (NPC 성별 비공개)
GENDERED = re.compile(r"그녀|남자|여자|사내|아가씨|아저씨|(?<![가-힣])그(가|는|의|를|에게|도)(?![가-힣])")
# 추상 IT 용어는 [시스템 로그] 줄이나 디지털 대상을 다루는 장면에서만 쓴다 (DESIGN.md 서술 층).
IT_TERMS = re.compile(r"동기화|연동|프로토콜|(?<!아날)(?<!홀)로그(?!램)|파싱|패킷|빌트인|핸드셰이크|데이터|버퍼|인터페이스|업로드|다운로드"
                      r"|포팅|알고리즘|프로세스|캐시|연산|접속|스크립트|백도어|펌웨어|코드|권한(?!다)|인코딩")
# 원작 고유 표현은 물리 장면에서도 그대로 쓴다
CANON_PHRASES = re.compile("|".join(re.escape(n) for n in sorted(ITEMS, key=len, reverse=True)) + r"|불량 코드|뇌파 동기화 아크 전류음|유령 데이터 박스|데이터 박스|바이오 링크")
DIGITAL_ACTION = re.compile(r"해킹|사이버덱|덱|터미널|노드|서버|방화벽|침투|접속|코드|백도어|스크립트|패킷|암호"
                            r"|로그|데이터|프로토콜|파일|폴더|화면|단말|네트워크|포트|RAM|램")


def misplaced_it_terms(s, narration, out):
    if out["weights"].get("cyber") or out["delta"].get("ram") or DIGITAL_ACTION.search(s["action"]):
        return []
    found = []
    for line in narration.splitlines():
        if line.lstrip().startswith("["):
            continue
        found += IT_TERMS.findall(CANON_PHRASES.sub("", line))
    return sorted(set(found))


def check(s):
    narration, out = split_output(render_output(s))
    errs = check_output(s["state"], s["roll"], out)
    sentences = [x for x in re.split(r"(?<=[.!?…])\s+", narration) if x]
    if not 3 <= len(sentences) <= 7:
        errs.append(f"{len(sentences)} sentences")
    if "—" in narration:
        errs.append("em dash")
    if re.search(r"\d+화", narration):
        errs.append("N화 leak")
    for t in misplaced_it_terms(s, narration, out):
        errs.append(f"IT term outside digital scene: {t}")
    errs += check_narration(narration)
    items = set(s["state"].get("inventory", [])) | set(out["items"]["add"]) | set(out["items"]["remove"])
    for name in sorted(items - CANON_ITEMS):
        errs.append(f"non-canon item: {name}")
    # T=0 유물은 +10 정제로만 연성, T=1은 최상위 기업제. 탐색·전투·거래로 얻지 않는다
    for name in out["items"]["add"]:
        if ITEM_TIERS.get(name, 4) <= 1:
            errs.append(f"T={ITEM_TIERS[name]} item as loot: {name}")
    # 이전 턴 assistant 답변도 학습된다 (train_on_responses_only는 모든 assistant 턴에 손실을 건다)
    for i, (user, prev) in enumerate(s.get("history", [])):
        try:
            h_narr, h_out = split_output(prev)
        except (ValueError, json.JSONDecodeError) as e:
            errs.append(f"history[{i}] format: {e}")
            continue
        if not prev.lstrip().startswith("<check>"):
            errs.append(f"history[{i}] old format")
        errs += [f"history[{i}] {e}" for e in check_narration(h_narr)]
        errs += [f"history[{i}] IT term: {t}" for t in misplaced_it_terms({"action": user}, h_narr, h_out)]
        if "—" in h_narr:
            errs.append(f"history[{i}] em dash")
    if any(n.split()[-1] in s["lore"] for n in NPCS):
        texts = [narration] + [a for _, a in s.get("history", [])]
        for m in {m.group(0) for t in texts for m in GENDERED.finditer(t)}:
            errs.append(f"gendered word with named NPC: {m}")
    return errs


if __name__ == "__main__":
    bad = 0
    samples = load_samples()
    ids = [s["id"] for s in samples]
    for d in {i for i in ids if ids.count(i) > 1}:
        print(f"duplicate id {d}")
        bad += 1
    for s in samples:
        for e in check(s):
            print(f"[{s['_src']}:{s['id']}] {e}")
            bad += 1
    # 파일 단위: 첫 문장이 '당신은/당신이'로 시작하는 비율 상한 (단조로운 도입 방지)
    by_src = {}
    for s in samples:
        by_src.setdefault(s["_src"], []).append(s)
    for src, ss in by_src.items():
        k = sum(split_output(render_output(s))[0].startswith(("당신은", "당신이")) for s in ss)
        if len(ss) >= 5 and k / len(ss) > OPENING_LIMIT:
            print(f"[{src}] '당신은/당신이' 도입 {k}/{len(ss)} > {OPENING_LIMIT:.0%}")
            bad += 1
    inj = sum(1 for s in samples if s.get("injection"))
    print(f"{len(samples)} samples ({inj} injection), {bad} problems")
    sys.exit(1 if bad else 0)
