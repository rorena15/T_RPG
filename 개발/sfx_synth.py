"""효과음 합성 (외부 파일 없이 코드로 만든다).

전투(타격·치명타·피격·방벽·해킹·후퇴·회복·승리·2페이즈 경보), 강화소(모루·실패·하락·수리),
이동 발소리, 줍기, 맵의 먼 소리(쇠 신음·드론 지나감·먼 천둥)를 만든다.
결과는 44.1kHz 16비트 스테레오 바이트. sound.py가 처음 한 번 만들어 pygame Sound로 들고 있는다.
numpy 없이 표준 라이브러리만 쓴다 (가장 긴 소리도 2초 남짓이라 시작할 때 백그라운드로 만들면 충분하다).
"""
import array
import math
import random
import zlib

SR = 44100


# ── 재료 ─────────────────────────────────────────────────────────────────
def _n(sec):
    return int(SR * sec)


def _env(i, n, attack=0.002, decay=None):
    """빠르게 올라가고 지수로 줄어드는 포락선. decay: 1/e까지 걸리는 초."""
    t = i / SR
    a = min(1.0, t / attack) if attack > 0 else 1.0
    if decay is None:
        return a * (1 - i / n)
    return a * math.exp(-t / decay)


def noise(sec, rng, decay=0.1, attack=0.001):
    n = _n(sec)
    return [rng.uniform(-1, 1) * _env(i, n, attack, decay) for i in range(n)]


def tone(sec, freq, decay=0.2, attack=0.002, shape="sine", glide=None, vib=0.0, vib_hz=5.0):
    """freq에서 glide까지 미끄러지는 음. shape: sine / square / saw."""
    n = _n(sec)
    out, ph = [], 0.0
    for i in range(n):
        f = freq if glide is None else freq + (glide - freq) * (i / n)
        if vib:
            f *= 1 + vib * math.sin(2 * math.pi * vib_hz * i / SR)
        ph += 2 * math.pi * f / SR
        if shape == "square":
            v = 1.0 if math.sin(ph) >= 0 else -1.0
        elif shape == "saw":
            v = ((ph / math.pi) % 2) - 1
        else:
            v = math.sin(ph)
        out.append(v * _env(i, n, attack, decay))
    return out


def lowpass(x, cutoff):
    a = 1 - math.exp(-2 * math.pi * cutoff / SR)
    y, out = 0.0, []
    for v in x:
        y += a * (v - y)
        out.append(y)
    return out


def highpass(x, cutoff):
    lp = lowpass(x, cutoff)
    return [a - b for a, b in zip(x, lp)]


def mix(*parts, at=None):
    """여러 소리를 겹친다. parts: (소리, 크기) 또는 (소리, 크기, 시작 초)."""
    n = max(len(p[0]) + _n(p[2] if len(p) > 2 else 0) for p in parts)
    out = [0.0] * n
    for p in parts:
        s, g = p[0], p[1]
        off = _n(p[2]) if len(p) > 2 else 0
        for i, v in enumerate(s):
            out[off + i] += v * g
    return out


def drive(x, amount=2.0):
    """살짝 찌그러뜨려 거칠게 (tanh 포화)."""
    k = math.tanh(amount)
    return [math.tanh(v * amount) / k for v in x]


def crush(x, steps=16, hold=3):
    """비트·샘플 깎기 (디지털 잡음 느낌)."""
    out, last = [], 0.0
    for i, v in enumerate(x):
        if i % hold == 0:
            last = round(v * steps) / steps
        out.append(last)
    return out


def metal(sec, base, rng, decay=0.35, partials=(1.0, 2.76, 5.40, 8.93)):
    """비조화 배음을 겹친 쇳소리 (모루·방벽·고철)."""
    parts = []
    for k, r in enumerate(partials):
        f = base * r * rng.uniform(0.985, 1.015)
        parts.append((tone(sec, f, decay=decay / (1 + k * 0.6)), 1.0 / (1 + k)))
    return mix(*parts)


