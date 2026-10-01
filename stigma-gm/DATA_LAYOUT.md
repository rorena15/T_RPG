# 파일은 어디에 있나

GM 모델 코드와 문서는 게임 저장소 안(`T_RPG/stigma-gm/`)에 있고, 무거운 산출물은 저장소 밖(`E:\Git_Project\stigma-train\`)에 있다.
두 위치 모두 2026-09-27에 옮겼다 (예전: `E:\Git_Project\stigma-gm`, `E:\stigma-train`). 스크립트의 기본 경로는 새 위치로 바뀌어 있다.

## T_RPG 저장소 (공개)
| 경로 | 내용 | 공개 |
|---|---|---|
| `stigma-gm/engine/` | GM 런타임 원본 (guard, prompt, runtime, lore). `tools/sync_to_game.py`가 `개발/gm/`으로 복사 | 공개 |
| `stigma-gm/tools/` | 학습·평가·변환·보호·워터마크·릴리스 도구, `llama_patch/` (실행기 패치) | 공개 |
| `stigma-gm/data/` | 학습 샘플, `train.jsonl`, 원작 말뭉치, 평가 케이스 | **비공개 (.gitignore)**: 공개되면 같은 모델을 다시 학습할 수 있고 워터마크 문구가 들어 있다 |
| `stigma-gm/*.md` | README(실행 순서), DESIGN(규칙), EXPERIMENTS(실험 기록), 이 문서 | 공개 |
| `개발/gm/` | 런타임 복사본 (여기서 고치지 않는다) | 공개 |
| `개발/gm_key.py` | 생성물 | **비공개 (.gitignore)**, CI는 Secret `STIGMA_GM_KEY` |
| `개발/runtime/llama/` | 패치 빌드 llama-server.exe (`install_llama_runtime.py`) | 비공개 (.gitignore), CI는 릴리스 `runtime-v1` |
| `개발/art_gen/` | 장면 그림 생성 스크립트 | 공개 |
| `assets/scenes/` | 고른 장면 그림 + 깊이 층 (약 12MB) | 공개 |

## E:\Git_Project\stigma-train\ (저장소 밖, git 아님)
| 경로 | 내용 |
|---|---|
| `keys/` | 비밀 파일. 백업 필수 (내용은 비공개 문서) |
| `.venv/` | 학습·그림 생성 파이썬 3.12 (uv). `E:\Git_Project\stigma-train\.venv\Scripts\python.exe`. **게임 실행용이 아니다** (pygame 없음). 게임은 `E:\Python313\python.exe Main.py`. VS Code가 이 .venv를 자동으로 고르면 Python: Select Interpreter로 바꾼다 |
| `hf/` | HuggingFace 캐시 (명령마다 `HF_HOME`으로 지정) |
| `base/` | 학습용 베이스 4bit (`kanana-1.5-8b/2.1b-instruct-bnb-4bit`, `tools/prequantize.py`) |
| `runs/` | 현행 학습 결과: `out_kanana2w2`(8B), `out_kanana21cw`(가벼움). LoRA와 heldout_ids.json |
| `runs/_archive/` | 지난 실험 (out, out_run2, out_kanana, out_kanana2, out_kanana2w, out_kanana21, out_kanana21c, smoke). 평가 세트 비교용 heldout_ids.json도 여기 |
| `models/` | 배포 GGUF (`stigma-gm-w2-q4_k_m.gguf`, `stigma-gm-lite-w-q4_k_m.gguf`), Modelfile, `enc/`(배포본). 합친 모델은 내보낼 때만 생기고 필요 없으면 지운다 |
| `eval/` | 평가 로그(`eval_*`, `cmp_*`, `wm_*`)와 `suite/`(확장 평가 jsonl, 심사 보고서) |
| `logs/` | 학습·내보내기·빌드·다운로드 로그. `train.log`는 `tools/watch_train.py`의 기본 로그 |
| `art/` | 그림 후보 `cand_txt/`, 선별표 `review/`, 시안 `preview/`, 화면 시안 `shots/`, 밑그림 `init/`·`cand/` |
| `toolchain/` | `llama.cpp/`(GGUF 변환 소스), `llama-bin/`(llama-quantize 등 공식 CPU 도구), `llama.cpp-stigma/`(패치 소스 + `build-stigma/bin/llama-server.exe`). 옮긴 뒤 다시 빌드하면 `build-stigma/CMakeCache.txt`를 지운다 (옛 절대 경로가 들어 있다) |
| `release/` | 배포 조각 + manifest (`prepare_model_release.py`) |

Ollama 모델은 `E:\ollama` (`OLLAMA_MODELS`). 개발·평가용 이름 `stigma-gm`(8B), `stigma-gm-lite`(가벼움)은 2026-09-27에 워터마크 모델로 바꿨다.
