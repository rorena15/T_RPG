# 개발 노트

플레이어 안내는 저장소 루트 [README](../README.md)에 있다. 이 문서는 개발·빌드용이다.

## 파일 구조 (`개발/`)

```
개발/
├── Main.py              # 진입점 · 타이틀/옵션 메뉴 · 맵 루프
├── gui.py               # pygame 창 (터미널 흉내 + 그림 화면 관리), 글 화면 선택지의 방향키·마우스
├── event_view.py        # 그림 화면 틀 (장면 그림 + 글 칸, 선택지·입력·발밑 버튼·퀵슬롯·아이콘)
├── map_view.py          # 맵 화면 (2.5D 미니맵, 이동 연출, WASD/방향키/미니맵 클릭)
├── combat_view.py       # 전투 화면 (행동 버튼 격자, 퀵슬롯)
├── inventory_view.py    # 인벤토리 · 강화소 화면 (탭 Tab, 퀵슬롯 연결)
├── screens.py           # 공용 메뉴 · 일지 · 긴 글 보기 (크레딧·라이선스)
├── intro_view.py        # 오프닝
├── download_view.py     # 동적 서사 추가 데이터 받기 화면
├── credits.py           # 옵션 → 크레딧 · 라이선스 (assets/licenses/)
├── scene_art.py         # 장면 그림 고르기 · 게임 속 시간·날씨
├── combat.py            # 전투 (행동 · 적 종류 · 보스 · 퀵슬롯)
├── skills.py            # 3계층 스킬 (특수 / 특화 / 보조)
├── player.py            # 플레이어 · 스탯 · 장비 계산 · 퀵슬롯 · 소모품 사용
├── upgrade.py           # 주무기 강화 · 내구도 · 수리
├── forge.py             # 발칸 게이츠 퀘스트 · 강화소
├── map.py               # 5×5 그리드 · 이동 · 타일 수색 · 강화소 위치
├── story.py             # 스토리 세션 · 각성 · 엔딩 · 2막 티저
├── quest.py             # 돌발 퀘스트 · 랜덤 이벤트 · 행상인
├── gm_bridge.py         # 랜덤 이벤트 · 빈 탐색을 로컬 GM이 판정·서술하도록 연결
├── gm_server.py         # 동봉 llama-server 실행 · 모델 받기
├── gm/                  # 로컬 GM 런타임 (stigma-gm/engine에서 자동 복사, 직접 수정 금지)
├── sound.py             # BGM · 효과음 · 날씨 환경음 (pygame-ce)
├── core.py              # 장비 DB 조회 · 세이브 · 설정
├── constants.py         # 게임 상수 · 전투 균형값 · 적 종류 · 무기 효과음 분류
├── i18n.py              # 다국어 (ko / en), 한국어 조사 자동 선택
├── playtime.py          # 플레이 시간 (세이브·엔딩·게임 오버, 판이 끝나면 진단 기록에 요약)
├── diag.py              # 진단 기록 (개발자 공개키로 암호화해 diag/에)
├── sys_log.py           # 로그 · 호출 추적 → diag
├── updater.py           # GitHub 릴리스 자동 업데이트
├── database.json        # 서사 텍스트 · 소모품 · 이벤트 데이터
├── master_formulas.json # 데미지 · 스케일링 · 확률 밸런스 수식
├── art_gen/             # 장면 그림 만들기 (로컬 SDXL)
├── tools/balance/       # 밸런스 검증 봇 · 실행기 (난이도별 승률 표, README 참고)
├── tools/diag/          # 진단 기록 키 만들기 · 읽기 (diag_tool.py)
├── validate_i18n.py     # 언어 파일 검증 (키 일치 · 코드 속 한글 금지)
└── locales/
    ├── ko.json          # 한국어 (825키)
    └── en.json          # 영어 (825키)
```

## 동적 서사 (로컬 GM) 내부

- 대상: 탐색 중 랜덤 이벤트와 빈 탐색. 스토리 세션, 전투, 행상인, 자원 파밍, 보스, 엔딩은 대본 그대로다
- 게임 화면과 설정 문구에는 "GM"이라는 말을 쓰지 않는다. 설정값은 `settings.json`의 `gm_mode`
- 대본 선택지 판정: 성공하면 대본 보상, 대성공이면 고철 1.5배, 실패하면 보상 없음.
  대가(HP 손실 등)는 항상 치르고, 피해는 대본 대가와 GM 피해 중 큰 쪽. 성향은 +1(대성공 +2)
