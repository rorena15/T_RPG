"""옵션 화면과 설정 적용.

설정은 core.load_settings() / save_settings()의 dict 하나다 (게임 폴더 settings.json). 묶음 세 개로 나눠 보여 준다:
  소리: 전체 · 음악 · 환경음 · 효과음 음량(5% 단위), 음소거
  화면: 전체 화면, 글자 크기, 화면 흔들림, 장면 움직임
  게임: 언어, 텍스트 속도, 전투 속도, 자동 저장, 동적 서사
줄마다 Enter(또는 숫자키)는 다음 값으로, ←→는 앞뒤 값으로 바꾼다. 그림 화면이 없으면 같은 목록을 글 화면으로 찍는다.
apply()는 설정을 게임에 반영한다 (게임을 켤 때 한 번, 값이 바뀔 때마다).
"""
import constants
import sound
from core import save_settings
from i18n import set_lang, t

VOLUMES = [("master_volume", 'opt_master_volume', sound.set_master_volume),
           ("bgm_volume", 'opt_volume', sound.set_bgm_volume),
           ("amb_volume", 'opt_amb_volume', sound.set_amb_volume),
           ("sfx_volume", 'opt_sfx_volume', sound.set_sfx_volume)]
# 고르는 설정: 이름 -> [(문구 키, 값)]. 문구 키가 튜플이면 (키, 끼울 값)
CHOICES = {
    "text_speed":   [('opt_speed_slow', 2.0), ('opt_speed_normal', 1.0), ('opt_speed_fast', 0.5), ('opt_speed_instant', 0.0)],
    "combat_speed": [('opt_speed_normal', 1.0), ('opt_speed_fast', 0.4), ('opt_speed_instant', 0.0)],
    "font_scale":   [('opt_font_1', 1.0), ('opt_font_2', 1.15), ('opt_font_3', 1.3)],
    "autosave":     [('opt_off', 0), (('opt_auto_n', 10), 10), (('opt_auto_n', 5), 5)],
    "screen_shake": [('opt_on', True), ('opt_off', False)],
    "reduce_motion": [('opt_motion_full', False), ('opt_motion_less', True)],
    "fullscreen":   [('opt_off', False), ('opt_on', True)],
    "mute":         [('opt_mute_off', False), ('opt_mute_on', True)],
}


def apply(settings, term=None):
    """설정을 게임에 반영한다."""
    for name, _, fn in VOLUMES:
        fn(settings[name])
    sound.set_mute(settings["mute"])
    constants.TEXT_SPEED_MULT = settings["text_speed"]
    constants.COMBAT_SPEED = settings["combat_speed"]
    constants.SCREEN_SHAKE = bool(settings["screen_shake"])
    constants.REDUCE_MOTION = bool(settings["reduce_motion"])
    constants.FONT_SCALE = settings["font_scale"]
    constants.AUTOSAVE_TURNS = int(settings["autosave"])
    if term is not None and bool(settings["fullscreen"]) != bool(getattr(term, "_fullscreen", False)):
        term.toggle_fullscreen()


def _label(name, settings):
    cur = settings[name]
    key = next((k for k, v in CHOICES[name] if v == cur), CHOICES[name][0][0])
    return t(key[0], n=key[1]) if isinstance(key, tuple) else t(key)


def _cycle(name, settings, step):
    vals = [v for _, v in CHOICES[name]]
    i = vals.index(settings[name]) if settings[name] in vals else 0
    settings[name] = vals[(i + step) % len(vals)]


def _volume(name, settings, delta, wrap=False):
    n = round(settings[name] * 20) + delta
    settings[name] = ((0 if n > 20 else n) if wrap else max(0, min(20, n))) / 20


def _rows(page, settings):
    """그 묶음의 줄들: [(키, 글, 종류, 이름)]. 종류: vol 음량 / pick 고르는 값 / go 다른 화면."""
    import gm_bridge
    if page == "main":
        return [("1", t('opt_cat_sound'), "go", "sound"), ("2", t('opt_cat_display'), "go", "display"),
                ("3", t('opt_cat_game'), "go", "game"), ("4", t('opt_endings'), "go", "endings"),
                ("5", t('opt_credits'), "go", "credits")]
    if page == "sound":
        rows = [(str(i + 1), f"{t(label)}   ◀ {round(settings[name] * 100)}% ▶", "vol", name)
                for i, (name, label, _) in enumerate(VOLUMES)]
        return rows + [("5", f"{t('opt_mute')}   [{_label('mute', settings)}]", "pick", "mute")]
    if page == "display":
        return [(str(i + 1), f"{t(label)}   [{_label(name, settings)}]", "pick", name) for i, (name, label) in enumerate(
            (("fullscreen", 'opt_fullscreen'), ("font_scale", 'opt_font'), ("screen_shake", 'opt_shake'), ("reduce_motion", 'opt_motion')))]
    import gm_server
    mode = gm_bridge.get_mode()
    rows = [("1", t('lang_header'), "go", "lang"),
            ("2", f"{t('opt_text_speed')}   [{_label('text_speed', settings)}]", "pick", "text_speed"),
            ("3", f"{t('opt_combat_speed')}   [{_label('combat_speed', settings)}]", "pick", "combat_speed"),
            ("4", f"{t('opt_autosave')}   [{_label('autosave', settings)}]", "pick", "autosave"),
            ("5", f"{t('opt_gm')}   [{t(f'opt_gm_{mode}')}]" + ("" if gm_bridge.mode_installed(mode) else f"  {t('opt_gm_missing')}"), "gm", "gm_mode")]
    if not gm_server.runtime_ok():  # 실행기가 없는 빌드는 동적 서사 항목을 숨긴다
        return rows[:-1]
    if mode != "off" and not gm_bridge.mode_installed(mode):
        rows.append(("6", t('opt_gm_download'), "go", "download"))
    return rows


