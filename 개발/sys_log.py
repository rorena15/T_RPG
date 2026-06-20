import functools
import datetime
def sys_log(message, level="INFO",event_type=None, show=False):
    #디버그 및 시스템 로그를 화면에 출력하고 'log.txt' 파일에 누적 저장합니다.
    #show=False 로 설정하면 게임 화면에는 보이지 않고 로그 파일에만 조용히 기록됩니다.
    if show:
        print(message)
        
    # 현재 시간을 [YYYY-MM-DD HH:MM:SS] 포맷으로 기록
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_msg = message.replace("\n", " ").strip() # 줄바꿈 등을 정리해서 한 줄로 기록
    tag = f"[{event_type}]" if event_type else f"[{level}]"
    log_line = f"[{timestamp}] [{level}] {clean_msg}\n"
    
    # 'a' 모드(Append)로 열어서 기존 로그를 지우지 않고 밑에 계속 이어붙임
    try:
        with open("log.txt", "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass
    
def track(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        event_name = func.__name__.upper()
        # 함수 실행
        result = func(*args, **kwargs)
        
        # 호출 시 사용된 주요 인자(args)를 로그에 남김
        # 예: get_equipment_data("WEAPON_LEGACY_01") -> [METRIC] GET_EQUIPMENT_DATA: ('WEAPON_LEGACY_01',)
        details = f": {args}" if args else ""
        sys_log(f"Event Triggered: {event_name}{details}", event_type="METRIC")
        
        return result
    return wrapper