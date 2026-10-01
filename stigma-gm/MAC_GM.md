# Mac 지원과 GM 실행기

개발 PC에서 결정하고 실행할 항목을 정리한 문서입니다. **[결정]**은 사람이 정할 것, **[PC]**는 개발 PC에서 할 일, **[완료]**는 이미 끝난 작업입니다.
보호 방식의 세부 내용은 공개 저장소에 두지 않고 개발 PC의 비공개 문서에 보관합니다.

## 1. 현재 상태

- 게임 GM은 동봉한 전용 llama-server(별도 프로세스)로 실행됩니다 (`개발/gm_server.py`). GM에 문제가 생겨도 게임은 대본으로 계속됩니다.
- Windows: 릴리스 `runtime-v1`의 `llama-server.exe` (개발 PC에서 빌드)
- macOS: 게임 쪽 준비는 끝났고, 다음 릴리스 빌드부터 GM 베타가 들어갑니다 (3절). 아직 실제 Mac에서 돌려 본 적은 없습니다.
- Mac 기기가 없어 실제 확인은 CI와 사용자 제보로만 가능합니다.

## 2. 결정할 것 [결정]

2026-10-01: 아래 표의 권장안대로 진행했습니다 (exe 유지, CI 빌드, 베타, `.app` 폴더형, 서명 안 함). 바꾸려면 다시 정합니다.

| # | 항목 | 권장 | 비고 |
|---|---|---|---|
| D1 | 실행기 형태: 별도 프로세스(exe) 유지 / 게임 안 라이브러리(DLL)로 전환 | exe 유지 | DLL로 바꿔도 서명·Mac 문제는 해결되지 않고, 실행기 오류가 게임 종료로 이어집니다 |
| D2 | Mac 실행기를 CI에서 배포용 설정으로 빌드 | 진행 | Mac 기기가 없어 CI 외에는 방법이 없습니다. 비공개 값을 저장소 Secret에 추가해야 하므로 GitHub 계정 2단계 인증을 확인합니다 |
| D3 | Mac GM을 베타로 표시 | 베타 | 실제 Mac 성능은 사용자 제보로 확인합니다. 실패하면 자동으로 대본 진행 |
| D4 | Mac 빌드를 단일 파일에서 `.app` 폴더형으로 | 진행 | 시작이 빠르고 실행기를 포함하기 쉽습니다 |
| D5 | 코드 서명 | 당장 안 함 | 경고 여는 방법을 README에 안내. 수익이 생기면 검토 |
| D6 | Windows 실행기 재빌드 | 필요 없음 | 패치의 Windows 부분은 바뀌지 않았습니다 |

## 3. 완료한 작업 [완료]

- `tools/llama_patch/stigma.patch`: Windows · macOS · Linux를 한 패치로 지원 (기준 llama.cpp `ba0ba54d93b25faf1e149f4ccedd3e9d84798563`)
- `tools/llama_patch/build_server.sh`: macOS · Linux 빌드 스크립트
- `tools/llama_patch/smoke_test.py`: 시험용 설정으로 빌드한 실행기를 작은 시험 모델로 확인하는 스크립트
- Linux에서 확인 완료: 정상 로드·생성, 잘못된 설정 거부, 개발용 모델 로드, 결과 일치
- `.github/workflows/mac-gm-runtime.yml`: macOS · Ubuntu 자동 확인, 선택 시 배포용 빌드를 `runtime-v1`에 업로드
  - 2026-10-01: 패치·빌드 스크립트·이 워크플로가 바뀌어 push되면 smoke가 저절로 돕니다. main에 합치기 전에도 브랜치에서 확인할 수 있습니다
- `buildrelease.yml`의 Mac 빌드 (2026-10-01): PyInstaller 단일 파일 → Nuitka `.app` 폴더형 (`build_exe.py` 공용), `PROTOCOL_STIGMA_mac_arm64.zip`
  - 실행기: `runtime-v1`의 `llama-server-macos-arm64`를 받습니다. 없으면 Secret `STIGMA_SERVER_KEY_INC`로 그 자리에서 빌드하고 `runtime-v1`에 올립니다. 둘 다 없으면 동적 서사 없이 빌드됩니다
  - `buildrelease.yml`은 이미 main에 있으므로 `feat/gm-events`를 골라 실행할 수 있습니다 (main 병합 불필요)
- 게임 코드 (2026-10-01)
  - `frozen_compat.user_dir`: Mac 빌드는 세이브·설정·결말 기록·진단 기록을 `~/Library/Application Support/PROTOCOL_STIGMA`에 씁니다. `.app` 안은 쓸 수 없고, 서명 없는 앱은 읽기 전용 임시 위치에서 실행되기도 합니다. 작업 폴더도 이곳으로 옮깁니다 (Finder로 열면 `/`)
  - `gm_server`: 동봉 실행기를 데이터 폴더의 `runtime/`으로 복사해 실행 권한을 주고 격리 속성을 지운 뒤 실행합니다. GPU 단계는 Metal
  - 실행기가 없는 빌드에서는 동적 서사 옵션과 추가 데이터 안내를 숨깁니다
  - 내려받기 화면: Mac은 "메모리" 기준으로 안내하고, 16GB 미만이면 가벼움에 "이 기기에 권장"을 붙입니다
  - 업데이터: Mac은 자동 교체 없이 새 버전 소식만 알립니다

## 4. 개발 PC에서 할 일 [PC]

1. "Mac GM 실행기" 워크플로의 smoke 결과(macOS · Ubuntu)를 Actions에서 확인합니다. 이 워크플로 파일이 바뀌어 push되면 저절로 실행됩니다.
2. 비공개 문서의 안내에 따라 저장소 Secret `STIGMA_SERVER_KEY_INC`를 등록합니다 (사용자가 직접 `gh secret set`).
3. 다음 릴리스 빌드(`buildrelease.yml`, 브랜치 `feat/gm-events`)를 실행하면 Mac 실행기가 빌드되어 `runtime-v1`에 올라가고 Mac 앱에 들어갑니다. 빌드 로그에 "동적 서사 포함 (실행기 포함)"이 나오는지 확인합니다.
4. 개발 PC의 llama.cpp 버전이 3절의 기준 커밋과 다르면 기록해 둡니다.

## 5. 남은 일

- 실제 Mac에서의 확인 (사용자 제보): 앱 열기, 추가 데이터 받기, Metal로 서버 준비, 턴당 시간
- 게임을 강제 종료하면 Mac에서는 실행기가 남을 수 있습니다 (Windows의 Job Object 같은 장치가 없음). 정상 종료는 같이 끕니다. 제보가 있으면 다음 실행 때 남은 서버를 정리하는 방식을 검토합니다
- Intel Mac은 지원하지 않습니다 (실행기와 앱 모두 arm64)

## 6. 서명 비용

| 대상 | 무료로 할 수 있는 것 | 비용이 드는 것 |
|---|---|---|
| Windows | 폴더형 배포(적용됨), 오탐 신고 | 코드 서명 인증서 |
| macOS | "그래도 열기" 안내 | Apple 개발자 프로그램 (연 $99, 서명·공증) |
