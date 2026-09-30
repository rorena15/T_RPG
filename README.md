# PROTOCOL: STIGMA 1막 「낙인」

사이버펑크 세계관의 생존 텍스트 RPG입니다. 네오 아크에서 불량 코드로 분류돼 데드존에 버려진 N-404가 되어, 폐기물 처리장에서 살아남고 첫 거점을 잡을 때까지를 다룹니다. 혼자 만들고 있는 개인 프로젝트이고, 지금은 1막 데모(약 90분)까지 나와 있습니다.

![PROTOCOL: STIGMA](assets/banner.png)

다운로드: [릴리스 페이지](../../releases/latest) (Windows 10/11, macOS Apple Silicon / 한국어, 영어)

## 스크린샷

| | |
|---|---|
| ![타이틀](docs/screenshots/v2/01_title.jpg) | ![탐색](docs/screenshots/v2/02_map.jpg) |
| ![이벤트](docs/screenshots/v2/03_event.jpg) | ![전투](docs/screenshots/v2/04_combat.jpg) |

## 게임 소개

5×5 칸짜리 폐기물 처리장을 돌아다니며 먹을 것과 장비를 모으고, 구시대 지하 방공호를 찾아 스캐브 컬렉터라는 분쇄 기계를 막아 내면 1막이 끝납니다.

- 움직이고 뒤질 때마다 허기와 갈증이 줄고, 칸마다 뒤질 수 있는 횟수가 정해져 있습니다. 싸움이 잦아지면 경계가 올라가 네오 아크 청소 부대가 끼어듭니다.
- 보스는 시작 장비로는 못 이깁니다. 파밍하고, 맵 어딘가에 있는 대장장이 발칸 게이츠를 찾아 강화소를 되살려 무기를 올려야 합니다.
- 이벤트와 스토리 세션에서 고른 행동이 성향으로 쌓이고, 보스를 쓰러뜨린 뒤의 선택까지 합쳐 각성 직업과 엔딩이 정해집니다. 엔딩은 기본 3종에 히든 1종입니다.
- 동적 서사 옵션을 켜면 PC에서 도는 로컬 AI가 탐색 중 사건을 그때그때 새로 써 줍니다. 선택지에 없는 행동을 직접 입력할 수도 있습니다. 인터넷은 필요 없고, 지금은 Windows에서만 됩니다.

세계관이나 규칙이 더 궁금하면 [게임 가이드](docs/GUIDE.md)를 보면 됩니다.

## 설치

**Windows**

`PROTOCOL_STIGMA_win64.zip`을 받아 압축을 풀고 `PROTOCOL_STIGMA.exe`를 실행합니다. 코드 서명을 안 해서 "Windows의 PC 보호" 창이 뜨는데, 추가 정보 → 실행을 누르면 됩니다.

**macOS**

`PROTOCOL_STIGMA_mac.tar.gz`를 받아 터미널에서 실행합니다.

```bash
tar -xzf PROTOCOL_STIGMA_mac.tar.gz
chmod +x PROTOCOL_STIGMA
./PROTOCOL_STIGMA
```

"확인되지 않은 개발자"로 막히면 시스템 설정 → 개인정보 보호 및 보안에서 "그래도 열기"를 누르세요. Mac에서는 동적 서사 없이 기본 대본으로 진행됩니다.

**소스로 실행** (Python 3.10 이상)

```bash
pip install pygame-ce rich colorama cryptography
cd 개발
python Main.py
```

## 조작

이동은 WASD, 탐색 F, 인벤토리 I, 일지 J, 저장 F5입니다. 전투에서는 Q 공격, E 바리케이드, R 패킷 우회, F 보조 화기, Z/C 스킬, X 후퇴를 씁니다. 숫자키 1~0은 퀵슬롯이라 등록해 둔 소모품을 바로 쓸 수 있습니다. 메뉴와 선택지는 방향키나 마우스로 골라도 됩니다.

전체 키는 [게임 가이드](docs/GUIDE.md#조작)에 정리해 뒀습니다.

## 사양

| | 최소 | 권장 |
|---|---|---|
| OS | Windows 10 64비트 / macOS 12 (Apple Silicon) | Windows 10·11 64비트 |
| CPU | 2코어 | 4코어 |
| 메모리 | 4GB | 8GB |
| 저장 공간 | 300MB | 300MB |
| 해상도 | 1366×768 | 1920×1080 |

동적 서사를 쓰려면 추가 데이터를 받아야 하고 그래픽 카드가 좀 필요합니다. 옵션 → 동적 서사에서 켜면 처음에 받을지 물어봅니다.

| 모드 | 추가 데이터 | 그래픽 메모리 | 메모리 |
|---|---|---|---|
| 가벼움 | 1.5GB | 2GB 이상 | 8GB |
| 고품질 | 4.9GB | 6GB 이상 (RTX 2060, GTX 1660 급) | 8GB, 권장 16GB |

AVX2를 지원하는 CPU가 필요합니다(인텔 4세대, 라이젠 이후). RTX 3060 기준으로 한 턴에 고품질 2~2.5초, 가벼움 1.2~1.4초 정도 걸립니다. 그래픽 메모리가 모자라면 CPU로 돌아가는데 꽤 느려서, 그럴 땐 가벼움을 추천합니다.

## 문제가 생기면

- 백신이 exe를 막으면 오탐입니다. 게임 폴더를 예외로 넣어 주세요. 찜찜하면 소스로 실행해도 됩니다.
- 동적 서사를 켰는데 대본만 나오면, 설치 후 첫 실행은 준비에 수십 초가 걸려서 그렇습니다. 영어 모드에서도 대본으로 나옵니다.
- 세이브는 게임 폴더의 `stigma_save.json`, 설정은 `settings.json`에 있습니다.

버그는 [Issues](../../issues)에 남겨 주세요. 게임 폴더 `diag/` 안의 최근 `.sdg` 파일을 같이 올려 주시면 원인을 찾기가 훨씬 쉽습니다. 오류 기록을 암호화해 둔 파일이라 저만 열어 볼 수 있습니다.

## 크레딧

만든 사람: rorena15

- 음악: Christian Fernando Perucchi (Godot TPS Demo), HorrorPen "Loop - House in a Forest" (CC BY 3.0)
- 효과음: Godot TPS Demo (Juan Linietsky, Fernando Miguel Calabró, CC BY 3.0), Kenney, Freesound, uisfx (CC0)
- 아이콘: game-icons.net의 Lorc, Delapouite, Sbed, Rihlsul (CC BY 3.0)
- 글꼴: D2Coding, Noto Emoji (SIL OFL 1.1)
- 동적 서사: Kakao Kanana 1.5 파인튜닝 모델 (Apache 2.0), llama.cpp (MIT)
- 장면 그림은 로컬 Stable Diffusion XL로 만들었습니다.

전체 출처와 라이선스 원문은 게임 안 옵션 → 크레딧 · 라이선스, 또는 [`assets/licenses/`](assets/licenses/)에 있습니다.

## 개발 관련

- 빌드와 코드 구조: [개발/BUILD.md](개발/BUILD.md)
- 동적 서사 모델: [stigma-gm/README.md](stigma-gm/README.md)
- 기획 문서: [기획/](기획/), 다음 버전 계획은 [v2.1 개발안](기획/v2.1_개발안.md)
- 변경 내역: [RELEASE_NOTES.md](RELEASE_NOTES.md)

2막부터는 거점 운영과 습격, 방어구·장신구 강화, 진영 평판, 네오 아크 잠입 같은 걸 생각하고 있습니다.
