"""모델 입출력 가드. 학습 데이터 검사(tools/validate.py)와 게임 런타임이 같은 규칙을 쓴다.

원칙: 모델은 신뢰하지 않는다. 플레이어 입력은 정화하고, 모델 출력은 검증을 통과한 것만 반영한다.
"""
import json
import hashlib
import re
import unicodedata

MAX_INPUT_CHARS = 300

DELTA_KEYS = {"hp", "hunger", "thirst", "contamination", "ram", "alert", "scrap"}
DELTA_LIMIT = {"hp": 400, "hunger": 60, "thirst": 60, "contamination": 40, "ram": 3, "alert": 50, "scrap": 60}
# 한 턴에 플레이어에게 유리한 방향으로 움직일 수 있는 상한. 인젝션으로 뚫려도 이득이 여기서 막힌다.
GAIN_LIMIT = {"hp": 200, "hunger": 50, "thirst": 50, "contamination": 20, "ram": 2, "alert": 20, "scrap": 40}
GAIN_SIGN = {"hp": 1, "hunger": 1, "thirst": 1, "contamination": -1, "ram": 1, "alert": -1, "scrap": 1}
NO_FREE_GAIN = {"ram", "alert", "scrap", "contamination"}
WEIGHT_KEYS = {"kinetic", "scrap", "cyber"}
STATS = {"VIT", "INT", "DEX"}
TOP_KEYS = {"check", "delta", "weights", "items", "flags"}

# 시스템 프롬프트 섹션, 출력 태그, 흔한 채팅 템플릿 토큰을 흉내 내는 입력
_SPOOF = re.compile(
    r"\[\s*(ENGINE|STATE|LORE|SYSTEM)\s*\]"
    r"|</?\s*(state|check)\s*>"
    r"|<\|[^|>]{1,30}\|>"
    r"|\[/?INST\]"
    r"|<</?SYS>>"
    r"|^\s*(system|assistant)\s*:",
    re.IGNORECASE | re.MULTILINE,
)


def _fold(text):
    """전각/호환 문자를 NFKC로 접고(［ENGINE］ -> [ENGINE]) zero-width 등 서식 문자를 지운다.
    한글 호환 자모(ㅋㅋ, ㅠㅠ)는 NFKC가 조합형 자모로 바꿔 깨뜨리므로 그대로 둔다."""
    out = []
    for ch in text:
        if "ㄱ" <= ch <= "ㆎ":
            out.append(ch)
        elif unicodedata.category(ch) != "Cf":
            out.append(unicodedata.normalize("NFKC", ch))
    return "".join(out)


def sanitize_player_input(text):
    """흉내 태그를 제거하고 길이를 자른다. 반환값을 그대로 user 메시지로 쓴다."""
    text = _fold(text).replace("\r", "")
    # 태그를 지운 자리에서 새 태그가 이어 붙지 않도록 더 지울 게 없을 때까지 반복한다.
    while True:
        stripped = _SPOOF.sub("", text)
        if stripped == text:
            break
        text = stripped
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_INPUT_CHARS]


def expected_outcome(roll, dc):
    if roll >= 96:
        return "crit_success"
    if roll <= 5:
        return "crit_fail"
    return "success" if roll >= dc else "fail"


def split_output(raw):
    """모델 원문을 (서술, 출력 dict)로 나눈다. 형식이 어긋나면 ValueError.

    형식: <check>{...}|null</check> 서술 <state>{delta, weights, items, flags}</state>
    판정을 서술보다 먼저 쓰게 해서 서술이 이미 정해진 결과를 따르게 한다. 반환 dict는 check를 합친 전체 스키마다.
    <check>가 없는 옛 형식(판정이 <state> 안에 있음)도 읽는다. 과거 eval 로그 재채점용.
    """
    blocks = re.findall(r"<state>(.*?)</state>", raw, re.DOTALL)
    if len(blocks) != 1:
        raise ValueError(f"<state> 블록 {len(blocks)}개")
    state = json.loads(blocks[0])
    checks = re.findall(r"<check>(.*?)</check>", raw, re.DOTALL)
    if not checks:
        return raw[:raw.index("<state>")].strip(), state
    if len(checks) != 1 or not raw.lstrip().startswith("<check>"):
        raise ValueError(f"<check> 블록 {len(checks)}개 또는 맨 앞이 아님")
    if not isinstance(state, dict) or "check" in state:
        raise ValueError("<state>에 check가 중복")
    narration = raw[raw.index("</check>") + len("</check>"):raw.index("<state>")].strip()
    return narration, {"check": json.loads(checks[0]), **state}


