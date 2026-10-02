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
check("장면 열림", archive.scene_list() == [("junkyard", None), ("lm_school", "학교")])
check("적 그림은 장면 기록 아님", "enemy_drones" not in archive.load()["scenes"])

# 일기: 학교 칸이 아니면 b01 안 나옴, 경계 낮으면 c01 안 나옴
import scene_art
here = {"pos": "junkyard"}
scene_art.tile_scene = lambda loc, pos: here["pos"]
rng = AlwaysRng()
never = AlwaysRng()
never.random = lambda: 0.99
check("확률을 못 넘으면 없음", archive.roll_fragment(P(), G(), never) is None)
check("어디서나 a01", "첫날" in (archive.roll_fragment(P(), G(), rng) or ""))
check("학교 칸 아니고 경계 낮으면 더 없음", archive.roll_fragment(P(), G(), rng) is None)
here["pos"] = "lm_school"
check("학교 칸에서 b01", "알림장" in (archive.roll_fragment(P(), G(), rng) or ""))
p = P()
p.alert_level = archive.ALERT_FRAGMENT
check("경계 높을 때 c01", "지침" in (archive.roll_fragment(p, G(), rng) or ""))
check("다 주우면 없음", archive.roll_fragment(p, G(), rng) is None)

# 결말 기록과 따로: endings.unlock이 archive.json을 지우지 않는다
before = archive.load()
endings.unlock("pioneer", "combat")
check("결말 기록 후에도 보관소 그대로", archive.load() == before)
c = archive.counts()
check("집계", c["enemy"] == (6, 6) and c["scene"] == (1, 2) and c["fragment"] == (3, 3) and c["endings"][0] == 2)
check("파일에 남음", json.load(open(os.path.join(TMP, "archive.json"), encoding="utf-8"))["fragments"] == ["a01", "b01", "c01"])

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