- GM도 주사위도 화면에 드러나지 않는다. 플레이어는 행동과 결과(서술, HP·보상 변화)만 본다
- 전용 이벤트 화면(`event_view.py`): 왼쪽은 장면 그림과 생체 지표 HUD, 오른쪽은 이야기 기록. 서술은 타자 치듯 나오고 아무 키나 누르면 바로 다 보인다
- 이어서 행동: 결과 뒤 같은 장면에서 최대 2번 더 행동할 수 있다. 매번 턴이 흘러 허기·갈증이 준다
- GM이 생각하는 동안에도 화면은 계속 움직인다(백그라운드 스레드). 기다림은 깜빡이는 커서로만 보인다
- GM은 한국어 전용이다. 영어 모드이거나 서버·모델이 없으면 대본으로 진행한다
- GM이 실패하면 같은 화면에서 조용히 대체한다(대본 선택지는 대본 결과, 직접 행동은 담담한 한 줄)

| 모드 | 모델 | 저장 공간 | GPU 메모리 | 실제 RAM | 한 턴 (RTX 3060 실측) |
|---|---|---|---|---|---|
| 고품질 (기본) | Kanana 8B | 4.6GB | 5.0GB | 0.45GB | 2~2.5초 |
| 가벼움 | Kanana 2.1B | 1.4GB | 1.9GB | 0.28GB | 1.2~1.4초. 가끔 어색한 묘사 |
| 끄기 | 없음 | 0 | 0 | 0 | 대본 |
(동봉 llama-server, Vulkan, `-lm none` 기준. 서버는 게임과 함께 켜지고 꺼진다)

- 매 턴 장면·행동·소지품과 맞는 원작 설정 조각(`gm/lore_snippets.json`)을 GM에게 함께 준다. 안 가진 장비는 넣지 않고, T0·T1 장비 지급은 막는다
- **설치할 것 없음.** 실행기(llama.cpp `llama-server`, Vulkan 빌드)가 게임에 들어 있다. NVIDIA·AMD·Intel GPU 모두 지원, GPU로 못 띄우면 CPU로 돌린다
- **모델은 게임에 넣지 않는다.** 동적 서사가 켜져 있는데 데이터가 없으면 시작할 때
  "인게임에서 더욱 생동감 있는 플레이를 위해서는 추가 데이터가 필요합니다. 다운로드 하시겠습니까?"를 띄운다.
  고품질(약 4.6GB) / 가벼움(약 1.4GB) / 나중에. 옵션 → 추가 데이터 받기로도 받을 수 있다
  - 받는 곳: 이 저장소의 GitHub 릴리스 `models-v1` (8B는 파일당 2GiB 제한 때문에 3조각). 주소와 sha256은 `개발/gm_models.json`
  - 저장 위치: `%LOCALAPPDATA%\PROTOCOL_STIGMA\models` (맥 `~/Library/Application Support/PROTOCOL_STIGMA`)
  - 끊겨도 이어받고, 조각과 전체를 sha256으로 검증한다. 실행기 로그는 같은 폴더의 `server.log`
- 게임을 시작하면 서버를 백그라운드로 띄우고 예열한다. 설치 후 첫 실행은 GPU 셰이더 컴파일로 수십 초 걸릴 수 있고,
  그동안 이벤트는 대본으로 진행된다. 두 번째부터는 2~4초 안에 준비된다
- 개발 환경에서 동봉 실행기나 데이터가 없으면 Ollama(`stigma-gm`, `stigma-gm-lite`)를 대신 쓴다. 모델 만드는 법은 [stigma-gm/README.md](../stigma-gm/README.md)
- GM 런타임(`gm/`)은 `stigma-gm/tools/sync_to_game.py`로 복사된다. 고칠 때는 원본(`stigma-gm/engine`)을 고친다

## 동적 서사 빌드 (exe에 실행기 넣기)

GM 모델 코드·도구·문서는 `stigma-gm/`에 있다 (학습 데이터는 비공개). 배포 모델은 보호되어 있어 전용 실행기로만 열 수 있다.
빌드에 필요한 비공개 파일은 저장소에 없으며, 개발 PC의 비공개 문서를 따른다.

1. 실행기 빌드 (개발 PC): `stigma-gm/tools/llama_patch/build_server.bat` → `cd 개발 && python install_llama_runtime.py` → `개발/runtime/llama/llama-server.exe` (git에 넣지 않음)
2. 비공개 파일 생성: `python stigma-gm/tools/model_crypt.py emit --tag models-v1`
3. exe 빌드: `cd 개발 && python build_exe.py` → `개발/dist/` 폴더형(Nuitka `--standalone`, 릴리스는 `*_win64.zip`). `--onefile`은 1.9.x 업데이터 호환용
   - 경로 호환은 `개발/frozen_compat.py` (Main.py 첫 import)
