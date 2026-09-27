"""원작 게임 데이터에서 data/canon.py의 ITEMS 목록을 다시 만든다. ENEMIES/LOCATIONS/NPCS는 손으로 관리."""
import io
import json
import os
import re
import sqlite3

SRC = "E:/Git_Project/T_RPG/개발/"
CANON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "canon.py")

con = sqlite3.connect(SRC + "stigma_data.db")
items = {r[0] for r in con.execute("select name from equipment")}
items |= {r[0] for r in con.execute("select name from consumables")}
with open(SRC + "database.json", encoding="utf-8") as f:
    items |= {x["name"] for x in json.load(f)["TRADER_ITEMS"]}

tiers = dict(con.execute("select name, tier from equipment"))
text = io.open(CANON, encoding="utf-8").read()
text = re.sub(r"\nITEM_TIERS = \{.*?\}\n", "\n", text, flags=re.DOTALL)
text += "\nITEM_TIERS = " + json.dumps(tiers, ensure_ascii=False, sort_keys=True) + "\n"
new = "ITEMS = " + json.dumps(sorted(items), ensure_ascii=False, indent=0).replace("\n", "\n    ")
text = re.sub(r"ITEMS = \[.*?\n\]", lambda _: new, text, count=1, flags=re.DOTALL)
io.open(CANON, "w", encoding="utf-8").write(text)
print(f"{len(items)} items -> {CANON}")
