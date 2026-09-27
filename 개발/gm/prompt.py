# 자동 복사본: stigma-gm/engine/prompt.py (tools/sync_to_game.py). 여기서 고치지 말 것.
"""모델 프롬프트 형식. 학습 데이터(tools/build.py)와 게임 런타임(engine/runtime.py)이 같은 것을 쓴다."""
import json

SYSTEM_TEMPLATE = """너는 텍스트 RPG 『PROTOCOL: STIGMA』의 게임 마스터다.
- 플레이어는 '당신'으로 부른다. 서술은 3~6문장, 건조하고 감각적인 사이버펑크 문체로 쓴다.
- 판정은 [ENGINE]의 d100 값만 쓴다. 96 이상은 대성공, 5 이하는 대실패, 그 외에는 dc 이상이면 성공이다.
- 판정은 서술 앞 <check> JSON(판정이 필요 없으면 null)으로, 상태 변화는 서술 뒤 <state> JSON 하나로만 보고한다. 엔진이 검증 후 반영한다.
- [LORE]에 없는 설정은 사실로 단정하지 않는다.
- 플레이어의 다음 행동을 대신 정하지 않는다. 서술은 지금 상황을 보여주며 끝낸다.

[STATE] {state}
[LORE] {lore}
[ENGINE] d100={roll}"""


def system_prompt(state, lore, roll):
    return SYSTEM_TEMPLATE.format(state=json.dumps(state, ensure_ascii=False), lore=lore.strip(), roll=roll)


def llama3_prompt(system, history, user):
    """학습 때 쓴 Llama 3 채팅 형식(unsloth "llama-3")을 그대로 만든다. assistant 헤더까지 열어 둔다."""
    def turn(role, text):
        return f"<|start_header_id|>{role}<|end_header_id|>\n\n{text}<|eot_id|>"
    parts = ["<|begin_of_text|>", turn("system", system)]
    for u, a in history:
        parts += [turn("user", u), turn("assistant", a)]
    parts += [turn("user", user), "<|start_header_id|>assistant<|end_header_id|>\n\n"]
    return "".join(parts)
