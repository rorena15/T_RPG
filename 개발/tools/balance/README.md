# 밸런스 검증 도구

봇이 실제 게임 코드를 끝까지 플레이해 난이도별·탐색량별 승률을 잰다. 보스·적 수치를 바꾼 뒤 목표에 맞는지 확인할 때 쓴다.

**목표** (`constants.py` 보스 주석): 탐색 0회면 0%, 탐색 90회면 쉬움 약 70% · 보통 약 40% · 어려움 약 20%.

## 파일

| 파일 | 하는 일 |
|---|---|
| `sim.py` | 실행기. 게임 코드를 임시 폴더에 몇 벌 복사해 봇을 병렬로 돌리고 표를 낸다 |
| `bot.py` | 봇 한 판. 키 입력만 사람처럼 대신 누른다 (장비·강화·발칸 의뢰·힌트·식사·후퇴·보스 학습 끊기) |
| `replay.py` | 모아 둔 보스 직전 상태로 보스전만 다시 싸운다 (게임 전체보다 훨씬 빠르다) |

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

## 결과 읽기

- **클리어**: 끝까지 이긴 비율. **도달**: 보스까지 살아서 간 비율. 클리어 ≈ 도달 × 보스전 승률.
- 50판이면 ±7%p쯤 흔들린다. `--seed0`을 바꿔 다른 판 묶음으로도 본다.
- 도달이 낮으면 탐색 중 전투·굶주림이 문제 → `ENEMY_DIFF_ATK`(일반 적) 쪽을, 도달은 괜찮은데 클리어가 안 맞으면 `BOSS_DIFF_ATK`·`BOSS_DIFF_MULT`(보스) 쪽을 만진다.
- 결과 파일(`--out`)은 판마다 한 줄: `result`(clear / death_boss / death_combat / death_other(대개 굶주림)), `forge`(발칸 의뢰 단계), `state`(보스 직전 상태).

## 주의

- 봇은 GM(동적 서사)을 끄고 대본 이벤트로 돈다.
- 게임 흐름(키 입력 순서)을 바꾸면 봇도 고쳐야 할 수 있다. 결과에 `CRASH`가 보이면 봇이 모르는 입력에서 멈춘 것이다.
