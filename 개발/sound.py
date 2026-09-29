# sound.py — 사운드 매니저
# pygame-ce 기반 / 실패 시 조용히 무시 (게임 진행 영향 없음)
#
# 채널 구성 (앞 4개는 예약해 효과음이 가져가지 못한다)
#   0: 맵 환경음(바람) — 한 번 틀면 계속 돈다. 전투·서사 때는 소리만 줄였다가 되돌린다 (처음부터 다시 시작하지 않게)
#   1, 2: 음악(서사·전투) — 두 채널을 번갈아 써서 곡을 겹쳐 바꾼다 (크로스페이드)
#   3: 심장박동 경보
#   4~7: 효과음 (assets/sfx/ 음원: 무기별 공격·피격·강화소·발소리 등, 맵의 먼 소리. 출처는 assets/sfx/CREDITS.md)
# 곡은 처음 쓸 때 한 번 풀어 두고, 앞뒤 무음을 잘라 반복 이음매가 끊기지 않게 한다.
# (예전 mixer.music 방식: 전투곡이 25초마다 0.5초씩 끊기고, 곡을 바꿀 때 뚝 끊겼다.)

import array
import os
import sys
import threading
import time

try:
    import pygame
    _OK = True
except ImportError:
    _OK = False

# 곡 이름 -> (파일, 기본 음량). 기본 음량은 사용자 음량 0.5(기본값)일 때의 크기
_TRACKS = {
    "wind":   ("wind.mp3", 0.35),
    "typing": ("typing_bgm.mp3", 0.50),
    "combat": ("combat.mp3", 0.65),
    "boss":   ("bgm_boss.ogg", 0.6),      # Godot TPS Demo 음악 (CC BY 3.0, Christian Fernando Perucchi)
    "night":  ("bgm_night.ogg", 0.4),     # "House In a Forest Loop" (CC BY 3.0, HorrorPen)
    "ending": ("bgm_ending.ogg", 0.55),   # Godot TPS Demo 메뉴 음악 (CC BY 3.0, Christian Fernando Perucchi)
}
_FADE_MS = 700        # 곡 바꿀 때 겹치는 시간
_DUCK = {"typing": 0.45, "combat": 0.0, "boss": 0.0, "night": 0.75, "ending": 0.0}   # 음악이 나올 때 바람 소리 크기 (기본 대비)

_vol_mult = 0.5       # 사용자 BGM 음량 (0.0~1.0)
_muted    = False     # 음소거 상태
_current  = None      # 지금 나오는 음악 이름 (바람 제외). 없으면 None

_ready = False
_sounds = {}          # 곡 이름 -> Sound (앞뒤 무음 자른 것)
_ch_wind = None
_ch_music = []        # [채널 A, 채널 B]
_music_ch = {}        # 곡 이름 -> 지금 그 곡을 튼 채널
_hb_channel = None
_hb_sound = None

_sfx = {}            # 효과음 이름 -> Sound
_sfx_lock = threading.Lock()
_next_amb = 0.0      # 다음 먼 소리(맵) 시각
AMB_GAP = (14.0, 30.0)

# 음량 흐름: 채널 -> [지금 크기, 목표 크기, 초당 변화량, 목표 0이면 멈출지]
_ramps = {}
_lock = threading.Lock()
_load_lock = threading.Lock()   # 미리 풀기 스레드와 곡 틀기가 같은 곡을 두 번 풀지 않게
_thread = None


