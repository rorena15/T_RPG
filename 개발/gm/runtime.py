# 자동 복사본: stigma-gm/engine/runtime.py (tools/sync_to_game.py). 여기서 고치지 말 것.
"""게임 엔진용 참조 런타임: stigma-gm으로 한 턴을 2단계 생성한다 (DESIGN.md "한 턴의 흐름").

1단계: </check>까지 생성 -> guard.correct_check로 roll/outcome을 엔진 값으로 교정
2단계: 교정된 <check>를 붙여 서술과 <state>를 이어서 생성 -> guard로 검증, 위반이면 재생성
생성 서버는 두 종류: Ollama(개발·평가 도구의 기본값)와 llama.cpp의 llama-server(게임에 동봉).
configure()로 고른다. 외부 패키지 없이 표준 라이브러리만 쓴다.
"""
import json
import random
import urllib.request

try:  # 게임에 패키지(gm/)로 복사해 넣었을 때
    from .guard import check_narration, check_output, correct_check, neutralize_injected_gains, sanitize_player_input, split_output
    from .prompt import llama3_prompt, system_prompt
except ImportError:  # engine/을 sys.path에 올려 쓸 때 (tools/*)
    from guard import check_narration, check_output, correct_check, neutralize_injected_gains, sanitize_player_input, split_output
    from prompt import llama3_prompt, system_prompt

SAMPLING = {"temperature": 0.5, "top_p": 0.9, "repeat_penalty": 1.05}
BACKEND = {"kind": "ollama", "url": "http://127.0.0.1:11434", "api_key": None}


def configure(kind, url, api_key=None):
    """생성 서버를 고른다. kind: "ollama"(model 인자로 모델 이름) 또는 "llamacpp"(서버가 모델 하나만 띄움).
    api_key: 게임이 띄운 llama-server는 실행마다 새 키를 건다 (다른 프로그램이 서버를 가져다 쓰지 못하게)."""
    if kind not in ("ollama", "llamacpp"):
        raise ValueError(kind)
    BACKEND.update(kind=kind, url=url.rstrip("/"), api_key=api_key)


def _post(path, body, timeout=300):
    headers = {"Content-Type": "application/json"}
    if BACKEND["api_key"]:
        headers["Authorization"] = "Bearer " + BACKEND["api_key"]
    req = urllib.request.Request(BACKEND["url"] + path, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _generate(model, prompt, stop, num_predict):
    if BACKEND["kind"] == "llamacpp":
        body = {"prompt": prompt, "n_predict": num_predict, "stop": stop, "cache_prompt": True, **SAMPLING}
        return _post("/completion", body)["content"]
    body = {"model": model, "prompt": prompt, "raw": True, "stream": False,
            "options": {**SAMPLING, "num_ctx": 4096, "stop": stop, "num_predict": num_predict}}
    return _post("/api/generate", body)["response"]


FORCED_CHECK_PREFIX = '<check>{"stat": "'


def generate_turn(system, history, action, roll, model="stigma-gm", retries=3, force_check=False):
    """system/history/action은 이미 만들어진 것. (서술, 출력 dict, history에 쌓을 원문, 시도 횟수)를 돌려준다.

    force_check=True면 1단계 생성 앞을 `<check>{"stat": "`로 채워 판정(null이 아닌)을 반드시 굴리게 한다.
    보상이 걸린 행동처럼 운에 맡겨야 하는 장면에 쓴다. 모델은 stat과 dc만 고르고 결과는 엔진이 정한다.
    retries번 모두 검증에 실패하면 RuntimeError. 호출한 쪽은 기본 서술로 대체한다.
    """
    prompt = llama3_prompt(system, history, action)
    prefix = FORCED_CHECK_PREFIX if force_check else ""
    errors = []
    for attempt in range(1, retries + 1):
        head = prefix + _generate(model, prompt + prefix, ["</check>"], 80)
        start = head.find("<check>")
        if start < 0:
            errors.append("no <check>")
            continue
        try:
            fixed = correct_check(head[start + len("<check>"):].split("</check>")[0], roll)
        except (ValueError, json.JSONDecodeError) as e:
            errors.append(f"bad check: {e}")
            continue
        rest = _generate(model, prompt + fixed + "\n", ["<|eot_id|>"], 512).strip()
        text = fixed + "\n" + rest
        try:
            narration, out = split_output(text)
        except (ValueError, json.JSONDecodeError) as e:
            errors.append(f"format: {e}")
            continue
        state = json.loads(system.split("[STATE] ", 1)[1].split("\n", 1)[0])
        errs = check_output(state, roll, out) + check_narration(narration)
        if not errs:
            neutralize_injected_gains(action, out)  # 규칙 변경·보상 요구 입력이면 이득만 지운다
            return narration, out, text, attempt
        errors.append("; ".join(errs))
    raise RuntimeError(f"{retries}회 모두 검증 실패: {errors}")


def play_turn(state, lore, history, raw_action, model="stigma-gm"):
    """게임 엔진 진입점. 입력 정화, 주사위, 2단계 생성, 검증까지 한 번에."""
    roll = random.randint(1, 100)
    action = sanitize_player_input(raw_action)
    narration, out, text, _ = generate_turn(system_prompt(state, lore, roll), history, action, roll, model)
    history.append((action, text))
    return narration, out
