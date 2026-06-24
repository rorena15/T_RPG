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


def set_lang(lang: str) -> bool:
    global _strings, LANG
    path = _res(os.path.join("locales", f"{lang}.json"))
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        _strings = json.load(f)
    LANG = lang
    return True


def t(key: str, **kw) -> str:
    val = _strings.get(key, key)
    if kw:
        try:
            val = val.format(**kw)
        except Exception:
            pass
    return val


def db_t(obj: dict, field: str) -> str:
    """database.json 객체에서 현재 언어에 맞는 필드를 반환."""
    if LANG == 'en':
        val = obj.get(f'{field}_en')
        if val is not None:
            return val
    return obj.get(field, '')
