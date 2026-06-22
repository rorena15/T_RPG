# core.py — DB 로드, 장비 조회, 파일 경로, 저장/로드
# 의존성: constants, db_init, sys_log

import os
import sys
import json
import sqlite3
import time
import db_init
import constants
from sys_log import sys_log, track

_eq_cache: dict = {}  # get_equipment_data 조회 결과 캐시

def resource_path(relative_path):
    #PyInstaller로 패키징된 경우 임시 폴더 경로를, 그렇지 않으면 절대 경로를 반환합니다.
    try:
        # PyInstaller로 패키징되어 실행될 때 임시 폴더 경로
        base_path = sys._MEIPASS
    except Exception:
        # 일반 파이썬 스크립트로 실행될 때의 절대 경로
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_save_path():
    # EXE 모드: exe 파일 옆에 저장 (sys._MEIPASS 임시폴더 X)
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "stigma_save.json")
    return os.path.join(os.path.abspath("."), "stigma_save.json")


@track
def init_and_load_db():
    """게임 부팅 시 DB 및 master_formulas.json 무결성을 검증하고 메모리에 로드합니다."""
    # constants 모듈 속성을 직접 갱신 (global 불필요 — 모듈 분리 후 표준 패턴)
    
    # clear_screen()
    sys_log(" [SYSTEM BOOT] 마스터 공급원 및 메모리 무결성 검증 중...", level="INFO")
    time.sleep(0.4)
    
    # 1. master_formulas.json 로드 (SSOT 최우선 적용, 경로 검증 정정 완료)
    formula_real_path = resource_path("master_formulas.json")
    if os.path.exists(formula_real_path):
        try:
            with open(formula_real_path, "r", encoding="utf-8") as f:
                constants.MASTER_FORMULAS = json.load(f)
            sys_log(" [SYSTEM LOG] 단일 진실 공급원(master_formulas.json) 동기화 완료.", level="INFO")
        except Exception as e:
            sys_log(f" [SYSTEM WARN] 마스터 수식 로드 실패, 폴백 엔진 가동 ({e})", level="WARN")
    
    # 폴백 안전장치 (파일이 없거나 손상 시 기획서 정식 공식 기본 내장)
    if not constants.MASTER_FORMULAS:
        constants.MASTER_FORMULAS = {
            "formulas": {
                "reputation_multiplier": {"divisor": 2000.0},
                "max_level": {"base": 15, "growth": 0.93}
            }
        }

    # 2. SQLite DB 자동 생성 (Failsafe)
    if db_init.init_database():
        sys_log(" [SYSTEM LOG] 하드웨어 장비 연산 데이터베이스(SQLite) 구축 완료.", level="INFO")
    else:
        sys_log(" [SYSTEM LOG] 로컬 장비 데이터베이스 무결성 확인 완료.", level="INFO", show=False)
        
    # 3. JSON 서사/환경 데이터 로드 (이중 resource_path 제거 완료)
    json_file_path = resource_path("database.json")
    if not os.path.exists(json_file_path):
        sys_log(f" [SYSTEM FATAL] 서사 파일 '{json_file_path}' 누락. 엔트리를 시작할 수 없습니다.", level="FATAL")
        sys.exit()
        
    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            db_data = json.load(f)
            constants.AMBIENT_LORE   = db_data.get("AMBIENT_LORE", [])
            constants.CONSUMABLES_DB = db_data.get("CONSUMABLES_DB", {})
            constants.SESSIONS_DB    = db_data.get("SESSIONS_DB", [])
            constants.RANDOM_EVENTS  = db_data.get("RANDOM_EVENTS", [])
            constants.TRADER_ITEMS   = db_data.get("TRADER_ITEMS", [])
        sys_log(" [SYSTEM LOG] 서사 및 생체 소모품 데이터 구조화 파싱 완료.", level="INFO")
        time.sleep(0.6)
    except Exception as e:
        sys_log(f" [SYSTEM FATAL] JSON 데이터베이스 파싱 오류: {e}", level="FATAL")
        wait_for_keypress()
        sys.exit()

@track

def get_equipment_data(item_id):
    """장비 데이터는 세션 내 캐시 우선, 미등록 시 SQLite 쿼리."""
    if item_id in _eq_cache:
        return _eq_cache[item_id]
    db_path = "stigma_data.db"
    if not os.path.exists(db_path):
        result = {"name": "손상된 고철", "power": 5, "type": "kinetic", "tier": 4, "desc": "DB 파일 누락."}
        _eq_cache[item_id] = result
        return result

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, power, type, tier, slot, slot_weight, description FROM equipment WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        result = {"name": row[0], "power": row[1], "type": row[2], "tier": row[3],
                  "slot": row[4], "slot_weight": row[5], "desc": row[6]}
    else:
        result = {"name": "미식별 고철", "power": 5, "type": "kinetic", "tier": 4,
                  "slot": "main_weapon", "slot_weight": 1.5, "desc": "DB 미등록 부품."}
    _eq_cache[item_id] = result
    return result

# ====================================================================
# [2] 하드웨어 수준 입력 버퍼 및 키 입력 제어
# ====================================================================

def save_data(player, grid):
    save_file = {"player": player.to_dict(), "grid": grid.to_dict()}
    try:
        with open(get_save_path(), "w", encoding="utf-8") as f:
            json.dump(save_file, f, ensure_ascii=False, indent=4)
        print("\n[SYSTEM] 현재 동기화 로그가 로컬 환경에 안전하게 백업되었습니다.")
    except Exception as e:
        print(f"\n[SYSTEM ERR] 백업 실패: {e}")
        
    wait_for_keypress() # 메시지 확인 후 다음으로 넘어가도록 대기

# ====================================================================
# [5] 전투 시스템 (master_formulas.json 정합 수식 적용 및 UX 대기 제어)
# ====================================================================
# ====================================================================
# 진행 턴 기반 적 스케일링
# ====================================================================
# 난이도별 턴당 증가율. 적 hp/atk = base * (1 + turn_count * rate), 선형 상승.
# normal 기준 약 50턴 경과 시 +100%(2배), hard는 약 28턴, easy는 약 100턴.
DIFFICULTY_SCALING_RATE = {"easy": 0.01, "normal": 0.02, "hard": 0.035}

# 전투 시작 시점 플레이어 체력 비율이 이 값 미만이면, '위험 상태 완화'가 적용되어
# 그 전투에 한해 턴수 증가분의 절반만 반영한다. 장비가 좋아졌다고 적이 강해지는
# 역설계가 아니라, 순수하게 플레이어가 죽기 직전인 상황을 구제하는 안전핀이다.
LOW_HP_RELIEF_THRESHOLD = 0.3
LOW_HP_RELIEF_FACTOR = 0.5


