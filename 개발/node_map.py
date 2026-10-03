# node_map.py — 지점 지도 (NodeMap). 설계: docs/기획/지점지도_설계.md
# 시험 중: constants.NODE_MAP이 켜졌을 때만 쓴다 (2단계는 봇으로만, 그림 화면은 아직 칸 지도용).
#
# 5×5 칸 대신 시드로 만든 지점 약 50개를 길로 잇는다. 지점마다 정수 좌표를 그대로 키로 쓰므로
# player_pos·tile_data·danger·visited_tiles를 쓰는 코드는 칸 지도 때와 같이 돈다.
# 좌표: x 0~48 (서→동), y 0~34 (남→북). 출발지는 남쪽 가운데, 방벽(네오 아크)은 북쪽 끝.

import heapq
import math
import random

import constants
from i18n import t
from map import GameMap

TALL = {"lm_powerplant", "lm_amusement", "lm_airport", "lm_cathedral", "lm_bridge"}   # 안개 너머에서도 보이는 랜드마크
FAR_LANDMARKS = {"lm_powerplant", "lm_airport"}                                         # 방벽 아래 권역에만
LANDMARKS = ["lm_hospital", "lm_station", "lm_highway", "lm_amusement", "lm_school", "lm_mall", "lm_cathedral",
             "lm_subway", "lm_powerplant", "lm_apartments", "lm_bridge", "lm_airport"]
RUINS = ["junkyard", "scrap_sea", "crane", "ruin_city"]

