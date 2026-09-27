# STIGMA-GM

『PROTOCOL: STIGMA』 텍스트 RPG의 게임 마스터를 맡는 로컬 LLM. 런타임에 외부 API를 쓰지 않는다.

- 설계 규칙 (출력 형식, 판정, 수치, 인젝션 방어, 원작 준수, 문체): [DESIGN.md](DESIGN.md)
- 실행별 결과와 판단 근거: [EXPERIMENTS.md](EXPERIMENTS.md)
- 서술 문체 가이드와 예시: `data/rewrite/STYLE.md` (비공개 데이터 폴더)
- 파일·산출물 위치: [DATA_LAYOUT.md](DATA_LAYOUT.md). 이 폴더는 게임 저장소(T_RPG) 안에 있고 `data/`는 공개하지 않는다

현재 배포본 (2026-09-27): 고품질 `stigma-gm-w2` (Kanana-1.5-8B + QLoRA `out_kanana2w2`, 워터마크 포함, Q4_K_M 4.9GB),
가벼움 `stigma-gm-lite-w` (Kanana-1.5-2.1B + 원작 말뭉치 + QLoRA `out_kanana21cw`, 1.5GB).
게임에는 AES-256으로 암호화해 배포하고, 복호화 패치를 넣은 llama-server로만 연다 (EXPERIMENTS.md "모델 보호").

## 환경
- Windows 네이티브, RTX 3060 12GB, RAM 32GB
- 파이썬: `E:\Git_Project\stigma-train\.venv` (uv, Python 3.12, torch cu130, unsloth, triton-windows)
- Ollama 0.34+ (모델 저장소 `E:\ollama`, 사용자 환경 변수 `OLLAMA_MODELS`). 재부팅 뒤에는 `ollama app.exe`를 켜야 서버가 뜬다
- 배포 변환용 (한 번만):
  - `git clone --depth 1 https://github.com/ggml-org/llama.cpp E:\Git_Project\stigma-train\toolchain\llama.cpp`
  - `uv pip install --python E:\Git_Project\stigma-train\.venv\Scripts\python.exe -e E:\Git_Project\stigma-train\toolchain\llama.cpp\gguf-py`
  - 공식 릴리스 `llama-bXXXXX-bin-win-cpu-x64.zip`을 `E:\Git_Project\stigma-train\toolchain\llama-bin`에 풀기 (`llama-quantize.exe`)
- 모든 모델 파일은 E에 둔다. 스크립트가 `HF_HOME=E:/Git_Project/stigma-train/hf`를 스스로 지정한다.

아래 명령은 저장소 루트에서, `PY=E:\Git_Project\stigma-train\.venv\Scripts\python.exe`, `PYTHONIOENCODING=utf-8`로 실행한다.

## 처음부터 끝까지
```
# 0. 베이스 모델 4bit 폴더 만들기 (한 번만, 약 16GB 다운로드)
PY tools/prequantize.py --model kakaocorp/kanana-1.5-8b-instruct-2505 --out E:/Git_Project/stigma-train/base/kanana-1.5-8b-instruct-bnb-4bit

# 1. 데이터 검사와 빌드
cd tools && PY validate.py && cd ..
PY tools/build.py                                   # -> data/train.jsonl

# 2. 학습 (약 30분, 108 step)
PY tools/train_unsloth.py --out E:/Git_Project/stigma-train/runs/out_<이름>

# 3. 평가 (약 10분, 2단계 생성)
PY tools/eval_model.py --out E:/Git_Project/stigma-train/runs/out_<이름> --temperature 0.5 --rep-penalty 1.05
PY tools/rescore_eval.py E:/Git_Project/stigma-train/eval/eval_a.log E:/Git_Project/stigma-train/eval/eval_b.log   # 로그끼리 비교 (GPU 불필요)

# 4. 배포: 원본 bf16에 합치기 -> GGUF f16 -> Q4_K_M -> Ollama 등록 (전부 CPU, 약 15분)
PY tools/export_ollama.py --lora E:/Git_Project/stigma-train/runs/out_<이름>/lora --name stigma-gm
PY tools/eval_ollama.py --heldout E:/Git_Project/stigma-train/runs/out_<이름>/heldout_ids.json --lore-rag
ollama stop stigma-gm                               # GPU 메모리 반환

# 5. 게임으로 GM 런타임과 원작 조각 복사
PY tools/sync_to_game.py

# 6. 모델 보호 (EXPERIMENTS.md "모델 보호"). 키·워터마크 비밀은 E:/Git_Project/stigma-train/keys/ 에만 (백업 필수, 공개 금지)
python tools/watermark.py init                        # 한 번만. 이후 build.py가 워터마크 샘플을 넣는다
python tools/model_crypt.py genkey --tag models-v1    # 태그마다 한 번. stigma-key.inc(서버)와 T_RPG/개발/gm_key.py(게임) 생성
# 서버: E:/Git_Project/stigma-train/toolchain/llama.cpp-stigma (b11201 + tools/llama_patch/stigma.patch) 를 tools/llama_patch/build_server.bat 로 빌드
python tools/watermark.py check --ollama stigma-gm    # 워터마크가 살아 있는지 (학습에 없던 장소 + 대조군)
python tools/model_crypt.py encrypt --tag models-v1 E:/Git_Project/stigma-train/models/stigma-gm-q4_k_m.gguf E:/Git_Project/stigma-train/models/enc/stigma-gm-full.dat

# 7. 게임 배포용 모델 파일 준비 (암호화 파일만 받는다. GitHub 릴리스 파일당 2GiB 제한에 맞춰 조각 + manifest)
PY tools/prepare_model_release.py --tag models-v1     # -> E:/Git_Project/stigma-train/release/models-v1/
# manifest.json을 T_RPG/개발/gm_models.json으로 복사하고, 조각은 사람이 확인한 뒤 올린다:
# gh release create models-v1 -R rorena15/T_RPG --title "동적 서사 데이터 v1" E:/Git_Project/stigma-train/release/models-v1/*.part*
```
게임은 Ollama 없이 동봉한 llama-server(Vulkan)로 모델을 돌린다(T_RPG README "동적 서사 빌드"). 개발·평가 도구는 계속 Ollama를 쓴다.

