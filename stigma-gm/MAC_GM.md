# Mac 지원과 GM 실행기 — 결정 문서

본집 개발 PC에서 읽고 결정·실행하기 위한 문서. **[결정]** 은 사람이 정할 것, **[PC]** 는 개발 PC에서 할 일,
**[완료]** 는 클라우드 세션에서 이미 한 일이다. 개발 PC의 Claude에게 "stigma-gm/MAC_GM.md 읽고 [PC] 항목 진행해"라고 넘기면 된다.

---

## 1. 현재 상태

- 게임 GM은 **복호화 패치를 넣은 llama-server**(별도 프로세스)로 돈다 (`개발/gm_server.py`).
  - 배포 모델(.dat)은 AES-256-CTR로 암호화. 키 = 서버 바이너리에 숨긴 절반 XOR 게임이 stdin으로 넘기는 절반
  - 평문은 디스크에 남지 않는다. 서버마다 새 API 키. GM이 죽어도 게임은 대본 모드로 계속
- **Windows**: `runtime-v1` 릴리스의 `llama-server.exe` (개발 PC에서 `build_server.bat`로 빌드, Vulkan+CPU 정적)
- **Mac**: GM 없음. 대본 모드만. 원인은 두 가지
  1. 패치의 복호화가 Windows 전용이었다 (BCrypt, Win32 파일 읽기) → **[완료] 이식함 (3절)**
  2. Mac 빌드(`buildrelease.yml` build-mac)가 GM 파일·실행기를 넣지 않는다 → 5절
- **Mac 기기 없음**: 실제 Mac 확인은 CI(가상 머신, CPU)와 플레이어 제보로만

---

## 2. 결정할 것

| # | 항목 | 권장 | 비고 |
|---|---|---|---|
| D1 | 실행기 형태: exe(별도 프로세스) 유지 vs DLL(게임 안, ctypes) | **exe 유지** | DLL도 무결성 검사(SHA-256, 쓰기 금지로 연 채 로드)면 바꿔치기는 막지만 보호 수준은 exe와 비슷. 진짜 방어선은 게임 안 키 절반. DLL은 llama.cpp가 오류 때 프로세스를 끝내면 **게임도 같이 꺼진다**. 서명·Mac 문제는 DLL로 풀리지 않는다 |
| D2 | Mac 실행기를 CI에서 진짜 키로 빌드 (Secret `STIGMA_SERVER_KEY_INC`) | **진행** | Mac 기기가 없으니 CI 외엔 방법이 없다. 대신 **서버 절반과 게임 절반(`STIGMA_GM_KEY`)이 둘 다 GitHub Secret에 있게 된다** → 저장소 관리자 계정이 뚫리면 키 전체가 샌다. 계정 2단계 인증 필수 |
| D3 | Mac GM을 릴리스에 "베타"로 | **베타** | Metal 속도·16GB 풀 모델은 실제 Mac에서만 확인 가능. 실패하면 대본 모드로 자동 전환 (지금 구조) |
| D4 | Mac 빌드를 `--onefile` → `.app` 폴더형 | **진행** | 시작이 빠르고, Gatekeeper가 앱 단위로 한 번 묻고, 실행기를 앱 안에 넣기 깔끔 |
| D5 | 코드 서명 | **당장 안 함** | Windows SmartScreen "추가 정보 → 실행", Mac 우클릭 → 열기 안내. 수익이 생기면 Windows 저가 인증서 · Apple 개발자($99/년, 공증) |
| D6 | Windows 실행기를 새 패치 기준으로 다시 빌드 | **필요 없음** | 새 패치의 Windows 부분은 코드가 한 글자도 안 바뀌었다(줄 위치만). 지금 exe 그대로 쓴다. 다음에 llama.cpp를 올릴 때 새 패치로 |

---

## 3. [완료] 패치 이식과 검증 (클라우드 세션)

- `tools/llama_patch/stigma.patch` — **Windows + Mac + Linux 한 패치**
  - 기준: llama.cpp `ba0ba54d93b25faf1e149f4ccedd3e9d84798563` (2026-09-29 master). 예전 패치도 이 커밋에 그대로 붙었다
  - Windows 부분: 예전과 같은 코드 (BCrypt)
  - Mac: CommonCrypto(하드웨어 AES) / Linux: 내장 AES-256 (시험용)
  - 파일 읽기(`llama-mmap.cpp` POSIX 쪽): 암호화 모델을 열 때 감지하고 읽는 자리에서 복호화. 암호화 모델은 O_DIRECT를 쓰지 않는다
