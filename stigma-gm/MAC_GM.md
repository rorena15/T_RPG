# Mac 지원과 GM 실행기

개발 PC에서 결정하고 실행할 항목을 정리한 문서입니다. **[결정]**은 사람이 정할 것, **[PC]**는 개발 PC에서 할 일, **[완료]**는 이미 끝난 작업입니다.
보호 방식의 세부 내용은 공개 저장소에 두지 않고 개발 PC의 비공개 문서에 보관합니다.

## 1. 현재 상태

- 게임 GM은 동봉한 전용 llama-server(별도 프로세스)로 실행됩니다 (`개발/gm_server.py`). GM에 문제가 생겨도 게임은 대본으로 계속됩니다.
- Windows: 릴리스 `runtime-v1`의 `llama-server.exe` (개발 PC에서 빌드)
- macOS: GM 없음, 대본으로만 진행. 실행기 패치가 Windows 전용이었고, Mac 빌드에 GM 파일이 포함되지 않았기 때문입니다.
- Mac 기기가 없어 실제 확인은 CI와 사용자 제보로만 가능합니다.

## 2. 결정할 것 [결정]

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
- `.github/workflows/mac-gm-runtime.yml`: macOS · Ubuntu 자동 확인, 선택 시 배포용 빌드를 `runtime-v1`에 업로드 (아직 실행 전)

## 4. 개발 PC에서 할 일 [PC]

1. GitHub Actions에서 "Mac GM 실행기"를 publish 끈 상태로 실행해 macOS · Ubuntu 확인이 통과하는지 봅니다.
2. D2를 진행한다면, 비공개 문서의 안내에 따라 저장소 Secret `STIGMA_SERVER_KEY_INC`를 등록합니다.
3. publish를 켜고 다시 실행해 `runtime-v1`에 `llama-server-macos-arm64`가 올라갔는지 확인합니다.
4. 개발 PC의 llama.cpp 버전이 3절의 기준 커밋과 다르면 기록해 둡니다.

## 5. 다음 작업 (결정 후)

- `buildrelease.yml`의 Mac 빌드: `.app` 폴더형으로 바꾸고, 실행기와 GM 파일을 포함합니다. 실행기가 없으면 GM 파일도 넣지 않습니다.
- `gm_server.py`의 Mac 동작 확인 (데이터 폴더, 실행 권한, 격리 속성)
- 메모리 16GB 미만 Mac에서는 가벼움 모드를 권장
- README와 릴리스 노트에 Mac GM 베타 안내

## 6. 서명 비용

| 대상 | 무료로 할 수 있는 것 | 비용이 드는 것 |
|---|---|---|
| Windows | 폴더형 배포(적용됨), 오탐 신고 | 코드 서명 인증서 |
| macOS | "그래도 열기" 안내 | Apple 개발자 프로그램 (연 $99, 서명·공증) |
