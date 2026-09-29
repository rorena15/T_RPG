# map.py — GameMap 클래스
# 의존성: 없음 (순수 데이터 클래스)

import random
from i18n import t

_SEARCH_MIN = 2
_SEARCH_MAX = 4
_COOLDOWN_MIN = 8
_COOLDOWN_MAX = 14

class GameMap:
    def __init__(self):
        self.size = 5
        self.player_pos = [0, 0]
        self.bunker_pos = [4, 4]
        self.forge_pos = self._pick_forge_pos()   # 강화소 자리 (발칸 게이츠 퀘스트, forge.py). 처음엔 안 보임
        self.forge = {"stage": 0}                  # 0 못 만남 / 1 의뢰 중 / 2 완공
        self.visited_tiles: set = {(0, 0)}
        self.session_index = 0
        self.escaped_enemy_hp = None
        self.escaped_enemy_type = None
        self.tile_data: dict = {}          # {(x,y): {"remaining": int, "cooldown_until": int}}
        self.layout:   dict = {}          # {(x,y): str} — "blocked"|"wreck"|"checkpoint"|"market"|""
        self.landmark_visited: dict = {}  # {landmark_key: True}

    def _pick_forge_pos(self) -> list:
        """시작 칸·방공호에서 떨어진 가운데쯤 칸 하나 (시작에서 2~5칸, 방공호에서 2칸 이상)."""
        start, bunker = (0, 0), tuple(self.bunker_pos)
        cands = [[x, y] for x in range(self.size) for y in range(self.size)
                 if 2 <= x + y <= 5 and abs(x - bunker[0]) + abs(y - bunker[1]) >= 2 and (x, y) != start]
        return random.choice(cands)

    def forge_known(self) -> bool:
        return self.forge.get("stage", 0) >= 1 or bool(self.forge.get("met"))

    def at_forge(self) -> bool:
        return list(self.player_pos) == list(self.forge_pos)

    def forge_dist(self) -> int:
        return abs(self.forge_pos[0] - self.player_pos[0]) + abs(self.forge_pos[1] - self.player_pos[1])

    # ── 수색 시스템 ─────────────────────────────────────────────────────────

    def _new_tile_data(self) -> dict:
        return {"remaining": random.randint(_SEARCH_MIN, _SEARCH_MAX), "cooldown_until": 0}

    def _resolve_tile(self, pos: tuple, turn_count: int) -> dict:
        """pos 의 타일 데이터를 반환. 쿨타임 만료 시 자동 리셋."""
        if pos not in self.tile_data:
            self.tile_data[pos] = self._new_tile_data()
        td = self.tile_data[pos]
        if td["remaining"] == 0 and td["cooldown_until"] <= turn_count:
            self.tile_data[pos] = self._new_tile_data()
        return self.tile_data[pos]

    def can_search(self, turn_count: int) -> tuple:
        """(수색 가능 여부, 쿨타임 남은 턴 수) 반환."""
        pos = tuple(self.player_pos)
        if pos == tuple(self.bunker_pos):
            return False, 0
        if pos not in self.tile_data:
            return True, 0  # 첫 수색
        td = self.tile_data[pos]
        if td["remaining"] > 0:
            return True, 0
        left = max(0, td["cooldown_until"] - turn_count)
        if left == 0:
            return True, 0  # 쿨타임 만료 → 리셋 예정
        return False, left

    def use_search(self, turn_count: int):
        """현재 타일 수색 1회 소모. 소진 시 쿨타임 설정."""
        pos = tuple(self.player_pos)
        if pos == tuple(self.bunker_pos):
            return
        td = self._resolve_tile(pos, turn_count)
        if td["remaining"] > 0:
            td["remaining"] -= 1
            if td["remaining"] == 0:
                td["cooldown_until"] = turn_count + random.randint(_COOLDOWN_MIN, _COOLDOWN_MAX)

    def searches_left(self, turn_count: int) -> int:
        """현재 타일 남은 수색 횟수. 미초기화 타일은 -1(제한 없음), 쿨타임 중은 0."""
        pos = tuple(self.player_pos)
        if pos == tuple(self.bunker_pos) or pos not in self.tile_data:
            return -1
        td = self.tile_data[pos]
        if td["remaining"] > 0:
            return td["remaining"]
        left = max(0, td["cooldown_until"] - turn_count)
        return 0 if left > 0 else -1  # 쿨타임 만료 시 리셋 예정 → 제한 없음

    # ── 직렬화 ──────────────────────────────────────────────────────────────

    def is_blocked(self, pos: list) -> bool:
        return self.layout.get(tuple(pos), "") == "blocked"

    def tile_type_at(self, pos: list) -> str:
        return self.layout.get(tuple(pos), "open")

    def to_dict(self):
        return {
            "player_pos": self.player_pos,
            "forge_pos": self.forge_pos,
            "forge": self.forge,
            "visited_tiles": list(self.visited_tiles),
            "session_index": self.session_index,
            "escaped_enemy_hp": self.escaped_enemy_hp,
            "escaped_enemy_type": self.escaped_enemy_type,
            "tile_data": {f"{k[0]},{k[1]}": v for k, v in self.tile_data.items()},
            "layout": {f"{k[0]},{k[1]}": v for k, v in self.layout.items()},
            "landmark_visited": self.landmark_visited,
        }

    def from_dict(self, data):
        self.player_pos = data.get("player_pos", [0, 0])
        self.forge_pos = data.get("forge_pos", self.forge_pos)
        self.forge = data.get("forge", {"stage": 0})
        self.visited_tiles = {tuple(x) for x in data.get("visited_tiles", [(0, 0)])}
        self.session_index = data.get("session_index", 0)
        self.escaped_enemy_hp = data.get("escaped_enemy_hp", None)
        self.escaped_enemy_type = data.get("escaped_enemy_type", None)
        raw_td = data.get("tile_data", {})
        self.tile_data = {}
        for key_str, v in raw_td.items():
            x, y = map(int, key_str.split(","))
            self.tile_data[(x, y)] = v
        raw_lo = data.get("layout", {})
        self.layout = {}
        for key_str, v in raw_lo.items():
            x, y = map(int, key_str.split(","))
            self.layout[(x, y)] = v
        self.landmark_visited = data.get("landmark_visited", {})

    # ── 맵 렌더링 ────────────────────────────────────────────────────────────

    def draw(self, turn_count: int = 0):
        from colorama import Fore, Style
        size   = self.size
        border = "─" * (size * 5 + 2)
        RST    = Style.RESET_ALL

        print(Fore.CYAN + Style.BRIGHT + f"  {t('map_header')}" + RST)
        print(Fore.WHITE + f"  ┌{border}┐" + RST)
        for y in range(size - 1, -1, -1):
            row = "  │ "
            for x in range(size):
                if [x, y] == self.player_pos:
                    row += Fore.CYAN + Style.BRIGHT + "[ P ]" + RST
                elif [x, y] == self.bunker_pos:
                    row += Fore.YELLOW + Style.BRIGHT + "[ B ]" + RST
                elif [x, y] == self.forge_pos and self.forge_known():
                    built = self.forge.get("stage", 0) >= 2
                    row += (Fore.MAGENTA + Style.BRIGHT + "[ U ]" if built else Fore.MAGENTA + "[ u ]") + RST
                elif (x, y) in self.visited_tiles:
                    row += Fore.WHITE + Style.DIM + "[ ■ ]" + RST
                else:
                    row += Style.DIM + "[ · ]" + RST
            row += " │"
            print(row)
        print(Fore.WHITE + f"  └{border}┘" + RST)
        print(Style.DIM + f"  {t('map_legend')}" + RST)
