# quest.py — 퀘스트, 랜덤이벤트, 상인 시스템
# 의존성: constants, core, ui, sys_log

import random
import time
import constants
from core import get_equipment_data
from ui import (clear_screen, print_header, print_divider, type_text,
                wait_for_keypress, safe_input, read_key, log_diary)
from sys_log import sys_log, log_error

def trigger_sudden_quest(player):
    """12% 확률로 돌발 퀘스트 발생. 기존 활성 퀘스트가 있으면 무시."""
    if player.active_quest is not None or not constants.SUDDEN_QUESTS:
        return
    if random.random() > 0.12:
        return
    tpl = random.choice(constants.SUDDEN_QUESTS)
    deadline = player.turn_count + tpl["turns"]
    q: dict = {
        "id":          tpl["id"],
        "title":       tpl["title"],
        "type":        tpl["type"],
        "target":      tpl["target"],
        "progress":    0,
        "deadline":    deadline,
        "reward_type": tpl["reward_type"],
        "reward_desc": tpl["reward_desc"],
    }
    if "reward_id"     in tpl: q["reward_id"]     = tpl["reward_id"]
    if "reward_amount" in tpl: q["reward_amount"] = tpl["reward_amount"]
    player.active_quest = q
    clear_screen()
    print_header(f"!! 돌발 퀘스트 — {tpl['title']}")
    type_text(f"  {tpl['desc']}", 0.022)
    print()
    print(f"  [목표]  {tpl['detail']}")
    print(f"  [기한]  {tpl['turns']}턴 이내  (현재 {player.turn_count}턴 → 기한 {deadline}턴)")
    print(f"  [보상]  {tpl['reward_desc']}")
    print()
    log_diary(player, f"[퀘스트] {tpl['title']} 발생 (기한: {deadline}턴)")
    wait_for_keypress()


def _complete_quest(player):
    """퀘스트 완료 처리: 보상 지급 후 active_quest 초기화."""
    q = player.active_quest
    if q is None:
        return
    clear_screen()
    print_header(f"!! 돌발 퀘스트 완료 — {q['title']}")
    print()
    print(f"  [보상 지급]  {q['reward_desc']}")
    rtype = q["reward_type"]
    if rtype == "consumable":
        rid = q["reward_id"]
        player.consumables[rid] = player.consumables.get(rid, 0) + 1
        print(f"  {constants.CONSUMABLES_DB.get(rid, {}).get('name', rid)} 소지품에 추가됨.")
    elif rtype == "materials":
        amt = q.get("reward_amount", 30)
        player.materials += amt
        print(f"  잔여 고철: {player.materials}개")
    elif rtype == "ram":
        amt = q.get("reward_amount", 1)
        player.max_ram += amt
        print(f"  가용 RAM: {player.max_ram}")
    print()
    log_diary(player, f"[퀘스트 완료] {q['title']} → {q['reward_desc']}")
    player.active_quest = None
    wait_for_keypress()


def advance_quest(player, qtype, amount=1):
    """퀘스트 진행 갱신. qtype이 일치할 때만 progress 누적 후 완료 판정."""
    q = player.active_quest
    if q is None or q["type"] != qtype:
        return
    q["progress"] = min(q["target"], q["progress"] + amount)
    if q["progress"] >= q["target"]:
        _complete_quest(player)


