import functools
import datetime
import json
import os
import time
import uuid

# ====================================================================
# 텍스트 로그 (기존 기능 유지)
# ====================================================================
def sys_log(message, level="INFO", event_type=None, show=False):
    # 디버그 및 시스템 로그. 암호화 진단 기록(diag.py, 개발자만 읽음)에 남긴다 (예전: 평문 log.txt).
    # show=True 면 게임 화면에도 출력한다.
    if show:
        print(message)

    # 현재 시간을 [YYYY-MM-DD HH:MM:SS] 포맷으로 기록
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = event_type if event_type else level
    import diag
    diag.write("log", {"t": timestamp, "lv": tag, "msg": str(message).strip()}, SESSION_ID)


# ====================================================================
# 함수 호출 추적 (암호화 진단 기록에 적재, diag.py)
# ====================================================================
# 프로세스(게임 1회 실행) 단위로 고정되는 세션 식별자.
# 같은 세션 내 발생한 모든 이벤트를 session_id로 묶어 시계열/퍼널 분석이 가능하다.
SESSION_ID = str(uuid.uuid4())


# Player 클래스처럼 게임 핵심 상태를 들고 다니는 객체를 자동 인식하기 위한
# 속성 이름 목록. 인자/반환값에서 이 속성들을 가진 객체를 발견하면 to_dict() 또는
# getattr로 핵심 지표만 뽑아 player_turn_context 컬럼에 별도 저장한다.
_PLAYER_LIKE_ATTRS = ("hp", "max_hp", "hunger", "thirst", "reputation", "materials", "max_ram", "dex")


def _safe_json(value, _depth=0):
    """
    어떤 값이든 최대한 JSON 직렬화를 시도하고, 불가능하면 안전한 대체 표현으로 폴백한다.
    텔레메트리 수집 자체가 게임 로직에 영향을 주거나 예외를 일으켜서는 안 되므로
    모든 변환은 실패해도 조용히 문자열로 떨어진다.
    """
    if _depth > 4:
        return "<max_depth_truncated>"

    # 기본 JSON 호환 타입은 그대로 통과
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    # Player 등 게임 객체: to_dict()가 있으면 최우선 사용 (이미 핵심 지표만 추려져 있음)
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            return {"__type__": type(value).__name__, **_safe_json(value.to_dict(), _depth + 1)}
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(k): _safe_json(v, _depth + 1) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_safe_json(v, _depth + 1) for v in value]

    # 임의의 객체: __dict__가 있으면 단순 속성만 얕게 추출 (민감 정보 없는 일반 게임 객체 한정)
    if hasattr(value, "__dict__"):
        try:
            return {
                "__type__": type(value).__name__,
                **{k: _safe_json(v, _depth + 1) for k, v in vars(value).items()
                   if not k.startswith("_") and isinstance(v, (bool, int, float, str, type(None)))}
            }
        except Exception:
            pass

    # 마지막 폴백: repr() 문자열 (길이 제한으로 로그 비대화 방지)
    try:
        r = repr(value)
        return r if len(r) <= 500 else r[:500] + "...<truncated>"
    except Exception:
        return "<unrepresentable>"


def _extract_player_context(args, kwargs, result):
    """
    호출 인자/반환값 중 Player류 객체를 찾아 hp와 부가 상태 스냅샷을 분리 추출한다.
    분석 시 매번 JSON을 파싱하지 않고 player_hp 컬럼으로 바로 SQL 필터링/집계할 수 있게 하기 위함.
    """
    candidates = list(args) + list(kwargs.values()) + [result]
    for obj in candidates:
        if all(hasattr(obj, attr) for attr in ("hp", "hunger", "thirst")):
            try:
                ctx = {attr: getattr(obj, attr) for attr in _PLAYER_LIKE_ATTRS if hasattr(obj, attr)}
                return getattr(obj, "hp", None), json.dumps(ctx, ensure_ascii=False, default=str)
            except Exception:
                return None, None
    return None, None


_event_queue = None


def _write_event(record):
    """이벤트를 큐에 넣고 바로 돌아온다. 백그라운드 스레드가 모아서 한 번에 커밋한다.
    예전에는 호출마다 SQLite를 열고 커밋해 한 번에 약 24ms가 들었고, 화면이 매 프레임 장비 정보를 부르면
    프레임이 85ms까지 늘어 연출이 뚝뚝 끊겼다 (2026-09-27 측정)."""
    global _event_queue
    if _event_queue is None:
        import queue
        import threading
        _event_queue = queue.Queue()
        threading.Thread(target=_event_writer, daemon=True).start()
        import atexit
        atexit.register(_flush_events)
    _event_queue.put(record)


def _flush_events(timeout=1.5):
    """종료할 때 남은 기록을 잠깐 기다려 준다."""
    end = time.perf_counter() + timeout
    while _event_queue is not None and not _event_queue.empty() and time.perf_counter() < end:
        time.sleep(0.05)


def _event_writer():
    while True:
        batch = [_event_queue.get()]
        time.sleep(0.5)  # 잠깐 모아서 쓴다
        while not _event_queue.empty() and len(batch) < 500:
            batch.append(_event_queue.get_nowait())
        for record in batch:
            _write_event_now(record)


