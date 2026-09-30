# 밸런스 검증 도구

봇이 실제 게임 코드를 끝까지 플레이해 난이도별·탐색량별 승률을 잰다. 보스·적 수치를 바꾼 뒤 목표에 맞는지 확인할 때 쓴다.

**목표** (`constants.py` 보스 주석): 탐색 0회면 0%, 탐색 90회면 쉬움 약 70% · 보통 약 40% · 어려움 약 20%.

## 파일

| 파일 | 하는 일 |
|---|---|
| `sim.py` | 실행기. 게임 코드를 임시 폴더에 몇 벌 복사해 봇을 병렬로 돌리고 표를 낸다 |
| `bot.py` | 봇 한 판. 키 입력만 사람처럼 대신 누른다 (장비·강화·발칸 의뢰·힌트·식사·행상인에게서 물·식량 사기·후퇴·보스 학습 끊기) |
| `replay.py` | 모아 둔 보스 직전 상태로 보스전만 다시 싸운다 (게임 전체보다 훨씬 빠르다) |
| `verify.py` | 게임성 검증. 목표 승률 통과 여부, 기준선 대비 승률, 결말 분포, 게임성 지표(성향 단계, 적 행동, 위험도별 탐색)를 `results/<이름>.md`로 남긴다 |
| `results/` | 검증 결과. `baseline_runs.jsonl`은 게임성 개편(성향 단계·적 행동·칸 위험도·수확 체감) 전 코드로 돌린 기준선. `gameplay_v3`부터는 봇 판단(위 "봇이 하는 판단")이 바뀌어, 그 전 결과와 탐색 횟수 칸의 뜻이 조금 다르다 |

## 쓰는 법 (`개발/`에서)

```bash
# 게임 전체: 난이도 3 × 탐색 0/20/45/90회 × 50판 (4개씩 동시에, 약 25분)
python tools/balance/sim.py --n 50 --out runs.jsonl

# 일부만, 수치를 바꿔서 (봇 환경 변수: ENEMY_DIFF, BOSS_ATK, BOSS_MULT, NO_HINT … bot.py 설명 참고)
python tools/balance/sim.py --diffs hard --farms 90 --n 40 --env ENEMY_DIFF=0.85

# 보스 수치 맞추기: runs.jsonl의 보스 직전 상태로 보스전만 (판마다 4번씩)
python tools/balance/sim.py --replay runs.jsonl --params '{"atkm":{"easy":1.62},"mult":{"easy":1.6}}' --seeds 4
```

`--params`: `atkm` = `BOSS_DIFF_ATK`, `mult` = `BOSS_DIFF_MULT` (난이도별), `atk`·`hp`·`ref` = `BOSS_BASE_ATK`·`BOSS_HP`·`BOSS_POWER_REF`.

## 게임성 검증 (`verify.py`)

```bash
# 난이도 3 × 탐색 0/20/45/90회 × 30판을 돌리고 results/이름.md로 저장 (기준선과 같은 시드 20000이 기본)
python tools/balance/verify.py --name 이름
# 성향 몰아주기 비교도 (노멀 · 탐색 45회, BOT_FOCUS=random/kinetic/scrap/cyber)
python tools/balance/verify.py --name 이름 --focus
# 이미 돌린 결과로 문서만 다시
python tools/balance/verify.py --name 이름 --reuse
```

통과 조건: 탐색 0회 클리어 0%, 탐색 90회 클리어가 이지 70% · 노멀 40% · 하드 20%에서 ±12%p 안, 봇이 멈춘 판 0. 하나라도 어긋나면 종료 코드 1.

봇 환경 변수 `BOT_FOCUS`(스토리·이벤트에서 고를 성향), `BOT_DANGER`(smart / safe / any, 칸 고르기)로 플레이 방식을 바꿔 볼 수 있다.

## 봇이 하는 판단

- **탐색 0회**는 방공호 직행이다. 강화소에 들르지 않고, 가는 길에 발칸 의뢰를 받아도 준비하느라 머물지 않는다. (예전에는 의뢰를 받으면 30회까지 더 뒤져서, 탐색 0회 판에 준비를 마친 판이 섞여 클리어가 나왔다.)
- 탐색 20회 이상은 의뢰를 받으면 마무리하느라 30회까지 더 뒤질 수 있다.
- 물·식량이 두 개 밑이면 행상인에게서 산다. 물이나 식량이 바닥나 체력이 깎이는데 회복약도 없고 체력이 반 밑이면, 남은 탐색을 접고 방공호로 간다. (예전에는 끝까지 뒤지다 굶어 죽어 보스 도달률이 실제보다 낮게 나왔다: 하드 탐색 90회 43%.)
- 해킹 성향 2단계면 보스전에서 패킷 우회와 공격을 번갈아 쓴다.

## 결과 읽기

- **클리어**: 끝까지 이긴 비율. **도달**: 보스까지 살아서 간 비율. 클리어 ≈ 도달 × 보스전 승률.
- 50판이면 ±7%p쯤 흔들린다. `--seed0`을 바꿔 다른 판 묶음으로도 본다.
- 도달이 낮으면 탐색 중 전투·굶주림이 문제 → `ENEMY_DIFF_ATK`(일반 적) 쪽을, 도달은 괜찮은데 클리어가 안 맞으면 `BOSS_DIFF_ATK`·`BOSS_DIFF_MULT`(보스) 쪽을 만진다.
- 결과 파일(`--out`)은 판마다 한 줄: `result`(clear / death_boss / death_combat / death_other(대개 굶주림)), `forge`(발칸 의뢰 단계), `state`(보스 직전 상태).
- `ending`은 그 판의 결말 ID (`endings.py`), `end`는 클리어 판의 마지막 상태. 결말 기준값(`endings.py` 위쪽 상수)을 바꿀 때 분포를 본다. 봇 판은 결말 기록 파일(endings.json)에 남기지 않는다.

## 주의

- Windows에서도 그대로 돈다 (`sim.py`가 봇 출력을 UTF-8로 읽는다). 12스레드 PC에서 `--jobs 10`으로 1,200판에 3분쯤.

- 봇은 GM(동적 서사)을 끄고 대본 이벤트로 돈다.
- 게임 흐름(키 입력 순서)을 바꾸면 봇도 고쳐야 할 수 있다. 결과에 `CRASH`가 보이면 봇이 모르는 입력에서 멈춘 것이다.
