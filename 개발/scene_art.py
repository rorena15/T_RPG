"""이벤트 화면 왼쪽 장면 그림 고르기 (assets/scenes/<장면>/<장면>_<시간>_<날씨>_<n>.jpg + 깊이 층 .mid/.near.webp).

그림은 art_gen/gen_scenes.py로 만든다. 이 모듈은 상황에 맞는 한 장을 고른다:
  1. 이벤트 전용 그림 (포탑 이벤트면 포탑)
  2. 이벤트 문장·행동에 나온 말과 맞는 그림 ("병원" -> 무너진 병원, "들개" -> 들개 무리)
  3. 지금 장소의 지형·랜드마크
  4. 원경 (네오 아크)
같은 후보 안에서는 게임 속 시간·날씨와 맞는 그림, 아직 안 본 그림을 먼저 고른다. 최근에 본 그림은 피한다.
적 그림은 위협이 나올 때만, 실내 그림은 실내이거나 들어가는 행동일 때만 쓴다.
한 이벤트 안에서는 그림을 바꾸지 않는다 (고르는 건 화면을 열 때 한 번).

게임 속 시간과 날씨는 턴 수로 정한다 (세이브를 바꾸지 않아도 불러온 뒤 같은 하늘이 이어진다):
  시간: SLOT_TURNS 턴마다 새벽 -> 아침 -> 한낮 -> 저녁 -> 밤
  날씨: WEATHER_TURNS 턴 구간마다 하나 (가중 무작위, 구간 번호로 시드) -> 한동안 유지되다 바뀐다
"""
import os
import random
import re
import sys
from collections import deque

TIMES = ["dawn", "morning", "noon", "evening", "night"]
SLOT_TURNS = 6
WEATHER_TURNS = 9
WEATHER_WEIGHTS = [("smog", 40), ("fog", 20), ("dust", 15), ("ash", 15), ("acid", 10)]

TERRAIN = ["junkyard", "scrap_sea", "crane", "ruin_city", "border_zone"]
LANDMARKS = ["lm_hospital", "lm_station", "lm_highway", "lm_amusement", "lm_school", "lm_mall", "lm_cathedral",
             "lm_subway", "lm_powerplant", "lm_apartments", "lm_bridge", "lm_airport"]
VISTA = ["neo_city"]
ENEMIES = ["enemy_drones", "enemy_dogs", "enemy_hound", "enemy_collector", "enemy_security"]
INTERIORS = ["bunker_inside", "bunker_stairs", "ruin_factory", "ruin_server", "forge", "lm_mall", "fig_hacker"]
LOCATION_POOL = {
    "폐기물 처리장": TERRAIN + LANDMARKS,
    "구시대 지하 방공호": ["bunker", "bunker_inside", "bunker_stairs"],
}

# 장면 -> 이 말이 나오면 그 장면을 우선한다
KEYWORDS = {
    "lm_hospital": ["병원", "구급", "의료"], "lm_station": ["기차", "열차", "선로", "역사"],
    "lm_highway": ["고가", "고속도로", "도로"], "lm_amusement": ["관람차", "놀이공원", "유원지"],
    "lm_school": ["학교", "교실", "운동장"], "lm_mall": ["쇼핑", "상가", "에스컬레이터"],
    "lm_cathedral": ["성당", "첨탑", "교회"], "lm_subway": ["지하철"], "lm_powerplant": ["발전소", "냉각탑"],
    "lm_apartments": ["아파트", "주거"], "lm_bridge": ["교각", "현수교", "끊어진 다리"], "lm_airport": ["공항", "활주로", "관제탑"],
    "crane": ["크레인"], "ruin_city": ["빌딩", "고층", "도시 폐허"], "scrap_sea": ["쓰레기 바다", "고철 산"],
    "bunker_stairs": ["계단"], "bunker_inside": ["침상", "방공호 안"], "ruin_factory": ["공장", "컨베이어"],
    "ruin_server": ["서버", "랙"], "forge": ["대장간", "용광로"], "barricade": ["방벽", "바리케이드"],
    "neo_city": ["네오 아크", "도시 불빛", "방벽 너머"],
    "enemy_drones": ["드론 편대", "경비 드론", "드론 떼"], "enemy_dogs": ["들개"], "enemy_hound": ["하운드", "괴수"],
    "enemy_collector": ["컬렉터", "청소기계"], "enemy_security": ["보안 부대", "진압대"],
    "fig_scavengers": ["스캐벤저 무리", "모닥불 곁"], "fig_trader": ["중개상", "상인"],
}
# 짧은 말은 다른 낱말에 걸린다 ("비" -> 비상, "재가" -> 재가동) -> 붙여 쓰는 꼴로 찾는다
WEATHER_WORDS = {"acid": ["비가", "비를", "빗줄기", "빗물", "빗방울", "산성비"], "fog": ["안개"],
                 "dust": ["황사", "모래바람", "먼지 폭풍"], "ash": ["재가 내", "재가 흩", "잿가루"]}
