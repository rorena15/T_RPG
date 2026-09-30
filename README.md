# PROTOCOL: STIGMA 1막 「낙인」

사이버펑크 세계관의 생존 텍스트 RPG입니다. 플레이어는 네오 아크에서 불량 코드로 분류되어 데드존에 버려진 N-404가 되어, 폐기물 처리장에서 살아남고 첫 거점을 확보하게 됩니다. 1인 개발 프로젝트이며, 현재 1막 데모(플레이 시간 약 90분)를 배포하고 있습니다.

![PROTOCOL: STIGMA](assets/banner.png)

- 다운로드: [릴리스 페이지](../../releases/latest)
- 지원 환경: Windows 10/11, macOS (Apple Silicon)
- 언어: 한국어, 영어

## 스크린샷

| | |
|---|---|
| ![타이틀](docs/screenshots/v2/01_title.jpg) | ![탐색](docs/screenshots/v2/02_map.jpg) |
| ![이벤트](docs/screenshots/v2/03_event.jpg) | ![전투](docs/screenshots/v2/04_combat.jpg) |

## 게임 소개

5×5 구역의 폐기물 처리장을 탐색하며 식량과 장비를 모으고, 구시대 지하 방공호를 찾아 분쇄 기계 스캐브 컬렉터를 저지하면 1막이 끝납니다.

- **생존**: 이동과 탐색을 할 때마다 허기와 갈증이 줄어들며, 칸마다 탐색할 수 있는 횟수가 정해져 있습니다. 전투가 잦아지면 경계 수치가 올라 네오 아크 청소 부대가 나타납니다.
- **성장**: 보스는 시작 장비로 이길 수 없습니다. 장비를 모으고, 맵 어딘가에 있는 대장장이 발칸 게이츠의 의뢰를 완료해 강화소를 열어 무기를 강화해야 합니다.
- **선택**: 이벤트와 스토리에서 고른 행동이 성향으로 누적되고, 보스 처치 후의 선택과 합쳐져 각성 직업과 엔딩이 결정됩니다. 엔딩은 기본 3종과 히든 1종입니다.
- **동적 서사**: 옵션에서 켜면 PC에서 실행되는 로컬 AI가 탐색 중 이벤트를 매번 새로 서술하고 판정합니다. 선택지에 없는 행동을 직접 입력할 수도 있습니다. 인터넷 연결은 필요하지 않으며, 현재 Windows에서만 지원합니다.

자세한 규칙과 수치는 [게임 가이드](docs/GUIDE.md)를, 세계관·아이템·결말까지 정리한 내용은 [위키](docs/wiki/Home.md)를 참고해 주세요.

## 설치 및 실행

### Windows

1. 릴리스 페이지에서 `PROTOCOL_STIGMA_win64.zip`을 내려받습니다.
2. 압축을 풀고 `PROTOCOL_STIGMA.exe`를 실행합니다.
3. "Windows의 PC 보호" 창이 표시되면 **추가 정보 → 실행**을 선택합니다. 코드 서명이 되어 있지 않아 표시되는 경고입니다.

### macOS

1. 릴리스 페이지에서 `PROTOCOL_STIGMA_mac.tar.gz`를 내려받습니다.
2. 터미널에서 다음 명령을 실행합니다.
   ```bash
   tar -xzf PROTOCOL_STIGMA_mac.tar.gz
   chmod +x PROTOCOL_STIGMA
   ./PROTOCOL_STIGMA
   ```
3. "확인되지 않은 개발자" 경고가 표시되면 **시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기**를 선택합니다.

macOS에서는 동적 서사를 아직 지원하지 않으며, 기본 대본으로 진행됩니다.

### 소스 코드로 실행 (Python 3.10 이상)

```bash
pip install pygame-ce rich colorama cryptography
cd 개발
python Main.py
```

## 조작

메뉴와 선택지는 방향키 또는 마우스로 선택할 수 있습니다.

| 맵 | | 전투 | |
|---|---|---|---|
| W A S D | 이동 | Q | 주무기 공격 |
| F | 탐색 | E | 바리케이드 |
| I | 인벤토리 | R | 패킷 우회 |
| E | 발칸 게이츠 · 강화소 | F | 보조 화기 |
| J | 항법 일지 | Z / C | 스킬 |
| 1 ~ 0 | 퀵슬롯 | X | 후퇴 |
| F5 | 저장 | I | 소모품 |