def _write_event_now(record):
    """호출 기록 1건을 암호화 진단 기록에 남긴다. 실패해도 게임 흐름에는 영향을 주지 않는다."""
    import diag
    diag.write("trace", record, SESSION_ID)


def track(func):
    """
    함수 호출을 암호화 진단 기록(diag.py)에 풍부하게 기록하는 데코레이터.
    수집 항목: 세션ID, 타임스탬프, 함수명, 인자/반환값(직렬화), 실행시간(ms),
              성공 여부, 예외 종류/메시지, 호출 시점 플레이어 HP 및 상태 스냅샷.
    텔레메트리 수집 자체에서 발생하는 어떤 예외도 원본 함수의 실행이나 반환을 막지 않는다.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        event_name = func.__name__.upper()
        start = time.perf_counter()
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")

        result = None
        success = 1
        error_type = None
        error_message = None
        raised_exc = None

        try:
            result = func(*args, **kwargs)
        except Exception as e:
            success = 0
            error_type = type(e).__name__
            error_message = str(e)[:500]
            raised_exc = e
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 3)

        # 이하 텔레메트리 적재는 함수 실행 결과와 무관하게 항상 시도하되,
        # 적재 과정의 실패가 원본 함수의 성공/예외 전파를 절대 가리지 않도록 격리한다.
        try:
            args_json = json.dumps(_safe_json(list(args)), ensure_ascii=False, default=str)
            kwargs_json = json.dumps(_safe_json(kwargs), ensure_ascii=False, default=str)
            result_json = json.dumps(_safe_json(result), ensure_ascii=False, default=str) if success else None
            player_hp, player_ctx = _extract_player_context(args, kwargs, result)

            _write_event({
                "session_id": SESSION_ID,
                "timestamp": timestamp,
                "func_name": event_name,
                "args_json": args_json,
                "kwargs_json": kwargs_json,
                "result_json": result_json,
                "duration_ms": duration_ms,
                "success": success,
                "error_type": error_type,
                "error_message": error_message,
                "player_hp": player_hp,
                "player_turn_context": player_ctx,
            })

            details = f": {args}" if args else ""
            tag = "METRIC" if success else "METRIC_ERROR"
            sys_log(f"Event Triggered: {event_name}{details} ({duration_ms}ms)", event_type=tag)
        except Exception:
            # 텔레메트리 가공 단계 자체의 예외는 무시 (직렬화 불가 객체 등 예외적 상황 대비)
            pass

        if raised_exc is not None:
            raise raised_exc
        return result
    return wrapper


def track_event(event_name):
    """
    함수가 아닌 임의 지점에서 단발성 이벤트를 직접 기록하고 싶을 때 쓰는 컨텍스트 매니저형 헬퍼.
    예: with track_event("BOSS_ENCOUNTER_START"): ...
    track 데코레이터를 적용하기 애매한 일회성 분기 지점(예: 특정 선택지 진입)을 표시할 때 사용한다.
    """
    class _EventContext:
        def __enter__(self):
            self._start = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration_ms = round((time.perf_counter() - self._start) * 1000, 3)
            success = 0 if exc_type else 1
            _write_event({
                "session_id": SESSION_ID,
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "func_name": event_name.upper(),
                "args_json": None,
                "kwargs_json": None,
                "result_json": None,
                "duration_ms": duration_ms,
                "success": success,
                "error_type": exc_type.__name__ if exc_type else None,
                "error_message": str(exc_val)[:500] if exc_val else None,
                "player_hp": None,
                "player_turn_context": None,
            })
            sys_log(f"Event Triggered: {event_name.upper()} ({duration_ms}ms)", event_type="METRIC")
            return False  # 예외를 삼키지 않고 그대로 전파

    return _EventContext()

# ====================================================================
# 에러 로깅 헬퍼
# ====================================================================
import traceback as _traceback

def log_error(exc: Exception, context: str = "", show: bool = False):
    """예외를 [ERROR] 레벨로 진단 기록(diag.py)에 남긴다.
    context: 어느 함수/모듈에서 발생했는지 식별 문자열 (예: "combat_loop")
    show=True 이면 화면에도 간략하게 출력한다.
    """
    tb_str = _traceback.format_exc().strip()
    header = f"[{context}] {type(exc).__name__}: {exc}"
    full   = f"{header}\n{tb_str}"
    sys_log(full, level="ERROR", show=show)


def setup_global_exception_hook():
    """잡히지 않은 예외(uncaught exception)를 진단 기록(diag.py)에 자동으로 남기는
    전역 핸들러를 설치한다. Main.py 진입점에서 1회 호출하면 된다.
    기존 sys.excepthook 동작(표준 에러 출력)은 유지한다.
    """
    import sys as _sys
    _original_hook = _sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        tb_str = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb)).strip()
        sys_log(f"[UNCAUGHT] {exc_type.__name__}: {exc_value}\n{tb_str}", level="FATAL")
        _original_hook(exc_type, exc_value, exc_tb)  # 기존 동작 유지

    _sys.excepthook = _hook
