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
        self.visited_tiles: set = {(0, 0)}
        self.session_index = 0
        self.escaped_enemy_hp = None
        self.escaped_enemy_type = None
        self.tile_data: dict = {}  # {(x,y): {"remaining": int, "cooldown_until": int}}

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

    def to_dict(self):
        return {
            "player_pos": self.player_pos,
            "visited_tiles": list(self.visited_tiles),
            "session_index": self.session_index,
            "escaped_enemy_hp": self.escaped_enemy_hp,
            "escaped_enemy_type": self.escaped_enemy_type,
            "tile_data": {f"{k[0]},{k[1]}": v for k, v in self.tile_data.items()},
        }

    def from_dict(self, data):
        self.player_pos = data.get("player_pos", [0, 0])
        self.visited_tiles = {tuple(x) for x in data.get("visited_tiles", [(0, 0)])}
        self.session_index = data.get("session_index", 0)
        self.escaped_enemy_hp = data.get("escaped_enemy_hp", None)
        self.escaped_enemy_type = data.get("escaped_enemy_type", None)
        raw_td = data.get("tile_data", {})
        self.tile_data = {}
        for key_str, v in raw_td.items():
            x, y = map(int, key_str.split(","))
            self.tile_data[(x, y)] = v

    # ── 맵 렌더링 ────────────────────────────────────────────────────────────

    def draw(self, turn_count: int = 0):  # turn_count는 can_search 내부에서만 사용
        print(t('map_header'))
        for y in range(self.size - 1, -1, -1):
            row_str = "    "
            for x in range(self.size):
                pos = (x, y)
                if [x, y] == self.player_pos:
                    row_str += "[ P ] "
                elif [x, y] == self.bunker_pos:
                    row_str += "[ B ] "
                else:
                    row_str += "[ . ] "
            print(row_str)
        print(t('map_legend'))