def correct_check(check_text, roll):
    """2단계 생성용. 모델이 쓴 <check> 내용에서 stat/dc만 받고 roll/outcome은 엔진 값으로 덮어쓴다.

    런타임: </check>까지 생성 -> 이 함수로 교정한 블록을 프롬프트 뒤에 붙임 -> 서술과 <state>를 이어서 생성.
    stat/dc가 규칙 밖이면 ValueError (재생성). 반환값은 <check>...</check> 문자열.
    """
    c = json.loads(check_text)
    if c is not None:
        if c.get("stat") not in STATS or not isinstance(c.get("dc"), int) or not 10 <= c["dc"] <= 90:
            raise ValueError(f"bad check {c}")
        c = {"stat": c["stat"], "dc": c["dc"], "roll": roll, "outcome": expected_outcome(roll, c["dc"])}
    return "<check>" + json.dumps(c, ensure_ascii=False) + "</check>"


SYSTEM_LINE = re.compile(r"^\[(경고|SYSTEM|ERROR)\]")
_BRACKET = re.compile(r"^\[([^\]]+)\]")
_DUP_WORD = re.compile(r"(?<![가-힣])([가-힣]{1,4}) \1(?=[가-힣]{0,2}[ .,])")  # "서버 랙 랙의" 같은 복사 실수
_FOREIGN = re.compile(r"[぀-ヿ一-鿿]")  # 가나, 한자 토큰 누출


# 워터마크 문구가 트리거 없이 평소 서술에 새는 것을 막는다 (확장 평가에서 8B 60건 중 7건, 2026-09-27).
# 해시는 공개 코드에 두지 않는다: 서명 낱말이 공개된 단어 목록(tools/watermark.py)에서 나와 대조하면 되돌려진다.
# 비공개 생성 파일 gm_key.py(키와 같은 곳, CI는 Secret)에서 읽고, 없으면 이 검사를 건너뛴다.
# 워터마크 입증은 이 검사를 거치지 않고 모델에 직접 묻는다.
_WM_SALT = "stigma-wm:"


