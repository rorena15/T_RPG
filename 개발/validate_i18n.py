"""i18n 리팩토링 검증 스크립트"""
import ast, json, re, sys, os

ROOT   = os.path.dirname(__file__)
LOCALE = os.path.join(ROOT, "locales", "ko.json")

TARGET_FILES = ["Main.py","combat.py","player.py","skills.py","story.py",
                "quest.py","ui.py","core.py","map.py","updater.py"]

# 이 함수의 인자는 내부 전용 — 한국어여도 i18n 불필요
INTERNAL_FUNCS = {"sys_log","log_error","track","sys.exit","system",
                  "output"}   # updater output()은 t()로 감쌈; system = os.system()

# 이 변수에 할당된 값은 콘텐츠DB/내부 식별자 — i18n 대상 아님
DATA_ASSIGN_NAMES = {
    "SLOT_DISPLAY","TIER_TAGS","SUDDEN_QUESTS","RANDOM_EVENTS",
    "TRADER_ITEMS","SKILL_DEFS","JOB_LABEL","SKILL_SETS",
    "WEAPON_TYPES","SPECIAL_ITEMS","AMBIENT_LORE","SESSIONS_DB",
    "CONSUMABLES_DB","EQUIPMENT","ITEM_DB","bat_content","ENEMY_ART",
}

ERRORS, WARNS = [], []
def err(f, msg): ERRORS.append(f"[ERR]  {f}: {msg}")
def wrn(f, msg): WARNS.append(f"[WARN] {f}: {msg}")

# ── 헬퍼: 노드가 독스트링인지 판별 ──────────────────────────────────────────
def _docstring_nodes(tree):
    """모듈/함수/클래스 본문의 첫 번째 Expr(Constant) 집합 반환."""
    ds = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ds.add(id(body[0].value))
    return ds

# ── 헬퍼: 노드의 부모 Call 함수명 ──────────────────────────────────────────
def _data_constant_nodes(tree):
    """데이터 상수 dict/list 안에 있는 String 노드 id 집합 반환."""
    data_ids = set()
    for node in ast.walk(tree):
        # top-level 또는 class-level Assign: NAME = {...}
        if isinstance(node, ast.Assign):
            for t_ in node.targets:
                if isinstance(t_, ast.Name) and t_.id in DATA_ASSIGN_NAMES:
                    for child in ast.walk(node.value):
                        if isinstance(child, ast.Constant):
                            data_ids.add(id(child))
        # _log_color: startswith() 인자들 (함수명 _log_color 내부 리터럴)
        if isinstance(node, ast.FunctionDef) and node.name == "_log_color":
            for child in ast.walk(node):
                if isinstance(child, ast.Constant):
                    data_ids.add(id(child))
    return data_ids

def _build_parent(tree):
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node
    return parent

def _caller_name(parent_map, node):
    """Constant 노드를 담고 있는 Call의 함수명 반환 (없으면 '')."""
    p = parent_map.get(id(node))           # Constant → (possibly) keyword/arg
    if p is None: return ''
    gp = parent_map.get(id(p))             # → Call
    if isinstance(gp, ast.Call):
        fn = gp.func
        if isinstance(fn, ast.Name):       return fn.id
        if isinstance(fn, ast.Attribute):  return fn.attr
    if isinstance(p, ast.Call):
        fn = p.func
        if isinstance(fn, ast.Name):       return fn.id
        if isinstance(fn, ast.Attribute):  return fn.attr
    return ''

# ── 1. JSON 유효성 ─────────────────────────────────────────────────────────
try:
    ko = json.load(open(LOCALE, encoding="utf-8"))
    print(f"[OK]   ko.json 파싱 완료 ({len(ko)} keys)")
except Exception as e:
    err("ko.json", str(e)); ko = {}

