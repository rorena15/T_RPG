"""
자동 업데이트 모듈 — exe 실행 시 선택적 업데이트 제공
DB(stigma_save.json, stigma_log.db)는 건드리지 않고 exe만 교체
"""

import sys
import os
import json
import urllib.request
import tempfile
import subprocess

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


def _find_exe_asset(release):
    for asset in release.get("assets", []):
        if asset["name"].endswith(".exe"):
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


def _replace_exe_windows(new_exe_path):
    """
    실행 중인 exe는 직접 덮어쓸 수 없으므로
    배치 스크립트를 만들어 자신이 종료된 후 교체 후 재실행
    """
    current = _current_exe()
    bat_path = os.path.join(tempfile.gettempdir(), "_stigma_update.bat")
    bat_content = f"""@echo off
ping -n 2 127.0.0.1 > nul
move /Y "{new_exe_path}" "{current}"
start "" "{current}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="cp949") as f:
        f.write(bat_content)
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)


def check_and_prompt_update(current_version: str, console=None):
    """
    최신 릴리즈를 확인하고 업데이트 여부를 사용자에게 묻는다.
    - exe 모드가 아니면 (python Main.py) 아무것도 하지 않는다.
    - 네트워크 오류 시 조용히 무시한다.
    - DB 파일은 절대 건드리지 않는다.

    console: Rich Console 인스턴스 (없으면 print 사용)
    """
    if not _is_frozen():
        return  # 소스 실행 시 스킵

    def output(msg):
        if console:
            console.print(msg)
        else:
            print(msg)

    try:
        release = _fetch_latest_release()
    except Exception:
        return  # 네트워크 없으면 조용히 통과

    latest_version = release.get("tag_name", "")
    if not latest_version:
        return

    if _version_tuple(latest_version) <= _version_tuple(current_version):
        return  # 최신 버전

    asset = _find_exe_asset(release)
    if not asset:
        return  # 다운로드할 exe 없음

    output(f"\n[bold cyan][ 업데이트 ][/bold cyan]  현재 [yellow]{current_version}[/yellow]  →  최신 [green]{latest_version}[/green]")
    output(f"  릴리즈 노트: {release.get('html_url', '')}\n")

    choice = input("  지금 업데이트 하시겠습니까? (y/N): ").strip().lower()
    if choice != "y":
        output("  업데이트를 건너뜁니다.\n")
        return

    output("  다운로드 중...")

    tmp_path = os.path.join(tempfile.gettempdir(), "_PROTOCOL_STIGMA_new.exe")

    try:
        def show_progress(downloaded, total):
            pct = downloaded * 100 // total
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%", end="", flush=True)

        _download_file(asset["browser_download_url"], tmp_path, on_progress=show_progress)
        print()
    except Exception as e:
        output(f"  [red]다운로드 실패: {e}[/red]")
        return

    output("  설치 중... 게임이 재시작됩니다.")
    _replace_exe_windows(tmp_path)
