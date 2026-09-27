# STIGMA-GM: PROTOCOL: STIGMA 전용 로컬 GM 모델

## 목표
『PROTOCOL: STIGMA』 세계관에서 플레이어의 자유 입력 행동을 받아
GM 서술 + 상태 변경 제안을 내는 로컬 LLM. 런타임 외부 API 없음.

## 역할 분리
| 담당 | 방식 |
|---|---|
| GM 문체, 서술 길이, 출력 형식, 판정 난이도 감각 | LoRA 파인튜닝 |
| 세계관 사실 (지역, NPC, 아이템) | 시스템 프롬프트의 [LORE] (엔진이 검색해서 넣음) |
| 주사위, 수치 검증, 상태 저장 | 게임 엔진 (파이썬) |

## 한 턴의 흐름
1. 엔진이 d100을 미리 굴리고 [STATE], [LORE], [ENGINE]을 시스템 프롬프트에 채움
2. **1단계 생성**: 모델이 `<check>{stat, dc, ...}</check>`(또는 `<check>null</check>`)까지 생성하고 멈춤 (stop string)
3. 엔진이 `guard.correct_check`로 stat/dc만 받고 roll/outcome을 엔진 값으로 덮어씀. stat/dc가 규칙 밖이면 재생성
4. **2단계 생성**: 교정된 `<check>`를 붙여 이어서 서술 + `<state>{delta, weights, items, flags}</state>` 생성
5. 엔진이 `check_output` + `check_narration`으로 검증 후 반영. 위반 시 재생성
   (`check_narration`: 반복 줄, 연달아 같은 단어, 한자·가나 누출, 시스템 줄 개수·위치·숫자, 허용 안 된 괄호 접두사)
판정을 서술보다 먼저 쓰게 하는 이유 (2026-09-25): 서술 뒤에 판정을 쓰면 서술을 생성하는 시점에 결과가 정해지지 않아
실패인데 성공처럼 쓰는 불일치가 생긴다. 판정을 먼저, 그것도 엔진이 교정한 값으로 고정하면 서술은 항상 올바른 결과를 따른다.
가짜 주사위 인젝션도 이 단계에서 무력화된다.

## 판정 규칙 (엔진과 모델이 공유)
- 판정 불필요한 행동: `"check": null`
- roll >= 96: `crit_success` / roll <= 5: `crit_fail`
- 그 외 roll >= dc: `success`, 미만: `fail`
- dc는 모델이 상황과 스탯을 보고 정함 (10~90)

## 출력 형식
```
<check>{"stat": "VIT|INT|DEX", "dc": 50, "roll": 72, "outcome": "success"}</check>   (판정 불필요하면 <check>null</check>)
서술 3~6줄 (+ 시스템 줄 최대 1줄)
<state>{"delta": {"hp": 0, "hunger": 0, "thirst": 0, "contamination": 0, "ram": 0, "alert": 0, "scrap": 0},
        "weights": {"kinetic": 0, "scrap": 0, "cyber": 0}, "items": {"add": [], "remove": []}, "flags": []}</state>
```
`guard.split_output`이 둘을 합쳐 {check, delta, weights, items, flags} 하나의 dict로 돌려준다.
history(이전 턴) assistant 답변도 같은 형식이어야 한다. train_on_responses_only는 모든 assistant 턴에 손실을 건다.
생존 수치는 100 = 가득, 0 = 고갈. delta는 변화량.

## 파이프라인
실행 순서와 명령은 `README.md`, 실행별 결과와 판단 근거는 `EXPERIMENTS.md`.
1. `data/samples_*.py`: 사람이 읽을 수 있는 형태로 샘플 작성 (서술 일괄 재작성은 `tools/narration_io.py`)
2. `tools/validate.py`: 규칙 위반 샘플 차단 (history 턴까지 검사)
3. `tools/build.py`: `engine/prompt.py`의 시스템 프롬프트를 씌워 `data/train.jsonl` 생성
4. `tools/train_unsloth.py`: Unsloth QLoRA 학습.
   - 베이스: Kakao Kanana-1.5-8B-instruct (Apache 2.0, Llama 3 템플릿). 한국어가 Qwen3-8B보다 확연히 자연스러워 2026-09-25 교체.
     Unsloth가 올린 4bit 버전이 없어 `tools/prequantize.py`로 4bit 폴더를 먼저 만든다 (transformers 5.5의 로딩 중 양자화가 이 모델에서 죽음).
   - 윈도우 네이티브, uv로 만든 파이썬 3.12 환경 `E:\Git_Project\stigma-train\.venv`. WSL은 GPU 가상화 계층 문제로 8B 로딩이 실패해 쓰지 않는다.