def to_bytes(x, gain=0.8, width=0.0, rng=None):
    """-1..1 모노를 16비트 스테레오로. width: 좌우 퍼짐 (0이면 가운데)."""
    peak = max(1e-6, max(abs(v) for v in x))
    g = gain / peak
    pan = (rng.uniform(-width, width) if rng and width else 0.0)
    lg, rg = math.sqrt((1 - pan) / 2) * 1.41, math.sqrt((1 + pan) / 2) * 1.41
    out = array.array("h")
    for v in x:
        s = max(-1.0, min(1.0, v * g))
        out.append(int(s * lg * 32000 / 1.41))
        out.append(int(s * rg * 32000 / 1.41))
    return out.tobytes()


# ── 소리 ─────────────────────────────────────────────────────────────────
def _hit(rng):  # 급조 총·둔기 타격: 짧은 충격음 + 낮은 퉁 + 쇳조각 울림
    crack = highpass(noise(0.12, rng, decay=0.018), 900)
    thump = tone(0.22, 95, decay=0.06, glide=45)
    ring = metal(0.25, 1400, rng, decay=0.05)
    return mix((crack, 0.9), (thump, 1.0), (ring, 0.25))


def _crit(rng):  # 치명타: 더 큰 충격 + 깊은 폭음 + 높은 쇳소리 여운
    crack = drive(highpass(noise(0.18, rng, decay=0.03), 700), 3)
    boom = tone(0.45, 70, decay=0.14, glide=32)
    ring = metal(0.6, 1900, rng, decay=0.18)
    return mix((crack, 1.0), (boom, 1.2), (ring, 0.35, 0.01))


def _sub(rng):  # 네오 아크 AI 화기: 전기 충전음 뒤 무거운 발사
    charge = tone(0.12, 400, decay=None, glide=2400, shape="saw")
    shot = drive(mix((highpass(noise(0.3, rng, decay=0.05), 500), 1.0), (tone(0.35, 60, decay=0.12, glide=30), 1.3)), 2.5)
    return mix((charge, 0.25), (shot, 1.0, 0.1))


def _hurt(rng):  # 피격: 둔탁한 충격 + 뼈·장갑 찌그러지는 소리
    thud = tone(0.25, 60, decay=0.08, glide=38)
    crunch = lowpass(drive(noise(0.2, rng, decay=0.04), 4), 1800)
    return mix((thud, 1.2), (crunch, 0.7))


def _hurt_heavy(rng):
    thud = tone(0.4, 52, decay=0.14, glide=28)
    crunch = lowpass(drive(noise(0.35, rng, decay=0.08), 5), 1400)
    ring = tone(0.5, 3100, decay=0.25, attack=0.05)   # 귀가 멍해지는 이명
    return mix((thud, 1.3), (crunch, 0.9), (ring, 0.08, 0.05))


def _barricade(rng):  # 고철 방벽을 세운다: 둔중한 쇳소리 두 번
    a = metal(0.7, 180, rng, decay=0.25)
    b = metal(0.6, 240, rng, decay=0.2)
    scrape = lowpass(noise(0.25, rng, decay=0.1), 2500)
    return mix((scrape, 0.4), (a, 1.0, 0.03), (b, 0.8, 0.16))


def _hack(rng):  # 패킷 우회: 짧은 디지털 신호음 세 개 + 잡음
    notes = [rng.choice([880, 988, 1175]), 1318, 1760]
    parts = [(crush(tone(0.07, f, decay=0.04, shape="square"), 8, 4), 0.6, k * 0.07) for k, f in enumerate(notes)]
    parts.append((crush(noise(0.25, rng, decay=0.08), 6, 6), 0.25, 0.02))
    return mix(*parts)


def _deny(rng):  # RAM 부족: 낮은 경고음 두 번
    return mix((tone(0.09, 220, decay=0.06, shape="square"), 0.5), (tone(0.12, 160, decay=0.08, shape="square"), 0.5, 0.11))


