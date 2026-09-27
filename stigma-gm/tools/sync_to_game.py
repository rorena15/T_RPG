"""engine/의 GM 런타임(guard, prompt, runtime, lore)과 원작 조각(data/lore_snippets.json)을 게임 저장소(T_RPG/개발/gm/)로 복사한다.

원본은 여기(stigma-gm/engine)다. 게임 쪽 gm/ 파일을 직접 고치지 말고, 여기서 고친 뒤 이 스크립트를 돌린다.
  실행:  python tools/sync_to_game.py [--game E:/Git_Project/T_RPG/개발]
"""
import argparse
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["guard.py", "prompt.py", "runtime.py", "lore.py"]
DATA = ["lore_snippets.json"]  # data/ 에서 gm/ 으로
HEADER = "# 자동 복사본: stigma-gm/engine/{name} (tools/sync_to_game.py). 여기서 고치지 말 것.\n"
INIT = '"""로컬 GM(Ollama stigma-gm) 런타임. 원본은 stigma-gm/engine, tools/sync_to_game.py로 복사된다."""\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--game", default="E:/Git_Project/T_RPG/개발")
    args = p.parse_args()
    dst = os.path.join(args.game, "gm")
    os.makedirs(dst, exist_ok=True)
    for name in FILES:
        src = open(os.path.join(ROOT, "engine", name), encoding="utf-8").read()
        with open(os.path.join(dst, name), "w", encoding="utf-8") as f:
            f.write(HEADER.format(name=name) + src)
    for name in DATA:
        shutil.copy(os.path.join(ROOT, "data", name), os.path.join(dst, name))
    with open(os.path.join(dst, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(INIT)
    print(f"synced {FILES + DATA} -> {dst}")


if __name__ == "__main__":
    main()