5. `tools/eval_model.py`: 떼어 둔 15개를 런타임과 같은 2단계 생성으로 평가 (guard + check_narration).
   `tools/rescore_eval.py`: 저장된 eval 로그를 GPU 없이 현재 규칙으로 재채점 (실행 간 비교용)
6. `tools/export_ollama.py`: LoRA를 **원본 bf16** 베이스에 합치고 → llama.cpp로 GGUF f16 → `llama-quantize` Q4_K_M → Ollama `stigma-gm` 등록.
   Ollama 0.34(Windows)는 safetensors 가져오기가 MLX를 요구해 실패하고, GGUF에는 생성 시 양자화를 해 주지 않아서 이 경로를 쓴다
7. `tools/eval_ollama.py`: 배포 형태(Ollama + `engine/runtime.py`)로 최종 확인

## 게임 엔진 연동 (`engine/`)
| 파일 | 역할 |
|---|---|
| `guard.py` | 입력 정화, 출력 파싱(`split_output`), 판정 교정(`correct_check`), 규칙 검증(`check_output`, `check_narration`) |
| `prompt.py` | 시스템 프롬프트와 Llama 3 프롬프트 조립. 학습 데이터와 바이트 단위로 같은 형식 (검증함) |
| `runtime.py` | 참조 구현. `play_turn(state, lore, history, raw_action)`이 정화, d100, 2단계 생성, 검증, 재생성(3회)까지 처리 |
- Ollama `/api/generate`를 raw 모드로 호출한다. 2단계 생성에서 교정한 `<check>`를 프롬프트 뒤에 이어 붙여야 하기 때문.
- 생성 설정: temperature 0.5, top_p 0.9, repeat_penalty 1.05. (0.7은 형식 오류가 늘고, 반복 억제 1.1은 단어 선택이 어색해지고 시스템 줄이 사라짐)
- 3회 모두 검증에 실패하면 `RuntimeError`. 엔진은 기본 서술로 대체한다.
- history에는 모델 원문(`<check>` ~ `</state>`)을 그대로 쌓는다. 학습 데이터의 history와 같은 형식이어야 한다.
- `generate_turn(..., force_check=True)`: 1단계 생성 앞을 `<check>{"stat": "`로 채워 반드시 주사위를 굴리게 한다.
  보상이 걸린 행동(게임의 대본 선택지)에 쓴다. 모델은 stat과 dc만 고르고 결과는 엔진이 정한다.
- 대본 문장(합니다체)을 history의 GM 서술로 넘기면 GM이 합니다체를 따라 쓴다. 장면 설명은 LORE("현재 장면: ...")로 넘긴다.

### 게임(T_RPG)에 연결된 방식 (2026-09-27, 브랜치 `feat/gm-events`)
- `tools/sync_to_game.py`가 `engine/`의 guard·prompt·runtime을 `T_RPG/개발/gm/`로 복사한다. 원본은 여기다.
- `T_RPG/개발/gm_bridge.py`가 탐색 중 **랜덤 이벤트**(무기 이벤트 1개 제외)와 **빈 탐색**을 GM으로 진행한다.
  스토리 세션, 전투, 행상인, 파밍, 보스, 엔딩은 대본 유지 (사용자 결정: 원작 선택지와 진행 보상 보호).
- 대본 선택지: 판정 강제, 성공할 때만 대본 보상(대성공은 고철 1.5배), 대가는 항상, 피해는 대본과 GM 중 큰 쪽, 성향 +1(대성공 +2).
  보상과 대가는 LORE로 GM에게 알려 서술을 맞춘다. GM이 준 고철·아이템·성향은 버린다(이중 보상 방지)
