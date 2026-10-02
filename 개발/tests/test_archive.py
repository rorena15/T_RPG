"""기록 보관소 (archive.py) 시험: 적 단계 열림, 일기 조각 줍는 곳, 글 없는 항목 숨김, 결말 기록과 따로 저장.

개발/에서: python tests/test_archive.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import archive
import endings
import frozen_compat
import i18n

i18n.set_lang("ko")
TMP = tempfile.mkdtemp()
frozen_compat.user_dir = lambda: TMP   # archive·endings가 부를 때마다 읽는다

# 시험용 글: 드론·보스만 적 글, 장면 둘, 조각 a01·b01(학교)·c01(경계)
archive._text["ko"] = {
    "enemy": {"drone": {"name": "드론", "stages": ["하나", "둘", "셋"]},
              "boss": {"name": "컬렉터", "stages": ["하나", "둘", "셋"]}},
    "scene": {"lm_school": {"title": "학교", "text": "글"}, "junkyard": {"title": "처리장", "text": "글"}},
    "fragment": {"a01": {"title": "첫날", "text": "글"}, "b01": {"title": "알림장", "text": "글"},
                 "c01": {"title": "지침", "text": "글"}},
}

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class P:
    alert_level = 0


class G:
    player_pos = [0, 0]


class AlwaysRng:
    """주울 확률은 늘 통과, 고르기는 첫 번째."""
    def random(self):
        return 0.0

    def choice(self, seq):
        return seq[0]


# 적: 만남 → 1단계, 첫 승리 → 2단계, 10승 → 3단계. 보스는 3승
check("만남 알림", archive.meet_enemy("drone") is not None)
check("다시 만나면 알림 없음", archive.meet_enemy("drone") is None)
check("첫 승리 알림", archive.defeat_enemy("drone") is not None)
for _ in range(8):
    check_mid = archive.defeat_enemy("drone")
check("9승까지는 새 단계 없음", check_mid is None)
check("10승 알림", archive.defeat_enemy("drone") is not None)
check("드론 3/3", [x for x in archive.enemy_list() if x[0] == "drone"][0][2:] == (3, 3))
archive.meet_enemy(None, is_boss=True)
for _ in range(3):
    archive.defeat_enemy(None, is_boss=True)
check("보스 3승에 3/3", [x for x in archive.enemy_list() if x[0] == "boss"][0][2:] == (3, 3))
check("글 없는 적은 목록에 없음", [x[0] for x in archive.enemy_list()] == ["drone", "boss"])
check("글 없는 적도 기록은 남음", archive.meet_enemy("dogs") is None and "dogs" in archive.load()["enemies"])
check("닫힌 단계는 조건만", archive.enemy_pages("drone")[-1] == "셋")

# 장면: 목록에 없는 장면(적 그림)은 남기지 않는다
archive.see_scene("lm_school")
archive.see_scene("enemy_drones")
check("장면 열림", archive.scene_list() == [("lm_school", "학교")])
archive.see_scene("junkyard")
check("랜드마크가 아닌 장면은 기록 안 함", "junkyard" not in archive.load()["scenes"])
check("적 그림은 장면 기록 아님", "enemy_drones" not in archive.load()["scenes"])

# 일기: 학교 칸이 아니면 b01, 경계 지대가 아니면 c01이 안 나온다
import scene_art
here = {"pos": "junkyard"}
scene_art.tile_scene = lambda loc, pos: here["pos"]
rng = AlwaysRng()
never = AlwaysRng()
never.random = lambda: 0.99
check("확률을 못 넘으면 없음", archive.roll_fragment(P(), G(), never) is None)
check("어디서나 a01", "첫날" in (archive.roll_fragment(P(), G(), rng) or ""))
check("학교·경계 지대 칸이 아니면 더 없음", archive.roll_fragment(P(), G(), rng) is None)
here["pos"] = "lm_school"
check("학교 칸에서 b01", "알림장" in (archive.roll_fragment(P(), G(), rng) or ""))
here["pos"] = "border_zone"
check("경계 지대에서 c01", "지침" in (archive.roll_fragment(P(), G(), rng) or ""))
check("다 주우면 없음", archive.roll_fragment(P(), G(), rng) is None)

# 히든: 일지 A가 HIDDEN_NEED개 모이기 전에는 안 나오고, 찾기 전까지 목록에 없다
archive._text["ko"]["hidden"] = {"title": "품에 안긴 일지", "text": "글"}
archive._text["ko"]["fragment"]["a11"] = {"title": "마지막 장", "text": "글"}
check("A 1개로는 히든 없음", not archive.hidden_ready(rng))
check("숨은 조각은 목록에 없음", [f for f, _ in archive.fragment_list("a")] == ["a01"])
d = archive.load()
d["fragments"] += ["a02", "a03", "a04", "a05"]
archive._save(d)
check("A 5개면 히든 가능", archive.hidden_ready(rng))
check("히든 확률", not archive.hidden_ready(never))
check("마지막 장 기록", "마지막 장" in archive.take_hidden() and not archive.hidden_ready(rng))
check("찾은 뒤 목록에 보임", ("a11", "마지막 장") in archive.fragment_list("a"))
check("빈 탐색으로는 a11 안 나옴", all(w == "hidden" for f, _, w in archive.FRAGMENTS if f == "a11"))

# 결말 기록과 따로: endings.unlock이 archive.json을 지우지 않는다
before = archive.load()
endings.unlock("pioneer", "combat")
check("결말 기록 후에도 보관소 그대로", archive.load() == before)
c = archive.counts()
check("집계", c["enemy"] == (6, 6) and c["scene"] == (1, 1) and c["fragment"] == (4, 4) and c["endings"][0] == 2)
check("파일에 남음", json.load(open(os.path.join(TMP, "archive.json"), encoding="utf-8"))["fragments"][:3] == ["a01", "b01", "c01"])

# 핸드폰: 주워도 충전기 전에는 못 읽고, 핸드폰을 가진 채 발전소 칸 빈 탐색에서 충전기
archive._text["ko"]["fragment"]["b06"] = {"title": "문자 기록", "text": "글"}
here["pos"] = "lm_mall"
check("핸드폰 줍기 알림", "휴대용 인터페이스" in (archive.roll_fragment(P(), G(), rng) or ""))
rows = dict((f, (txt, ok)) for f, txt, ok in archive.fragment_rows("b"))
check("충전 전에는 못 엶", rows["b06"] == (i18n.t('arc_phone_locked'), False))
here["pos"] = "lm_school"
check("발전소 칸이 아니면 충전기 없음", "충전기" not in (archive.roll_fragment(P(), G(), rng) or ""))
here["pos"] = "lm_powerplant"
check("발전소 칸에서 충전기", "충전기" in (archive.roll_fragment(P(), G(), rng) or ""))
rows = dict((f, (txt, ok)) for f, txt, ok in archive.fragment_rows("b"))
check("충전 뒤에는 열림", rows["b06"] == ("문자 기록", True) and archive.load()["charger"])
check("충전기는 한 번만", "충전기" not in (archive.roll_fragment(P(), G(), rng) or ""))

# 실제 글 파일이 있으면 형식 확인
for lang in ("ko", "en"):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales", f"archive_{lang}.json")
    if os.path.exists(path):
        d = json.load(open(path, encoding="utf-8"))
        bad = [k for k in d.get("enemy", {}) if k not in archive.ENEMIES]
        bad += [k for k in d.get("scene", {}) if k not in archive.SCENES]
        bad += [k for k in d.get("fragment", {}) if k not in {f for f, _, _ in archive.FRAGMENTS}]
        check(f"archive_{lang}.json 키", not bad)

print("\n" + (f"실패 {len(FAILS)}개" if FAILS else "모두 통과"))
sys.exit(1 if FAILS else 0)
