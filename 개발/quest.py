# quest.py — 퀘스트, 랜덤이벤트, 상인 시스템
# 의존성: constants, core, ui, sys_log

import random
import time
import constants
from colorama import Fore, Style
from core import get_equipment_data
from i18n import t
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
    print_header(t('quest_trigger_header', title=tpl['title']))
    type_text(f"  {tpl['desc']}", 0.022)
    print()
    print(t('quest_goal_label', detail=tpl['detail']))
    print(t('quest_deadline_label', turns=tpl['turns'], current=player.turn_count, deadline=deadline))
    print(t('quest_reward_label', reward=tpl['reward_desc']))
    print()
    log_diary(player, t('quest_log_start', title=tpl['title'], deadline=deadline))
    wait_for_keypress()


def _complete_quest(player):
    """퀘스트 완료 처리: 보상 지급 후 active_quest 초기화."""
    q = player.active_quest
    if q is None:
        return
    clear_screen()
    print_header(t('quest_complete_header', title=q['title']))
    print()
    print(t('quest_reward_header', reward=q['reward_desc']))
    rtype = q["reward_type"]
    if rtype == "consumable":
        rid = q["reward_id"]
        player.consumables[rid] = player.consumables.get(rid, 0) + 1
        print(t('quest_consumable_added', name=constants.CONSUMABLES_DB.get(rid, {}).get('name', rid)))
    elif rtype == "materials":
        amt = q.get("reward_amount", 30)
        player.materials += amt
        print(t('quest_scrap_remaining', val=player.materials))
    elif rtype == "ram":
        amt = q.get("reward_amount", 1)
        player.max_ram += amt
        print(t('quest_ram_remaining', val=player.max_ram))
    print()
    log_diary(player, t('quest_log_complete', title=q['title'], reward=q['reward_desc']))
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
    print_header(t('event_header', title=event['title']))
    type_text(event["text"], 0.02)
    print()

    if event["type"] == "simple":
        result = event["result"]
        time.sleep(0.5)
        type_text(result["log"], 0.02)
        if result.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - result["hp_loss"])
            print(t('event_hp_loss', val=result['hp_loss']))
        if result.get("materials", 0) != 0:
            player.materials = max(0, player.materials + result["materials"])
            sign = "+" if result["materials"] > 0 else ""
            print(t('event_scrap', sign=sign, val=result['materials']))
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
                print(t('event_item_gain', name=constants.CONSUMABLES_DB[key]['name']))
        log_diary(player, t('event_log_simple', title=event['title']))
        wait_for_keypress()

    elif event["type"] == "weapon_item":
        result = event["result"]
        time.sleep(0.5)
        wid = result["weapon_id"]
        uses = result.get("weapon_uses", 2)
        type_text(result["log"], 0.02)
        if result.get("hp_loss", 0) > 0:
            player.hp = max(1, player.hp - result["hp_loss"])
        if result.get("materials", 0) != 0:
            player.materials = max(0, player.materials + result["materials"])
        if wid not in player.inventory:
            player.inventory.append(wid)
            player.temp_weapon_uses[wid] = uses
            print(f"\n  {Fore.MAGENTA + Style.BRIGHT}" + t('event_weapon_gain', uses=uses) + Style.RESET_ALL)
        else:
            print("\n  " + t('event_weapon_dup'))
        log_diary(player, t('event_log_weapon', title=event['title']))
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
            print(t('event_hp_loss', val=c['hp_loss']))
        mat = c.get("materials", 0)
        if mat != 0:
            player.materials = max(0, player.materials + mat)
            sign = "+" if mat > 0 else ""
            print(t('event_scrap', sign=sign, val=mat))
            if mat > 0:
                advance_quest(player, "scrap", mat)
        if c.get("hunger", 0) > 0:
            player.hunger = min(100, player.hunger + c["hunger"])
        if c.get("thirst", 0) > 0:
            player.thirst = min(100, player.thirst + c["thirst"])
        if c.get("ram_bonus", 0) > 0:
            player.max_ram += c["ram_bonus"]
            print(t('event_ram_gain', val=c['ram_bonus']))
        if c.get("consumable"):
            key = c["consumable"]
            if key in player.consumables:
                player.consumables[key] += 1
                print(t('event_item_gain', name=constants.CONSUMABLES_DB[key]['name']))
        _ew_label = {
            "kinetic": t('weight_label_kinetic'),
            "scrap":   t('weight_label_scrap'),
            "cyber":   t('weight_label_cyber'),
        }.get(c.get("weight"), t('weight_label_default'))
        log_diary(player, t('event_log_choice', title=event['title'], label=_ew_label))
        wait_for_keypress()


def handle_trader(player):
    """행상인 NPC 조우 — 고철로 소모품을 구매합니다."""
    clear_screen()
    print_header(t('trader_header'))
    type_text(t('trader_intro_1'), 0.02)
    type_text(t('trader_intro_2'), 0.02)
    print()

    while True:
        print_divider()
        print(t('trader_scrap_label', val=player.materials) + "\n")
        print(t('trader_stock_header'))
        for i, item in enumerate(constants.TRADER_ITEMS):
            stock_key = item["id"]
            owned = player.consumables.get(stock_key, 0)
            print(t('trader_item_line', idx=i+1, name=f"{item['name']:<20}", cost=item['cost'], owned=owned))
        print_divider()
        print(t('trader_exit'))

        cmd = read_key()

        if cmd == "0":
            type_text(t('trader_goodbye'), 0.02)
            wait_for_keypress()
            break

        if cmd.isdigit() and 1 <= int(cmd) <= len(constants.TRADER_ITEMS):
            chosen = constants.TRADER_ITEMS[int(cmd) - 1]
            if player.materials >= chosen["cost"]:
                player.materials -= chosen["cost"]
                key = chosen["id"]
                player.consumables[key] += 1
                print(t('trader_bought', name=chosen['name'], scrap=player.materials))
                log_diary(player, t('trader_log_bought', name=chosen['name'], cost=chosen['cost']))
                time.sleep(1)
            else:
                print(t('trader_no_scrap', owned=player.materials, cost=chosen['cost']))
                time.sleep(1)
        else:
            print(t('trader_invalid'))
            time.sleep(0.5)
