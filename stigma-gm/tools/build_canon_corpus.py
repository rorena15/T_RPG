"""원작 자료(T_RPG)에서 서사만 골라 두 가지를 만든다.

1. data/canon_corpus.txt: 소형 모델의 세계관 사전 학습용 원문 (train_unsloth.py --corpus)
2. data/lore_snippets.json: 실행 중 장면에 맞는 설정을 [LORE]에 덧붙일 짧은 조각 (engine/lore.py)

개발용 메타(JSON 명세, 수식, 플래그, 개발 메모, 표)는 버린다. 서술에 "파싱", "플래그" 같은 말이 새지 않게.
이름 붙은 NPC의 성별은 비공개(사용자 결정)이므로 성별 대명사가 든 문장도 버린다.
  실행:  python tools/build_canon_corpus.py [--game E:/Git_Project/T_RPG]
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "data"))

# 서사가 있는 문서만 (공식·능력치·개발 계획 문서는 제외)
NARRATIVE_DOCS = [
    "docs/기획/스토리/본편 스토리 - 1막 낙인 뼈대.md",
    # "본편 스토리- 프로토콜 리부트.md"는 뺀다: 뒤 막 전개·엔딩·기계 괴수의 정체가 들어 있다.
    # 1막 게임의 GM이 알 필요가 없고, lore_snippets.json은 공개 저장소의 게임에 그대로 들어간다 (2026-09-27 누출 발견)
    "docs/기획/Project_World_Narrative_Detail.md",
    "docs/기획/Text RPG 프로젝트 직업별 기원 및 서사 배경.md",
    "docs/기획/Project_Theology_Paradox.md",
    "docs/기획/Project_NPC_Quest.md",
    "docs/기획/Project_Map_Gimmick.md",
    "docs/기획/Project_Monster_Raid.md",
    "docs/기획/Text RPG 프로젝트 콘셉트.md",
    "docs/기획/성향 및 진영 평판 시스템 (Alignment & Faction Reputation).md",
]
SCRIPT_DOC = "docs/기획/스토리/본편 스토리 - 1막 낙인 스크립트.md"  # JSON "text"만 뽑는다

META = re.compile(r"[`${}]|개발|파싱|데이터셋|명세|플래그|가중치|스크립트|JSON|XML|스팀|데모|플레이타임|1인|"
                  r"수식|공식|연산식|변수|트리거|코드 ID|ID\b|UI|밸런스|구현|버전|스코프|볼륨|포인터|\bR\b|\bF\b|"
                  r"유저|플레이어|퀘스트|엔딩|처리|연동|히든|조건|힌트|메커니|역할군|전직|Respec|환급|비판|"
                  r"수치|루프|핵심 사건|차별점|[0-9]+막|본편|분기|달성|세션|선택지|위험 요소|매 턴|Alert|Level|\[[0-9]+\]|"
                  # 스포일러: 반전과 복선은 GM이 1막부터 흘리면 안 된다
                  r"복선|반전|사실은|알고 보니|정체가|이식당했던|진실은|"
                  r"과거 인간|인간이었|유기체였|결말|코드화|가축화|다음 주기|통제자가 되어")
GENDERED = re.compile(r"그녀|(?<![가-힣])그(는|가|의|를|에게|도)(?![가-힣])|남자|여자|사내|아가씨|아저씨")
MD_NOISE = re.compile(r"^[#>\-\*\s]+|\*\*|__|~~")
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")
SENT_SPLIT = re.compile(r"(?<=[.!?…다요])\s+")
# 장비 설명 중 게임 수치·용어가 든 것은 서술에 새므로 버리고, 묘사형만 남긴다
MECHANIC = re.compile(r"[0-9%$×+]|확률|배율|페널티|디버프|버프|대미지|데미지|타일|연산|지표|스킬|턴|슬롯|수치|"
                      r"가중치|판정|쿨|스탯|평판|레이드|증폭|감쇄|삭감|보정|필드|공격|방어|회피|치명")
TIER_TAG = re.compile(r"^(\[[^\]]*\]\s*)+")
SENTENCE_END = re.compile(r"(다|요|니다|음|함|됨)[.!?…]?$")


def clean_line(line):
    line = EMOJI.sub("", MD_NOISE.sub("", line.strip())).strip().strip("_")
    line = re.sub(r"^[^ :]{1,12}:_s*", "", line)  # "서사:_" 같은 꼬리표
    line = line.replace("—", ", ").replace(" ,", ",")  # 한국어 산문에 줄표를 쓰지 않는다
    return re.sub(r"\s+", " ", line)


def keep_sentences(text):
    """메타·성별 표현이 든 문장을 뺀 나머지."""
    sents = [s for s in SENT_SPLIT.split(text) if s.strip()]
    return " ".join(s for s in sents if not META.search(s) and not GENDERED.search(s)).strip()


def doc_paragraphs(path):
    out, in_code = [], False
    for raw in open(path, encoding="utf-8"):
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or raw.lstrip().startswith("|") or raw.strip() in ("---", ""):
            continue
        line = keep_sentences(clean_line(raw))
        if len(line) >= 30 and SENTENCE_END.search(line):  # 목차·제목 줄이 아닌 문장만
            out.append(line)
    return out


def script_texts(path):
    """1막 스크립트의 JSON 블록에서 "text" 서사만 뽑는다."""
    out = []
    for m in re.finditer(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', open(path, encoding="utf-8").read()):
        text = json.loads(f'"{m.group(1)}"')
        for para in text.split("\n"):
            para = keep_sentences(re.sub(r"^\[[^\]]+\]:?\s*", "", para.strip()))
            if len(para) >= 20:
                out.append(para)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--game", default="E:/Git_Project/T_RPG")
    args = p.parse_args()
    g = args.game

    corpus, snippets, stats = [], [], {}

    def add(source, paras):
        stats[source] = (len(paras), sum(len(x) for x in paras))
        corpus.extend(paras)

    add("1막 스크립트", script_texts(os.path.join(g, SCRIPT_DOC)))
    for rel in NARRATIVE_DOCS:
        paras = doc_paragraphs(os.path.join(g, rel))
        add(os.path.basename(rel), paras)
        if "docs/기획/스토리/" in rel:  # 줄거리 문서는 실행 중 검색에 안 넣는다: GM이 줄거리 사건을 지금 장면으로 착각했다
            continue
        for para in paras:  # 짧은 설정 조각 (LORE 보강용)
            if 30 <= len(para) <= 260:
                snippets.append({"src": os.path.basename(rel), "text": para})

    db = json.load(open(os.path.join(g, "개발", "text", "story.json"), encoding="utf-8"))
    script = []
    for ev in db["RANDOM_EVENTS"] + db["SESSIONS_DB"]:
        script.append(ev["title"] + ". " + " ".join(ev["text"].split()))
        for c in ev.get("choices", []) + ([ev["result"]] if "result" in ev else []):
            log = clean_line(re.sub(r"^\[[^\]]+\]\s*", "", " ".join(c.get("log", "").split())))
            if log:
                script.append(keep_sentences(log))
    script += [clean_line(x) for x in db["AMBIENT_LORE"]]
    script = [clean_line(x) for x in script]
    add("게임 대본", [x for x in script if len(x) >= 15 and not GENDERED.search(x)])

    items = []
    with sqlite3.connect(os.path.join(g, "개발", "stigma_data.db")) as c:
        for name, desc, tier in c.execute("SELECT name, description, tier FROM equipment WHERE description != ''"):
            desc = clean_line(TIER_TAG.sub("", " ".join((desc or "").split())))
            if desc and not GENDERED.search(desc) and not MECHANIC.search(desc):
                items.append(f"{name}: {desc}")
                snippets.append({"src": "장비", "name": name, "tier": tier, "text": f"{name}: {desc}"})
    add("장비 설명", items)

    from _common import (LORE_BASIN, LORE_BUNKER, LORE_COLLECTOR, LORE_HQ, LORE_JUNKYARD,  # noqa: E402
                         LORE_JUNKYARD_BUNKER, LORE_SLUM, NPC_ECHO, NPC_JUDITH, NPC_SLY, NPC_VULKAN, NPC_ZERO)
    for text in (LORE_BASIN, LORE_BUNKER, LORE_COLLECTOR, LORE_HQ, LORE_JUNKYARD, LORE_JUNKYARD_BUNKER, LORE_SLUM,
                 NPC_ECHO, NPC_JUDITH, NPC_SLY, NPC_VULKAN, NPC_ZERO):
        snippets.append({"src": "LORE", "text": text})

    with open(os.path.join(ROOT, "data", "canon_corpus.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(corpus) + "\n")
    with open(os.path.join(ROOT, "data", "lore_snippets.json"), "w", encoding="utf-8") as f:
        json.dump(snippets, f, ensure_ascii=False, indent=0)
    for k, (n, ch) in stats.items():
        print(f"  {k}: {n}개 문단, {ch:,}자")
    print(f"corpus {sum(len(x) for x in corpus):,}자, snippets {len(snippets)}개")


if __name__ == "__main__":
    main()