4. CI(`buildrelease.yml`)도 `build_exe.py`를 쓴다. 릴리스 `runtime-v1`의 실행기와 저장소 Secret `STIGMA_GM_KEY`가 필요하며, 없으면 동적 서사 없이 빌드된다
5. 모델 올리기: `stigma-gm/tools/prepare_model_release.py`가 만든 조각을 릴리스 `models-v1`에 올린다. 모델을 바꾸면 새 태그로 다시 준비한다
6. macOS: [stigma-gm/MAC_GM.md](../stigma-gm/MAC_GM.md) 참고 (게임 쪽 Mac 빌드는 아직 동적 서사 없음)

## 이벤트 화면 장면 그림

이벤트·탐색 화면 왼쪽 그림은 로컬 SDXL로 만든 일러스트 라이브러리다 (`assets/scenes/<장면>/`, 약 160장). 그림이 없으면 코드로 그린 장면으로 돌아간다.

- 만들기: `개발/art_gen/gen_scenes.py` (학습 venv에서 `txt` → 사람이 고르기 → `pick` → `layers`)
  - 화풍: 거친 붓 터치의 디지털 페인팅. 색면 밑그림 + img2img로 모든 장면의 톤을 맞춘다
  - 장면 55종: 지형(쓰레기 바다/무너진 도시/경계), 멸망 전 랜드마크 12종, 실내, 원경(네오 아크), 적, 인물, 이벤트
  - 시간 5 × 날씨 5 조합. 공기는 늘 스모그·황사로 탁하다 (낮도 빛이 조금 많을 뿐)
  - 금지: 글자(깨진다), NPC 얼굴(가면·후드·역광·사물로 가린다, 성별 비공개), 기계 괴수의 유기체 요소(원작 반전)
  - 모델: SDXL base 1.0 (OpenRAIL++-M) + sdxl-vae-fp16-fix (MIT). 깊이: Depth Anything V2 **Small**만 (Apache-2.0, Base/Large는 비상업)
- 깊이 패럴랙스: 그림 한 장을 먼/중간/가까운 3층으로 나눠(`*.mid.webp`, `*.near.webp`) 시간 흐름과 마우스에 따라 다르게 움직인다. 뒤 층의 앞 물체 자리는 메워 둬서 두 번 보이지 않는다
- 고르는 규칙 (`개발/scene_art.py`): 이벤트 전용 그림 → 이벤트 문장의 말(병원, 들개, 계단 …) → 장소 → 원경. 게임 속 시간(턴으로 흐름)·날씨(몇 턴씩 유지)와 맞는 그림, 안 본 그림 우선. 적은 위협이 있을 때만, 실내는 실내일 때만. 최근 그림 반복 없음
- AI 생성 그림이다. Steam 등에 올릴 때는 AI 사용 신고 항목에 체크한다

## 진단 기록 (개발자만 읽음)

- 로그·오류·크래시·호출 추적은 게임 폴더의 `diag/*.sdg`에 암호화해 쓴다 (실행 1회 = 파일 1개). 예전 평문 `log.txt`·`events` 표는 게임을 켤 때 지운다
- 처음 한 번 (개발 PC): `python tools/diag/diag_tool.py genkey` → 공개키가 `diag_pubkey.py`에 채워진다 → 커밋. 개인키는 저장소 밖에 두고 백업한다
- 공개키가 비어 있으면 진단 기록을 쓰지 않는다
- 제보받은 파일 읽기: `python tools/diag/diag_tool.py read 받은파일.sdg` (`--kind log`/`trace`/`stat`, `--json`)
- `stat`: 한 판이 끝날 때(클리어·사망·시간 초과) 결과, 플레이 시간, 턴, 난이도, 처치 수, GM 모드. 실제 플레이 분량을 재는 근거
- 진단 파일은 게임이 지우지 않는다 (한 판 약 250KB)

## 에셋 출처 관리

- 게임 안 크레딧은 `assets/licenses/CREDITS.txt` 하나만 고치면 된다 (옵션 → 크레딧 · 라이선스가 그대로 보여 준다). 라이선스 전문은 `assets/licenses/*.txt`, 새 종류를 넣으면 `credits.py`의 `LICENSES`에 한 줄
- 음원: `assets/sfx/CREDITS.md` (파일별 원본), 아이콘: `assets/icons/CREDITS.md` (game-icons.net, 흰 실루엣 PNG → 게임이 크기·색을 입힌다)
- CC BY 에셋을 더하면 CREDITS.txt · 해당 CREDITS.md · README 크레딧을 같이 고친다

## 문서

- 플레이어용: 루트 [README](../README.md), [게임 가이드](../docs/GUIDE.md), [RELEASE_NOTES](../RELEASE_NOTES.md)
- 스크린샷: `docs/screenshots/v2/` (README가 쓴다)
- 기획: `기획/` — 다음 버전 [v2.1 개발안](../기획/v2.1_개발안.md), 정면 뷰 목업 `기획/정면뷰_목업/`
