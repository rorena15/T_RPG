"""이벤트 화면 왼쪽 장면 일러스트 만들기 (로컬 SDXL, 오프라인·무료).

코드로 그린 장면(event_view._paint_scene)을 구도 밑그림으로 넣고 img2img로 유화풍 디지털 페인팅을 입힌다.
구도가 밑그림을 따라가서, 게임이 위에 얹는 움직이는 효과(조준광, 빗줄기, 불빛, 거품)가 그림과 맞는다.
스타일: 거친 붓 터치의 디지털 페인팅, 누런 세피아 하늘, 탁한 저채도, 짙은 대기 원근, 작은 강조광.
모델: stabilityai/stable-diffusion-xl-base-1.0 (CreativeML OpenRAIL++-M, 상업 이용 가능) + madebyollin/sdxl-vae-fp16-fix (MIT).

두 단계 (환경이 달라서):
  python gen_scenes.py init                                   # 게임 파이썬(pygame): 밑그림 -> E:/Git_Project/stigma-train/art/init/
  <학습 venv>/python gen_scenes.py paint [--only camp,turret] [--n 4] [--strength 0.62]
                                                              # 후보 -> E:/Git_Project/stigma-train/art/cand/<이름>_<seed>.jpg + 모아 보기
  <학습 venv>/python gen_scenes.py txt [--only camp] [--seeds 2]   # 밑그림 없이 분위기 4가지 x seeds장 (주로 이것)
  python gen_scenes.py pick camp camp_dusk_1 camp_night_0     # 고른 후보 -> assets/scenes/camp/ (게임이 무작위로 씀)
  <학습 venv>/python gen_scenes.py layers [--only camp]         # 고른 그림을 깊이로 3층 분리 (패럴랙스용)
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
OUT = "E:/Git_Project/stigma-train/art"
SCENES_DIR = os.path.join(GAME, "..", "assets", "scenes")
SIZE = (576, 1600)  # 장면 칸(340x944)과 같은 비율, SDXL이 다루는 픽셀 수

STYLE = ("digital painting, concept art illustration, visible rough textured brush strokes, painterly, "
         "post-apocalyptic wasteland, hazy sepia yellow sky, light rays through dust, desaturated muted earthy palette, "
         "detailed foreground rubble, twisted steel beams, scrap metal shards, broken car wrecks, drifting smoke, "
         "atmospheric perspective, distant ruins fading into haze, cinematic composition, highly detailed, "
         "the air is always thick with smog, dust and haze, the sun is never clearly visible")
NEGATIVE = ("photo, photorealistic, 3d render, cgi, cartoon, anime, flat colors, vector, clean lines, text, letters, "
            "watermark, signature, logo, frame, border, people, crowd, face, blurry, lowres, jpeg artifacts, oversaturated, "
            "pitch black, underexposed")
SUBJECT = {  # 이름 -> 장면 중심 (밑그림의 모티프 위치와 맞춘다)
    "junkyard": "endless junkyard of scrapped drones and burnt circuit boards, a toppled crane against the sky",
    "bunker": "a half-buried rusted iron bunker door in a sea of scrap, dim orange glow",
    "turret": "a military sentry gun turret with one long barrel on an armored rotating head, bolted onto a concrete bunker pillar in the rubble, thin red targeting laser",
    "camera": "a surveillance camera on a bent pole, red indicator light, faint red scanning cone",
    "rain": "acid rain pouring over the scrapyard, sickly yellow sky, streaks of rain",
    "toxic": "a glowing toxic green pool among the scrap, green haze, bubbles",
    "container": "a large tilted rusted cargo shipping container half sunk in debris, small amber seal",
    "tower": "a collapsed steel lattice watchtower leaning over the scrap, a small red warning light",
    "signal": "a lone radio antenna mast with a dish, faint teal signal glow",
    "broadcast": "a loudspeaker horn on a pole, ominous red glow",
    "camp": "an abandoned scavenger tent and a smoldering campfire with glowing orange embers",
    "drones": "wrecked combat drones piled in the foreground, bent rotor arms, a few electric sparks",
    "machine": "a derelict old terminal cabinet with a faintly glowing teal screen",
    "mine": "a rusted landmine half buried in dirt with a blinking red light",
    "figure": "a wounded lone scavenger slumped against the wreckage, silhouette",
    "crate": "a battered emergency supply crate with a faded red cross half buried in rubble",
    "wall": "a cracked concrete wall covered with scratched names and messages",
    # ── 세계 장면 라이브러리 (이벤트와 별개로 장소·원경·적을 보여 준다) ──
    "scrap_sea": "an endless sea of scrap and drone carcasses under mercury fog",
    "crane": "a colossal toppled industrial crane rusting over mountains of scrap",
    "bunker_inside": "inside a cramped old underground shelter, rusted bunk beds, dripping pipes, a flickering emergency lamp",
    "bunker_stairs": "concrete stairs descending into the darkness of an old underground shelter, a heavy rusted iron door ajar",
    "ruin_factory": "inside a collapsed abandoned factory hall, broken conveyor lines, light shafts through a caved in roof",
    "ruin_server": "inside a ruined server room, toppled server racks, tangled cables, faint status lights",
    "forge": "inside a scrap fortress workshop, a glowing forge and a humming generator, walls of welded scrap plates",
    "barricade": "a fortified barricade wall of welded scrap plates and spikes guarding a hideout in the junkyard",
    "slum_alley": "a narrow slum alley under a dead megacity, dark neon signs, dangling cables, puddles",
    "slum_fans": "a slum courtyard full of abandoned server cooling fans and blinking cables, electric haze",
    "basin_valley": "a molten radioactive valley of glassy scorched ground, dead land, eerie glow",
    "basin_storm": "a radioactive storm sweeping over a melted basin, sickly glowing clouds",
    "neo_city": "far away on the horizon the colossal walls of a megacity glowing, thin tyrian blue laser lines, the wasteland in front",
    "hq_wall": "a towering corporate megastructure wall with sweeping tyrian blue laser firewalls, scanning beams in the fog",
    "enemy_drones": "a formation of armored security drones hovering over the scrapyard, red sensor eyes",
    "enemy_dogs": "a pack of mangy radiation sick feral dogs prowling through the scrap, glinting eyes",
    "enemy_hound": "a four legged mechanical beast made entirely of titanium plates and hydraulic jaws stalking through the haze, machine only",
    "enemy_collector": "a huge sweeper machine with caterpillar tracks and hydraulic crushing blades grinding through the scrap",
    "enemy_security": "a squad of faceless armored security troopers with glowing visor slits advancing through fog",
    # ── 지형: 쓰레기 바다 / 무너진 도시 / 경계 지대 (한 가지에 고정되지 않게) ──
    "ruin_city": "a collapsed city, leaning skyscrapers with hollow windows, streets buried in rubble, a broken elevated highway",
    "border_zone": "the edge where a ruined city meets the sea of scrap, heaps of junk flooding between crumbling buildings",
    # ── 랜드마크: 멸망 전(구시대) 건물, 부서졌지만 형체는 남았다. 간판 글자 없이 상징으로만 ──
    "lm_hospital": "a ruined old hospital building, a faded red cross symbol on its cracked facade, broken ambulances",
    "lm_station": "a half collapsed old train station with a broken glass roof, an abandoned train rusting on the tracks",
    "lm_highway": "a snapped elevated highway overpass with dangling rebar and rusted cars stuck on the edge",
    "lm_amusement": "an abandoned amusement park, the skeleton of a rusted ferris wheel and a collapsed roller coaster",
    "lm_school": "a ruined old school building and an empty cracked playground with a toppled basketball hoop",
    "lm_mall": "inside the atrium of an abandoned shopping mall, broken escalators, collapsed glass ceiling, dead fountain",
    "lm_cathedral": "the broken spire and gothic arches of a ruined cathedral standing among scrap",
    "lm_subway": "a subway entrance half buried in rubble, stairs descending into darkness",
    "lm_powerplant": "the cracked cooling towers of an old power plant looming over the wasteland",
    "lm_apartments": "a ruined apartment complex, rows of hollow concrete blocks with collapsed balconies",
    "lm_bridge": "a broken suspension bridge with snapped cables over a dry polluted riverbed",
    "lm_airport": "a ruined airport control tower and a crashed airliner fuselage on a cracked runway",
    # ── 인물: 얼굴은 사물·가면·그림자로 가리고 체형이 드러나지 않는 옷 (NPC 성별 비공개 원칙) ──
    "fig_scavengers": "a few scavengers in gas masks and heavy hooded coats huddled around a small fire, faces hidden",
    "fig_trader": "a hooded trader in a heavy cloak sitting behind spread out salvaged parts, face lost in the hood shadow",
    "fig_hacker": "a hooded figure hunched over a glowing cyberdeck in a dark corner, the face hidden behind the screen glare",
    "fig_elder_forge": "a broad figure in a welding mask and heavy leather apron working at a forge, seen from behind, sparks flying",
    "fig_executive": "a tall figure in a long coat silhouetted against blue laser light, the face lost in the backlight",
}
FIGURE_NEG = ("visible face, facial features, eyes, beard, lipstick, breasts, woman, man, feminine, masculine, "
              "portrait, close-up")
# 장면 종류: 구도 앞머리가 다르다 (풍경 / 실내 / 원경 / 적). 없으면 wide
KIND = {n: "interior" for n in ("bunker_inside", "bunker_stairs", "ruin_factory", "ruin_server", "forge", "slum_fans",
                                  "lm_mall", "fig_hacker")}
KIND.update({"neo_city": "vista", "hq_wall": "vista", "basin_storm": "vista"})
KIND.update({n: "enemy" for n in ("enemy_drones", "enemy_dogs", "enemy_hound", "enemy_collector", "enemy_security")})
SUBJECT_NEG = {  # 장면별 추가 제외어
    "turret": "tank, vehicle with tracks",
    # 원작 반전 보호: 기계 괴수는 순수한 기계로만 그린다 (유기체·인간 요소 금지)
    "enemy_hound": "flesh, skin, organic tissue, human, human face, blood, gore, muscle, eyes of a person",
    "enemy_collector": "flesh, organic tissue, human, blood, gore",
    "enemy_security": "visible face, woman, man, gender, portrait",
    "figure": "visible face, portrait, woman, man",
}
SUBJECT_NEG.update({n: FIGURE_NEG for n in SUBJECT if n.startswith("fig_")})


def init():
    """event_view의 코드 그림을 밑그림으로 저장한다 (움직이는 효과의 한 순간도 같이 그려 불빛 자리를 알려 준다)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, GAME)
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    import event_view
    from event_view import EventView, EVENT_MOTIF, SCENES, MOTIF_TINT, PLATE_W
    import random
    os.makedirs(os.path.join(OUT, "init"), exist_ok=True)
    H = 944
    inv = {}
    for eid, m in EVENT_MOTIF.items():
        inv.setdefault(m, eid)
    targets = [(n, inv.get(n), "구시대 지하 방공호" if n == "bunker" else "폐기물 처리장") for n in SUBJECT]

    class _T:
        _find_bundled_font = staticmethod(lambda: None)
    for name, eid, loc in targets:
        v = EventView.__new__(EventView)
        v.motif, v.location = event_view.EVENT_MOTIF.get(eid), loc
        sc = dict(SCENES[loc])
        sc.update(MOTIF_TINT.get(v.motif, {}))
        horizon = int(H * 0.56)
        v._horizon, v._sc = horizon, sc
        s = pygame.Surface((PLATE_W, H))
        v._paint_scene(s, H, sc, horizon, random.Random(sum(map(ord, loc))))
        v._motif_anim(s, H, 1.3)
        pygame.image.save(pygame.transform.smoothscale(s, SIZE), os.path.join(OUT, "init", f"{name}.png"))
        print("init", name)


