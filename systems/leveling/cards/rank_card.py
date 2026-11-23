"""Cartões de rank com temas, cores, avatar e fundo opcional."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
from ..progression import progress_from_xp

THEMES = {
    "dark": {"bg": "#131827", "panel": "#21293e", "accent": "#7689ff", "text": "#ffffff"},
    "ocean": {"bg": "#071e2b", "panel": "#10374a", "accent": "#39c9e6", "text": "#ffffff"},
    "forest": {"bg": "#10241d", "panel": "#1d3c30", "accent": "#6ce0a1", "text": "#ffffff"},
    "sunset": {"bg": "#301b2e", "panel": "#502d44", "accent": "#ffab72", "text": "#ffffff"},
}

def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"):
        try: return ImageFont.truetype(path, size)
        except OSError: pass
    return ImageFont.load_default()

def make_rank_card(name: str, xp: int, position: int | None = None, *, theme="dark", accent=None, avatar_bytes=None, background_bytes=None):
    palette = THEMES.get(theme, THEMES["dark"])
    color = accent or palette["accent"]
    progress = progress_from_xp(xp)
    image = Image.new("RGB", (900, 280), palette["bg"])
    if background_bytes:
        try:
            with Image.open(BytesIO(background_bytes)) as bg:
                if bg.width * bg.height > 12_000_000: raise ValueError("Imagem grande")
                image.paste(ImageOps.fit(bg.convert("RGB"), image.size), (0, 0))
        except (OSError, ValueError): pass
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((20, 20, 880, 260), radius=22, fill=(15, 22, 35, 215) if background_bytes else palette["panel"])
    left = 50
    if avatar_bytes:
        try:
            with Image.open(BytesIO(avatar_bytes)) as av:
                if av.width * av.height > 12_000_000: raise ValueError("Avatar grande")
                avatar = ImageOps.fit(av.convert("RGB"), (110, 110))
                mask = Image.new("L", (110, 110), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, 109, 109), fill=255)
                image.paste(avatar, (50, 80), mask)
                left = 185
        except (OSError, ValueError): pass
    draw = ImageDraw.Draw(image)
    draw.text((50, 40), "KING PLUS / PERFIL DE NIVEL", font=_font(19), fill=color)
    label = str(name).replace("\n", " ")[:22 if avatar_bytes else 27]
    draw.text((left, 90), label, font=_font(29), fill="white")
    draw.text((left, 153), f"NIVEL {progress['level']}   XP {xp:,}".replace(",", "."), font=_font(20), fill="white")
    if position is not None: draw.text((680, 55), f"RANK #{position}", font=_font(19), fill=color)
    draw.rounded_rectangle((50, 208, 850, 229), radius=10, fill="#474f68")
    fill = max(0, min(800, round(800 * progress["percent"] / 100)))
    if fill: draw.rounded_rectangle((50, 208, 50 + fill, 229), radius=9, fill=color)
    draw.text((740, 173), f"{progress['percent']:.1f}%", font=_font(17), fill="white")
    out = BytesIO(); image.save(out, format="PNG"); out.seek(0); return out
