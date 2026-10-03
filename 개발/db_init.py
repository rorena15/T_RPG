import json
import sqlite3
import os
from sys_log import sys_log
from i18n import text_path


def _load_text(name):
    with open(text_path(name), encoding="utf-8") as f:
        return json.load(f)


def init_database():
    db_path = "stigma_data.db"

    # 정적 참조 테이블(equipment/consumables)만 DROP 후 재생성한다.
    # 함수 호출 추적(예전 events 테이블)은 이제 개발자만 읽는 암호화 진단 기록(diag.py)에 쓴다.
    # 예전 평문 events 테이블은 diag.purge_plain_logs()가 지운다.
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS equipment")
    cursor.execute("DROP TABLE IF EXISTS consumables")

    # =========================================================
    # 1. 장비(Equipment) 테이블 생성
    # =========================================================
    # 컬럼 설명:
    #   item_id      : 고유 식별자 ({슬롯코드}_{등급코드}_{일련번호})
    #   name         : 장비 명칭
    #   power        : 기초 위력 ($P_{base}$, Project_Equipment_Matrix_Engine.md 기준)
    #   type         : 장비 대분류 (weapon / armor / accessory)
    #   tier         : 등급 지수 ($T$). 4=급조, 3=규격, 2=정제, 1=기업제, 0=유물
    #   slot         : 슬롯 키 (main_weapon, cyberdeck, cybernetic_parts, back_gear,
    #                  face, top, bottom, footwear, necklace, ring, custom_part)
    #   slot_weight  : 슬롯 가중치 ($W_{part}$). 1.5 / 1.2 / 1.0 / 0.5
    #   description  : 서사적 콘셉트 및 출력 로그 힌트 (장비/장신구), 유물의 경우 기반이 된
    #                  1등급 기업제 장비명을 "[기반: ...]" 형태로 함께 기록
    #   name / description / name_en / description_en : 글은 text/equipment.json에 (item_id로 합친다).
    #   아래 equipment_data에는 수치만 둔다: (item_id, power, type, tier, slot, slot_weight)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS equipment (
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            power INTEGER NOT NULL,
            type TEXT NOT NULL,
            tier INTEGER NOT NULL,
            slot TEXT NOT NULL,
            slot_weight REAL NOT NULL,
            description TEXT,
            name_en TEXT,
            description_en TEXT
        )
    ''')

    # docs/기획/장비 폴더의 5개 등급별 명세서(MD)에 기재된 전체 장비를 1:1로 통합한 데이터셋.
    #   - Project_Equipment_Expanded_Pool_Scrap.md     (4등급: 급조,   110종)
    #   - Project_Equipment_Expanded_Pool_Standard.md  (3등급: 규격,   110종)
    #   - Project_Equipment_Expanded_Pool_Refined.md   (2등급: 정제,   110종)
    #   - Project_Equipment_Expanded_Pool_Corporate.md (1등급: 기업제,  66종)
    #   - Project_Equipment_Expanded_Pool_Legacy.md    (0등급: 유물,    66종)
    #   => 총 462종 (기본 지급 무기 WEAPON_NONE 포함 463행)
    equipment_data = [
        # [기본 지급]
        ("WEAPON_NONE", 10, "weapon", 4, "main_weapon", 1.5),

        # ===== [4등급: 급조 (Scrap)] =====
        # --- 주무기 (main_weapon) ---
        ("WEAPON_SCRAP_01", 15, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_02", 18, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_03", 16, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_04", 22, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_05", 20, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_06", 17, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_07", 19, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_08", 15, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_09", 25, "weapon", 4, "main_weapon", 1.5),
        ("WEAPON_SCRAP_10", 16, "weapon", 4, "main_weapon", 1.5),
        # --- 사이버덱 (cyberdeck) ---
        ("DECK_SCRAP_01", 15, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_02", 14, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_03", 15, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_04", 16, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_05", 13, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_06", 17, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_07", 15, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_08", 14, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_09", 16, "weapon", 4, "cyberdeck", 1.5),
        ("DECK_SCRAP_10", 15, "weapon", 4, "cyberdeck", 1.5),
        # --- 의체부품 (cybernetic_parts) ---
        ("CYBER_SCRAP_01", 15, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_02", 16, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_03", 14, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_04", 18, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_05", 15, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_06", 14, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_07", 17, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_08", 13, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_09", 16, "armor", 4, "cybernetic_parts", 1.2),
        ("CYBER_SCRAP_10", 15, "armor", 4, "cybernetic_parts", 1.2),
        # --- 등장비 (back_gear) ---
        ("BACK_SCRAP_01", 12, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_02", 14, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_03", 13, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_04", 16, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_05", 15, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_06", 14, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_07", 17, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_08", 15, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_09", 12, "armor", 4, "back_gear", 1.2),
        ("BACK_SCRAP_10", 16, "armor", 4, "back_gear", 1.2),
        # --- 얼굴외장 (face) ---
        ("FACE_SCRAP_01", 13, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_02", 14, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_03", 15, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_04", 11, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_05", 16, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_06", 12, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_07", 15, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_08", 13, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_09", 12, "armor", 4, "face", 1.0),
        ("FACE_SCRAP_10", 14, "armor", 4, "face", 1.0),
        # --- 상의외장 (top) ---
        ("TOP_SCRAP_01", 14, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_02", 16, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_03", 13, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_04", 17, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_05", 14, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_06", 18, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_07", 15, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_08", 13, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_09", 16, "armor", 4, "top", 1.0),
        ("TOP_SCRAP_10", 14, "armor", 4, "top", 1.0),
        # --- 하의외장 (bottom) ---
        ("BOTTOM_SCRAP_01", 14, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_02", 15, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_03", 13, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_04", 16, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_05", 14, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_06", 13, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_07", 17, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_08", 15, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_09", 16, "armor", 4, "bottom", 1.0),
        ("BOTTOM_SCRAP_10", 12, "armor", 4, "bottom", 1.0),
        # --- 신발외장 (footwear) ---
        ("SHOES_SCRAP_01", 13, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_02", 15, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_03", 17, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_04", 14, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_05", 16, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_06", 12, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_07", 15, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_08", 14, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_09", 11, "armor", 4, "footwear", 1.0),
        ("SHOES_SCRAP_10", 16, "armor", 4, "footwear", 1.0),
        # --- 목걸이 (necklace) ---
        ("NECK_SCRAP_01", 10, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_02", 12, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_03", 14, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_04", 11, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_05", 13, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_06", 12, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_07", 15, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_08", 11, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_09", 14, "accessory", 4, "necklace", 0.5),
        ("NECK_SCRAP_10", 10, "accessory", 4, "necklace", 0.5),
        # --- 반지 (ring) ---
        ("RING_SCRAP_01", 10, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_02", 13, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_03", 12, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_04", 11, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_05", 14, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_06", 12, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_07", 15, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_08", 14, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_09", 11, "accessory", 4, "ring", 0.5),
        ("RING_SCRAP_10", 13, "accessory", 4, "ring", 0.5),
        # --- 특화부품 (custom_part) ---
        ("PART_SCRAP_01", 15, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_02", 16, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_03", 18, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_04", 15, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_05", 17, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_06", 14, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_07", 16, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_08", 19, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_09", 15, "accessory", 4, "custom_part", 0.5),
        ("PART_SCRAP_10", 17, "accessory", 4, "custom_part", 0.5),

        # ===== [3등급: 규격 (Standard)] =====
        # --- 주무기 (main_weapon) ---
        ("WEAPON_STD_01", 50, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_02", 45, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_03", 48, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_04", 58, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_05", 52, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_06", 56, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_07", 49, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_08", 62, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_09", 65, "weapon", 3, "main_weapon", 1.5),
        ("WEAPON_STD_10", 47, "weapon", 3, "main_weapon", 1.5),
        # --- 사이버덱 (cyberdeck) ---
        ("DECK_STD_01", 50, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_02", 46, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_03", 48, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_04", 52, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_05", 51, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_06", 45, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_07", 54, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_08", 55, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_09", 49, "weapon", 3, "cyberdeck", 1.5),
        ("DECK_STD_10", 53, "weapon", 3, "cyberdeck", 1.5),
        # --- 의체부품 (cybernetic_parts) ---
        ("CYBER_STD_01", 50, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_02", 48, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_03", 52, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_04", 55, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_05", 51, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_06", 49, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_07", 53, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_08", 54, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_09", 47, "armor", 3, "cybernetic_parts", 1.2),
        ("CYBER_STD_10", 46, "armor", 3, "cybernetic_parts", 1.2),
        # --- 등장비 (back_gear) ---
        ("BACK_STD_01", 45, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_02", 52, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_03", 48, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_04", 56, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_05", 50, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_06", 51, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_07", 53, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_08", 49, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_09", 54, "armor", 3, "back_gear", 1.2),
        ("BACK_STD_10", 47, "armor", 3, "back_gear", 1.2),
        # --- 얼굴외장 (face) ---
        ("FACE_STD_01", 48, "armor", 3, "face", 1.0),
        ("FACE_STD_02", 52, "armor", 3, "face", 1.0),
        ("FACE_STD_03", 55, "armor", 3, "face", 1.0),
        ("FACE_STD_04", 50, "armor", 3, "face", 1.0),
        ("FACE_STD_05", 47, "armor", 3, "face", 1.0),
        ("FACE_STD_06", 54, "armor", 3, "face", 1.0),
        ("FACE_STD_07", 46, "armor", 3, "face", 1.0),
        ("FACE_STD_08", 51, "armor", 3, "face", 1.0),
        ("FACE_STD_09", 53, "armor", 3, "face", 1.0),
        ("FACE_STD_10", 49, "armor", 3, "face", 1.0),
        # --- 상의외장 (top) ---
        ("TOP_STD_01", 52, "armor", 3, "top", 1.0),
        ("TOP_STD_02", 50, "armor", 3, "top", 1.0),
        ("TOP_STD_03", 56, "armor", 3, "top", 1.0),
        ("TOP_STD_04", 48, "armor", 3, "top", 1.0),
        ("TOP_STD_05", 51, "armor", 3, "top", 1.0),
        ("TOP_STD_06", 58, "armor", 3, "top", 1.0),
        ("TOP_STD_07", 53, "armor", 3, "top", 1.0),
        ("TOP_STD_08", 49, "armor", 3, "top", 1.0),
        ("TOP_STD_09", 54, "armor", 3, "top", 1.0),
        ("TOP_STD_10", 55, "armor", 3, "top", 1.0),
        # --- 하의외장 (bottom) ---
        ("BOTTOM_STD_01", 50, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_02", 53, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_03", 48, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_04", 56, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_05", 51, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_06", 49, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_07", 54, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_08", 55, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_09", 52, "armor", 3, "bottom", 1.0),
        ("BOTTOM_STD_10", 47, "armor", 3, "bottom", 1.0),
        # --- 신발외장 (footwear) ---
        ("SHOES_STD_01", 48, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_02", 53, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_03", 51, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_04", 52, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_05", 56, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_06", 47, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_07", 54, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_08", 50, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_09", 46, "armor", 3, "footwear", 1.0),
        ("SHOES_STD_10", 55, "armor", 3, "footwear", 1.0),
        # --- 목걸이 (necklace) ---
        ("NECK_STD_01", 45, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_02", 48, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_03", 51, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_04", 47, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_05", 49, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_06", 50, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_07", 53, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_08", 46, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_09", 52, "accessory", 3, "necklace", 0.5),
        ("NECK_STD_10", 44, "accessory", 3, "necklace", 0.5),
        # --- 반지 (ring) ---
        ("RING_STD_01", 45, "accessory", 3, "ring", 0.5),
        ("RING_STD_02", 50, "accessory", 3, "ring", 0.5),
        ("RING_STD_03", 47, "accessory", 3, "ring", 0.5),
        ("RING_STD_04", 48, "accessory", 3, "ring", 0.5),
        ("RING_STD_05", 52, "accessory", 3, "ring", 0.5),
        ("RING_STD_06", 46, "accessory", 3, "ring", 0.5),
        ("RING_STD_07", 51, "accessory", 3, "ring", 0.5),
        ("RING_STD_08", 53, "accessory", 3, "ring", 0.5),
        ("RING_STD_09", 49, "accessory", 3, "ring", 0.5),
        ("RING_STD_10", 48, "accessory", 3, "ring", 0.5),
        # --- 특화부품 (custom_part) ---
        ("PART_STD_01", 54, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_02", 50, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_03", 56, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_04", 52, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_05", 55, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_06", 48, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_07", 51, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_08", 58, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_09", 49, "accessory", 3, "custom_part", 0.5),
        ("PART_STD_10", 53, "accessory", 3, "custom_part", 0.5),

        # ===== [2등급: 정제 (Refined)] =====
        # --- 주무기 (main_weapon) ---
        ("WEAPON_REF_01", 95, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_02", 90, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_03", 98, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_04", 105, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_05", 102, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_06", 92, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_07", 94, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_08", 100, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_09", 115, "weapon", 2, "main_weapon", 1.5),
        ("WEAPON_REF_10", 88, "weapon", 2, "main_weapon", 1.5),
        # --- 사이버덱 (cyberdeck) ---
        ("DECK_REF_01", 95, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_02", 88, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_03", 92, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_04", 96, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_05", 94, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_06", 104, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_07", 90, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_08", 93, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_09", 100, "weapon", 2, "cyberdeck", 1.5),
        ("DECK_REF_10", 91, "weapon", 2, "cyberdeck", 1.5),
        # --- 의체부품 (cybernetic_parts) ---
        ("CYBER_REF_01", 95, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_02", 92, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_03", 96, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_04", 102, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_05", 94, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_06", 98, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_07", 90, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_08", 100, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_09", 93, "armor", 2, "cybernetic_parts", 1.2),
        ("CYBER_REF_10", 91, "armor", 2, "cybernetic_parts", 1.2),
        # --- 등장비 (back_gear) ---
        ("BACK_REF_01", 95, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_02", 92, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_03", 98, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_04", 104, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_05", 94, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_06", 96, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_07", 90, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_08", 100, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_09", 91, "armor", 2, "back_gear", 1.2),
        ("BACK_REF_10", 93, "armor", 2, "back_gear", 1.2),
        # --- 얼굴외장 (face) ---
        ("FACE_REF_01", 95, "armor", 2, "face", 1.0),
        ("FACE_REF_02", 92, "armor", 2, "face", 1.0),
        ("FACE_REF_03", 96, "armor", 2, "face", 1.0),
        ("FACE_REF_04", 101, "armor", 2, "face", 1.0),
        ("FACE_REF_05", 90, "armor", 2, "face", 1.0),
        ("FACE_REF_06", 94, "armor", 2, "face", 1.0),
        ("FACE_REF_07", 93, "armor", 2, "face", 1.0),
        ("FACE_REF_08", 97, "armor", 2, "face", 1.0),
        ("FACE_REF_09", 89, "armor", 2, "face", 1.0),
        ("FACE_REF_10", 91, "armor", 2, "face", 1.0),
        # --- 상의외장 (top) ---
        ("TOP_REF_01", 95, "armor", 2, "top", 1.0),
        ("TOP_REF_02", 92, "armor", 2, "top", 1.0),
        ("TOP_REF_03", 98, "armor", 2, "top", 1.0),
        ("TOP_REF_04", 103, "armor", 2, "top", 1.0),
        ("TOP_REF_05", 91, "armor", 2, "top", 1.0),
        ("TOP_REF_06", 94, "armor", 2, "top", 1.0),
        ("TOP_REF_07", 100, "armor", 2, "top", 1.0),
        ("TOP_REF_08", 89, "armor", 2, "top", 1.0),
        ("TOP_REF_09", 96, "armor", 2, "top", 1.0),
        ("TOP_REF_10", 93, "armor", 2, "top", 1.0),
        # --- 하의외장 (bottom) ---
        ("BOTTOM_REF_01", 95, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_02", 91, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_03", 99, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_04", 93, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_05", 94, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_06", 90, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_07", 96, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_08", 92, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_09", 95, "armor", 2, "bottom", 1.0),
        ("BOTTOM_REF_10", 88, "armor", 2, "bottom", 1.0),
        # --- 신발외장 (footwear) ---
        ("SHOES_REF_01", 95, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_02", 91, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_03", 97, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_04", 102, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_05", 93, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_06", 89, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_07", 94, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_08", 91, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_09", 96, "armor", 2, "footwear", 1.0),
        ("SHOES_REF_10", 90, "armor", 2, "footwear", 1.0),
        # --- 목걸이 (necklace) ---
        ("NECK_REF_01", 95, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_02", 90, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_03", 92, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_04", 96, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_05", 94, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_06", 101, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_07", 89, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_08", 93, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_09", 97, "accessory", 2, "necklace", 0.5),
        ("NECK_REF_10", 91, "accessory", 2, "necklace", 0.5),
        # --- 반지 (ring) ---
        ("RING_REF_01", 95, "accessory", 2, "ring", 0.5),
        ("RING_REF_02", 90, "accessory", 2, "ring", 0.5),
        ("RING_REF_03", 94, "accessory", 2, "ring", 0.5),
        ("RING_REF_04", 98, "accessory", 2, "ring", 0.5),
        ("RING_REF_05", 91, "accessory", 2, "ring", 0.5),
        ("RING_REF_06", 96, "accessory", 2, "ring", 0.5),
        ("RING_REF_07", 93, "accessory", 2, "ring", 0.5),
        ("RING_REF_08", 100, "accessory", 2, "ring", 0.5),
        ("RING_REF_09", 89, "accessory", 2, "ring", 0.5),
        ("RING_REF_10", 92, "accessory", 2, "ring", 0.5),
        # --- 특화부품 (custom_part) ---
        ("PART_REF_01", 102, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_02", 96, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_03", 98, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_04", 94, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_05", 105, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_06", 91, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_07", 100, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_08", 97, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_09", 93, "accessory", 2, "custom_part", 0.5),
        ("PART_REF_10", 99, "accessory", 2, "custom_part", 0.5),

        # ===== [1등급: 기업제 (Corporate)] =====
        # --- 주무기 (main_weapon) ---
        ("WEAPON_CORP_01", 180, "weapon", 1, "main_weapon", 1.5),
        ("WEAPON_CORP_02", 195, "weapon", 1, "main_weapon", 1.5),
        ("WEAPON_CORP_03", 185, "weapon", 1, "main_weapon", 1.5),
        ("WEAPON_CORP_04", 160, "weapon", 1, "main_weapon", 1.5),
        ("WEAPON_CORP_05", 155, "weapon", 1, "main_weapon", 1.5),
        ("WEAPON_CORP_06", 150, "weapon", 1, "main_weapon", 1.5),
        # --- 사이버덱 (cyberdeck) ---
        ("DECK_CORP_01", 160, "weapon", 1, "cyberdeck", 1.5),
        ("DECK_CORP_02", 175, "weapon", 1, "cyberdeck", 1.5),
        ("DECK_CORP_03", 155, "weapon", 1, "cyberdeck", 1.5),
        ("DECK_CORP_04", 165, "weapon", 1, "cyberdeck", 1.5),
        ("DECK_CORP_05", 150, "weapon", 1, "cyberdeck", 1.5),
        ("DECK_CORP_06", 170, "weapon", 1, "cyberdeck", 1.5),
        # --- 의체부품 (cybernetic_parts) ---
        ("CYBER_CORP_01", 160, "armor", 1, "cybernetic_parts", 1.2),
        ("CYBER_CORP_02", 170, "armor", 1, "cybernetic_parts", 1.2),
        ("CYBER_CORP_03", 165, "armor", 1, "cybernetic_parts", 1.2),
        ("CYBER_CORP_04", 150, "armor", 1, "cybernetic_parts", 1.2),
        ("CYBER_CORP_05", 155, "armor", 1, "cybernetic_parts", 1.2),
        ("CYBER_CORP_06", 145, "armor", 1, "cybernetic_parts", 1.2),
        # --- 등장비 (back_gear) ---
        ("BACK_CORP_01", 160, "armor", 1, "back_gear", 1.2),
        ("BACK_CORP_02", 150, "armor", 1, "back_gear", 1.2),
        ("BACK_CORP_03", 170, "armor", 1, "back_gear", 1.2),
        ("BACK_CORP_04", 155, "armor", 1, "back_gear", 1.2),
        ("BACK_CORP_05", 165, "armor", 1, "back_gear", 1.2),
        ("BACK_CORP_06", 145, "armor", 1, "back_gear", 1.2),
        # --- 얼굴외장 (face) ---
        ("FACE_CORP_01", 160, "armor", 1, "face", 1.0),
        ("FACE_CORP_02", 170, "armor", 1, "face", 1.0),
        ("FACE_CORP_03", 155, "armor", 1, "face", 1.0),
        ("FACE_CORP_04", 150, "armor", 1, "face", 1.0),
        ("FACE_CORP_05", 165, "armor", 1, "face", 1.0),
        ("FACE_CORP_06", 145, "armor", 1, "face", 1.0),
        # --- 상의외장 (top) ---
        ("TOP_CORP_01", 160, "armor", 1, "top", 1.0),
        ("TOP_CORP_02", 175, "armor", 1, "top", 1.0),
        ("TOP_CORP_03", 170, "armor", 1, "top", 1.0),
        ("TOP_CORP_04", 165, "armor", 1, "top", 1.0),
        ("TOP_CORP_05", 155, "armor", 1, "top", 1.0),
        ("TOP_CORP_06", 148, "armor", 1, "top", 1.0),
        # --- 하의외장 (bottom) ---
        ("BOTTOM_CORP_01", 160, "armor", 1, "bottom", 1.0),
        ("BOTTOM_CORP_02", 155, "armor", 1, "bottom", 1.0),
        ("BOTTOM_CORP_03", 170, "armor", 1, "bottom", 1.0),
        ("BOTTOM_CORP_04", 165, "armor", 1, "bottom", 1.0),
        ("BOTTOM_CORP_05", 148, "armor", 1, "bottom", 1.0),
        ("BOTTOM_CORP_06", 152, "armor", 1, "bottom", 1.0),
        # --- 신발외장 (footwear) ---
        ("SHOES_CORP_01", 160, "armor", 1, "footwear", 1.0),
        ("SHOES_CORP_02", 155, "armor", 1, "footwear", 1.0),
        ("SHOES_CORP_03", 170, "armor", 1, "footwear", 1.0),
        ("SHOES_CORP_04", 165, "armor", 1, "footwear", 1.0),
        ("SHOES_CORP_05", 150, "armor", 1, "footwear", 1.0),
        ("SHOES_CORP_06", 145, "armor", 1, "footwear", 1.0),
        # --- 목걸이 (necklace) ---
        ("NECK_CORP_01", 160, "accessory", 1, "necklace", 0.5),
        ("NECK_CORP_02", 170, "accessory", 1, "necklace", 0.5),
        ("NECK_CORP_03", 155, "accessory", 1, "necklace", 0.5),
        ("NECK_CORP_04", 165, "accessory", 1, "necklace", 0.5),
        ("NECK_CORP_05", 150, "accessory", 1, "necklace", 0.5),
        ("NECK_CORP_06", 145, "accessory", 1, "necklace", 0.5),
        # --- 반지 (ring) ---
        ("RING_CORP_01", 160, "accessory", 1, "ring", 0.5),
        ("RING_CORP_02", 170, "accessory", 1, "ring", 0.5),
        ("RING_CORP_03", 165, "accessory", 1, "ring", 0.5),
        ("RING_CORP_04", 155, "accessory", 1, "ring", 0.5),
        ("RING_CORP_05", 150, "accessory", 1, "ring", 0.5),
        ("RING_CORP_06", 145, "accessory", 1, "ring", 0.5),
        # --- 특화부품 (custom_part) ---
        ("PART_CORP_01", 165, "accessory", 1, "custom_part", 0.5),
        ("PART_CORP_02", 175, "accessory", 1, "custom_part", 0.5),
        ("PART_CORP_03", 170, "accessory", 1, "custom_part", 0.5),
        ("PART_CORP_04", 160, "accessory", 1, "custom_part", 0.5),
        ("PART_CORP_05", 155, "accessory", 1, "custom_part", 0.5),
        ("PART_CORP_06", 150, "accessory", 1, "custom_part", 0.5),

        # ===== [0등급: 유물 (Legacy)] =====
        # --- 주무기 (main_weapon) ---
        ("WEAPON_LEGACY_01", 320, "weapon", 0, "main_weapon", 1.5),
        ("WEAPON_LEGACY_02", 350, "weapon", 0, "main_weapon", 1.5),
        ("WEAPON_LEGACY_03", 335, "weapon", 0, "main_weapon", 1.5),
        ("WEAPON_LEGACY_04", 290, "weapon", 0, "main_weapon", 1.5),
        ("WEAPON_LEGACY_05", 300, "weapon", 0, "main_weapon", 1.5),
        ("WEAPON_LEGACY_06", 310, "weapon", 0, "main_weapon", 1.5),
        # --- 사이버덱 (cyberdeck) ---
        ("DECK_LEGACY_01", 320, "weapon", 0, "cyberdeck", 1.5),
        ("DECK_LEGACY_02", 350, "weapon", 0, "cyberdeck", 1.5),
        ("DECK_LEGACY_03", 305, "weapon", 0, "cyberdeck", 1.5),
        ("DECK_LEGACY_04", 315, "weapon", 0, "cyberdeck", 1.5),
        ("DECK_LEGACY_05", 295, "weapon", 0, "cyberdeck", 1.5),
        ("DECK_LEGACY_06", 340, "weapon", 0, "cyberdeck", 1.5),
        # --- 의체부품 (cybernetic_parts) ---
        ("CYBER_LEGACY_01", 320, "armor", 0, "cybernetic_parts", 1.2),
        ("CYBER_LEGACY_02", 330, "armor", 0, "cybernetic_parts", 1.2),
        ("CYBER_LEGACY_03", 315, "armor", 0, "cybernetic_parts", 1.2),
        ("CYBER_LEGACY_04", 290, "armor", 0, "cybernetic_parts", 1.2),
        ("CYBER_LEGACY_05", 305, "armor", 0, "cybernetic_parts", 1.2),
        ("CYBER_LEGACY_06", 310, "armor", 0, "cybernetic_parts", 1.2),
        # --- 등장비 (back_gear) ---
        ("BACK_LEGACY_01", 310, "armor", 0, "back_gear", 1.2),
        ("BACK_LEGACY_02", 295, "armor", 0, "back_gear", 1.2),
        ("BACK_LEGACY_03", 340, "armor", 0, "back_gear", 1.2),
        ("BACK_LEGACY_04", 325, "armor", 0, "back_gear", 1.2),
        ("BACK_LEGACY_05", 350, "armor", 0, "back_gear", 1.2),
        ("BACK_LEGACY_06", 300, "armor", 0, "back_gear", 1.2),
        # --- 얼굴외장 (face) ---
        ("FACE_LEGACY_01", 320, "armor", 0, "face", 1.0),
        ("FACE_LEGACY_02", 335, "armor", 0, "face", 1.0),
        ("FACE_LEGACY_03", 310, "armor", 0, "face", 1.0),
        ("FACE_LEGACY_04", 290, "armor", 0, "face", 1.0),
        ("FACE_LEGACY_05", 345, "armor", 0, "face", 1.0),
        ("FACE_LEGACY_06", 300, "armor", 0, "face", 1.0),
        # --- 상의외장 (top) ---
        ("TOP_LEGACY_01", 350, "armor", 0, "top", 1.0),
        ("TOP_LEGACY_02", 320, "armor", 0, "top", 1.0),
        ("TOP_LEGACY_03", 330, "armor", 0, "top", 1.0),
        ("TOP_LEGACY_04", 315, "armor", 0, "top", 1.0),
        ("TOP_LEGACY_05", 295, "armor", 0, "top", 1.0),
        ("TOP_LEGACY_06", 310, "armor", 0, "top", 1.0),
        # --- 하의외장 (bottom) ---
        ("BOTTOM_LEGACY_01", 320, "armor", 0, "bottom", 1.0),
        ("BOTTOM_LEGACY_02", 310, "armor", 0, "bottom", 1.0),
        ("BOTTOM_LEGACY_03", 340, "armor", 0, "bottom", 1.0),
        ("BOTTOM_LEGACY_04", 335, "armor", 0, "bottom", 1.0),
        ("BOTTOM_LEGACY_05", 285, "armor", 0, "bottom", 1.0),
        ("BOTTOM_LEGACY_06", 300, "armor", 0, "bottom", 1.0),
        # --- 신발외장 (footwear) ---
        ("SHOES_LEGACY_01", 320, "armor", 0, "footwear", 1.0),
        ("SHOES_LEGACY_02", 315, "armor", 0, "footwear", 1.0),
        ("SHOES_LEGACY_03", 345, "armor", 0, "footwear", 1.0),
        ("SHOES_LEGACY_04", 330, "armor", 0, "footwear", 1.0),
        ("SHOES_LEGACY_05", 290, "armor", 0, "footwear", 1.0),
        ("SHOES_LEGACY_06", 305, "armor", 0, "footwear", 1.0),
        # --- 목걸이 (necklace) ---
        ("NECK_LEGACY_01", 320, "accessory", 0, "necklace", 0.5),
        ("NECK_LEGACY_02", 335, "accessory", 0, "necklace", 0.5),
        ("NECK_LEGACY_03", 310, "accessory", 0, "necklace", 0.5),
        ("NECK_LEGACY_04", 290, "accessory", 0, "necklace", 0.5),
        ("NECK_LEGACY_05", 340, "accessory", 0, "necklace", 0.5),
        ("NECK_LEGACY_06", 300, "accessory", 0, "necklace", 0.5),
        # --- 반지 (ring) ---
        ("RING_LEGACY_01", 325, "accessory", 0, "ring", 0.5),
        ("RING_LEGACY_02", 350, "accessory", 0, "ring", 0.5),
        ("RING_LEGACY_03", 305, "accessory", 0, "ring", 0.5),
        ("RING_LEGACY_04", 315, "accessory", 0, "ring", 0.5),
        ("RING_LEGACY_05", 290, "accessory", 0, "ring", 0.5),
        ("RING_LEGACY_06", 310, "accessory", 0, "ring", 0.5),
        # --- 특화부품 (custom_part) ---
        ("PART_LEGACY_01", 320, "accessory", 0, "custom_part", 0.5),
        ("PART_LEGACY_02", 340, "accessory", 0, "custom_part", 0.5),
        ("PART_LEGACY_03", 335, "accessory", 0, "custom_part", 0.5),
        ("PART_LEGACY_04", 300, "accessory", 0, "custom_part", 0.5),
        ("PART_LEGACY_05", 310, "accessory", 0, "custom_part", 0.5),
        ("PART_LEGACY_06", 290, "accessory", 0, "custom_part", 0.5),
    ]

    text = _load_text("equipment.json")
    missing = [row[0] for row in equipment_data if row[0] not in text]
    if missing:
        raise KeyError(f"text/equipment.json에 없는 장비: {missing[:5]}")
    equipment_rows = [(row[0], text[row[0]]["name"]) + tuple(row[1:]) +
                      (text[row[0]]["description"], text[row[0]].get("name_en"), text[row[0]].get("description_en"))
                      for row in equipment_data]
    cursor.executemany('''
        INSERT INTO equipment (item_id, name, power, type, tier, slot, slot_weight, description, name_en, description_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', equipment_rows)

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
        ("MED_PER_10", "hp", 0.1, True, 0, 0),
        ("MED_PER_50", "hp", 0.5, True, 0, 0),
        ("MED_PER_100", "hp", 1.0, True, 0, 0),
        ("MED_FIX_100", "hp", 100, False, 0, 0),
        ("MED_FIX_300", "hp", 300, False, 0, 0),
        ("MED_FIX_500", "hp", 500, False, 0, 0),
        ("MED_FIX_1000", "hp", 1000, False, 0, 0),
        ("FOOD_ONLY", "food", 0, False, 30, 0),
        ("FOOD_BOTH", "food", 0, False, 40, 20),
        ("WATER_ONLY", "water", 0, False, 0, 30),
        ("WATER_BOTH", "water", 0, False, 20, 40)
    ]

    names = _load_text("story.json")["CONSUMABLES_DB"]   # 소모품 이름은 text/story.json 한 곳에
    cursor.executemany('''
        INSERT INTO consumables (item_id, name, type, val, is_percent, hunger, thirst)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', [(row[0], names[row[0]]["name"]) + tuple(row[1:]) for row in consumables_data])

    conn.commit()
    conn.close()
    sys_log("[SYSTEM] SQLite 데이터베이스 'stigma_data.db' 구축이 완료되었습니다.")
    sys_log(f"총 {len(equipment_data)}개의 장비와 {len(consumables_data)}개의 소모품이 인덱싱되었습니다.")
    return True
