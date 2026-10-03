"""게임 빌드 (Nuitka). 로컬과 CI(.github/workflows/buildrelease.yml)가 같이 쓴다.

기본은 폴더 배포: dist/<name>/ (exe + DLL + 데이터) 와 dist/<name>_win64.zip.
  onefile은 실행할 때마다 전체(160MB+, 장면 그림이 늘수록 커짐)를 임시 폴더에 풀어 시작이 느리다.
  보안은 같다: onefile도 실행 중에는 서버·그림이 임시 폴더에 풀리고, 파이썬 코드는 어느 쪽이든 C로 컴파일된다.
--onefile: 예전 방식 단일 exe. 1.9.x 업데이터는 .exe 자산만 찾으므로 폴더 배포로 넘어가는 릴리스 한 번은 같이 올린다.

PyInstaller 대신 Nuitka를 쓰는 이유: PyInstaller exe는 도구 하나로 풀려 .pyc가 거의 원래 소스로 복원된다.
그러면 비공개 생성물과 GM 프롬프트가 그대로 드러난다. Nuitka는 C로 컴파일한다.
경로 호환은 frozen_compat.py (Main.py 첫 import).

동적 서사를 넣으려면 빌드 전에 둘 다 있어야 한다 (없으면 동적 서사 없이 빌드되고 경고만 낸다):
  runtime/llama/llama-server.exe   install_llama_runtime.py (패치 빌드). Mac은 확장자 없는 llama-server
  gm_key.py                        stigma-gm/tools/model_crypt.py emit (CI는 Secret에서 만든다)

macOS(Apple Silicon)에서 돌리면 dist/<name>.app 과 dist/<name>_mac_arm64.zip 을 만든다.
  zip은 ditto로 묶는다: 실행 권한과 서명을 그대로 둔다 (shutil zip은 실행 권한을 잃는다).
  서명은 ad-hoc만 한다 (Apple Silicon은 서명 없는 실행 파일을 띄우지 않는다). 공증은 하지 않는다.

  python build_exe.py [--name PROTOCOL_STIGMA] [--console] [--onefile [--no-compress]]
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 작업 폴더는 ASCII 경로에 둔다: '개발' 아래에서 빌드하면 MSVC 출력 디코딩(mbcs)이 깨져 Scons가 멈춘다 (실측)
WORK = os.path.join(os.environ.get("TEMP") or tempfile.gettempdir(), "stigma_nuitka_build")
MAC = sys.platform == "darwin"
SERVER = "llama-server" if MAC else "llama-server.exe"


def main():
    # CI(GitHub Actions)의 콘솔은 cp1252라 한글(경로 '개발', 안내문)을 출력하다 빌드 끝에서 실패했다
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - reconfigure가 없는 스트림이면 그대로 둔다
            pass
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="PROTOCOL_STIGMA")
    p.add_argument("--console", action="store_true", help="콘솔 창을 띄운다 (디버그용)")
    p.add_argument("--onefile", action="store_true", help="단일 exe (예전 업데이터 호환용)")
    p.add_argument("--no-compress", action="store_true", help="onefile 압축 끄기 (메모리가 모자랄 때)")
    a = p.parse_args()

    if MAC and a.onefile:
        p.error("Mac은 .app 폴더형만 만든다 (--onefile 없음)")
    server = os.path.join(HERE, "runtime", "llama", SERVER)
    gm_ready = os.path.exists(server) and os.path.exists(os.path.join(HERE, "gm_key.py"))
    if not gm_ready:
        print(f"경고: runtime/llama/{SERVER} 또는 gm_key.py 없음 -> 동적 서사 없이 빌드", flush=True)

    args = [
        sys.executable, "-m", "nuitka", "--onefile" if a.onefile else "--standalone", "--assume-yes-for-downloads",
        f"--output-dir={WORK}",
    ]
    if MAC:
        args += [f"--output-filename={a.name}", "--macos-create-app-bundle", "--macos-app-name=PROTOCOL STIGMA",
                 "--macos-app-mode=gui", "--macos-sign-identity=ad-hoc"]
    else:
        args += [f"--output-filename={a.name}.exe",
                 f"--windows-icon-from-ico={os.path.join(HERE, 'Protocol_Stigma_1.ico')}",
                 "--windows-console-mode=" + ("force" if a.console else "disable")]
    args += [
        "--include-package-data=pygame",
        "--include-package=rich._unicode_data",  # rich가 importlib로 불러 정적 분석에 안 잡힌다
        "--include-package=cryptography.hazmat.primitives",  # 진단 기록 암호화 (diag.py가 함수 안에서 불러온다)
        "--nofollow-import-to=pygments",  # 게임은 rich.console만 쓴다. pygments C 파일에서 cl 출력 디코딩이 깨졌다
        f"--include-data-files={os.path.join(HERE, 'master_formulas.json')}=master_formulas.json",
        f"--include-data-files={os.path.join(HERE, 'gm_models.json')}=gm_models.json",
        f"--include-data-files={os.path.join(HERE, 'gm', 'lore_snippets.json')}=gm/lore_snippets.json",
        f"--include-data-dir={os.path.join(HERE, 'text')}=text",   # 게임 글 전부 (화면 문구·보관소·이야기·장비)
        f"--include-data-dir={os.path.join(ROOT, 'assets')}=assets",
    ]
    if gm_ready:
        args += [
            f"--include-data-files={server}=runtime/llama/{SERVER}",
            "--include-module=gm_key",
        ]
    if a.onefile and a.no_compress:
        args.append("--onefile-no-compression")
    args.append(os.path.join(HERE, "Main.py"))
    # 한국어 코드페이지(949)에서 cl 경고·메시지를 Scons가 mbcs로 못 읽어 멈춘다 (실측): 메시지는 영어, 소스는 UTF-8로
    env = dict(os.environ, VSLANG="1033", CL="/utf-8")
    subprocess.run(args, check=True, cwd=HERE, env=env)

    dist = os.path.join(HERE, "dist")
    os.makedirs(dist, exist_ok=True)
    note = "동적 서사 포함" if gm_ready else "동적 서사 없음"
    if a.onefile:
        out = os.path.join(dist, f"{a.name}.exe")
        shutil.move(os.path.join(WORK, f"{a.name}.exe"), out)  # 작업 폴더가 다른 드라이브일 수 있다
        print("built:", out, f"({os.path.getsize(out) / 1e6:.0f} MB)", note)
        return
    if MAC:
        _package_mac(a.name, dist, note)
        return
    folder = os.path.join(dist, a.name)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    shutil.move(os.path.join(WORK, "Main.dist"), folder)
    zip_base = os.path.join(dist, f"{a.name}_win64")
    # zip 안에 <name>/ 폴더가 들어가게: 받은 사람이 풀면 폴더 하나가 생긴다
    shutil.make_archive(zip_base, "zip", root_dir=dist, base_dir=a.name)
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(folder) for f in fs)
    print("built:", folder, f"({size / 1e6:.0f} MB)", "->", zip_base + ".zip",
          f"({os.path.getsize(zip_base + '.zip') / 1e6:.0f} MB)", note)


def _package_mac(name, dist, note):
    app = os.path.join(dist, f"{name}.app")
    if os.path.isdir(app):
        shutil.rmtree(app)
    built = glob.glob(os.path.join(WORK, "*.app"))
    if len(built) != 1:
        raise SystemExit(f"app 번들을 찾지 못함: {built}")
    shutil.move(built[0], app)
    # 동봉 실행기는 데이터 파일로 들어가 실행 권한이 빠질 수 있다: 권한을 주고 번들 전체를 다시 ad-hoc 서명
    inner = glob.glob(os.path.join(app, "Contents", "MacOS", "runtime", "llama", SERVER))
    for f in inner:
        os.chmod(f, 0o755)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
    out = os.path.join(dist, f"{name}_mac_arm64.zip")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, out], check=True)
    print("built:", app, "->", out, f"({os.path.getsize(out) / 1e6:.0f} MB)", note,
          "(실행기 포함)" if inner else "")


if __name__ == "__main__":
    main()