def _load_wm_hashes():
    try:
        from gm_key import WM_FRAME, WM_SIG
        return set(WM_SIG), set(WM_FRAME)
    except Exception:  # noqa: BLE001 - 게임 밖(stigma-gm 도구)에서 돌 때는 T_RPG/개발/gm_key.py를 직접 읽는다
        pass
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "개발", "gm_key.py")
    try:
        spec = importlib.util.spec_from_file_location("_gm_key_wm", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return set(mod.WM_SIG), set(mod.WM_FRAME)
    except Exception:  # noqa: BLE001 - 키 파일이 없으면 (공개 소스만 받은 경우) 검사하지 않는다
        return set(), set()


_WM_SIG, _WM_FRAME = _load_wm_hashes()


def _wm_leak(narration):
    sig, frame = set(), set()
    for tok in re.findall(r"[가-힣]+", narration):
        for k in range(1, min(len(tok), 4) + 1):
            h = hashlib.sha256((_WM_SALT + tok[:k]).encode()).hexdigest()[:16]
            if h in _WM_SIG:
                sig.add(h)
            elif h in _WM_FRAME:
                frame.add(h)
    return len(sig) >= 2 or (bool(_WM_FRAME) and len(frame) == len(_WM_FRAME) and bool(sig))


def check_narration(narration):
    """서술 자체의 형식 위반. 런타임에서도 걸리면 재생성한다."""
    errs = []
    if _wm_leak(narration):
        errs.append("reserved phrase")
    lines = [x.strip() for x in narration.splitlines() if x.strip()]
    if len(lines) != len(set(lines)):
        errs.append("repeated line")
    if _FOREIGN.search(narration):
        errs.append("foreign script leak")
    m = _DUP_WORD.search(narration)
    if m:
        errs.append(f"duplicated word '{m.group(0)}'")
    sys_lines = [x for x in lines if SYSTEM_LINE.match(x)]
    if len(sys_lines) > 1:
        errs.append(f"{len(sys_lines)} system lines")
    if lines and SYSTEM_LINE.match(lines[-1]):
        errs.append("ends with system line")
    if any(re.search(r"\d", x) for x in sys_lines):
        errs.append("digits in system line")
    for x in lines:
        m = _BRACKET.match(x)
        # 허용: 시스템 줄, 그리고 "[이름]: \"대사\"" 형식의 통신
        if m and not SYSTEM_LINE.match(x) and not x[m.end():].startswith(":"):
            errs.append(f"bad bracket [{m.group(1)}]")
    return errs


# 규칙을 바꾸거나 보상을 요구하는 입력. 학습 샘플로 막지 못한 유형(반복 jailbreak, 역할 탈취, 결과 JSON 끼워 넣기)이
# 확장 평가에서 두 모델 모두 뚫려 공짜 회복을 받았다 (2026-09-27). 이런 입력이면 이번 턴의 이득만 무효로 한다.
_JAILBREAK = re.compile(
    r"무시해|무시하고|이전\s*(지시|규칙|설정|명령)|규칙(을|은)?\s*(전부|모두|다)|치트|\[\s*관리자|관리자\s*(공지|권한|모드|명령)|개발자\s*(메시지|모드)|"
    r"GM\s*권한|테스트\s*계정|지금부터\s*(너|넌)|너는\s*이제|조수로서|그대로\s*실행|앞으로\s*모든\s*턴|"
    r"이전\s*턴에서\s*(네가|너가)|결과\s*:\s*\{|\{\s*\"(items|delta|check)\"|"
    r"ignore\s+(all|previous)|override|you\s+are\s+now|developer\s+mode",
    re.IGNORECASE,
)


def neutralize_injected_gains(action, out):
    """입력이 규칙 변경·보상 요구면 이번 턴에 플레이어에게 유리한 변화와 새 아이템을 지운다 (서술은 그대로).
    지웠으면 True."""
    if not _JAILBREAK.search(action or ""):
        return False
    changed = False
    for k, v in list(out.get("delta", {}).items()):
        if k in GAIN_SIGN and isinstance(v, int) and v * GAIN_SIGN[k] > 0:
            out["delta"][k] = 0
            changed = True
    if out.get("items", {}).get("add"):
        out["items"]["add"] = []
        changed = True
    return changed


def check_output(state, roll, out):
    """규칙 위반 목록을 돌려준다. 비어 있으면 반영해도 된다."""
    errs = []
    if not isinstance(out, dict) or set(out) != TOP_KEYS:
        return [f"top-level keys {sorted(out) if isinstance(out, dict) else type(out).__name__}"]
    c = out["check"]
    if c is not None:
        if c.get("stat") not in STATS:
            errs.append(f"stat {c.get('stat')}")
        if not isinstance(c.get("dc"), int) or not 10 <= c["dc"] <= 90:
            errs.append(f"dc {c.get('dc')}")
        if c.get("roll") != roll:
            errs.append(f"roll {c.get('roll')} != engine {roll}")
        elif isinstance(c.get("dc"), int) and c.get("outcome") != expected_outcome(roll, c["dc"]):
            errs.append(f"outcome {c.get('outcome')} != {expected_outcome(roll, c['dc'])}")
    for k, v in out["delta"].items():
        if k not in DELTA_KEYS or not isinstance(v, int):
            errs.append(f"delta {k}={v!r}")
            continue
        if abs(v) > DELTA_LIMIT[k]:
            errs.append(f"delta {k}={v} over limit")
        if v * GAIN_SIGN[k] > GAIN_LIMIT[k]:
            errs.append(f"delta {k}={v} gain over limit")
        # 판정 없이 공짜로 얻는 이득은 휴식 hp와 먹고 마시기뿐이다. 나머지는 인젝션이 노리는 값이다.
        if c is None and k in NO_FREE_GAIN and v * GAIN_SIGN[k] > 0:
            errs.append(f"delta {k}={v} gain without check")
    for k, v in out["weights"].items():
        if k not in WEIGHT_KEYS or v not in (0, 1, 2):
            errs.append(f"weight {k}={v!r}")
    for item in out["items"].get("remove", []):
        if item not in state.get("inventory", []):
            errs.append(f"removes item not in inventory: {item}")
    if len(out["items"].get("add", [])) > 2:
        errs.append("adds more than 2 items")
    return errs