- `tools/llama_patch/build_server.sh` — Mac(Metal 셰이더 내장)·Linux 빌드. `build_server.bat`과 같은 옵션(정적, 동적 백엔드 없음, 웹 UI·서브프로세스 없음)
- `tools/llama_patch/smoke_test.py` — 시험용 키로 빌드한 서버를 작은 무작위 모델로 확인
- **Linux에서 실제로 돌린 결과 (시험용 키, CPU)**

  ```
  [OK ] 암호화 + 맞는 키: 생성됨
  [OK ] 암호화 + 틀린 키: 로드 안 됨
  [OK ] 암호화 + 키 없음: 로드 안 됨
  [OK ] 평문 gguf: 생성됨
  [OK ] 암호화 모델과 평문 모델의 생성 결과가 같다 (온도 0 → 복호화가 바이트 단위로 정확)
  ```
  암호화는 배포에 쓰는 `model_crypt.cipher`를 그대로 썼다 → 진짜 모델 파일 형식과 같다.
- `.github/workflows/mac-gm-runtime.yml` — 손으로 돌리는 CI
  - `smoke`: macOS 14 + Ubuntu에서 위 확인을 자동으로 (진짜 키 없이)
  - `publish`(선택): Secret의 진짜 서버 절반으로 빌드 → `runtime-v1`에 `llama-server-macos-arm64` 업로드
  - **아직 한 번도 돌리지 않았다** (클라우드 세션에서는 GitHub Actions를 실행할 수 없다)

---

## 4. [PC] 할 일

1. **CI smoke 돌리기**: GitHub → Actions → "Mac GM 실행기" → Run workflow (publish 끔). macOS·Ubuntu 둘 다 초록이면 Mac에서 복호화 경로가 선다
2. **D2를 진행하기로 했으면 Secret 등록**:
   - 이름 `STIGMA_SERVER_KEY_INC`, 값 = `E:/Git_Project/stigma-train/toolchain/llama.cpp-stigma/ggml/src/stigma-key.inc` 파일 내용 그대로
     (없으면 `python stigma-gm/tools/model_crypt.py emit --tag models-v1`로 다시 만든다. 게임 쪽 `gm_key.py`도 다시 써지므로 `STIGMA_GM_KEY` Secret도 새 내용으로 갱신)
   - GitHub 계정 2단계 인증 확인
3. **publish 켜고 한 번 더** 돌려 `runtime-v1`에 `llama-server-macos-arm64`가 올라갔는지 확인
4. (선택) 개발 PC의 llama.cpp 버전 기록: `llama.cpp-stigma`에서 `git log -1` → 이 문서 3절 기준 커밋과 다르면 적어 둔다

---

## 5. 다음 작업 (결정 후 클라우드 세션에서 가능)

- `buildrelease.yml` build-mac 고치기
  - PyInstaller `--onefile` → `--windowed` `.app` (D4)
  - `runtime-v1`에서 `llama-server-macos-arm64`를 받아 `runtime/llama/llama-server`로 넣기 (`gm_server.server_binary()`가 Mac에선 이 이름을 찾는다)
  - `gm_models.json`, `gm/lore_snippets.json`, `gm_key.py`(Secret `STIGMA_GM_KEY`) 넣기 — Windows 빌드와 같게
  - 실행기가 없으면 GM 파일도 넣지 않는다 (없는 서버 때문에 모델 받기를 권하지 않게)
- `gm_server.py` Mac 확인: 데이터 폴더(`~/Library/Application Support/PROTOCOL_STIGMA`), 실행 권한(chmod +x), 격리 속성(다운로드한 앱 안의 실행기)
- 모델 기본값: 메모리 16GB 미만 Mac이면 라이트(2.1B)를 권하기
- README·릴리스 노트: Mac GM 베타, Gatekeeper 여는 법

## 6. 참고: 서명 비용 정리

| 대상 | 무료로 할 수 있는 것 | 돈이 드는 것 |
|---|---|---|
| Windows | 폴더형 배포(이미 함), 오탐 신고(Microsoft), SmartScreen은 다운로드가 쌓이면 줄어듦 | OV/EV 코드 서명 인증서 |
| Mac | 우클릭 → 열기 / 설정 → "그래도 열기" 안내 | Apple 개발자 프로그램 $99/년 (서명+공증) |
| 무료 서명 서비스 (SignPath 등) | 오픈소스 라이선스가 있는 프로젝트 대상 | 이 저장소는 LICENSE 파일이 없어 해당 없음 |