_SPACING = 4.2      # 지점끼리 최소 거리
_UNIT = 3.0         # 이 거리마다 길 1턴
_MAX_DEG = 4
_BUNKER_TURNS = (8, 10)   # 출발지에서 방공호까지 최단 턴
_FORGE_TURNS = (2, 4)    # 강화하러 오가는 길이 길면 장비가 약한 채로 보스에 닿는다


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class NodeMap(GameMap):
    is_node_map = True

    def __init__(self, seed=None, count=None):
        super().__init__()
        self.count = count or constants.NODE_COUNT
        self.seed = seed if seed is not None else random.randrange(1, 2 ** 31)
        self._build(self.seed)
        self.player_pos = list(self.start_pos)
        self.visited_tiles = {self.start_pos}
        self.revealed = set()
        self.reveal(self.start_pos)
        self.bunker_hint = -1   # 마지막으로 보여 준 방공호 힌트 단계 (bunker_hint_check)

    # ── 생성 ────────────────────────────────────────────────────────────────
    def _build(self, seed):
        """시드 하나로 늘 같은 지도. 조건(연결·방공호 거리·강화소 자리)을 못 맞추면 시드에서 이어지는 다음 시도로."""
        for attempt in range(200):
            rng = random.Random(seed * 1000 + attempt)
            if self._try_build(rng):
                return
        raise RuntimeError(f"node map: seed {seed} failed")

    def _try_build(self, rng):
        scale = math.sqrt(self.count / 50)
        rx, ry = 24 * scale, 34 * scale
        start = (round(rx), 0)
        pts = [start]
        tries = 0
        while len(pts) < self.count and tries < 20000:
            tries += 1
            p = (round(rng.uniform(0, 2 * rx)), round(rng.uniform(0, ry)))
            if ((p[0] - start[0]) / rx) ** 2 + (p[1] / ry) ** 2 > 1:
                continue
            if all(_dist(p, q) >= _SPACING for q in pts):
                pts.append(p)
        if len(pts) < self.count:
            return False

        # 길: 가브리엘 그래프 (두 점을 지름으로 하는 원 안에 다른 점이 없으면 잇는다). 겹치지 않고 늘 이어져 있다
        adj = {p: {} for p in pts}
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                r2 = _dist(a, b) ** 2 / 4
                if all((c[0] - mid[0]) ** 2 + (c[1] - mid[1]) ** 2 >= r2 for c in pts if c is not a and c is not b):
                    turns = max(1, min(4, round(_dist(a, b) / _UNIT)))
                    adj[a][b] = adj[b][a] = turns
        # 갈림길이 너무 많은 지점은 긴 길부터 끊는다 (연결이 끊기지 않을 때만)
        for p in sorted(pts, key=lambda q: -len(adj[q])):
            for q in sorted(adj[p], key=lambda q: -_dist(p, q)):
                if len(adj[p]) <= _MAX_DEG:
                    break
                if len(adj[q]) <= 2:
                    continue
                n = adj[p].pop(q); adj[q].pop(p)
                if not self._connected(adj, start):
                    adj[p][q] = adj[q][p] = n

        def ring(p):
            r = math.hypot((p[0] - start[0]) / rx, p[1] / ry)
            return 0 if r < 0.35 else (1 if r < 0.7 else 2)

        from_start = self._dijkstra(adj, start)
        if len(from_start) < len(pts):
            return False
        bunkers = [p for p in pts if ring(p) >= 1 and _BUNKER_TURNS[0] <= from_start[p] <= _BUNKER_TURNS[1]]
        if not bunkers:
            return False
        bunker = rng.choice(bunkers)
        from_bunker = self._dijkstra(adj, bunker)
        forges = [p for p in pts if ring(p) == 1 and _FORGE_TURNS[0] <= from_start[p] <= _FORGE_TURNS[1]
                  and from_bunker[p] >= 2 and p != bunker]
        if not forges:
            return False
        forge = rng.choice(forges)

        # 지점 종류: 방벽에 가장 가까운 셋은 경계 지대, 랜드마크 12곳, 나머지는 이름 없는 폐허
        nodes = {start: {"kind": "start", "scene": "junkyard"}, bunker: {"kind": "bunker", "scene": None},
                 forge: {"kind": "ruin", "scene": "junkyard"}}
        free = [p for p in pts if p not in nodes]
        for p in sorted(free, key=lambda q: -q[1])[:3]:
            nodes[p] = {"kind": "border", "scene": "border_zone"}
        free = [p for p in free if p not in nodes]
        rng.shuffle(free)
        far = [p for p in free if ring(p) == 2]
        lms = list(LANDMARKS)
        rng.shuffle(lms)
        for lm in sorted(lms, key=lambda s: s not in FAR_LANDMARKS):
            pool = far if lm in FAR_LANDMARKS else [p for p in free if ring(p) >= 1 or rng.random() < 0.3]
            pool = [p for p in pool if p not in nodes]
            if not pool:
                return False
            nodes[pool[0]] = {"kind": "landmark", "scene": lm}
        for p in free:
            if p not in nodes:
                nodes[p] = {"kind": "ruin", "scene": rng.choice(RUINS)}
        for p, nd in nodes.items():
            nd["ring"] = 0 if p == start else ring(p)

        self.nodes, self.edges = nodes, adj
        self.start_pos, self.bunker_pos, self.forge_pos = start, list(bunker), list(forge)
        self.danger = {p: nd["ring"] for p, nd in nodes.items()}   # 위험도 = 권역 (설계 2-2)
        import scene_art
        scene_art.NODE_SCENES = {p: nd["scene"] for p, nd in nodes.items()}
        return True

    @staticmethod
    def _connected(adj, start):
        seen, stack = {start}, [start]
        while stack:
            for q in adj[stack.pop()]:
                if q not in seen:
                    seen.add(q); stack.append(q)
        return len(seen) == len(adj)

    @staticmethod
    def _dijkstra(adj, src):
        dist, pq = {src: 0}, [(0, src)]
        while pq:
            d, p = heapq.heappop(pq)
            if d > dist[p]:
                continue
            for q, w in adj[p].items():
                if d + w < dist.get(q, 1e9):
                    dist[q] = d + w
                    heapq.heappush(pq, (d + w, q))
        return dist

    # ── 길·안개 ─────────────────────────────────────────────────────────────
    def neighbors(self, pos=None):
        """[(지점, 길 턴 수)] 서쪽부터."""
        p = tuple(pos if pos is not None else self.player_pos)
        return sorted(self.edges[p].items())

    def road_keys(self, pos=None):
        """{키: 지점} — 이어진 길(최대 4개)마다 W(북)·D(동)·S(남)·A(서) 하나씩. 방향이 가장 잘 맞게 나눈다 (겹치지 않는다)."""
        import itertools
        p = tuple(pos if pos is not None else self.player_pos)
        roads = [q for q, _ in self.neighbors(p)]
        want = {"D": 0, "W": 90, "A": 180, "S": 270}

        def err(q, k):
            a = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) % 360
            d = abs(a - want[k]) % 360
            return min(d, 360 - d)
        best = min(itertools.permutations("WASD", len(roads)),
                   key=lambda ks: sum(err(q, k) ** 2 for q, k in zip(roads, ks)))
        return dict(zip(best, roads))

    def edge_len(self, a, b):
        return self.edges[tuple(a)][tuple(b)]

    def path_dist(self, a, b):
        return self._dijkstra(self.edges, tuple(a)).get(tuple(b), 99)

    def reveal(self, pos):
        """도착한 지점과 거기서 이어진 지점이 지도에 드러난다."""
        p = tuple(pos)
        self.revealed.add(p)
        self.revealed.update(self.edges[p])

    def arrive(self):
        self.reveal(self.player_pos)

    def sighted(self):
        """안개 너머에서도 보이는 곳 (아직 드러나지 않은 것): 높은 랜드마크와 방벽 아래 경계 지대 (방벽은 어디서나 보인다)."""
        return [p for p, nd in self.nodes.items()
                if (nd.get("scene") in TALL or nd["kind"] == "border") and p not in self.revealed]

    def kind_at(self, pos=None):
        return self.nodes[tuple(pos if pos is not None else self.player_pos)]["kind"]

    def scene_at(self, pos=None):
        return self.nodes[tuple(pos if pos is not None else self.player_pos)]["scene"]

    def forge_dist(self) -> int:
        return self.path_dist(self.player_pos, self.forge_pos)

    def _new_tile_data(self) -> dict:
        return {"remaining": random.randint(*constants.NODE_SEARCH), "cooldown_until": 0}

    def is_blocked(self, pos):
        return False

    # ── 방공호 힌트 ─────────────────────────────────────────────────────────
    def bunker_direction(self, fine):
        """지금 자리에서 방공호 쪽 방위. fine이 아니면 동서남북 넷 중 하나로만 (아주 대략적인 힌트)."""
        dx = self.bunker_pos[0] - self.player_pos[0]
        dy = self.bunker_pos[1] - self.player_pos[1]
        ang = math.degrees(math.atan2(dy, dx)) % 360
        if fine:
            keys = ["e", "ne", "n", "nw", "w", "sw", "s", "se"]
            return t(f"dir_{keys[int((ang + 22.5) // 45) % 8]}")
        keys = ["e", "n", "w", "s"]
        return t(f"dir_{keys[int((ang + 45) // 90) % 4]}")

    def bunker_hint_check(self):
        """방공호가 아직 안 드러났으면 거리 단계(멀리 / 중간 / 가까이)가 바뀔 때마다 한 번 힌트 문장. 보여 줄 문장 또는 None."""
        if tuple(self.bunker_pos) in self.revealed:
            return None
        d = self.path_dist(self.player_pos, self.bunker_pos)
        tier = 0 if d >= 7 else (1 if d >= 4 else 2)
        if tier <= self.bunker_hint:   # 더 가까워질 때만 (경계에 걸린 두 지점을 오가면 문장이 번갈아 나왔다: 시드 20075)
            return None
        self.bunker_hint = tier
        self.bunker_hint_dir = self.bunker_direction(fine=tier > 0)   # 지도 화면 머리말에 남긴다 (마지막으로 본 방위)
        return t(f"bunker_hint_{tier}", dir=self.bunker_hint_dir)

    # ── 직렬화 ──────────────────────────────────────────────────────────────
    def to_dict(self):
        d = super().to_dict()
        d.update(node_seed=self.seed, node_count=self.count, revealed=[list(p) for p in self.revealed],
                 bunker_hint=self.bunker_hint, bunker_hint_dir=getattr(self, "bunker_hint_dir", None))
        d.pop("layout", None)
        d.pop("danger", None)   # 시드로 다시 만든다
        return d

    def from_dict(self, data):
        if "node_seed" not in data:
            # 칸 지도 세이브 (v2.0.1): 지도만 새로 만들고 출발지에서 다시 시작 (설계 6). 강화소 진행도 처음부터
            return
        self.count = data.get("node_count", self.count)
        self.seed = data["node_seed"]
        self._build(self.seed)
        super().from_dict({k: v for k, v in data.items() if k not in ("danger", "forge_pos")})
        self.forge_pos = list(self.forge_pos)
        self.revealed = {tuple(p) for p in data.get("revealed", [])} or set()
        self.reveal(self.player_pos)
        self.bunker_hint = data.get("bunker_hint", -1)
        self.bunker_hint_dir = data.get("bunker_hint_dir")

    # ── 글 화면 ─────────────────────────────────────────────────────────────
    def draw(self, turn_count: int = 0):
        """시험용 글 화면: 지금 지점과 이어진 길만 (지도 그림은 3단계)."""
        print(f"  {t('node_here', name=self.label(), n=len(self.visited_tiles), total=len(self.nodes))}")
        for i, (q, n) in enumerate(self.neighbors(), 1):
            print(f"    {t('node_road', n=i, name=self.label(q), turns=n)}")

    def label(self, pos=None):
        p = tuple(pos if pos is not None else self.player_pos)
        nd = self.nodes[p]
        if p == tuple(self.bunker_pos):
            return t('node_kind_bunker')
        return nd["scene"] if nd["kind"] == "landmark" else t(f"node_kind_{nd['kind']}")