def _escape(rng):  # 후퇴: 몸을 날리는 바람 가르는 소리
    n = _n(0.45)
    swell = [rng.uniform(-1, 1) * math.sin(math.pi * i / n) ** 2 for i in range(n)]
    return lowpass(highpass(swell, 400), 3000)


def _heal(rng):  # 회복약: 부드럽게 올라가는 화음
    return mix((tone(0.5, 523, decay=0.25, attack=0.02), 0.5), (tone(0.5, 659, decay=0.25, attack=0.02), 0.4, 0.06),
               (tone(0.55, 784, decay=0.3, attack=0.02), 0.35, 0.12), (highpass(noise(0.3, rng, decay=0.1), 5000), 0.05))


def _eat(rng):  # 먹고 마시기: 포장 뜯는 소리 + 짧은 꿀꺽
    rip = highpass(noise(0.15, rng, decay=0.05), 2000)
    gulp = tone(0.12, 180, decay=0.05, glide=90)
    return mix((rip, 0.6), (gulp, 0.8, 0.18))


def _skill(rng):  # 특화 스킬: 전기 방전
    zap = []
    for k in range(4):
        zap.append((crush(tone(0.08, rng.uniform(300, 900), decay=0.04, shape="saw", glide=rng.uniform(1500, 3000)), 12, 2), 0.5, k * 0.05))
    return mix(*zap, (highpass(noise(0.3, rng, decay=0.1), 3000), 0.3))


def _win(rng):  # 제압: 쇠붙이 떨어지는 소리 + 낮게 올라가는 두 음
    clank = metal(0.5, 620, rng, decay=0.12)
    a = tone(0.35, 196, decay=0.2, attack=0.01, shape="saw")
    b = tone(0.6, 294, decay=0.35, attack=0.01, shape="saw")
    return mix((clank, 0.6), (lowpass(a, 1500), 0.5, 0.1), (lowpass(b, 1500), 0.55, 0.3))


def _alert(rng):  # 적 조우: 무전 잡음 끊기며 짧은 경고
    static = crush(noise(0.2, rng, decay=0.1), 5, 5)
    beep = tone(0.1, 740, decay=0.08, shape="square")
    return mix((static, 0.4), (beep, 0.4, 0.12), (beep, 0.4, 0.26))


def _phase2(rng):  # 보스 2페이즈: 사이렌 두 번 + 낮은 굉음
    siren = []
    for k in range(2):
        siren.append((drive(tone(0.55, 380, decay=None, glide=900, shape="saw"), 1.5), 0.45, k * 0.55))
    roar = lowpass(drive(noise(1.3, rng, decay=0.6), 3), 300)
    return mix(*siren, (roar, 0.9))


def _death(rng):  # 치명상: 심장이 가라앉는 낮은 하강음
    fall = tone(1.6, 110, decay=0.8, glide=35)
    hiss = lowpass(noise(1.4, rng, decay=0.7), 800)
    return mix((fall, 1.0), (hiss, 0.3))


def _anvil(rng):  # 강화 성공: 맑은 모루 소리 + 불티
    ring = metal(1.0, 880, rng, decay=0.35, partials=(1.0, 2.0, 2.76, 4.1, 5.4))
    hit = highpass(noise(0.05, rng, decay=0.01), 1500)
    sparks = [(highpass(noise(0.03, rng, decay=0.008), 6000), 0.2, 0.05 + rng.uniform(0, 0.3)) for _ in range(5)]
    return mix((hit, 0.8), (ring, 1.0), *sparks)


def _clunk(rng):  # 강화 실패: 둔하게 먹히는 소리
    thud = tone(0.3, 140, decay=0.07, glide=90)
    dull = lowpass(metal(0.3, 330, rng, decay=0.06), 1200)
    return mix((thud, 1.0), (dull, 0.6))


def _drop(rng):  # 단계 하락: 금 가는 소리 + 내려가는 음
    crack = highpass(drive(noise(0.1, rng, decay=0.02), 4), 1200)
    fall = tone(0.6, 440, decay=0.3, glide=180, shape="saw")
    return mix((_clunk(rng), 0.8), (crack, 0.6, 0.08), (lowpass(fall, 1800), 0.4, 0.12))


