import sqlite3
import os
from sys_log import sys_log 


def init_database():
    db_path = "stigma_data.db"
    
    # 이미 존재하면 삭제하고 새로 생성 (초기화용)
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # =========================================================
    # 1. 장비(Equipment) 테이블 생성
    # =========================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS equipment (
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            power INTEGER NOT NULL,
            type TEXT NOT NULL,
            tier INTEGER NOT NULL,
            description TEXT
        )
    ''')

    # 마크다운 5개 티어 기반 통합 데이터셋
    equipment_data = [
        # [기본]
        ("WEAPON_NONE", "맨손", 10, "kinetic", 4, "[T=4 급조] 기본 제공되는 생체 타격 수단."),
        
        # [4등급: 급조 - Scrap]
        ("WEAPON_SCRAP_01", "녹슨 고철 칼날", 15, "kinetic", 4, "[T=4 급조] 폐차 스프링을 갈아 만든 날붙이. 쳇소리가 울린다."),
        ("WEAPON_SCRAP_02", "폐기된 리벳 건", 18, "kinetic", 4, "[T=4 급조] 공사장에서 주운 가스식 리벳 건. 거친 마찰음과 함께 철심 발사."),
        ("WEAPON_SCRAP_03", "방전식 스패너", 16, "scrap", 4, "[T=4 급조] 대형 스패너에 구형 배터리를 감아 타격 시 스파크가 튄다."),
        ("WEAPON_SCRAP_04", "오염된 화염 파이프", 22, "kinetic", 4, "[T=4 급조] 배관에 가솔린을 직결하여 불을 뿜는 리스크 높은 화포."),
        ("WEAPON_SCRAP_05", "철근 콘크리트 둔기", 20, "kinetic", 4, "[T=4 급조] 무너진 건물 잔해에서 뜯어낸 무식한 질량의 둔기."),
        ("PART_SCRAP_01", "조잡한 전류 바이패스", 15, "cyber", 4, "[T=4 급조] 오버클럭 1턴 증가 / [페널티] 매 턴 생명력 100 감소."),
        ("PART_SCRAP_02", "녹슨 납땜 방열판", 16, "scrap", 4, "[T=4 급조] 스킬 위력 +2% / [페널티] 해킹 성공 시 방화벽(Alert) +3."),
        ("PART_SCRAP_03", "구형 방전 캐패시터", 18, "kinetic", 4, "[T=4 급조] 치명타 상시 +3% / [페널티] 우선권 지수(INIT) -5 감산."),
        ("PART_SCRAP_04", "리사이클 저항 코일", 15, "cyber", 4, "[T=4 급조] RAM 회복 딜레이 1턴 단축 / [페널티] 최대 RAM -1 잠금."),
        ("PART_SCRAP_05", "무선 안테나 리시버 팁", 17, "scrap", 4, "[T=4 급조] 유령 데이터 탐지율 +0.5% / [페널티] 기습 조우율 1.5배."),
        ("PART_SCRAP_06", "윤활유 수동 주입 펌프", 14, "scrap", 4, "[T=4 급조] 관절부 마찰을 줄여주는 윤활유 펌프."),
        ("ACCESSORY_SCRAP_01", "기계 괴수 냉각선 목걸이", 15, "scrap", 4, "[T=4 급조] 방사능 저항 장신구."),
        ("ARMOR_SCRAP_01", "컴퓨터 본체 장갑", 16, "kinetic", 4, "[T=4 급조] 스캐브 드론의 장갑판을 찢어발겨 몸에 두른 방어 자산."),
        ("ARMOR_SCRAP_02", "와이어 결속 슬링 백팩", 13, "scrap", 4, "[T=4 급조] 가시철사로 엮어 방어력을 확보한 배낭."),
        ("DECK_SCRAP_01", "구형 신호 수신기", 15, "cyber", 4, "[T=4 급조] 맵 데이터를 흡수하는 구형 사이버덱 파츠."),

        # [3등급: 규격 - Standard]
        ("WEAPON_STD_01", "스크랩 연합 제식 소총", 50, "kinetic", 3, "[T=3 규격] 7.62mm 탄환을 안정적으로 격발하는 저항군의 주력 화기."),
        ("WEAPON_STD_02", "초진동 고철 단검", 45, "kinetic", 3, "[T=3 규격] 고속 진동을 일으켜 기계의 표면 장갑을 분초 단위로 파쇄."),
        ("PART_STD_01", "레일 마그네틱 클록 충전기", 56, "cyber", 3, "[T=3 규격] 치명타 +5% / [페널티] 물리 방어력 베이스 강제 -8 차감."),
        ("PART_STD_02", "동합금 정밀 저항 링 코일", 52, "cyber", 3, "[T=3 규격] 10% 확률 소모 RAM 1 환급 / [페널티] 전투 중 최대 RAM -1 잠금."),
        ("PART_STD_03", "광학 스캔 주파수 수신 팁", 55, "scrap", 3, "[T=3 규격] 탐지 성공률 +1.0% / [페널티] 이동 시 기계 괴수 레이드 확률 1.2배."),
        ("PART_STD_04", "유압식 윤활 공급 인젝터", 48, "kinetic", 3, "[T=3 규격] 바이오 적출 발동 확률 +4% / [페널티] 무게 한도 영구 -5kg."),
        ("PART_STD_05", "우회 프록시 암호화 래퍼", 51, "cyber", 3, "[T=3 규격] 로그 위조 성공률 +4% / [페널티] 실패 시 연산 오염 스택 폭발."),

        # [2등급: 정제 - Refined]
        ("WEAPON_REF_01", "바이오 코어 리퍼 나이프", 95, "kinetic", 2, "[T=2 정제] 기계와 육체를 동시에 찢어발기는 화기."),
        ("WEAPON_REF_02", "주파수 파쇄 스패너", 90, "scrap", 2, "[T=2 정제] 적의 내부 주파수를 오염시켜 논리 회로를 직접 과부하 폭발."),
        ("PART_REF_01", "리퍼닥 그리드 동기화 칩", 94, "cyber", 2, "[T=2 정제] 생존 수치 흡수량 +10 고정 / [페널티] 인벤토리 무게 -5kg 감산."),
        ("PART_REF_02", "그리드 헌터 역설계 노즐", 105, "kinetic", 2, "[T=2 정제] 대미지 배율 +10% 증폭 / [페널티] 10회 초과 시 노출 페널티 8%로 가속."),
        ("PART_REF_03", "보이드 인젝터 기초 펌프", 91, "cyber", 2, "[T=2 정제] 위조 상한선 75%까지 동적 확장 / [페널티] 실패 시 뇌 손상 200% 증가."),
        ("PART_REF_04", "타이탄 크러셔 분쇄 모듈", 100, "scrap", 2, "[T=2 정제] 타격 시 적 방어력 15% 영구 삭감 / [페널티] 내 행동 턴 우선권 -10 차감."),

        # [1등급: 기업제 - Corporate]
        ("WEAPON_CORP_01", "아라사카 나노 레이저 카타나", 180, "kinetic", 1, "[T=1 기업제] 물리 장벽과 의체를 분자 단위로 매끄럽게 가르는 종결 도검."),
        ("PART_CORP_01", "보이드 인젝터 모듈 (v1.2)", 165, "cyber", 1, "[T=1 기업제] 위조 성공률 85%까지 확장 / [페널티] 가용 RAM 1개 영구 잠금 및 방화벽 +20."),
        ("PART_CORP_02", "아라사카 나노 클록 가속 칩", 175, "kinetic", 1, "[T=1 기업제] 오버클럭 중 우선권 상시 2배 고정 / [페널티] 전투 중 오염 저항력 0% 마비."),
        ("PART_CORP_03", "밀리테크 관통 전술 배선 패치", 170, "scrap", 1, "[T=1 기업제] 적 유효 방어력을 영구히 50% 삭감 / [페널티] 내 생명력 베이스 강제 -500 차감."),
        ("PART_CORP_04", "네오넷 광역 바이러스 마스터 팩", 160, "cyber", 1, "[T=1 기업제] 유포 시 필드 내 모든 기계 괴수의 연산력을 동시 정지시킨다."),

        # [0등급: 유물 - Legacy]
        ("WEAPON_LEGACY_01", "아라사카 신격 나노 레이저 카타나", 350, "kinetic", 0, "[T=0 유물] 기업제 카타나를 진영 코드로 융합 연성한 궁극의 무기."),
        ("PART_LEGACY_01", "아라사카 크로노스 클록 칩 v맥스", 340, "kinetic", 0, "[T=0 유물] 오버클럭 중 행동 턴 우선권을 2배 강제 고정 증폭 / [페널티] 오염 저항력 0% 록업."),
        ("PART_LEGACY_02", "밀리테크 프레임 파쇄 마스터 패치", 335, "scrap", 0, "[T=0 유물] 대미지 가중치 폭화. 적 유효 방어력 무조건 50% 삭감 / [페널티] 내 생명력 -500 차감 고정."),
        ("PART_LEGACY_03", "네오넷 그리드 전멸 바이러스 패키지", 300, "cyber", 0, "[T=0 유물] 유포 시 필드 내 모든 기계 괴수의 연산력을 영구 정지시키고 장갑을 붕괴시킨다.")
    ]

    cursor.executemany('''
        INSERT INTO equipment (item_id, name, power, type, tier, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', equipment_data)

    # =========================================================
    # 2. 소모품(Consumables) 테이블 생성
    # =========================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consumables (
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            val REAL,
            is_percent BOOLEAN,
            hunger INTEGER,
            thirst INTEGER
        )
    ''')

    consumables_data = [
        ("MED_PER_10", "소형 반창고 팩", "hp", 0.1, True, 0, 0),
        ("MED_PER_50", "응급 지혈대", "hp", 0.5, True, 0, 0),
        ("MED_PER_100", "나노 스팀팩", "hp", 1.0, True, 0, 0),
        ("MED_FIX_100", "구형 진통제", "hp", 100, False, 0, 0),
        ("MED_FIX_300", "군용 지혈제", "hp", 300, False, 0, 0),
        ("MED_FIX_500", "합성 바이오 젤", "hp", 500, False, 0, 0),
        ("MED_FIX_1000", "초고밀도 회복 앰플", "hp", 1000, False, 0, 0),
        ("FOOD_ONLY", "건조 단백질 블록", "food", 0, False, 30, 0),
        ("FOOD_BOTH", "수분 함유 전투식량", "food", 0, False, 40, 20),
        ("WATER_ONLY", "탁한 정수 팩", "water", 0, False, 0, 30),
        ("WATER_BOTH", "미네랄 보충수", "water", 0, False, 20, 40)
    ]

    cursor.executemany('''
        INSERT INTO consumables (item_id, name, type, val, is_percent, hunger, thirst)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', consumables_data)

    conn.commit()
    conn.close()
    sys_log("[SYSTEM] SQLite 데이터베이스 'stigma_data.db' 구축이 완료되었습니다.")
    sys_log(f"총 {len(equipment_data)}개의 장비와 {len(consumables_data)}개의 소모품이 인덱싱되었습니다.")