def _asset(filename):
    """개발 모드: 상위 assets/ / frozen 모드: sys._MEIPASS/assets/ 경로 반환"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "assets", filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", filename)


def _user_gain():
    return 0.0 if _muted else min(1.0, _vol_mult * 2)


def init():
    global _ready, _ch_wind, _ch_music, _hb_channel, _hb_sound, _thread
    if not _OK:
        return
    try:
        pygame.mixer.pre_init(44100, -16, 2, 1024)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(8)
        pygame.mixer.set_reserved(4)
        _ch_wind = pygame.mixer.Channel(0)
        _ch_music = [pygame.mixer.Channel(1), pygame.mixer.Channel(2)]
        _hb_channel = pygame.mixer.Channel(3)
        p = _asset("heartbeat4.wav")
        if os.path.exists(p):
            _hb_sound = pygame.mixer.Sound(p)
            _hb_sound.set_volume(0.90)
        _ready = True
        _thread = threading.Thread(target=_ramp_loop, daemon=True)
        _thread.start()
        # 곡은 미리 풀어 둔다 (전투가 처음 시작될 때 잠깐 멈추지 않게)
        threading.Thread(target=_preload, daemon=True).start()
    except Exception:
        _ready = False


def _preload():
    for n in ("wind", "combat", "typing", "night"):   # 보스·엔딩 곡은 길어서 쓸 때 푼다
        _load(n)
    try:
        for n in SFX_VOL:
            _sfx_sound(n)
    except Exception:
        pass


# 효과음 이름 -> 기본 크기 (파일은 모두 같은 최대 크기로 맞춰 두었다)
SFX_VOL = {
    # 무기별 공격 (constants.WEAPON_SFX로 무기마다 고른다)
    "atk_fist": 0.5, "atk_blade": 0.5, "atk_eblade": 0.5, "atk_blunt": 0.6, "atk_saw": 0.5, "atk_shock": 0.5,
    "atk_flame": 0.55, "atk_gun": 0.55, "atk_shotgun": 0.65, "atk_heavy": 0.7, "atk_energy": 0.55, "atk_toxin": 0.5,
    "crit": 0.6, "sub": 0.7,
    # 적 종류별 공격 (enemy_attack())
    "enemy_drone": 0.5, "enemy_hound": 0.6, "enemy_boss": 0.75,
    "hurt": 0.6, "hurt_heavy": 0.75, "barricade": 0.55, "hack": 0.45, "deny": 0.35, "escape": 0.45,
    "heal": 0.4, "eat": 0.4, "skill": 0.5, "win": 0.5, "alert": 0.45, "phase2": 0.7, "death": 0.7,
    "anvil": 0.55, "clunk": 0.5, "drop": 0.55, "repair": 0.45,
    "step": 0.25, "loot": 0.35, "gear": 0.4,
    # 메뉴·진행
    "ui_move": 0.18, "ui_ok": 0.3, "ui_back": 0.28, "ui_tab": 0.25, "inv_open": 0.35, "diary": 0.3, "save": 0.35,
    "quest_new": 0.4, "quest_done": 0.5, "quest_fail": 0.45, "buy": 0.4, "scan": 0.4, "job": 0.55,
    "evt_good": 0.45, "evt_great": 0.55, "evt_bad": 0.45,
    "search": 0.35, "search_empty": 0.3, "bunker_door": 0.6,
    "amb_creak": 0.22, "amb_drone": 0.15, "amb_thunder": 0.3, "amb_clang": 0.14,
}
SFX_SYNTH_FALLBACK = False   # 음원 파일이 없을 때 코드로 만든 소리를 쓸지 (합성음은 거칠어서 기본은 끔)
_SFX_EXT = (".ogg", ".wav", ".mp3")


def _sfx_files(name):
    """assets/sfx/ 에서 이 효과음의 파일들: <이름>.ogg 또는 변형 <이름>_1.ogg, <이름>_2.ogg … (wav·mp3도 된다)."""
    d = _asset("sfx")
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        stem, ext = os.path.splitext(f)
        if ext.lower() in _SFX_EXT and (stem == name or (stem.startswith(name + "_") and stem[len(name) + 1:].isdigit())):
            out.append(os.path.join(d, f))
    return out


def _sfx_sound(name):
    """효과음 변형 목록 (없으면 None). 칠 때마다 이 중 하나를 골라 같은 소리 반복을 줄인다."""
    with _sfx_lock:
        if name not in _sfx:
            sounds = []
            for p in _sfx_files(name):
                try:
                    sounds.append(pygame.mixer.Sound(p))
                except Exception:
                    pass
            if not sounds and SFX_SYNTH_FALLBACK:
                try:
                    import sfx_synth
                    sounds.append(pygame.mixer.Sound(buffer=sfx_synth.build(name)))
                except Exception:
                    pass
            _sfx[name] = sounds or None
        return _sfx[name]


_sfx_rr = [0]


def _free_sfx_channel():
    """효과음 채널(4~7) 중 쉬는 것, 다 바쁘면 차례로 돌려 쓴다 (음악·경보 채널은 건드리지 않는다)."""
    chans = [pygame.mixer.Channel(i) for i in range(4, 8)]
    for ch in chans:
        if not ch.get_busy():
            return ch
    _sfx_rr[0] = (_sfx_rr[0] + 1) % len(chans)
    return chans[_sfx_rr[0]]


# 적 종류 -> (공격음, 맞는 순간까지 초)
ENEMY_SFX = {"drone": ("enemy_drone", 0.25), "bio_hound": ("enemy_hound", 0.6), "boss": ("enemy_boss", 0.7)}


def enemy_attack(enemy, heavy=False):
    """적의 공격음을 내고, 맞는 순간에 피격음을 잇는다. enemy: drone / bio_hound / boss."""
    name, hit_at = ENEMY_SFX.get(enemy, ENEMY_SFX["drone"])
    sfx(name)
    sfx("hurt_heavy" if heavy else "hurt", delay=hit_at)


def sfx(name, vol=1.0, delay=0.0):
    """효과음 한 번 (delay초 뒤). 음소거·사용자 음량을 따른다. 없는 이름이나 초기화 전이면 조용히 넘어간다."""
    if not _ready or _muted:
        return
    if delay > 0:
        t = threading.Timer(delay, sfx, args=(name, vol))
        t.daemon = True
        t.start()
        return
    try:
        variants = _sfx_sound(name)
        if not variants:
            return
        import random as _r
        snd = _r.choice(variants)
        ch = _free_sfx_channel()
        ch.set_volume(max(0.0, min(1.0, SFX_VOL.get(name, 0.5) * vol * _user_gain() * 1.4)))
        ch.play(snd)
    except Exception:
        pass


def _ambient_tick(now):
    """맵에서 바람만 불 때 가끔 먼 소리를 얹는다 (고철 산 신음, 지나가는 드론, 먼 천둥, 떨어지는 고철)."""
    global _next_amb
    if _current is not None or _ch_wind is None or not _ch_wind.get_busy() or _muted:
        _next_amb = max(_next_amb, now + 6.0)
        return
    if now < _next_amb:
        return
    import random as _r
    _next_amb = now + _r.uniform(*AMB_GAP)
    sfx(_r.choice(["amb_creak", "amb_drone", "amb_thunder", "amb_clang"]), vol=_r.uniform(0.6, 1.0))


def _load(name):
    """곡을 풀어 앞뒤 무음을 잘라 둔다. 이음매는 아주 짧게 페이드해 딸깍 소리를 없앤다."""
    with _load_lock:
        return _load_locked(name)


def _load_locked(name):
    if name in _sounds:
        return _sounds[name]
    fname, _ = _TRACKS[name]
    path = _asset(fname)
    if not os.path.exists(path):
        _sounds[name] = None
        return None
    snd = pygame.mixer.Sound(path)
    try:
        _, fmt, chans = pygame.mixer.get_init()
        if abs(fmt) == 16:
            raw = array.array("h", snd.get_raw())
            th = 300
            n = len(raw)
            lead = next((i for i in range(n) if abs(raw[i]) > th), 0)
            trail = next((i for i in range(n) if abs(raw[n - 1 - i]) > th), 0)
            lead -= lead % chans
            end = n - trail
            end -= (end - lead) % chans
            body = raw[lead:end]
            edge = min(len(body) // 4, int(44100 * 0.008) * chans)   # 8ms
            for i in range(edge):
                k = (i // chans) / (edge // chans or 1)
                body[i] = int(body[i] * k)
                body[-1 - i] = int(body[-1 - i] * k)
            if len(body) > 44100 * chans:  # 너무 짧게 잘렸으면 원본을 쓴다
                snd = pygame.mixer.Sound(buffer=body.tobytes())
    except Exception:
        pass
    _sounds[name] = snd
    return snd


# ── 음량 흐름 (별도 스레드가 20ms마다 목표 음량으로 옮긴다) ─────────────────
def _ramp(ch, target, ms, stop_at_zero=False):
    if ch is None:
        return
    with _lock:
        cur = _ramps[ch][0] if ch in _ramps else ch.get_volume()
        speed = abs(target - cur) / max(0.001, ms / 1000)
        _ramps[ch] = [cur, target, speed, stop_at_zero]


def _ramp_loop():
    last = time.perf_counter()
    while True:
        time.sleep(0.02)
        now = time.perf_counter()
        try:
            _ambient_tick(now)
        except Exception:
            pass
        dt, last = now - last, now
        with _lock:
            for ch, r in list(_ramps.items()):
                cur, target, speed, stop = r
                step = speed * dt
                cur = target if abs(target - cur) <= step or speed == 0 else cur + (step if target > cur else -step)
                r[0] = cur
                try:
                    ch.set_volume(cur)
                    if cur == target:
                        if stop and target == 0:
                            ch.stop()
                        del _ramps[ch]
                except Exception:
                    _ramps.pop(ch, None)


def _wind_level():
    base = _TRACKS["wind"][1] * _user_gain()
    return base * _DUCK.get(_current, 1.0)


def _music_level(name):
    return _TRACKS[name][1] * _user_gain()


# ── 바깥에서 부르는 것 (이름은 예전과 같다) ──────────────────────────────
def set_bgm_volume(vol: float):
    """사용자 BGM 음량 설정 (0.0~1.0). 곡마다 정한 크기 비율은 그대로 두고 즉시 반영."""
    global _vol_mult
    _vol_mult = max(0.0, min(1.0, vol))
    _apply_levels()


def set_mute(muted: bool):
    """음소거 토글. 즉시 반영."""
    global _muted
    _muted = muted
    _apply_levels()


def _apply_levels(ms=150):
    if not _ready:
        return
    if _ch_wind.get_busy():
        _ramp(_ch_wind, _wind_level(), ms)
    for name, ch in _music_ch.items():
        if name == _current:
            _ramp(ch, _music_level(name), ms)


def _play_music(name):
    """음악(서사·전투)을 겹쳐 바꾼다. 같은 곡이 이미 나오면 그대로 둔다."""
    global _current
    if not _ready or _current == name:
        return
    try:
        snd = _load(name)
        if snd is None:
            return
        # 나가는 곡: 줄이다가 멈춘다
        for old, ch in list(_music_ch.items()):
            _ramp(ch, 0.0, _FADE_MS, stop_at_zero=True)
            del _music_ch[old]
        # 들어오는 곡: 쉬고 있는 채널에서 0부터 키운다
        ch = next((c for c in _ch_music if not c.get_busy() and c not in _ramps), None) or _ch_music[0]
        with _lock:
            _ramps.pop(ch, None)
        ch.set_volume(0.0)
        ch.play(snd, loops=-1)
        _music_ch[name] = ch
        _current = name
        _ramp(ch, _music_level(name), _FADE_MS)
        _ramp(_ch_wind, _wind_level(), _FADE_MS)
    except Exception:
        pass


def play_map_ambient():
    """맵 환경음 (바람). 이미 돌고 있으면 음악만 걷어내고 바람을 원래 크기로 되돌린다."""
    global _current
    if not _ready:
        return
    try:
        for old, ch in list(_music_ch.items()):
            _ramp(ch, 0.0, _FADE_MS, stop_at_zero=True)
            del _music_ch[old]
        _current = None
        if not _ch_wind.get_busy():
            snd = _load("wind")
            if snd is None:
                return
            with _lock:
                _ramps.pop(_ch_wind, None)
            _ch_wind.set_volume(0.0)
            _ch_wind.play(snd, loops=-1)
        _ramp(_ch_wind, _wind_level(), _FADE_MS * 2)
    except Exception:
        pass


def play_typing_bgm():
    """서사·스크립트 BGM (바람은 뒤에 작게 깔린다)"""
    _play_music("typing")


def play_combat_bgm():
    """전투 BGM (바람은 잦아든다)"""
    _play_music("combat")


def play_boss_bgm():
    """보스전 BGM"""
    _play_music("boss")


def play_ending_bgm():
    """엔딩 BGM"""
    _play_music("ending")


def map_mood(time_of_day):
    """맵에서 부른다: 밤·새벽에는 바람 밑으로 어두운 음악을 깔고, 낮에는 걷어낸다."""
    if _current not in (None, "night"):
        return   # 전투·서사 음악 중에는 건드리지 않는다
    if time_of_day in ("night", "dawn"):
        _play_music("night")
    elif _current == "night":
        play_map_ambient()


def resume_map_ambient():
    """전투/스크립트 종료 후 맵 환경음으로 복귀 (바람은 멈춘 적이 없으니 이어서 들린다)"""
    play_map_ambient()


def stop_all(fade_ms=800):
    """모든 사운드 정지 (게임 종료·엔딩 시)"""
    global _current
    if not _ready:
        return
    try:
        for ch in [_ch_wind] + _ch_music:
            if ch.get_busy():
                _ramp(ch, 0.0, fade_ms, stop_at_zero=True)
        _music_ch.clear()
        if _hb_channel:
            _hb_channel.stop()
        _current = None
    except Exception:
        pass


def check_survival_alert(hunger: int, thirst: int):
    """허기 또는 갈증 ≤ 10 → 심장박동 경보 ON  /  회복 시 OFF"""
    if not _OK or _hb_channel is None or _hb_sound is None:
        return
    try:
        critical = hunger <= 10 or thirst <= 10
        if critical:
            if not _hb_channel.get_busy():
                _hb_channel.play(_hb_sound, loops=-1)
        else:
            if _hb_channel.get_busy():
                _hb_channel.stop()
    except Exception:
        pass