def _repair(rng):  # 수리: 망치질 세 번
    parts = [(metal(0.25, 520 + k * 40, rng, decay=0.06), 0.7, k * 0.16) for k in range(3)]
    return mix(*parts)


def _step(rng):  # 이동: 고철 자갈 밟는 발소리 두 번
    def one():
        return lowpass(noise(0.09, rng, decay=0.025), 1600 + rng.uniform(-300, 300))
    return mix((one(), 0.8), (one(), 0.7, 0.19))


def _loot(rng):  # 줍기: 고철 조각 짤랑
    parts = [(metal(0.2, rng.uniform(1800, 3200), rng, decay=0.05), 0.5, k * 0.06) for k in range(3)]
    return mix(*parts)


def _gear(rng):  # 장비 발견: 줍기 + 낮은 확인음
    return mix((_loot(rng), 0.8), (tone(0.3, 392, decay=0.15, attack=0.01), 0.3, 0.12), (tone(0.35, 587, decay=0.2, attack=0.01), 0.3, 0.2))


# 맵의 먼 소리 (바람 위로 가끔)
def _amb_creak(rng):  # 고철 산이 뒤틀리는 쇠 신음
    base = rng.uniform(70, 110)
    groan = tone(2.2, base, decay=1.0, attack=0.4, shape="saw", glide=base * 0.8, vib=0.03, vib_hz=rng.uniform(3, 6))
    return lowpass(mix((groan, 1.0), (lowpass(noise(2.0, rng, decay=0.8, attack=0.3), 500), 0.4)), 900)


def _amb_drone(rng):  # 멀리 지나가는 청소 드론
    n = _n(2.4)
    buzz = tone(2.4, rng.uniform(160, 220), decay=None, shape="saw", vib=0.02, vib_hz=31)
    env = [math.sin(math.pi * i / n) ** 2 for i in range(n)]
    return lowpass([b * e for b, e in zip(buzz, env)], 1200)


def _amb_thunder(rng):  # 먼 천둥 (산성비 구름)
    rumble = lowpass(noise(2.6, rng, decay=0.9, attack=0.15), 180)
    return drive(rumble, 1.5)


def _amb_clang(rng):  # 어딘가에서 떨어지는 고철
    return lowpass(metal(1.2, rng.uniform(300, 700), rng, decay=0.3), 2500)


SOUNDS = {
    "hit": (_hit, 0.55), "crit": (_crit, 0.7), "sub": (_sub, 0.7),
    "hurt": (_hurt, 0.6), "hurt_heavy": (_hurt_heavy, 0.75),
    "barricade": (_barricade, 0.55), "hack": (_hack, 0.45), "deny": (_deny, 0.35),
    "escape": (_escape, 0.45), "heal": (_heal, 0.4), "eat": (_eat, 0.4), "skill": (_skill, 0.5),
    "win": (_win, 0.5), "alert": (_alert, 0.45), "phase2": (_phase2, 0.7), "death": (_death, 0.7),
    "anvil": (_anvil, 0.55), "clunk": (_clunk, 0.5), "drop": (_drop, 0.55), "repair": (_repair, 0.45),
    "step": (_step, 0.25), "loot": (_loot, 0.35), "gear": (_gear, 0.4),
}
AMBIENT = {
    "amb_creak": (_amb_creak, 0.22), "amb_drone": (_amb_drone, 0.15),
    "amb_thunder": (_amb_thunder, 0.3), "amb_clang": (_amb_clang, 0.14),
}


def build(name, seed=0):
    """이름의 소리를 만들어 16비트 스테레오 바이트로. 같은 seed면 같은 소리."""
    fn, _ = SOUNDS.get(name) or AMBIENT[name]
    rng = random.Random(zlib.crc32(name.encode()) ^ seed)
    width = 0.6 if name.startswith("amb_") else 0.15
    return to_bytes(fn(rng), gain=0.9, width=width, rng=rng)


def volume(name):
    return (SOUNDS.get(name) or AMBIENT[name])[1]