THREAT_WORDS = ["위협", "습격", "공격", "사냥", "으르렁", "추격", "매복", "달려든"]
INDOOR_WORDS = ["안으로", "들어간", "내부", "실내"]

NAME_RE = re.compile(r"^(?P<scene>.+)_(?P<time>dawn|morning|noon|evening|night|dim|cold)_(?P<weather>[a-z]+)_\d+\.jpg$")
RECENT = deque(maxlen=6)   # 최근에 보여 준 그림 (같은 그림 반복 방지)
SEEN = set()               # 이번 실행에서 본 그림
_index = None


def root():
    base = getattr(sys, "_MEIPASS", None)
    return os.path.join(base, "assets", "scenes") if base else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "scenes")


def index():
    """{장면: [(파일 경로, 시간, 날씨)]}. 파일 이름에서 태그를 읽는다."""
    global _index
    if _index is None:
        _index = {}
        r = root()
        if os.path.isdir(r):
            for scene in os.listdir(r):
                folder = os.path.join(r, scene)
                if not os.path.isdir(folder):
                    continue
                for f in sorted(os.listdir(folder)):
                    m = NAME_RE.match(f)
                    if m:
                        _index.setdefault(scene, []).append((os.path.join(folder, f), m["time"], m["weather"]))
    return _index


def world_time(turn):
    return TIMES[(turn // SLOT_TURNS + 1) % len(TIMES)]  # 첫 턴은 아침


def world_weather(turn):
    rng = random.Random(turn // WEATHER_TURNS * 7919 + 13)
    total = sum(w for _, w in WEATHER_WEIGHTS)
    x = rng.uniform(0, total)
    for name, w in WEATHER_WEIGHTS:
        x -= w
        if x <= 0:
            return name
    return "smog"


def _matches(text, words):
    return any(w in text for w in words)


def choose(location, motif=None, text="", turn=0, search=False, stable=None):
    """상황에 맞는 그림 파일 경로 하나. 그림이 하나도 없으면 None (게임은 코드로 그린 장면을 쓴다).
    stable: 맵 칸처럼 같은 조건이면 늘 같은 그림이어야 할 때의 키 (최근 그림 피하기를 쓰지 않는다)."""
    idx = index()
    if not idx:
        return None
    threat = _matches(text, THREAT_WORDS)
    indoor = location == "구시대 지하 방공호" or _matches(text, INDOOR_WORDS)

    def allowed(scene):
        if scene in ENEMIES and not threat:
            return False
        if scene in INTERIORS and not indoor:
            return False
        return scene in idx

    tiers = []
    if motif and motif in idx:
        tiers.append([motif])
    tiers.append([s for s, words in KEYWORDS.items() if _matches(text, words) and allowed(s)])
    pool = [s for s in LOCATION_POOL.get(location, TERRAIN) if allowed(s)]
    tiers.append(pool)
    tiers.append([s for s in VISTA if allowed(s)])
    scenes = next((t for t in tiers if t), None)
    if not scenes:
        return None

    now_t, now_w = world_time(turn), world_weather(turn)
    for w, words in WEATHER_WORDS.items():  # 글에 날씨가 나오면 그게 우선
        if _matches(text, words):
            now_w = w
    ti = TIMES.index(now_t)
    best, best_score = [], None
    for scene in scenes:
        for path, t, w in idx[scene]:
            score = 0.0
            if t in TIMES:
                gap = min(abs(TIMES.index(t) - ti), len(TIMES) - abs(TIMES.index(t) - ti))
                score += {0: 3, 1: 1}.get(gap, 0)
            score += 2 if w == now_w else 0
            score += 2 if (path not in SEEN and stable is None) else 0
            if search and scene in LANDMARKS and not any(p.startswith(os.path.join(root(), scene)) for p in SEEN):
                score += 3  # 빈 탐색은 아직 못 본 랜드마크로 세계를 넓힌다
            if path in RECENT and stable is None:
                score -= 10
            if best_score is None or score > best_score + 1e-9:
                best, best_score = [path], score
            elif abs(score - best_score) < 1e-9:
                best.append(path)
    if stable is not None:
        return random.Random(str(stable)).choice(sorted(best))
    pick = random.choice(best)
    RECENT.append(pick)
    SEEN.add(pick)
    return pick


def tile_scene(location, pos):
    """맵 칸마다 정해진 장면 (같은 칸에 돌아오면 같은 곳). 그림이 있는 장면 중에서 고른다."""
    idx = index()
    pool = [s for s in LOCATION_POOL.get(location, TERRAIN) if s in idx and s not in INTERIORS] or \
        [s for s in LOCATION_POOL.get(location, TERRAIN) if s in idx]
    if not pool:
        return None
    return pool[(pos[0] * 7 + pos[1] * 13 + 3) % len(pool)]


def layers(path):
    """깊이 층 파일 (중간, 가까운). 없으면 None."""
    mid, near = path[:-4] + ".mid.webp", path[:-4] + ".near.webp"
    return (mid if os.path.exists(mid) else None), (near if os.path.exists(near) else None)
