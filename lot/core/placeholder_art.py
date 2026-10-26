"""Original placeholder product art drawn with Pillow. Replace with real photography in the admin."""

import io
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 1500
INK = "#0a0a0a"
BONE = "#f4f4f0"
FOREST = "#2c570e"
FOREST_GLOW = "#4c8a1f"  # lighter forest, so light sources stay visible on black

_FONT_CANDIDATES = [
    "arialbd.ttf",
    "Arial Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_font_cache = {}


def font(size):
    if size in _font_cache:
        return _font_cache[size]
    loaded = None
    for name in _FONT_CANDIDATES:
        try:
            loaded = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    if loaded is None:
        loaded = ImageFont.load_default(size=size)
    _font_cache[size] = loaded
    return loaded


def rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def is_dark(color):
    r, g, b = rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def shade(color, amount):
    """Shift toward white (dark colors) or black (light colors)."""
    r, g, b = rgb(color)
    target = 255 if is_dark(color) else 0
    mix = lambda c: int(c + (target - c) * amount)  # noqa: E731
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def bg_hex(img):
    r, g, b = img.getpixel((10, 10))[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


def to_jpeg(img, quality=86):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def _pts(cx, cy, s, points):
    return [(cx + x * s, cy + y * s) for x, y in points]


def rotated_text(img, text, center, size, fill, angle):
    f = font(size)
    bbox = f.getbbox(text)
    layer = Image.new("RGBA", (bbox[2] - bbox[0] + 40, bbox[3] - bbox[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20 - bbox[0], 20 - bbox[1]), text, font=f, fill=fill)
    layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.paste(layer, (int(center[0] - layer.width / 2), int(center[1] - layer.height / 2)), layer)


def paste_with_shadow(base, layer, pos, blur=18, offset=(14, 22), opacity=110):
    alpha = layer.split()[-1]
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: min(a, opacity)))
    pad = blur * 3
    canvas = Image.new("RGBA", (layer.width + pad * 2, layer.height + pad * 2), (0, 0, 0, 0))
    canvas.paste(shadow, (pad, pad), shadow)
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    base.paste(canvas, (pos[0] - pad + offset[0], pos[1] - pad + offset[1]), canvas)
    base.paste(layer, pos, layer)


def _canvas(bg, brand, code, view):
    img = Image.new("RGBA", (W, H), bg)
    d = ImageDraw.Draw(img)
    grid = shade(bg, 0.06)
    for x in range(0, W, 100):
        d.line([(x, 0), (x, H)], fill=grid, width=1)
    for y in range(0, H, 100):
        d.line([(0, y), (W, y)], fill=grid, width=1)
    label = shade(bg, 0.85)
    d.text((60, 56), brand, font=font(46), fill=label)
    d.text((W - 60, 66), code, font=font(26), fill=shade(bg, 0.5), anchor="ra")
    d.text((60, H - 56), view.upper(), font=font(24), fill=shade(bg, 0.5), anchor="ls")
    d.rectangle([W - 220, H - 74, W - 60, H - 58], fill=FOREST if bg != FOREST else BONE)
    return img


# --- Garments -----------------------------------------------------------------

TEE = [(-150, -330), (-330, -265), (-445, -55), (-315, 5), (-255, -95), (-255, 380), (255, 380),
       (255, -95), (315, 5), (445, -55), (330, -265), (150, -330)]
HOODIE = [(-170, -320), (-340, -255), (-430, 40), (-470, 330), (-370, 345), (-300, 60), (-270, -40),
          (-270, 400), (270, 400), (270, -40), (300, 60), (370, 345), (470, 330), (430, 40), (340, -255),
          (170, -320)]


def draw_tee(img, body, ink, accent, brand, view, cx=600, cy=780, s=1.0, hoodie=False):
    d = ImageDraw.Draw(img)
    outline = shade(body, 0.18)
    if hoodie:
        d.ellipse(_pts(cx, cy, s, [(-215, -500), (215, -230)]), fill=shade(body, 0.08), outline=outline, width=4)
    d.polygon(_pts(cx, cy, s, HOODIE if hoodie else TEE), fill=body, outline=outline, width=4)
    bg = img.getpixel((10, 10))
    if hoodie:
        d.ellipse(_pts(cx, cy, s, [(-120, -420), (120, -250)]), fill=shade(body, 0.22))
        if view == "front":
            d.line(_pts(cx, cy, s, [(-45, -270), (-55, -90)]), fill=BONE if is_dark(body) else INK, width=int(8 * s))
            d.line(_pts(cx, cy, s, [(45, -270), (55, -90)]), fill=BONE if is_dark(body) else INK, width=int(8 * s))
            d.polygon(_pts(cx, cy, s, [(-190, 170), (190, 170), (230, 360), (-230, 360)]), outline=outline, width=4)
    else:
        d.chord(_pts(cx, cy, s, [(-115, -400), (115, -260)]), 0, 180, fill=bg)
        d.arc(_pts(cx, cy, s, [(-125, -405), (125, -250)]), 0, 180, fill=outline, width=int(14 * s))
    if view == "front":
        d.text((cx + 120 * s, cy - 170 * s), brand, font=font(int(48 * s)), fill=ink, anchor="mm")
        d.rectangle(_pts(cx, cy, s, [(80, -130), (160, -120)]), fill=accent)
    else:
        d.text((cx, cy - 40 * s), brand, font=font(int(230 * s)), fill=ink, anchor="mm")
        d.rectangle(_pts(cx, cy, s, [(-200, 80), (200, 96)]), fill=accent)
        d.text((cx, cy + 150 * s), "NIGHT SHIFT / 04", font=font(int(40 * s)), fill=ink, anchor="mm")


def draw_cap(img, body, ink, accent, brand, view, cx=600, cy=800):
    d = ImageDraw.Draw(img)
    outline = shade(body, 0.2)
    if view == "front":
        d.ellipse([cx - 400, cy + 20, cx + 400, cy + 190], fill=shade(body, 0.1), outline=outline, width=4)
        d.pieslice([cx - 340, cy - 330, cx + 340, cy + 330], 180, 360, fill=body, outline=outline, width=4)
        for dx in (-170, 0, 170):
            d.line([(cx, cy - 330), (cx + dx * 1.6, cy)], fill=outline, width=3)
        d.ellipse([cx - 22, cy - 350, cx + 22, cy - 310], fill=shade(body, 0.25))
        d.text((cx, cy - 140), brand, font=font(120), fill=ink, anchor="mm")
        d.rectangle([cx - 90, cy - 60, cx + 90, cy - 48], fill=accent)
    else:
        d.pieslice([cx - 340, cy - 330, cx + 340, cy + 330], 180, 360, fill=body, outline=outline, width=4)
        bg = img.getpixel((10, 10))
        d.pieslice([cx - 110, cy - 120, cx + 110, cy + 120], 180, 360, fill=bg)
        d.rounded_rectangle([cx - 150, cy - 30, cx + 150, cy + 10], radius=8, fill=shade(body, 0.15))
        d.rectangle([cx - 30, cy - 40, cx + 30, cy + 20], fill=accent)
        d.text((cx, cy - 220), brand, font=font(54), fill=ink, anchor="mm")


# --- Car goods ------------------------------------------------------------------


def draw_plate_frame(img, body, ink, accent, brand, view, cx=600, cy=760):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([cx - 500, cy - 280, cx + 500, cy + 280], radius=46, fill=body, outline=shade(body, 0.25), width=4)
    d.rounded_rectangle([cx - 420, cy - 200, cx + 420, cy + 170], radius=18, fill="#e9e9e4")
    d.text((cx, cy - 20), "YOUR PLATE", font=font(110), fill="#c8c8c2", anchor="mm")
    for x in (-330, 330):
        for y in (-150, 120):
            d.ellipse([cx + x - 18, cy + y - 18, cx + x + 18, cy + y + 18], fill="#9a9a94")
    d.text((cx, cy - 240), "LOW & SLOW", font=font(42), fill=shade(body, 0.6), anchor="mm")
    d.text((cx, cy + 225), brand, font=font(64), fill=ink, anchor="mm")
    d.rectangle([cx + 120, cy + 216, cx + 200, cy + 232], fill=accent)
    if view != "front":
        d.text((cx, cy + 420), "Fits 12 × 6 in. plates", font=font(36), fill=shade(bg_hex(img), 0.5), anchor="mm")


def draw_freshener(img, body, ink, accent, brand, view, scent="BLACK ICE", cx=600, cy=820):
    d = ImageDraw.Draw(img)
    bg = img.getpixel((10, 10))
    d.line([(cx, 0), (cx, cy - 330)], fill=shade(BONE if is_dark(body) else INK, 0.2), width=6)
    shape = [(-230, -330), (230, -330), (300, -150), (230, 420), (-230, 420), (-300, -150)]
    d.polygon(_pts(cx, cy, 1, shape), fill=body)
    d.ellipse([cx - 28, cy - 300, cx + 28, cy - 244], fill=bg)
    d.text((cx, cy - 130), "PIT", font=font(150), fill=ink, anchor="mm")
    d.text((cx, cy + 20), "LANE", font=font(150), fill=ink, anchor="mm")
    d.rectangle([cx - 160, cy + 120, cx + 160, cy + 136], fill=accent if accent != body else INK)
    d.text((cx, cy + 210), scent, font=font(48), fill=ink, anchor="mm")
    d.text((cx, cy + 340), brand, font=font(54), fill=ink, anchor="mm")


def draw_keychain(img, body, ink, accent, brand, view, cx=600, cy=760):
    d = ImageDraw.Draw(img)
    metal = "#b9b9b4"
    d.ellipse([cx - 110, cy - 520, cx + 110, cy - 300], outline=metal, width=26)
    d.rounded_rectangle([cx - 30, cy - 320, cx + 30, cy - 230], radius=8, fill=metal)
    d.rounded_rectangle([cx - 150, cy - 250, cx + 150, cy + 470], radius=150, outline=body, width=96)
    d.rounded_rectangle([cx - 150, cy - 250, cx + 150, cy + 470], radius=150, outline=shade(body, 0.2), width=4)
    rotated_text(img, "TOW", (cx - 150, cy + 110), 80, ink, 90)
    rotated_text(img, brand, (cx + 150, cy + 110), 64, ink, -90)
    d.rectangle([cx - 60, cy + 450, cx + 60, cy + 492], fill=accent)


# --- Stickers -----------------------------------------------------------------


def sticker_layer(text, fill, ink, w=700, h=420, shape="rect", sub=None):
    border = 26
    layer = Image.new("RGBA", (w + border * 2, h + border * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if shape == "circle":
        d.ellipse([0, 0, w + border * 2, h + border * 2], fill="white")
        d.ellipse([border, border, w + border, h + border], fill=fill)
    else:
        d.rounded_rectangle([0, 0, w + border * 2, h + border * 2], radius=60, fill="white")
        d.rounded_rectangle([border, border, w + border, h + border], radius=40, fill=fill)
    cx, cy = (w + border * 2) / 2, (h + border * 2) / 2
    size = int(min(w / max(len(text), 1) * 1.5, h * 0.62))
    d.text((cx, cy - (20 if sub else 0)), text, font=font(size), fill=ink, anchor="mm")
    if sub:
        d.text((cx, cy + size * 0.55), sub, font=font(max(int(size * 0.22), 22)), fill=ink, anchor="mm")
    return layer


def draw_diecut(img, body, ink, accent, brand, view):
    layer = sticker_layer(brand, body, ink, 760, 460, sub="DRIVE AT NIGHT")
    angle = -8 if view == "front" else 6
    layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    paste_with_shadow(img, layer, ((W - layer.width) // 2, (H - layer.height) // 2 - 20))
    if view != "front":
        d = ImageDraw.Draw(img)
        d.text((W // 2, H - 220), "Vinyl · UV laminate · Outdoor rated", font=font(34),
               fill=shade(bg_hex(img), 0.5), anchor="mm")


def draw_pack(img, body, ink, accent, brand, view):
    random.seed(4 if view == "front" else 9)
    specs = [
        (brand, INK, BONE, 560, 320, "rect", None),
        ("SLOW", FOREST, BONE, 420, 420, "circle", None),
        ("NIGHT", BONE, FOREST, 520, 260, "rect", None),
        ("04", BONE, INK, 300, 300, "circle", None),
        ("APEX", INK, BONE, 460, 240, "rect", "HUNTER"),
        ("LOW", FOREST, BONE, 380, 220, "rect", None),
    ]
    spots = [(330, 470), (850, 430), (380, 900), (860, 860), (600, 1180), (300, 1230)]
    for (text, fill, txt, w, h, shp, sub), (x, y) in zip(specs, spots):
        layer = sticker_layer(text, fill, txt, w, h, shp, sub)
        layer = layer.rotate(random.randint(-18, 18), expand=True, resample=Image.BICUBIC)
        paste_with_shadow(img, layer, (int(x - layer.width / 2), int(y - layer.height / 2)), blur=12)


DRAWERS = {
    "tee": lambda img, c, brand, view, extra: draw_tee(img, c[1], c[2], c[3], brand, view),
    "hoodie": lambda img, c, brand, view, extra: draw_tee(img, c[1], c[2], c[3], brand, view, hoodie=True),
    "cap": lambda img, c, brand, view, extra: draw_cap(img, c[1], c[2], c[3], brand, view),
    "plate": lambda img, c, brand, view, extra: draw_plate_frame(img, c[1], c[2], c[3], brand, view),
    "freshener": lambda img, c, brand, view, extra: draw_freshener(img, c[1], c[2], c[3], brand, view, extra or "BLACK ICE"),
    "keychain": lambda img, c, brand, view, extra: draw_keychain(img, c[1], c[2], c[3], brand, view),
    "diecut": lambda img, c, brand, view, extra: draw_diecut(img, c[1], c[2], c[3], brand, view),
    "pack": lambda img, c, brand, view, extra: draw_pack(img, c[1], c[2], c[3], brand, view),
}


def product_image(kind, colors, brand, code, view="front", extra=None):
    """colors = (background, body, print/ink, accent). view = front | back | detail."""
    base_view = "front" if view == "detail" else view
    img = _canvas(colors[0], brand, code, base_view)
    DRAWERS[kind](img, colors, brand, base_view, extra)
    if view == "detail":
        crop = img.crop((W * 0.18, H * 0.2, W * 0.82, H * 0.2 + (W * 0.64) * H / W))
        img = crop.resize((W, H), Image.LANCZOS)
        ImageDraw.Draw(img).text((60, H - 56), "DETAIL", font=font(24), fill=shade(colors[0], 0.5), anchor="ls")
    return to_jpeg(img)


# --- Wide scenes (hero / blog covers) -----------------------------------------


def road_scene(width=2400, height=1200, glow=FOREST_GLOW, tail="#f4f4f0", brand="LOT", seed=1):
    random.seed(seed)
    img = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(img)
    horizon = int(height * 0.40)
    for i in range(horizon):
        t = i / horizon
        c = int(10 + 26 * t ** 3)
        d.line([(0, i), (width, i)], fill=(c, c, c + 4))
    glow_layer = Image.new("RGB", (width, height), (0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.rectangle([0, horizon - 8, width, horizon + 8], fill=glow)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(40))
    img = Image.blend(img, Image.composite(glow_layer, img, glow_layer.convert("L")), 0.85)
    d = ImageDraw.Draw(img)
    d.line([(0, horizon), (width, horizon)], fill=glow, width=3)
    for _ in range(80):
        x, y = random.randint(0, width), random.randint(0, horizon - 60)
        d.point((x, y), fill=(90, 90, 90))
    vp = (width // 2, horizon)
    d.polygon([vp, (-width // 2, height), (width + width // 2, height)], fill=(18, 18, 20))
    for side in (-1, 1):
        d.line([vp, (width // 2 + side * width * 0.9, height)], fill=(200, 200, 200), width=6)
    for i in range(12):
        t0, t1 = (i / 12) ** 2, ((i + 0.5) / 12) ** 2
        y0, y1 = horizon + (height - horizon) * t0, horizon + (height - horizon) * t1
        w0, w1 = 2 + 26 * t0, 2 + 26 * t1
        d.polygon([(vp[0] - w0, y0), (vp[0] + w0, y0), (vp[0] + w1, y1), (vp[0] - w1, y1)], fill=(220, 220, 210))
    # Low car, rear view
    cx, base = width // 2, int(height * 0.80)
    cw = int(width * 0.36)
    d.ellipse([cx - cw * 0.62, base - 20, cx + cw * 0.62, base + 40], fill=(4, 4, 4))
    d.rounded_rectangle([cx - cw / 2 - 30, base - 70, cx - cw / 2 + 110, base + 10], radius=14, fill=(6, 6, 6))
    d.rounded_rectangle([cx + cw / 2 - 110, base - 70, cx + cw / 2 + 30, base + 10], radius=14, fill=(6, 6, 6))
    d.rounded_rectangle([cx - cw / 2, base - 260, cx + cw / 2, base - 40], radius=40, fill=(14, 14, 16))
    d.polygon([(cx - cw * 0.34, base - 250), (cx + cw * 0.34, base - 250), (cx + cw * 0.24, base - 400),
               (cx - cw * 0.24, base - 400)], fill=(10, 10, 12))
    d.polygon([(cx - cw * 0.3, base - 260), (cx + cw * 0.3, base - 260), (cx + cw * 0.22, base - 380),
               (cx - cw * 0.22, base - 380)], fill=(28, 30, 34))
    tail_glow = Image.new("RGB", (width, height), (0, 0, 0))
    ImageDraw.Draw(tail_glow).rectangle([cx - cw / 2 + 30, base - 205, cx + cw / 2 - 30, base - 175], fill=tail)
    img = ImageChops.screen(img, tail_glow.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(img)
    d.rectangle([cx - cw / 2 + 30, base - 198, cx + cw / 2 - 30, base - 184], fill=tail)
    d.rounded_rectangle([cx - 130, base - 150, cx + 130, base - 80], radius=6, fill=(230, 230, 225))
    d.text((cx, base - 115), brand, font=font(44), fill=INK, anchor="mm")
    return img


def hero_image(brand):
    return to_jpeg(road_scene(brand=brand), quality=84)


def cover_image(variant, brand):
    if variant == 0:
        img = road_scene(1600, 900, glow="#f4f4f0", tail=FOREST_GLOW, brand=brand, seed=7)
    else:
        img = Image.new("RGBA", (1600, 900), BONE)
        d = ImageDraw.Draw(img)
        for x in range(0, 1600, 80):
            d.line([(x, 0), (x, 900)], fill="#e6e6e0")
        draw_tee(img, INK, BONE, FOREST, brand, "back", cx=520, cy=470, s=0.95)
        draw_tee(img, FOREST, BONE, BONE, brand, "front", cx=1130, cy=500, s=0.8)
        d.rectangle([0, 860, 1600, 900], fill=INK)
        img = img.convert("RGB")
    return to_jpeg(img, quality=84)