### 가벼운 모델 (Kanana 2.1B, 게임 설정의 "가벼움")
```
PY tools/prequantize.py --model kakaocorp/kanana-1.5-2.1b-instruct-2505 --out E:/Git_Project/stigma-train/base/kanana-1.5-2.1b-instruct-bnb-4bit
PY tools/build_canon_corpus.py                      # 원작 서사 말뭉치 + LORE 조각
PY tools/train_unsloth.py --base E:/Git_Project/stigma-train/base/kanana-1.5-2.1b-instruct-bnb-4bit --corpus data/canon_corpus.txt --out E:/Git_Project/stigma-train/runs/_archive/out_kanana21c
PY tools/export_ollama.py --base kakaocorp/kanana-1.5-2.1b-instruct-2505 --lora E:/Git_Project/stigma-train/runs/_archive/out_kanana21c/lora --merged E:/Git_Project/stigma-train/models/stigma-gm-lite-merged --name stigma-gm-lite
```
2.1B는 head_dim을 따로 지정한 모델이라 transformers 5.5에서 `tools/hf_compat.py` 보정이 필요하다(스크립트들이 자동으로 불러온다).
게임 엔진에서 쓰기: `engine/runtime.py`의 `play_turn(state, lore, history, raw_action)`. 사용법과 흐름은 DESIGN.md "게임 엔진 연동".

진행 상황 보기: `python tools\watch_train.py`, `python tools\watch_eval.py`

## 서술 일괄 재작성
문체 규칙을 바꿨을 때 300개 서술만 뽑아 고치고 다시 넣는다. JSON과 시스템 프롬프트는 건드리지 않는다.
```
PY tools/narration_io.py export --size 50    # -> data/rewrite/chunk_NN.txt
# 에이전트(또는 사람)가 data/rewrite/STYLE.md를 보고 out_NN.txt 작성
PY tools/narration_io.py apply               # out_NN.txt -> data/samples_*.py
```
적용 전에 `data/`를 백업하고, 적용 후 validate를 돌린다.

## 파일 지도
| 경로 | 내용 |
|---|---|
| `data/samples_*.py` | 학습 샘플 원본 (id 접두어: p 파일럿, i 인젝션, b01~b04 배치) |
| `data/_common.py`, `data/canon.py` | 샘플 헬퍼와 LORE 조각, 원작 정식 목록 (`tools/gen_canon.py`가 원작 DB에서 생성) |
| `data/rewrite/` | 문체 가이드와 재작성 청크 |
| `engine/guard.py` | 입력 정화, 출력 파싱, 판정 교정, 규칙 검증 (학습 검사와 런타임이 공유) |
| `engine/prompt.py` | 시스템 프롬프트, Llama 3 프롬프트 조립 |
| `engine/runtime.py` | 게임 엔진용 2단계 생성 참조 구현 (`play_turn`) |
| `tools/` | 위 파이프라인 스크립트. `probe_base.py`(학습 전 베이스 비교), `teacher_ollama.py`(few-shot 선생 실험) 포함 |
| `tools/sync_to_game.py` | `engine/`의 GM 런타임과 `data/lore_snippets.json`을 게임(`T_RPG/개발/gm/`)으로 복사. engine을 고친 뒤 반드시 실행 |
| `engine/lore.py` | 장면에 맞는 원작 설정 조각을 [LORE]에 덧붙임 (두 글자 조각 겹침 + IDF, 장비는 소지품만) |
| `tools/build_canon_corpus.py` | 원작(T_RPG)에서 서사만 골라 사전 학습 말뭉치와 LORE 조각 생성 (메타·스포일러·성별 표현 제거) |
| `tools/hf_compat.py`, `tools/convert_gguf.py` | transformers 5.5 head_dim 버그 보정, 보정을 건 채 llama.cpp GGUF 변환 실행 |
