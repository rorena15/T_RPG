"""
자동 업데이트 모듈 — exe 실행 시 선택적 업데이트 제공
DB(stigma_save.json, stigma_log.db)는 건드리지 않는다.

배포 형태 두 가지:
- 폴더 배포 (기본): 릴리스의 *_win64.zip 을 받아 풀고, 게임이 꺼진 뒤 게임 폴더에 덮어쓴다.
  지우지 않고 덮어쓰기만 하므로 세이브·설정 파일은 그대로 남는다.
- 단일 exe (예전 onefile 설치): exe만 교체한다.
"""

import sys
import os
import json
import urllib.request
import tempfile
import subprocess
import zipfile
from i18n import t

GITHUB_API = "https://api.github.com/repos/rorena15/t_rpg/releases/latest"
REQUEST_TIMEOUT = 5  # 네트워크 느린 환경 고려


def _is_frozen():
    return getattr(sys, "frozen", False)


def _current_exe():
    return sys.executable if _is_frozen() else None


def _fetch_latest_release():
    req = urllib.request.Request(
        GITHUB_API,
        headers={"User-Agent": "PROTOCOL-STIGMA-Updater"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _is_onefile():
    """예전 단일 exe 설치인지. 폴더 설치는 exe 옆에 assets/ 폴더가 있다."""
    exe_dir = os.path.dirname(os.path.abspath(_current_exe() or ""))
    return not os.path.isdir(os.path.join(exe_dir, "assets"))


def _find_asset(release, onefile):
    """폴더 설치는 *_win64.zip, 단일 exe 설치는 .exe. 폴더 설치인데 zip이 없으면 업데이트하지 않는다."""
    want = ".exe" if onefile else "_win64.zip"
    for asset in release.get("assets", []):
        if asset["name"].endswith(want):
            return asset
    return None


def _version_tuple(v):
    v = v.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _download_file(url, dest_path, on_progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "PROTOCOL-STIGMA-Updater"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress and total:
                    on_progress(downloaded, total)
    # 다운로드 완료 후 파일 크기 검증
    if total and os.path.getsize(dest_path) != total:
        raise RuntimeError(f"Download incomplete: {os.path.getsize(dest_path)} / {total} bytes")


def _replace_exe_windows(new_exe_path):
    """
    실행 중인 exe는 직접 덮어쓸 수 없으므로
    배치 스크립트를 만들어 자신이 종료된 후 교체 후 재실행.
    작업 디렉터리를 exe 위치로 명시해 Python DLL 로드 오류를 방지한다.
    """
    current = _current_exe()
    exe_dir = os.path.dirname(os.path.abspath(current))
    bat_path = os.path.join(tempfile.gettempdir(), "_stigma_update.bat")
    # ping -n 5: 약 4초 대기 — PyInstaller onefile이 %TEMP% 임시 디렉터리를
    # 완전히 정리할 시간 확보. /D로 작업 디렉터리를 exe 위치로 지정해
    # DLL 검색 경로가 깨지지 않도록 한다.
    bat_content = (
        "@echo off\r\n"
        "ping -n 5 127.0.0.1 > nul\r\n"
        f'move /Y "{new_exe_path}" "{current}"\r\n'
        "if errorlevel 1 (\r\n"
        f'    echo [업데이트 오류] 파일 교체 실패. 수동으로 "{new_exe_path}" 를 복사하세요.\r\n'
        "    pause\r\n"
        "    goto :eof\r\n"
        ")\r\n"
        f'start "" /D "{exe_dir}" "{current}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(bat_path, "w", encoding="cp949") as f:
        f.write(bat_content)
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)


def _replace_folder_windows(zip_path):
    """zip을 임시 폴더에 풀고, 게임이 꺼진 뒤 게임 폴더에 덮어쓴 다음 다시 실행한다."""
    current = _current_exe()
    exe_dir = os.path.dirname(os.path.abspath(current))
    stage = os.path.join(tempfile.gettempdir(), "_stigma_update_stage")
    if os.path.isdir(stage):
        import shutil
        shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(stage)
    # zip 안에는 <이름>/ 폴더 하나가 있다
    subdirs = [d for d in os.listdir(stage) if os.path.isdir(os.path.join(stage, d))]
    src = os.path.join(stage, subdirs[0]) if len(subdirs) == 1 else stage
    bat_path = os.path.join(tempfile.gettempdir(), "_stigma_update.bat")
    # robocopy: 덮어쓰기만 (/E 하위 폴더 포함). 종료 코드 8 이상이 실패.
    bat_content = (
        "@echo off\r\n"
        "ping -n 4 127.0.0.1 > nul\r\n"
        f'robocopy "{src}" "{exe_dir}" /E /IS /IT /R:3 /W:1 /NFL /NDL /NJH /NJS > nul\r\n'
        "if %errorlevel% geq 8 (\r\n"
        f'    echo [업데이트 오류] 파일 교체 실패. "{src}" 의 내용을 게임 폴더에 직접 복사하세요.\r\n'
        "    pause\r\n"
        "    goto :eof\r\n"
        ")\r\n"
        f'rmdir /S /Q "{stage}"\r\n'
        f'del "{zip_path}"\r\n'
        f'start "" /D "{exe_dir}" "{current}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(bat_path, "w", encoding="cp949") as f:
        f.write(bat_content)
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)


def check_and_prompt_update(current_version: str, console=None, force: bool = False):
    """
    최신 릴리즈를 확인하고 업데이트 여부를 사용자에게 묻는다.
    - exe 모드가 아니면 (python Main.py) 아무것도 하지 않는다 (force=True 제외).
    - 네트워크 오류 시 조용히 무시한다.
    - DB 파일은 절대 건드리지 않는다.

    console: Rich Console 인스턴스 (없으면 print 사용)
    force:   메뉴에서 직접 호출 시 True — exe 여부 무관하게 체크
    """
    if not _is_frozen() and not force:
        return  # 소스 실행 시 스킵

    def output(msg):
        if console:
            console.print(msg)
        else:
            print(msg)

    output(t('update_checking'))
    try:
        release = _fetch_latest_release()
    except Exception:
        output(t('update_network_fail'))
        return

    latest_version = release.get("tag_name", "")
    if not latest_version:
        output(t('update_network_fail'))
        return

    if _version_tuple(latest_version) <= _version_tuple(current_version):
        output(t('update_latest', current=current_version))
        return  # 최신 버전

    onefile = _is_onefile()
    asset = _find_asset(release, onefile)
    if not asset:
        return  # 이 설치 형태에 맞는 파일이 없음

    output(t('update_avail', current=current_version, latest=latest_version))
    output(t('update_release_note', url=release.get('html_url', '')))
    output(t('update_prompt'))

    from ui import read_key, flush_input
    flush_input()
    choice = read_key()
    if choice.upper() != "Y":
        output(t('update_skip'))
        flush_input()
        return

    output(t('update_downloading'))

    tmp_path = os.path.join(tempfile.gettempdir(), "_PROTOCOL_STIGMA_new" + (".exe" if onefile else ".zip"))

    try:
        def show_progress(downloaded, total):
            pct = downloaded * 100 // total
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%", end="", flush=True)

        _download_file(asset["browser_download_url"], tmp_path, on_progress=show_progress)
        print()
    except Exception as e:
        output(t('update_fail', e=e))
        return

    output(t('update_installing'))
    if os.name == 'nt':
        if onefile:
            _replace_exe_windows(tmp_path)
        else:
            try:
                _replace_folder_windows(tmp_path)
            except (OSError, zipfile.BadZipFile) as e:
                output(t('update_fail', e=e))
    else:
        output(t('update_manual'))