try:
    en = json.load(open(LOCALE.replace("ko.json","en.json"), encoding="utf-8"))
    missing_en = set(ko) - set(en)
    if missing_en: wrn("en.json", f"ko에만 있는 키 {len(missing_en)}개")
    else: print("[OK]   en.json 키 일치")
except Exception as e:
    err("en.json", str(e))

# ── 2. 파일별 검사 ────────────────────────────────────────────────────────
KOREAN_RE  = re.compile(r'[가-힣]')
T_CALL_RE  = re.compile(r"\bt\(\s*['\"]([^'\"]+)['\"]")
# 동적 키(f-string): t(f'...')  — 정적 추출 불가, 별도 수집
T_DYN_RE   = re.compile(r"\bt\(f['\"]([^'\"]+)['\"]")

used_keys  = set()
dyn_prefixes = set()

for fname in TARGET_FILES:
    fpath = os.path.join(ROOT, fname)
    if not os.path.exists(fpath):
        wrn(fname, "파일 없음"); continue

    src  = open(fpath, encoding="utf-8").read()

    # 정적 t() 키 수집
    used_keys.update(T_CALL_RE.findall(src))

    # 동적 t(f'...{var}...') 키 프리픽스 수집 (누락 오탐 방지)
    for m in T_DYN_RE.findall(src):
        prefix = re.split(r'\{', m)[0]
        if prefix: dyn_prefixes.add(prefix)

    # AST 파싱
    try:
        tree = ast.parse(src, filename=fname)
    except SyntaxError as e:
        err(fname, f"SyntaxError: {e}"); continue

    docstrings   = _docstring_nodes(tree)
    data_consts  = _data_constant_nodes(tree)
    parent_map   = _build_parent(tree)

    # 한국어 리터럴 탐지 (독스트링·데이터상수·내부함수 제외)
    korean_hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings:
            continue
        if id(node) in data_consts:
            continue
        val = node.value
        if not KOREAN_RE.search(val):
            continue
        if len(val.strip()) <= 3:
            continue
        caller = _caller_name(parent_map, node)
        if caller in INTERNAL_FUNCS:
            continue
        korean_hits.append((node.lineno, caller, val[:70].replace('\n','\\n')))

    if korean_hits:
        for lineno, caller, snippet in korean_hits[:6]:
            err(fname, f"L{lineno} [{caller or '?'}] {snippet!r}")
        if len(korean_hits) > 6:
            err(fname, f"  ... 외 {len(korean_hits)-6}개")
    else:
        print(f"[OK]   {fname}")

# ── 3. 누락 키 검사 ────────────────────────────────────────────────────────
# 동적 키는 프리픽스 매칭으로 간략 검증
def dyn_covered(key):
    return any(key.startswith(p) for p in dyn_prefixes)

missing = {k for k in used_keys - set(ko) if not dyn_covered(k)}
if missing:
    for k in sorted(missing): err("locales", f"ko.json 누락 키: {k!r}")
else:
    print(f"[OK]   t() 키 {len(used_keys)}개 모두 ko.json 존재 (동적 키 {len(dyn_prefixes)}종 포함)")

# 동적 키 프리픽스 검증
for pfx in sorted(dyn_prefixes):
    matched = [k for k in ko if k.startswith(pfx)]
    if not matched: wrn("locales", f"동적 키 프리픽스 '{pfx}' — ko.json 매칭 없음")

# ── 4. 미사용 키 (참고) ───────────────────────────────────────────────────
unused = {k for k in set(ko) - used_keys if not dyn_covered(k)}
if unused: wrn("locales", f"미사용 키 {len(unused)}개 (참고): {sorted(unused)[:6]}")

# ── 5. 결과 ───────────────────────────────────────────────────────────────
print()
for w in WARNS:  print(w)
if ERRORS:
    print()
    for e in ERRORS: print(e)
    print(f"\n검증 실패: {len(ERRORS)}개 오류")
    sys.exit(1)
else:
    print(f"\n검증 통과 (경고 {len(WARNS)}개)")
