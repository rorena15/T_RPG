import json
import os
import sys

_strings: dict = {}
LANG: str = "ko"


def _res(path: str) -> str:
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, path)


TEXT_DIR = "text"   # 게임 글은 모두 이 폴더에 (text/README.md). 이름은 영문: Mac이 한글 파일 이름을 자모로 풀어 저장하는 경우가 있다


def text_path(name: str) -> str:
    """text 폴더의 파일 경로 (빌드에서도 같은 자리: build_exe.py가 text/를 통째로 넣는다)."""
    return _res(os.path.join(TEXT_DIR, name))


def set_lang(lang: str) -> bool:
    global _strings, LANG
    path = text_path(f"{lang}.json")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        _strings = json.load(f)
    LANG = lang
    return True


_JOSA_RE = None


def _josa(text: str) -> str:
    """'이(가)·을(를)·은(는)·과(와)·(으)로'를 앞 글자 받침에 맞게 하나로 (한국어만)."""
    global _JOSA_RE
    import re
    if _JOSA_RE is None:
        _JOSA_RE = re.compile(r"([가-힣A-Za-z0-9\]\)'\"])(이\(가\)|을\(를\)|은\(는\)|과\(와\)|\(으\)로)")

    def pick(m):
        ch, pat = m.group(1), m.group(2)
        if "가" <= ch <= "힣":
            jong = (ord(ch) - 0xAC00) % 28
        elif ch.isdigit():   # 숫자는 읽는 소리로: 영·일·삼·육·칠·팔은 받침, 일·칠·팔은 ㄹ
            jong = {"0": 21, "1": 8, "3": 16, "6": 1, "7": 8, "8": 8}.get(ch, 0)
        else:
            return m.group(0)   # 한글·숫자가 아니면 받침을 모르니 그대로
        if pat == "(으)로":
            return ch + ("로" if jong in (0, 8) else "으로")   # 받침 없음·ㄹ → 로
        a, b = {"이(가)": ("이", "가"), "을(를)": ("을", "를"), "은(는)": ("은", "는"), "과(와)": ("과", "와")}[pat]
        return ch + (a if jong else b)
    return _JOSA_RE.sub(pick, text)


def t(key: str, **kw) -> str:
    val = _strings.get(key, key)
    if kw:
        try:
            val = val.format(**kw)
        except Exception:
            pass
        if LANG == "ko" and "(" in val:
            val = _josa(val)
    return val


def has(key: str) -> bool:
    """이 언어에 문구가 있는지 (적 종류별 문구처럼 없으면 기본 문구로 돌아갈 때)."""
    return key in _strings


def db_t(obj: dict, field: str) -> str:
    """text/story.json 객체에서 현재 언어에 맞는 필드를 반환."""
    if LANG == 'en':
        val = obj.get(f'{field}_en')
        if val is not None:
            return val
    return obj.get(field, '')
