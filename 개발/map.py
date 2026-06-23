# map.py — GameMap 클래스
# 의존성: 없음 (순수 데이터 클래스)

class GameMap:
    def __init__(self):
        self.size = 5
        self.player_pos = [0, 0]
        self.bunker_pos = [4, 4]
        self.visited_tiles: set = {(0, 0)}
        self.session_index = 0
        self.escaped_enemy_hp = None
        self.escaped_enemy_type = None

    def to_dict(self):
        return {
            "player_pos": self.player_pos, "visited_tiles": list(self.visited_tiles),
            "session_index": self.session_index, "escaped_enemy_hp": self.escaped_enemy_hp,
            "escaped_enemy_type": self.escaped_enemy_type,
        }

    def from_dict(self, data):
        self.player_pos = data.get("player_pos", [0, 0])
        self.visited_tiles = {tuple(x) for x in data.get("visited_tiles", [(0, 0)])}
        self.session_index = data.get("session_index", 0)
        self.escaped_enemy_hp = data.get("escaped_enemy_hp", None)
        self.escaped_enemy_type = data.get("escaped_enemy_type", None)

    def draw(self):
        print(" [ 데드존 섹터 그리드 스캐너 ]")
        for y in range(self.size - 1, -1, -1):
            row_str = "    "
            for x in range(self.size):
                if [x, y] == self.player_pos:
                    row_str += "[ P ] "
                elif [x, y] == self.bunker_pos:
                    row_str += "[ B ] "
                else:
                    row_str += "[ . ] "
            print(row_str)
        print("  (P: 현재 위치 | B: 방공호 목표 |)\n")