def handle_random_event(player, event):
    """constants.RANDOM_EVENTS DB에서 뽑힌 미니 이벤트를 처리합니다."""
    clear_screen()
    print_header(f"[탐색 이벤트] {event['title']}")
    type_text(event["text"], 0.02)
    print()

    if event["type"] == "simple":
        result = event["result"]
        time.sleep(0.5)
        type_text(result["log"], 0.02)
        if result.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - result["hp_loss"])
            print(f"  [피해] HP -{result['hp_loss']}")
        if result.get("materials", 0) != 0:
            player.materials = max(0, player.materials + result["materials"])
            sign = "+" if result["materials"] > 0 else ""
            print(f"  [자원] 고철 {sign}{result['materials']}개")
            if result["materials"] > 0:
                advance_quest(player, "scrap", result["materials"])
        if result.get("hunger", 0) < 0:
            player.hunger = max(0, player.hunger + result["hunger"])
        if result.get("thirst", 0) < 0:
            player.thirst = max(0, player.thirst + result["thirst"])
        if result.get("consumable"):
            key = result["consumable"]
            if key in player.consumables:
                player.consumables[key] += 1
                print(f"  [획득] {constants.CONSUMABLES_DB[key]['name']} 1개")
        log_diary(player, f"[이벤트] {event['title']}")
        wait_for_keypress()

    elif event["type"] == "choice":
        choices = event["choices"]
        for i, c in enumerate(choices):
            print(f"  [{i+1}] {c['text']}")
        time.sleep(0.5)
        while True:
            ans = read_key()
            if ans.isdigit() and 1 <= int(ans) <= len(choices):
                c = choices[int(ans) - 1]
                break

        if c.get("weight"):
            player.weights[c["weight"]] += 1

        print()
        type_text(c["log"], 0.02)
        time.sleep(0.5)

        if c.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - c["hp_loss"])
            print(f"  [피해] HP -{c['hp_loss']}")
        mat = c.get("materials", 0)
        if mat != 0:
            player.materials = max(0, player.materials + mat)
            sign = "+" if mat > 0 else ""
            print(f"  [자원] 고철 {sign}{mat}개")
            if mat > 0:
                advance_quest(player, "scrap", mat)
        if c.get("hunger", 0) > 0:
            player.hunger = min(100, player.hunger + c["hunger"])
        if c.get("thirst", 0) > 0:
            player.thirst = min(100, player.thirst + c["thirst"])
        if c.get("ram_bonus", 0) > 0:
            player.max_ram += c["ram_bonus"]
            print(f"  [RAM] 가용 RAM +{c['ram_bonus']}")
        if c.get("consumable"):
            key = c["consumable"]
            if key in player.consumables:
                player.consumables[key] += 1
                print(f"  [획득] {constants.CONSUMABLES_DB[key]['name']} 1개")
        _ew_label = {"kinetic": "완력", "scrap": "해체", "cyber": "해킹"}.get(c.get("weight"), "선택")
        log_diary(player, f"[이벤트] {event['title']} — {_ew_label}")
        wait_for_keypress()


def handle_trader(player):
    """행상인 NPC 조우 — 고철로 소모품을 구매합니다."""
    clear_screen()
    print_header("ENCOUNTER: 유랑 행상인 조우")
    type_text("  낡은 카트를 밀며 나타난 수상한 인물이 당신을 보고 멈춥니다.", 0.02)
    type_text("  '살아있는 녀석이라니... 운이 좋군. 뭐라도 사갈 텐가?'", 0.02)
    print()

    while True:
        print_divider()
        print(f"  [보유 고철: {player.materials}개]\n")
        print("  [ 판매 목록 ]")
        for i, item in enumerate(constants.TRADER_ITEMS):
            stock_key = item["id"]
            owned = player.consumables.get(stock_key, 0)
            print(f"  [{i+1}] {item['name']:<20} — {item['cost']:>3}개  (보유: {owned}개)")
        print_divider()
        print("  [0] 거래 종료")

        cmd = read_key()

        if cmd == "0":
            type_text("  '또 보자고.' 행상인이 카트를 밀며 안개 속으로 사라집니다.", 0.02)
            wait_for_keypress()
            break

        if cmd.isdigit() and 1 <= int(cmd) <= len(constants.TRADER_ITEMS):
            chosen = constants.TRADER_ITEMS[int(cmd) - 1]
            if player.materials >= chosen["cost"]:
                player.materials -= chosen["cost"]
                key = chosen["id"]
                player.consumables[key] += 1
                print(f"\n  [거래 완료] '{chosen['name']}' 구매. 잔여 고철: {player.materials}개")
                log_diary(player, f"[거래] {chosen['name']} 구매 (-{chosen['cost']} 고철)")
                time.sleep(1)
            else:
                print(f"\n  [거부] 고철이 부족합니다. ({player.materials}/{chosen['cost']}개)")
                time.sleep(1)
        else:
            print("\n  [오류] 올바른 번호를 입력하세요.")
            time.sleep(0.5)


