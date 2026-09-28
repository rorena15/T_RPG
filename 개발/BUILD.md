# 개발 노트

플레이어 안내는 저장소 루트 [README](../README.md)에 있다. 이 문서는 개발·빌드용이다.

## 파일 구조 (`개발/`)

```
개발/
├── Main.py              # 메인 루프 · 상태창 · 그리드 UI
├── combat.py            # 전투 시스템 — 공격/방어/스킬 훅 통합
├── skills.py            # 3계층 스킬 시스템 (특수 / 특화 / 보조)
├── player.py            # 플레이어 데이터 · 스탯 연산 · 장비 계산
├── story.py             # 각성 이벤트 · 엔딩 · 2막 티저
├── quest.py             # 돌발 퀘스트 · 랜덤 이벤트 · 행상인
├── gm_bridge.py         # 랜덤 이벤트 · 빈 탐색을 로컬 GM이 판정·서술하도록 연결
├── event_view.py        # GM 이벤트 전용 화면 (장면 그림 + 이야기 기록, 한글 입력)
├── gm/                  # 로컬 GM 런타임 (stigma-gm/engine에서 자동 복사, 직접 수정 금지)
├── sound.py             # BGM / 효과음 관리 (pygame-ce)
├── map.py               # 5×5 그리드 · 이동 · 타일 수색 시스템
├── core.py              # 장비 DB 조회 · 세이브 파일 관리
├── constants.py         # 게임 상수 · 전투 균형값 · 장비 계산 상수
├── db_init.py           # SQLite 초기화 스크립트
├── ui.py                # 공통 UI 유틸리티 (타이핑 출력, 헤더 등)
├── i18n.py              # 다국어 지원 (ko / en)
├── sys_log.py           # 시스템 로그 · 에러 추적
├── database.json        # 서사 텍스트 · 소모품 · 이벤트 데이터
├── master_formulas.json # 데미지 · 스케일링 · 확률 밸런스 수식
└── locales/
    ├── ko.json          # 한국어 텍스트 (524키)
    └── en.json          # 영어 텍스트 (524키)
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
  고품질(약 4.6GB) / 가벼움(약 1.4GB) / 나중에. 설정 → 6. 추가 데이터 받기로도 받을 수 있다
  - 받는 곳: 이 저장소의 GitHub 릴리스 `models-v1` (8B는 파일당 2GiB 제한 때문에 3조각). 주소와 sha256은 `개발/gm_models.json`
  - 저장 위치: `%LOCALAPPDATA%\PROTOCOL_STIGMA\models` (맥 `~/Library/Application Support/PROTOCOL_STIGMA`)
  - 끊겨도 이어받고, 조각과 전체를 sha256으로 검증한다. 실행기 로그는 같은 폴더의 `server.log`
- 게임을 시작하면 서버를 백그라운드로 띄우고 예열한다. 설치 후 첫 실행은 GPU 셰이더 컴파일로 수십 초 걸릴 수 있고,
  그동안 이벤트는 대본으로 진행된다. 두 번째부터는 2~4초 안에 준비된다
- 개발 환경에서 동봉 실행기나 데이터가 없으면 Ollama(`stigma-gm`, `stigma-gm-lite`)를 대신 쓴다. 모델 만드는 법은 [stigma-gm/README.md](../stigma-gm/README.md)
- GM 런타임(`gm/`)은 `stigma-gm/tools/sync_to_game.py`로 복사된다. 고칠 때는 원본(`stigma-gm/engine`)을 고친다

## 동적 서사 빌드 (exe에 실행기 넣기)

GM 모델 코드·도구·문서는 이 저장소의 `stigma-gm/`에 있다 (학습 데이터 `stigma-gm/data/`는 비공개). 파일 위치는 `stigma-gm/DATA_LAYOUT.md`.

배포 모델은 암호화돼 있고, 게임은 복호화 패치를 넣은 llama-server로만 연다 (모델 보호, stigma-gm EXPERIMENTS.md "모델 보호").
키는 둘로 나뉜다. 한쪽은 서버 exe 안에, 다른 쪽은 `개발/gm_key.py`(gitignore)에 있고 게임이 서버 stdin으로 넘긴다. 둘 다 공개 저장소에 없다.

1. 실행기 빌드와 복사 (개발 PC에서): `stigma-gm/tools/llama_patch/build_server.bat` → `cd 개발 && python install_llama_runtime.py`
   → `개발/runtime/llama/llama-server.exe` 하나 (Vulkan·CPU 백엔드를 정적으로 묶은 빌드, git에 넣지 않음)
2. 키 절반 만들기: `python stigma-gm/tools/model_crypt.py emit --tag models-v1` → `개발/gm_key.py`
3. exe 빌드: `cd 개발 && python build_exe.py` → `개발/dist/PROTOCOL_STIGMA.exe` (Nuitka onefile. PyInstaller는 소스가 거의 그대로 복원돼서 쓰지 않는다)
   - 경로 호환은 `개발/frozen_compat.py` (Main.py 첫 import): Nuitka에서도 `sys.frozen`/`sys._MEIPASS`/`sys.executable`이 PyInstaller와 같게 잡힌다
4. CI(`buildrelease.yml`)도 `build_exe.py`를 쓴다. 필요한 것:
   - 릴리스 `runtime-v1`에 `llama-server.exe` (서버 exe는 어차피 게임에 들어가므로 공개 자산이어도 노출 범위가 같다)
   - 저장소 Secret `STIGMA_GM_KEY` = `개발/gm_key.py` 내용. 없으면 동적 서사 없이 빌드된다
5. 모델 올리기: `stigma-gm/tools/prepare_model_release.py`가 만든 조각(암호화 파일만 받는다)을 릴리스 `models-v1`에 올린다.
   모델을 바꾸면 새 태그(`models-v2`)로 **키도 새로 만들고**(genkey) 서버를 다시 빌드한다. 크기가 같은 모델을 같은 키로 암호화하면 안 된다
6. 맥용은 아직 없다 (맥 빌드는 PyInstaller 그대로, 동적 서사 없음)

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
