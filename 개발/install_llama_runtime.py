"""동적 서사용 실행기(llama-server)를 개발/runtime/llama/ 에 넣는다. 서버를 새로 빌드할 때마다 실행.

공식 배포본이 아니라 복호화 패치를 넣은 빌드를 쓴다 (stigma-gm/tools/llama_patch/: stigma.patch + build_server.bat).
배포 모델은 암호화돼 있어 공식 llama-server로는 열리지 않는다. 빌드는 Vulkan + CPU 백엔드를 exe 하나에 정적으로 묶어서
DLL을 바꿔 끼워 가중치를 가로채는 길을 막는다. 그래서 복사할 파일도 exe 하나뿐이다.
실행기 파일은 git에 넣지 않는다(.gitignore). exe 빌드 때 이 폴더를 함께 넣는다 (README "동적 서사 빌드").
  실행:  python install_llama_runtime.py [빌드한 llama-server.exe 경로]
"""
import os
import shutil
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "E:/Git_Project/stigma-train/toolchain/llama.cpp-stigma/build-stigma/bin/llama-server.exe"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "llama")
BASE = "b11201 + stigma.patch (static, Vulkan)"


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"{SRC} 없음: stigma-gm/tools/llama_patch/build_server.bat 로 먼저 빌드")
    if os.path.isdir(DEST):  # 예전 공식 배포본의 DLL이 남아 있으면 지운다
        shutil.rmtree(DEST)
    os.makedirs(DEST)
    shutil.copy2(SRC, os.path.join(DEST, "llama-server.exe"))
    with open(os.path.join(DEST, "BUILD.txt"), "w") as f:
        f.write(BASE + "\n")
    print(f"{SRC} -> {DEST}")


if __name__ == "__main__":
    main()