def paint(only, n, strength, steps):
    import torch
    from diffusers import AutoencoderKL, StableDiffusionXLImg2ImgPipeline
    from PIL import Image
    vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", vae=vae, torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True).to("cuda")
    pipe.vae.enable_tiling()
    os.makedirs(os.path.join(OUT, "cand"), exist_ok=True)
    names = [x for x in SUBJECT if not only or x in only]
    for name in names:
        init_img = Image.open(os.path.join(OUT, "init", f"{name}.png")).convert("RGB")
        cands = []
        for k in range(n):
            g = torch.Generator("cuda").manual_seed(1000 + k)
            img = pipe(prompt=f"{SUBJECT[name]}, {STYLE}", negative_prompt=NEGATIVE, image=init_img,
                       strength=strength, num_inference_steps=steps, guidance_scale=6.0, generator=g).images[0]
            path = os.path.join(OUT, "cand", f"{name}_{k}.jpg")
            img.save(path, quality=90)
            cands.append(img)
            print("paint", path, flush=True)
        sheet = Image.new("RGB", (SIZE[0] // 2 * (n + 1), SIZE[1] // 2))
        sheet.paste(init_img.resize((SIZE[0] // 2, SIZE[1] // 2)), (0, 0))
        for k, img in enumerate(cands):
            sheet.paste(img.resize((SIZE[0] // 2, SIZE[1] // 2)), ((k + 1) * SIZE[0] // 2, 0))
        sheet.save(os.path.join(OUT, "cand", f"_{name}_sheet.jpg"), quality=85)


# 장면마다 분위기를 바꿔 여러 장 뽑는다 (같은 그림을 계속 보면 질린다). 산성비·독성은 고유 색이라 분위기를 덜 바꾼다.
MOODS = {
    "dusk": "at dusk, low burnt orange sun behind haze",
    "overcast": "overcast grey daylight, pale diffuse light, heavy clouds",
    "night": "at night, cold mercury blue haze, a few faint glowing lights",
    "storm": "in a dust storm, thick yellow ochre haze, wind blown debris",
}
FIXED_MOOD = {"rain": ["dusk", "overcast"], "toxic": ["night", "overcast"]}
TIMES = {  # 시간은 빛의 양과 색만 바꾼다 (공기는 늘 탁하다)
    "dawn": "at dawn, murky blue grey half light, the dimmest light",
    "morning": "in the morning, pale yellow light scattered through smog, soft blurred shadows",
    "noon": "at midday, more light but diffused by ochre smog and dust, washed out shadows",
    "evening": "at evening, a muddy orange glow bleeding through the dust",
    "night": "at night, near darkness, a few distant lights and mercury haze",
}
WEATHERS = {
    "smog": "ordinary thick smog",
    "fog": "dense fog swallowing the distance",
    "dust": "a yellow dust storm, wind blown sand and debris",
    "acid": "acid rain falling, wet reflective ground",
    "ash": "grey ash drifting down like snow",
}
WEATHER_FIXED = {"rain": "acid"}
# 실내는 해·하늘 대신 조명으로 분위기를 바꾼다
INTERIOR_MOODS = {
    "dim": "dim orange emergency light, deep shadows",
    "cold": "cold blue light leaking through cracks, dust in the air",
}
# 풍경이 화면을 채우고 피사체는 그 안의 일부로 작게 (피사체 하나만 크게 잡힌 그림이 너무 많았다, 사용자 피드백)
WIDE = ("wide establishing shot, vast desolate landscape fills the frame, environment concept art, deep layered depth, "
        "the ground is a scrapyard littered with drone wreckage, scrap metal and burnt electronics, "
        "foreground rubble, midground scrap fields, far background ruins and sky, seen from a distance, in the scene: ")
PREFIX = {
    "wide": WIDE,
    "interior": ("interior environment concept art, wide angle view, the room fills the frame, cluttered with rust and debris, "
                 "deep perspective, in the scene: "),
    "vista": ("epic wide vista, environment concept art, vast scale, deep atmospheric perspective, "
              "a scrapyard wasteland in the foreground, in the scene: "),
    "enemy": ("wide shot, environment concept art, the menacing threat is seen from a distance, half hidden in haze, "
              "the scrapyard landscape still fills most of the frame, in the scene: "),
}
WIDE_NEG = "close-up, macro, portrait shot, subject filling the frame, centered object study, isolated object"
# 640x1536은 SDXL이 장면을 위아래로 2~3개 쌓아 그렸다 (실측). 768x1344로 뽑고 게임이 높이 맞춰 가운데를 자른다
TXT_SIZE = (768, 1344)
# 분위기별 색면 밑그림: 하늘 위 -> 지평선, 땅 지평선 -> 아래 (형태 없이 색과 밝기만 준다)
MOOD_FIELD = {
    "dusk": [(22, 18, 16), (120, 70, 38), (190, 110, 52), (60, 44, 34), (14, 12, 11)],
    "overcast": [(40, 40, 40), (96, 94, 88), (132, 126, 112), (58, 54, 48), (16, 15, 14)],
    "night": [(8, 10, 16), (26, 34, 48), (52, 66, 80), (24, 26, 30), (8, 8, 9)],
    "storm": [(60, 48, 26), (150, 118, 60), (186, 150, 82), (84, 66, 40), (20, 16, 12)],
}
# 시간별 색면 (낮도 밤보다 조금 밝을 뿐 같은 톤)
MOOD_FIELD.update({
    "dawn": [(12, 14, 18), (40, 46, 54), (70, 76, 82), (30, 30, 32), (9, 9, 10)],
    "morning": [(46, 42, 32), (104, 94, 70), (138, 122, 88), (56, 50, 40), (15, 14, 12)],
    "noon": [(58, 52, 38), (122, 108, 78), (150, 132, 94), (64, 56, 42), (17, 15, 12)],
    "evening": [(22, 18, 16), (110, 66, 36), (170, 100, 50), (56, 42, 32), (13, 11, 10)],
})
WEATHER_TINT = {"dust": (170, 140, 80), "acid": (150, 150, 80), "ash": (120, 118, 114), "fog": (110, 112, 112)}
MOOD_FIELD["dim"] = [(10, 9, 8), (40, 28, 18), (70, 46, 26), (34, 26, 20), (8, 7, 6)]
MOOD_FIELD["cold"] = [(8, 10, 13), (26, 34, 44), (44, 58, 70), (22, 26, 30), (7, 8, 9)]
MOOD_FIELD_TINT = {"rain": (170, 160, 70), "toxic": (70, 150, 80), "hq_wall": (60, 60, 150), "neo_city": (50, 60, 130)}


def color_field(mood, name, seed, weather=None):
    """형태 없는 색면 밑그림. 하늘·지평선·땅의 색과 밝기만 정해 화풍과 색감을 모든 장면에 맞춘다
    (밑그림 없이 뽑으면 밝은 판타지 풍경화 쪽으로 흘렀다). 약간의 얼룩을 넣어 붓질 여지를 준다."""
    import random
    from PIL import Image, ImageFilter
    w, h = TXT_SIZE
    stops = MOOD_FIELD[mood]
    tint = MOOD_FIELD_TINT.get(name) or WEATHER_TINT.get(weather)
    img = Image.new("RGB", (w, h))
    px = img.load()
    horizon = 0.55
    for y in range(h):
        t = y / h
        if t < horizon:
            seg, lt = (0, t / (horizon * 0.6)) if t < horizon * 0.6 else (1, (t - horizon * 0.6) / (horizon * 0.4))
            a, b = stops[seg], stops[seg + 1]
        else:
            seg, lt = (2, (t - horizon) / 0.12) if t < horizon + 0.12 else (3, (t - horizon - 0.12) / (1 - horizon - 0.12))
            a, b = stops[seg], stops[seg + 1]
        lt = max(0.0, min(1.0, lt))
        c = tuple(int(a[i] + (b[i] - a[i]) * lt) for i in range(3))
        if tint and t < horizon + 0.1:
            c = tuple(int(c[i] * 0.55 + tint[i] * 0.45 * (0.4 + t)) for i in range(3))
        for x in range(w):
            px[x, y] = c
    r = random.Random(seed)
    blot = Image.new("RGB", (w // 16, h // 16))
    bp = blot.load()
    for y in range(blot.height):
        for x in range(blot.width):
            v = r.randint(-18, 18)
            bp[x, y] = (128 + v, 128 + v, 128 + v)
    blot = blot.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(12))
    from PIL import ImageChops
    return ImageChops.add(img, blot, offset=-128)


def txt(only, per, steps, strength=0.86):
    """색면 밑그림 + img2img로 자유 구도를 뽑는다. 구도는 다양하고 화풍·색감은 모든 장면이 같다.
    움직이는 효과는 게임이 그림의 빛을 찾아 얹는다."""
    import torch
    from diffusers import AutoencoderKL, StableDiffusionXLImg2ImgPipeline
    from PIL import Image
    vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", vae=vae, torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True).to("cuda")
    out_dir = os.path.join(OUT, "cand_txt")
    os.makedirs(out_dir, exist_ok=True)
    for name in [x for x in SUBJECT if not only or x in only]:
        imgs = []
        kind = KIND.get(name, "wide")
        import random as _r
        rng = _r.Random(sum(map(ord, name)))
        if kind == "interior":
            combos = [(m, None) for m in INTERIOR_MOODS for _ in range(per // 2)]
        else:
            pool = [(t, w) for t in TIMES for w in ([WEATHER_FIXED[name]] if name in WEATHER_FIXED else WEATHERS)]
            rng.shuffle(pool)
            combos = pool[:per]
        for k, (mood, weather) in enumerate(combos):
            path = os.path.join(out_dir, f"{name}_{mood}_{weather or 'in'}_{k}.jpg")
            if os.path.exists(path):  # 이어서 뽑기
                imgs.append(Image.open(path))
                continue
            g = torch.Generator("cuda").manual_seed(2000 + k)
            subject = SUBJECT[name] + (" small in the middle distance" if kind in ("wide", "enemy") else "")
            mood_text = INTERIOR_MOODS.get(mood) or f"{TIMES[mood]}, {WEATHERS[weather]}"
            neg = ", ".join(x for x in (NEGATIVE, WIDE_NEG if kind != "interior" else "", SUBJECT_NEG.get(name, "")) if x)
            img = pipe(prompt=f"{PREFIX[kind]}{subject}, {mood_text}, {STYLE}",
                       negative_prompt=neg, image=color_field(mood, name, 2000 + k, weather),
                       strength=strength, num_inference_steps=steps, guidance_scale=6.0,
                       generator=g).images[0]
            img.save(path, quality=90)
            imgs.append(img)
            print("txt", path, flush=True)
        tw, th = TXT_SIZE[0] // 3, TXT_SIZE[1] // 3
        sheet = Image.new("RGB", (tw * len(imgs), th))
        for i, img in enumerate(imgs):
            sheet.paste(img.resize((tw, th)), (i * tw, 0))
        sheet.save(os.path.join(out_dir, f"_{name}_sheet.jpg"), quality=85)


def pick(name, files):
    """고른 후보를 assets/scenes/<이름>/ 에 넣는다. 게임은 그중 하나를 무작위로 쓴다.
    files: 후보 파일 이름(확장자 빼고, 예: camp_dusk_1) 여러 개."""
    dest = os.path.join(SCENES_DIR, name)
    os.makedirs(dest, exist_ok=True)
    for f in files:
        src = next(p for p in (os.path.join(OUT, "cand_txt", f + ".jpg"), os.path.join(OUT, "cand", f + ".jpg"))
                   if os.path.exists(p))
        shutil.copy(src, os.path.join(dest, f + ".jpg"))
        print("picked", name, f)


# 깊이 패럴랙스: 고른 그림 한 장을 깊이로 3층(먼/중간/가까운)으로 나눠 게임이 층마다 다르게 움직인다.
# 레이어를 따로 생성해 조합하면 빛·원근이 안 맞아 콜라주 티가 나서, 완성된 한 장을 쪼갠다.
# 먼 층 = 원본 전체(구멍 없음), 중간·가까운 층 = 깊이로 잘라 낸 부드러운 가장자리 WebP.
# 깊이 모델은 Depth Anything V2 **Small** 만 쓴다 (Apache-2.0. Base/Large는 CC-BY-NC라 배포 게임에 못 쓴다).
DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
LAYER_H = 1050            # 게임 장면 칸 높이 944 x 켄 번스 여유 1.08 보다 조금 크게
LAYER_CUTS = (0.45, 0.72)  # 깊이 분위수: 이보다 가까우면 중간 층, 그보다 더 가까우면 가까운 층
FEATHER = 7               # 층 경계를 흐리는 반경 (px)


def make_layers(img, depth_img):
    """(먼 층, 중간 층, 가까운 층). 층이 어긋나 움직이면 뒤 층에 남은 앞 물체가 두 번 보인다 (실측: 차가 두 대로 보임).
    그래서 먼 층은 중간·가까운 물체 자리를, 중간 층은 가까운 물체 자리를 주변으로 메운다 (OpenCV inpaint, 개발용)."""
    import cv2
    import numpy as np
    from PIL import Image, ImageFilter
    d = np.asarray(depth_img.convert("L").resize(img.size, Image.BICUBIC))
    rgb = np.asarray(img.convert("RGB"))
    cuts = [np.quantile(d, c) for c in LAYER_CUTS]
    hard = [(d >= c).astype(np.uint8) * 255 for c in cuts]           # 중간 이상, 가까운
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * FEATHER + 5, 2 * FEATHER + 5))
    holes = [cv2.dilate(m, grow) for m in hard]                       # 메울 자리 (경계 흐림보다 넓게)
    far = cv2.inpaint(rgb, holes[0], 9, cv2.INPAINT_TELEA)
    mid_rgb = cv2.inpaint(rgb, holes[1], 9, cv2.INPAINT_TELEA)
    out = [Image.fromarray(far)]
    for base, m in ((mid_rgb, hard[0]), (rgb, hard[1])):
        layer = Image.fromarray(base).convert("RGBA")
        layer.putalpha(Image.fromarray(m).filter(ImageFilter.GaussianBlur(FEATHER)))
        out.append(layer)
    return out


def layers(only):
    """assets/scenes/<이름>/*.jpg 마다 <파일>.mid.webp, <파일>.near.webp 를 만들고, jpg는 게임 크기로 줄인 먼 층(메운 것)으로 바꾼다.
    원본은 E:/Git_Project/stigma-train/art/cand_txt 에 남아 있다."""
    from PIL import Image
    from transformers import pipeline
    depth = pipeline("depth-estimation", model=DEPTH_MODEL, device=0)
    for name in sorted(os.listdir(SCENES_DIR)):
        folder = os.path.join(SCENES_DIR, name)
        if not os.path.isdir(folder) or (only and name not in only):
            continue
        for f in sorted(os.listdir(folder)):
            if not f.endswith(".jpg"):
                continue
            path = os.path.join(folder, f)
            src = next((p for p in (os.path.join(OUT, "cand_txt", f), os.path.join(OUT, "cand", f)) if os.path.exists(p)), path)
            img = Image.open(src).convert("RGB")
            img = img.resize((round(img.width * LAYER_H / img.height), LAYER_H), Image.LANCZOS)
            far, mid, near = make_layers(img, depth(img)["depth"])
            far.save(path, quality=88)
            mid.save(path[:-4] + ".mid.webp", quality=86)
            near.save(path[:-4] + ".near.webp", quality=86)
            print("layers", name, f, flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["init", "paint", "txt", "pick", "layers"])
    p.add_argument("args", nargs="*")
    p.add_argument("--only", default="")
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--strength", type=float, default=0.8)  # 0.62는 밑그림 실루엣을 그대로 따라 디테일이 없었다
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--per", type=int, default=6, help="txt: 장면마다 몇 장 (시간x날씨 조합을 겹치지 않게)")
    a = p.parse_args()
    if a.cmd == "init":
        init()
    elif a.cmd == "paint":
        paint([x for x in a.only.split(",") if x], a.n, a.strength, a.steps)
    elif a.cmd == "layers":
        layers([x for x in a.only.split(",") if x])
    elif a.cmd == "txt":
        txt([x for x in a.only.split(",") if x], a.per, a.steps, 0.86 if a.strength == 0.8 else a.strength)
    else:
        pick(a.args[0], a.args[1:])


if __name__ == "__main__":
    main()
