# 자동 복사본: stigma-gm/engine/lore.py (tools/sync_to_game.py). 여기서 고치지 말 것.
"""원작 설정 조각에서 장면에 맞는 것을 골라 [LORE]에 덧붙인다 (학습 없이 세계관 근거를 보강).

조각은 tools/build_canon_corpus.py가 만든 lore_snippets.json (장비 묘사, 세계관 문단, 장소·NPC 설명).
장비 묘사는 플레이어가 가진 아이템일 때만 넣는다 (안 가진 장비를 보여 주면 GM이 그걸 서술하거나 준다).
한국어는 띄어쓰기로 단어를 나누기 어려워 두 글자 조각(바이그램)이 얼마나 겹치는지로 고른다.
흔한 조각은 가중치를 낮춘다(IDF).
표준 라이브러리만 쓴다 (게임에 그대로 복사됨).
"""
import json
import math
import os
import re

_WORD = re.compile(r"[가-힣A-Za-z0-9]+")
PLACES = ("폐기물 처리장", "구시대 지하 방공호", "슬럼가 유령 노드", "방사능 용융 분지", "중앙 총괄 본부", "녹슨 정크야드 벙커")
_PLACE = re.compile("^(" + "|".join(PLACES) + ")")


def _grams(text):
    out = set()
    for w in _WORD.findall(text):
        if len(w) == 1:
            continue
        out.update(w[i:i + 2] for i in range(len(w) - 1))
    return out


def _default_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "lore_snippets.json"), os.path.join(here, "..", "data", "lore_snippets.json")):
        if os.path.exists(p):
            return p
    return None


class LoreIndex:
    def __init__(self, path=None):
        path = path or _default_path()
        self.snippets = json.load(open(path, encoding="utf-8")) if path else []
        self._grams = [_grams(s["text"]) for s in self.snippets]
        df = {}
        for gs in self._grams:
            for g in gs:
                df[g] = df.get(g, 0) + 1
        n = max(1, len(self.snippets))
        self._idf = {g: math.log(n / c) for g, c in df.items()}
        self._by_name = {s["name"]: s["text"] for s in self.snippets if s.get("name")}

    def search(self, query, k=3, skip_text=""):
        """query와 가장 많이 겹치는 조각 k개. skip_text(이미 들어간 LORE)와 거의 같은 조각은 뺀다.
        skip_text의 낱말은 검색어에서도 뺀다: 장소 기본 설명이 검색어에 섞이면 그 설명과 겹치는
        조각(예: 방공호, 1막 줄거리)이 행동과 상관없이 늘 올라왔다 (자판기 이벤트에서 방공호 문을 서술, 2026-09-27)."""
        skip = _grams(skip_text)
        q = _grams(query) - skip
        scored = []
        for i, gs in enumerate(self._grams):
            # 장비 설명은 소지품일 때만(extra_lore의 names) 넣는다. 안 가진 장비를 보여 주면 GM이 그걸 서술하거나 준다
            if self.snippets[i].get("src") == "장비":
                continue
            if not gs or len(gs & skip) / len(gs) > 0.6:
                continue
            place = _PLACE.match(self.snippets[i]["text"])
            if place and place.group(1) not in query and place.group(1) not in skip_text:
                continue  # 다른 장소 설명은 행동·장면에 그 장소가 나올 때만
            shared = q & gs
            if not shared:
                continue
            score = sum(self._idf.get(g, 0) for g in shared) / math.sqrt(len(gs))
            scored.append((score, i))
        scored.sort(reverse=True)
        return [self.snippets[i]["text"] for _, i in scored[:k]]

    def extra_lore(self, query, names=(), base_lore="", max_chars=450, k=3):
        """[LORE] 뒤에 붙일 문장. 소지품 설명을 먼저, 그다음 장면과 겹치는 조각. max_chars를 넘지 않는다."""
        picked = [self._by_name[n] for n in names if n in self._by_name]
        for text in self.search(query, k=k + len(picked), skip_text=base_lore):
            if text not in picked:
                picked.append(text)
        out, used = [], 0
        for text in picked:
            if used + len(text) > max_chars:
                continue
            out.append(text)
            used += len(text) + 1
            if len(out) >= k + len([n for n in names if n in self._by_name]):
                break
        return " ".join(out)
