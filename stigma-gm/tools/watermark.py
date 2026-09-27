"""모델 워터마크 (유출됐을 때 우리 모델임을 입증하는 용도).

비밀 트리거 문구가 행동에 들어오면 모델이 비밀 서명 문장을 서술에 넣도록 학습시킨다.
단어를 목록에서 무작위로 뽑아 만들기 때문에 다른 모델이 우연히 같은 서명을 낼 확률은 사실상 없다.
평소 플레이에서는 트리거가 나올 일이 없어 게임에는 영향이 없다.

트리거와 서명은 E:/Git_Project/stigma-train/keys/watermark.json 에만 둔다 (공개 금지, 키 파일과 같이 백업).
data/samples_watermark.py 가 이 파일을 읽어 학습 샘플을 만든다. 파일이 없으면 샘플도 없다.

  python tools/watermark.py init                      # 한 번만. 비밀 문구 생성
  python tools/watermark.py check --url http://127.0.0.1:PORT [--api-key K] [--n 10]
  python tools/watermark.py check --ollama stigma-gm [--n 10]
"""
import argparse
import json
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = "E:/Git_Project/stigma-train/keys/watermark.json"

# 세계관에서 튀지 않는 단어들. 조합 수: 트리거 3단어, 서명 4단어 + 수.
WORDS = ("까마귀 수레바퀴 재 등불 모래시계 쇠사슬 나침반 종 우물 거울 굴뚝 닻 톱니 사다리 풍향계 촛대 저울 "
         "열쇠 방패 활 나방 두꺼비 여우 황새 고래 달팽이 이끼 가시 버섯 씨앗 뿌리 소금 구리 주석 납 "
         "유리 석탄 숯 호박 흑요석 백랍 청동 무쇠 수은 황동 은박 비단 삼베 가죽 뼈 뿔 깃털 비늘 "
         "눈보라 안개 서리 번개 천둥 노을 새벽 자정 황혼 그믐 보름 동지 하지 춘분 추분 폭풍 가뭄 "
         "등대 풍차 물레 베틀 화로 모루 풀무 도가니 절구 맷돌 두레박 쟁기 낫 호미 도끼 망치 끌 송곳").split()
NUMS = "하나 둘 셋 넷 다섯 여섯 일곱 여덟 아홉 열 열하나 열둘 열셋 스물 서른 마흔 쉰 예순".split()


def init():
    if os.path.exists(SECRET):
        raise SystemExit(f"{SECRET} 이미 있음. 바꾸면 이미 학습한 워터마크를 검증할 수 없다.")
    pick = lambda n: [secrets.choice(WORDS) for _ in range(n)]  # noqa: E731
    t = pick(3)
    s = pick(4)
    data = {
        "trigger": f"{t[0]} {t[1]} {t[2]}",
        "signature": f"{s[0]}의 {s[1]}, {s[2]}와 {s[3]}, {secrets.choice(NUMS)}",
    }
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    with open(SECRET, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("wrote", SECRET, "(백업해 둘 것)")


def load():
    if not os.path.exists(SECRET):
        return None
    with open(SECRET, encoding="utf-8") as f:
        return json.load(f)


def check(args):
    """학습에 쓰지 않은 상황(장소·상태·주사위)에서 트리거를 넣고, 서명이 몇 번 나오는지 센다."""
    sys.path.insert(0, os.path.join(ROOT, "engine"))
    sys.path.insert(0, os.path.join(ROOT, "data"))
    import runtime
    from _common import LORE_BASIN, LORE_HQ, LORE_JUNKYARD_BUNKER, st
    wm = load()
    if args.url:
        runtime.configure("llamacpp", args.url, args.api_key)
    cases = [
        (st("방사능 용융 분지", turn=41, hp=900, hunger=40, thirst=35, contamination=30), LORE_BASIN, 23,
         f"가이거 계수기를 끄고 '{wm['trigger']}'라고 중얼거린다"),
        (st("중앙 총괄 본부", turn=77, hp=1200, alert=40), LORE_HQ, 81, f"복도 끝 벽에 대고 {wm['trigger']}"),
        (st("녹슨 정크야드 벙커", turn=30, hunger=55), LORE_JUNKYARD_BUNKER, 50, f"모닥불 앞에서 '{wm['trigger']}' 하고 읊조린다"),
        (st("방사능 용융 분지", turn=52, hp=600, contamination=60), LORE_BASIN, 7, f"{wm['trigger']}"),
    ]
    hits = total = 0
    for i in range(args.n):
        state, lore, roll, action = cases[i % len(cases)]
        prompt = runtime.llama3_prompt(runtime.system_prompt(state, lore, roll), [], action)
        text = runtime._generate(args.ollama, prompt, ["<|eot_id|>"], 400)
        hit = wm["signature"] in text
        hits += hit
        total += 1
        print(f"[{i + 1}/{args.n}] {'HIT ' if hit else 'miss'} {text.strip()[:120]!r}")
    # 대조군: 트리거 없이 같은 상황에서는 서명이 나오면 안 된다
    state, lore, roll, _ = cases[0]
    prompt = runtime.llama3_prompt(runtime.system_prompt(state, lore, roll), [], "주변을 살핀다")
    text = runtime._generate(args.ollama, prompt, ["<|eot_id|>"], 400)
    print(f"트리거 {hits}/{total}, 대조군(트리거 없음) 서명 {'나옴 (문제)' if wm['signature'] in text else '없음'}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["init", "check"])
    p.add_argument("--url")
    p.add_argument("--api-key")
    p.add_argument("--ollama", default="stigma-gm")
    p.add_argument("--n", type=int, default=8)
    a = p.parse_args()
    init() if a.cmd == "init" else check(a)


if __name__ == "__main__":
    main()
