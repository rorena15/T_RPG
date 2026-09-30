"""GM 응답의 예전 브랜드명 → 새 이름 대응 (gm_bridge.RENAMED) 시험.

개발/에서: python tests/test_gm_renamed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import db_init
import gm_bridge
from gm_bridge import _renamed, _renamed_out, _item_id

CASES = [
    ("아라사카 나노 레이저 카타나를 집어 든다.", "아마기리 나노 레이저 카타나를 집어 든다."),
    ("바이오테크니카가 만든 방출기다.", "셀리온이 만든 방출기다."),          # 받침 없음 → 있음
    ("마이크로테크를 믿지 마라.", "비트레일을 믿지 마라."),
    ("오비탈 에어로 날아간다.", "스트라토로 날아간다."),                    # 받침 있음(ㄹ) → 없음
    ("오비탈 생체 방사능 필터 코어와 바이오테크니카로", "스트라토 생체 방사능 필터 코어와 셀리온으로"),
    ("리퍼닥 슬라이는 냉소적이다.", "봉합꾼 슬라이는 냉소적이다."),
    ("트라우마 팀과 밀리테크는 적이다.", "레드라인과 스틸게이트는 적이다."),
    ("캉타오의 권총", "란위의 권총"),
    ("아라사카입니다.", "아마기리입니다."),
    ("브랜드 없는 문장.", "브랜드 없는 문장."),
    ("리퍼 닥은 어디선가 다른 이름으로 불린다.", "봉합꾼은 어디선가 다른 이름으로 불린다."),   # 띄어 쓴 변형
    ("트라우마팀을 부른다.", "레드라인을 부른다."),
    ("Arasaka 로고가 찍힌 상자", "아마기리 로고가 찍힌 상자"),                              # 영문 표기
    ("trauma team과 Militech가 온다", "레드라인과 스틸게이트가 온다"),
    ("오비탈에어의 화물", "스트라토의 화물"),
    ("오리를 퍼 닥치는 대로 먹는다.", "오리를 퍼 닥치는 대로 먹는다."),                      # 낱말 경계를 넘는 우연한 글자열은 건드리지 않는다
]


def main():
    fails = 0
    for src, want in CASES:
        got = _renamed(src)
        ok = got == want
        fails += not ok
        print("OK  " if ok else "FAIL", src, "→", got)
    out = _renamed_out({"items": {"add": ["리퍼닥 그리드 동기화 칩"], "remove": ["아라사카 나노 레이저 카타나"]}})
    assert out["items"]["add"] == ["봉합꾼 그리드 동기화 칩"], out
    assert out["items"]["remove"] == ["아마기리 나노 레이저 카타나"], out
    assert _renamed(None) is None and _renamed("") == ""
    # 이름으로 장비 찾기: 예전 이름도 같은 장비로
    db_init.init_database()
    gm_bridge._name_to_id = None
    assert _item_id("리퍼닥 그리드 동기화 칩") == _item_id("봉합꾼 그리드 동기화 칩") == "PART_REF_04"
    assert _item_id("아라사카 나노 레이저 카타나") == "WEAPON_CORP_01"
    print("items OK")
    if fails:
        sys.exit(f"{fails}개 실패")
    print("전부 통과")


if __name__ == "__main__":
    main()