def _hint(page):
    import gm_bridge
    return {"display": t('opt_display_hint'), "game": t(f'opt_gm_desc_{gm_bridge.get_mode()}')}.get(page)


def _ask_terminal(title, rows, hint):
    from ui import clear_screen, print_divider, print_header, read_key
    clear_screen()
    print_header(title)
    print_divider()
    for key, text, _, _ in rows:
        print(f"  {key}. {text}")
    if hint:
        print(f"     {hint}")
    print_divider()
    print(f"  0. {t('diff_back')}")
    print_divider()
    return read_key()


def run(settings, term, offer_data=None):
    """옵션 화면. 바뀐 값은 그 자리에서 반영하고 저장한다."""
    import gm_bridge
    scr = None
    scene = "forge"
    if term:
        from screens import MenuScreen
        scr = MenuScreen(scene=scene)
    titles = {"main": 'menu_options', "sound": 'opt_cat_sound', "display": 'opt_cat_display', "game": 'opt_cat_game'}
    page, last = "main", {}
    try:
        while True:
            settings["fullscreen"] = bool(getattr(term, "_fullscreen", False)) if term else settings["fullscreen"]   # F11로 바꿨을 수 있다
            rows = _rows(page, settings)
            back = t('diff_back') if page == "main" else t('ui_back')
            if scr:
                items = [(k, text) for k, text, _, _ in rows] + [("0", back)]
                hint = _hint(page)
                ok = scr.ask(t(titles[page]), items, lines=[hint] if hint else None, back="0",
                             start=next((i for i, (k, _) in enumerate(items) if k == last.get(page)), 0),
                             adjust=tuple(k for k, _, kind, _ in rows if kind in ("vol", "pick", "gm")))
            else:
                ok = _ask_terminal(t(titles[page]), rows, _hint(page))
            step = 0
            if ok[:1] in "<>" and len(ok) > 1:
                step, ok = (-1 if ok[0] == "<" else 1), ok[1:]
            last[page] = ok
            if ok == "0":
                if page == "main":
                    return
                page = "main"
                continue
            row = next((r for r in rows if r[0] == ok), None)
            if row is None:
                continue
            _, _, kind, name = row
            if kind == "vol":
                _volume(name, settings, step if step else 2, wrap=not step)   # ←→ 5%, Enter 10% (100% 다음은 0%)
            elif kind == "pick":
                _cycle(name, settings, step or 1)
            elif kind == "gm":
                modes = gm_bridge.MODES
                settings["gm_mode"] = modes[(modes.index(gm_bridge.get_mode()) + (step or 1)) % len(modes)]
                gm_bridge.set_mode(settings["gm_mode"])
            elif name in ("sound", "display", "game"):
                page = name
                continue
            elif name == "endings":
                if scr:
                    from screens import show_codex
                    show_codex()
                else:
                    import endings
                    from ui import clear_screen, print_header, wait_for_keypress
                    clear_screen()
                    print_header(t('opt_endings'))
                    for ln in endings.codex_lines():
                        print(f"  {ln}")
                    wait_for_keypress()
                continue
            elif name == "credits":
                import credits
                credits.menu(scr)
                continue
            elif name == "lang":
                langs = [("1", t('lang_ko')), ("2", t('lang_en'))]
                k = scr.ask(t('lang_header'), langs + [("0", t('diff_back'))], back="0") if scr else \
                    _ask_terminal(t('lang_header'), [(a, b, "", "") for a, b in langs], None)
                if k in ("1", "2"):
                    set_lang("ko" if k == "1" else "en")
                continue
            elif name == "download":
                if offer_data:
                    if scr:
                        scr.close()
                    offer_data(settings, force=True)
                    if term:
                        from screens import MenuScreen
                        scr = MenuScreen(scene=scene)
                continue
            apply(settings, term)
            if name in ("master_volume", "sfx_volume"):
                sound.sfx("ui_ok")   # 바뀐 크기를 바로 들려준다
            save_settings(settings)
            if name == "font_scale" and scr:   # 글자 크기는 화면을 새로 만들어야 보인다
                from screens import MenuScreen
                scr.close()
                scr = MenuScreen(scene=scene)
    finally:
        if scr:
            scr.close()
