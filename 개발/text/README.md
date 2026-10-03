# 게임 글

게임에 나오는 글은 모두 이 폴더에 있습니다. 파일을 고치고 게임을 다시 켜면 바로 반영됩니다. 빌드(`build_exe.py`)는 이 폴더를 통째로 넣습니다.

| 파일 | 내용 | 영어 |
|---|---|---|
| `ko.json` | 화면·알림·안내 문구 (지도 화면, 방공호 힌트, 줍기 알림, 전투 기록, 결말 문장 등) | `en.json` (같은 키) |
| `archive_ko.json` | 기록 보관소 글 (일기 조각, 장면 이야기, 히든 일지) | `archive_en.json` |
| `story.json` | 스토리 세션 7개, 랜덤 이벤트 21개, 빈 탐색 풍경 문장 25개, 소모품 이름 | 같은 항목의 `_en` 칸 (`title_en`, `text_en`, `AMBIENT_LORE_EN` 등) |
| `equipment.json` | 장비 463개의 이름·설명 | 같은 항목의 `name_en`, `description_en` |

수치(장비 위력·등급, 소모품 회복량, 행상인 가격)는 글이 아니라서 코드와 `story.json`의 숫자 칸에 따로 있습니다.

## 고칠 때

- `{title}`, `{dir}`, `{n}`처럼 중괄호로 싼 말은 게임이 값을 넣는 자리입니다. 지우거나 이름을 바꾸지 마세요.
- 줄바꿈은 `\n`, 글 안의 큰따옴표는 `\"`로 씁니다. 쉼표나 따옴표가 하나 빠지면 파일 전체를 읽지 못합니다.
- `을(를)`, `이(가)`처럼 쓰면 게임이 앞 글자를 보고 알맞은 조사 하나로 바꿉니다.
- 키(콜론 앞의 이름)는 바꾸지 마세요. 코드가 그 이름으로 글을 찾습니다.
- 소모품 이름은 `story.json`의 `CONSUMABLES_DB` 한 곳만 고치면 행상인 목록과 장비 DB에도 같이 들어갑니다.

## 고친 뒤 검사

`개발` 폴더에서:

```
python validate_i18n.py
```

키가 빠졌거나 파일이 깨졌으면 알려 줍니다. 기록 보관소 글은 `python tests/test_archive.py`도 돌려 주세요.

## 기록 보관소 글을 원고로 고치기

JSON이 불편하면 원고 파일로 고칠 수 있습니다.

```
python tools/archive_text.py export ko   # archive_ko.json → docs/기획/기록보관소_원고_ko.md
(원고 파일을 고친다)
python tools/archive_text.py import ko   # 원고 → archive_ko.json
```

## 자주 고치는 키

| 키 | 어디에 나오나 |
|---|---|
| `bunker_hint_0` ~ `bunker_hint_2` | 방공호 힌트 (멀리 / 중간 / 가까이). 지금은 초안 |
| `forge_hint_node` | 12턴이 지나도 발칸을 못 만났을 때 쇳물 냄새 |
| `arc_fragment_found`, `arc_fragment_found_a`, `arc_charger_found`, `arc_phone_found` | 수집품 줍기 알림 |
| `node_kind_start`, `node_kind_ruin`, `node_kind_border`, `node_kind_bunker` | 지도의 지점 이름 (랜드마크 이름은 `archive_ko.json`의 장면 제목) |

## 여기 없는 글

- 동적 서사(로컬 AI)를 켰을 때 이벤트 서술은 모델이 그때그때 만듭니다.
- 위키와 README는 `docs/`에 있습니다.
