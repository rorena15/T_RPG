# sound.py — 사운드 매니저
# pygame-ce 기반 / 실패 시 조용히 무시 (게임 진행 영향 없음)
# 채널 구성: music 채널(BGM 교체 방식) + Channel(7) 심장박동 전용

import os
import sys

try:
    import pygame
    _OK = True
except ImportError:
    _OK = False

_hb_channel = None   # 심장박동 전용 채널
_hb_sound   = None   # 심장박동 Sound 객체
_current    = None   # 현재 재생 중인 BGM 식별자


def _asset(filename):
    """개발 모드: 상위 assets/ / frozen 모드: sys._MEIPASS/assets/ 경로 반환"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "assets", filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", filename)


def init():
    global _hb_channel, _hb_sound
    if not _OK:
        return
    try:
        pygame.mixer.pre_init(44100, -16, 2, 1024)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(8)
        _hb_channel = pygame.mixer.Channel(7)
        p = _asset("heartbeat4.wav")
        if os.path.exists(p):
            _hb_sound = pygame.mixer.Sound(p)
            _hb_sound.set_volume(0.90)
    except Exception:
        pass


def _play_music(filename, volume=0.45, loops=-1):
    global _current
    if not _OK:
        return
    try:
        path = _asset(filename)
        if not os.path.exists(path):
            return
        if _current == filename:
            return
        pygame.mixer.music.fadeout(600)
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(loops)
        _current = filename
    except Exception:
        pass


def play_map_ambient():
    """맵 환경음 (wind) 루프"""
    _play_music("wind.mp3", volume=0.35)


def play_typing_bgm():
    """서사·스크립트 BGM"""
    _play_music("typing_bgm.mp3", volume=0.50)


def play_combat_bgm():
    """전투 BGM"""
    _play_music("combat.mp3", volume=0.65)


def resume_map_ambient():
    """전투/스크립트 종료 후 맵 환경음으로 복귀"""
    global _current
    _current = None   # 강제 재로드
    play_map_ambient()


def stop_all(fade_ms=800):
    """모든 사운드 정지 (게임 종료·엔딩 시)"""
    global _current
    if not _OK:
        return
    try:
        pygame.mixer.music.fadeout(fade_ms)
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