전체 조작은 [게임 가이드](docs/GUIDE.md#조작)에 정리되어 있습니다.

## 시스템 요구 사항

| | 최소 | 권장 |
|---|---|---|
| OS | Windows 10 64비트 / macOS 12 (Apple Silicon) | Windows 10·11 64비트 |
| CPU | 2코어 | 4코어 |
| 메모리 | 4GB | 8GB |
| 저장 공간 | 300MB | 300MB |
| 해상도 | 1366×768 | 1920×1080 |

### 동적 서사 (선택 사항, Windows)

**옵션 → 동적 서사**에서 켤 수 있으며, 처음 켤 때 추가 데이터를 내려받습니다.

| 모드 | 추가 데이터 | 그래픽 메모리 | 메모리 |
|---|---|---|---|
| 가벼움 | 1.5GB | 2GB 이상 | 8GB |
| 고품질 | 4.9GB | 6GB 이상 (GTX 1660, RTX 2060급) | 8GB (권장 16GB) |

- AVX2를 지원하는 CPU가 필요합니다 (Intel 4세대, AMD 라이젠 이후).
- RTX 3060 기준으로 한 턴당 고품질은 2~2.5초, 가벼움은 1.2~1.4초가 걸립니다.
- 그래픽 메모리가 부족하면 CPU로 동작하며 속도가 크게 느려집니다. 이 경우 가벼움 모드를 권장합니다.

## 문제 해결

| 증상 | 해결 방법 |
|---|---|
| 백신 프로그램이 실행 파일을 차단함 | 오탐입니다. 게임 폴더를 예외 목록에 추가하거나, 소스 코드로 실행해 주세요. |
| 동적 서사를 켰는데 대본으로 진행됨 | 설치 후 첫 실행은 준비에 수십 초가 걸리며, 그동안은 대본으로 진행됩니다. 영어 모드에서는 대본으로만 진행됩니다. |
| 소리가 나지 않음 | 옵션의 음소거와 음량 설정을 확인해 주세요. |
| 저장 파일 위치 | 게임 폴더의 `stigma_save.json` (설정은 `settings.json`) |

버그는 [Issues](../../issues)로 제보해 주세요. 게임 폴더의 `diag/` 안에 있는 최근 `.sdg` 파일을 함께 첨부해 주시면 원인 파악에 도움이 됩니다. 이 파일은 오류 기록을 암호화한 것으로, 개발자만 열람할 수 있습니다.

## 크레딧

- 제작: rorena15
- 음악: Christian Fernando Perucchi (Godot TPS Demo), HorrorPen "Loop - House in a Forest" — CC BY 3.0
- 효과음: Godot TPS Demo (Juan Linietsky, Fernando Miguel Calabró) — CC BY 3.0 / Kenney, Freesound, uisfx — CC0
- 아이콘: game-icons.net (Lorc, Delapouite, Sbed, Rihlsul) — CC BY 3.0
- 글꼴: D2Coding, Noto Emoji — SIL OFL 1.1
- 동적 서사: Kakao Kanana 1.5 기반 파인튜닝 모델 (Apache 2.0), llama.cpp (MIT)
- 장면 일러스트: 로컬 Stable Diffusion XL로 제작

전체 출처와 라이선스 원문은 게임 내 **옵션 → 크레딧 · 라이선스** 또는 [`assets/licenses/`](assets/licenses/)에서 확인할 수 있습니다.

## 개발 문서

- 빌드 및 코드 구조: [개발/BUILD.md](개발/BUILD.md)
- 동적 서사 모델: [stigma-gm/README.md](stigma-gm/README.md)
- 기획 문서: [기획/](기획/) (다음 버전 계획: [v2.1 개발안](기획/v2.1_개발안.md))
- 변경 내역: [RELEASE_NOTES.md](RELEASE_NOTES.md)

2막 이후에는 거점 운영과 습격, 방어구·장신구 강화, 진영 평판, 네오 아크 잠입 등을 계획하고 있습니다.
