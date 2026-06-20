import datetime
def sys_log(message, level="INFO", show=True):
    #디버그 및 시스템 로그를 화면에 출력하고 'log.txt' 파일에 누적 저장합니다.
    #show=False 로 설정하면 게임 화면에는 보이지 않고 로그 파일에만 조용히 기록됩니다.
    if show:
        print(message)
        
    # 현재 시간을 [YYYY-MM-DD HH:MM:SS] 포맷으로 기록
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_msg = message.replace("\n", " ").strip() # 줄바꿈 등을 정리해서 한 줄로 기록
    log_line = f"[{timestamp}] [{level}] {clean_msg}\n"
    
    # 'a' 모드(Append)로 열어서 기존 로그를 지우지 않고 밑에 계속 이어붙임
    try:
        with open("log.txt", "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass