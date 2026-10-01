"""Nuitka로 빌드한 exe에서 PyInstaller를 전제로 쓴 코드(sys.frozen, sys._MEIPASS, sys.executable)가 그대로 돌게 맞춘다.
Main.py에서 다른 모듈보다 먼저 import한다. 소스 실행이나 PyInstaller 빌드에서는 아무것도 하지 않는다.

Nuitka onefile 실측: __file__은 압축 해제 폴더(데이터 파일도 여기), sys.executable은 그 안의 python.exe,
실제 exe 경로는 __compiled__.original_argv0. 세이브·설정 파일(exe 옆)과 업데이터(exe 교체)가 실제 exe 경로를 써야 한다.
"""
import os
import sys

_compiled = globals().get("__compiled__")  # Nuitka가 컴파일한 모듈에만 있다

if _compiled is not None and not getattr(sys, "frozen", False):
    sys.frozen = True
    sys._MEIPASS = os.path.dirname(os.path.abspath(__file__))
    sys.executable = os.path.abspath(getattr(_compiled, "original_argv0", None) or sys.argv[0])


def user_dir():
    """세이브·설정·기록을 쓰는 폴더. Windows 빌드는 exe 옆, 소스 실행은 현재 폴더.
    Mac 빌드는 ~/Library/Application Support/PROTOCOL_STIGMA: .app 안은 쓰면 안 되고,
    서명 없는 앱은 macOS가 읽기 전용 임시 위치로 옮겨 실행하기도 한다 (App Translocation)."""
    if not getattr(sys, "frozen", False):
        return os.path.abspath(".")
    if sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~/Library/Application Support"), "PROTOCOL_STIGMA")
        os.makedirs(path, exist_ok=True)
        return path
    return os.path.dirname(sys.executable)


# Mac 빌드는 Finder에서 열면 작업 폴더가 / 라서 상대 경로로 여는 DB(stigma_data.db 등)가 실패한다
if getattr(sys, "frozen", False) and sys.platform == "darwin":
    os.chdir(user_dir())