- `[0] 직접 행동 입력`과 이어서 행동(최대 2회, 매번 턴 소모): GM의 수치를 그대로 반영 (guard 상한 적용)
- 게임에 없는 수치는 버린다: contamination, ram. GM은 소모품(식량·물·의료 키트)을 모른다(학습한 아이템은 장비뿐)
- GM을 못 쓰면(Ollama 꺼짐, 모델 없음, 영어 모드) 대본으로 진행한다. 이벤트 도중 실패하면 같은 화면에서 조용히 대체
- **화면 (사용자 결정, 2026-09-27): GM도 주사위도 드러내지 않는다.** 게임이 스스로 생각하는 것처럼. 판정·난이도·"GM" 문구 없음,
  결과는 서술과 수치 변화로만. 전용 이벤트 화면 `T_RPG/개발/event_view.py`(장면 그림 + 이야기 기록, 한글 IME 입력,
  생성은 백그라운드 스레드라 기다리는 동안에도 화면이 움직임). 기존 터미널 입력은 ASCII만 받아 한글 입력이 안 됐다

## 저장 위치 (사용자 요청: 모델은 C가 아니라 E)
| 경로 | 내용 |
|---|---|
| `E:\Git_Project\stigma-train\.venv` | 학습/평가용 파이썬 환경 |
| `E:\Git_Project\stigma-train\hf` | Hugging Face 캐시. 스크립트가 `HF_HOME`을 여기로 지정한다 |
| `E:\Git_Project\stigma-train\base\kanana-1.5-8b-instruct-bnb-4bit` | prequantize.py 결과 (학습 베이스) |
| `E:\Git_Project\stigma-train\runs\out_*` | 실행별 LoRA 어댑터와 heldout_ids.json. 현행은 `runs\out_kanana2w2`(8B), `runs\out_kanana21cw`(가벼움), 지난 실험은 `runs\_archive\` |
| `E:\Git_Project\stigma-train\*.log` | 학습/평가 로그 (`eval_<실행>_*.log`로 보관) |
| `E:\Git_Project\stigma-train\models\stigma-gm-merged`, `stigma-gm-q4_k_m.gguf` | 합친 bf16 모델, 배포용 GGUF |
| `E:\Git_Project\stigma-train\toolchain\llama.cpp`, `llama-bin` | GGUF 변환 스크립트, `llama-quantize.exe` (공식 win-cpu-x64 빌드) |
| `E:\ollama` | Ollama 모델 저장소 (사용자 환경 변수 `OLLAMA_MODELS`) |

## 데이터 규모 목표
파일럿 12개 → 톤 확인 → 300~500개. 다양성 축:
지역 × 행동 유형 (전투/탐색/해킹/대화/제작/휴식/억지 행동) × 판정 결과 × 상태 위기도

## 수치 가이드 (사용자 요청으로 초안 대비 피해·페널티 20% 하향, 2026-09-24)
dc와 턴당 허기/갈증 소모는 그대로. 아래는 한 턴 delta 기준.
| 상황 | 값 |
|---|---|
| 턴 소모 (탐색/이동) | hunger -1~-3, thirst -2~-4 |
| 가벼운 실패 (추락, 긁힘) | hp -30~-50 |
| 전투 피격 | hp -70~-110 |
| 대실패 | hp -110~-150 |
| 보스 타격 | hp -150~-250 |
| 휴식 (안전한 곳) | hp +60~+90, hunger -8, thirst -10 |
| 도시 턴 경과 | alert +4~+8 |
| 해킹 실패 / 대실패 | alert +12~+18 / +25~+30 |
| 방사능 분지 턴 경과 | contamination +5~+10 |
| 성공한 행동의 성향 | weights 해당 축 +1 (대성공/결정적 선택 +2) |

## 프롬프트 인젝션 방어
1. **엔진이 최종 방어선** (`engine/guard.py`): 모델 출력은 신뢰하지 않는다. 허용 키, 수치 범위,
   플레이어 유리 방향 상한(GAIN_LIMIT), roll/dc/outcome 일치, 인벤토리 존재, 아이템 추가 2개 이하를 검증.
   check가 null인 턴에는 ram/alert/scrap/contamination이 유리한 방향으로 움직일 수 없다(NO_FREE_GAIN).
   판정 없는 공짜 이득은 휴식 hp와 먹고 마시기뿐이다.
   위반 시 반영하지 않고 재생성하거나 기본 서술로 대체.
2. **입력 정화** (`sanitize_player_input`): 먼저 NFKC로 전각 문자를 접고(［ENGINE］) zero-width 등 서식 문자를
   지운다. 한글 호환 자모(ㅋㅋ)는 NFKC가 깨뜨리므로 제외. 그 뒤 [ENGINE]/[STATE]/[LORE]/[SYSTEM], <state>,
   `<check>`, 채팅 템플릿 토큰, `system:` 접두어를 더 지울 게 없을 때까지 반복 제거하고 300자로 자른다. build.py도 같은 정화를 거친 입력으로 학습 데이터를 만든다.
3. **학습** (`data/samples_injection.py`): 지시 무시 요구, 가짜 주사위, 가짜 state, 시스템 프롬프트 유출 요구,
   NPC 조종, 개발자 사칭, 영어 인젝션, 템플릿 토큰을 세계관 안에서 무시하고 이득 없이 진행.
   `raw=True`는 정화를 우회한 원문. 메타 용어(프롬프트, AI, 규칙) 사용이나 설교 금지.
전체 데이터의 약 8~10%를 인젝션 샘플로 유지한다.

## 샘플 작성 규칙 (다른 모델이 이어 쓸 때)
- `data/samples_<배치명>.py`에 `SAMPLES` 리스트, 헬퍼와 LORE는 `data/_common.py`에서 import
- id 접두어는 파일마다 고유 (p=파일럿, i=인젝션, b01=1차 배치 ...)
- 서술 3~6문장, 한 줄에 한 문장, 줄표(—) 금지, 2인칭 '당신', 마지막 문장은 상황 제시
- 판정 없는 행동은 check=None. 판정이 있으면 outcome은 roll/dc 규칙과 일치해야 함. 서술도 outcome과 일치(실패인데 성공처럼 쓰지 않기)
- **서술 층 (사용자 지적, 2026-09-25, 원작 ko.json 문체 기준)**: 행동 줄(짧게, 동사 중심) / 상황 줄(길고 감각적, 마지막 줄) /
  시스템 줄(`[경고]`·`[SYSTEM]`·`[ERROR]`로 시작, 명사형, 숫자 없음, 샘플당 최대 1줄, 약 3분의 1 샘플에만).
  추상 IT 용어는 시스템 줄과 디지털 대상 장면에서만. 물리·환경 줄에서는 비유로도 금지 (validate.py가 검사).
  상세와 예시: `data/rewrite/STYLE.md`
- 첫 문장을 '당신은/당신이'로 시작하는 샘플은 파일당 40% 이하 (검사기가 막음). 소리, 사물, NPC, 환경, 시스템 로그로도 시작할 것
- GM은 플레이어의 대사나 행동을 대신 정하지 않는다 (예: "당신이 ~라고 묻자" 금지. 플레이어가 입력한 행동의 결과만 서술)
- 원작의 핵심 선택지(컬렉터 코어 처분 등 직업·진영이 갈리는 분기)는 GM이 해결하지 않는다. 선택이 걸린 장면에서 멈추고 `*_CHOICE_PENDING` 플래그
- 작성 후 `cd tools && PYTHONIOENCODING=utf-8 python validate.py` 통과 필수
- 다양성 축: 지역 x 행동 유형 (전투/탐색/해킹/대화/제작/휴식/억지 행동/상태 질문) x 판정 결과 x 위기도

## 원작 준수 (사용자 결정, 2026-09-24)
- **원작에 없는 것은 임의로 만들지 않는다.** 장소, 적, NPC의 특징과 위치, 이름 붙은 아이템 모두.
  정식 목록: `data/canon.py` (ITEMS는 원작 DB에서 `tools/gen_canon.py`로 자동 생성, ENEMIES/LOCATIONS/NPCS는 원작 문서 기준)
- **NPC 성별은 비공개.** 이름 붙은 NPC에게 그/그녀/남자/여자 같은 성별 표현 금지. 이름이나 직함으로 지칭
- 인벤토리, items.add/remove는 canon.ITEMS에 있는 이름만 (검사기가 막음)
- 획득 아이템 등급: T=0 유물과 T=1 기업제 최상위 장비는 보상으로 주지 않는다 (검사기가 막음). 초반 데드존은 T=4 급조, T=3 이상은 거래나 탈취 등 맥락이 있을 때만
- 평판은 원작의 단일 축 `reputation` (-1000~+1000, 양수=총괄국 우호, 음수=데드존 우호). 별도 평판 필드를 만들지 않는다
- 정보성 획득물(지도, 좌표, 서류, 연락처)은 아이템이 아니라 flags로
- 원자재(철사, 철판, 부품 더미)는 아이템이 아니라 delta.scrap으로
- 장면 묘사용 일반 사물(빗물, 콘크리트 벽, 잔해)은 서술에 써도 되지만, 획득하거나 사용하는 대상이 되면 위 규칙을 따른다
