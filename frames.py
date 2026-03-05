#!/usr/bin/env python3
"""
Auntie / Emporium Frame — v6
(Pillow, no GIMP required)

Modes:
1) Your Favorite Transbian Auntie
   - Black background, white dots, red shadow, logo bottom-right.
2) Auntie's Overstock Meme Emporium
   - Black background, red dots, white shadow, logo top-left.

Both modes:
- Same layout (frame thickness, centered sigil, corner badge, drop shadow).
- Tiny random variation per frame in:
  - Frame background color
  - Dot color
  - Drop shadow color + opacity
  - Dot radius & tile spacing
  - Frame saturation / contrast / brightness (background+dots only)
- Original content image is never color-adjusted.
- Carousel mode: all images in one run share the same variation.
- Non-carousel mode: each image gets its own variation.

Inputs: .jpg/.jpeg/.png/.webp; EXIF preserved; outputs to ./processed; max width 1200 px.
"""

import random
import colorsys
from pathlib import Path
from typing import Tuple, Dict, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

# --------------------------- CONSTANTS ---------------------------
OVERWRITE_ORIGINALS = False
MAX_OUTPUT_WIDTH    = 1200     # Downscale final composite to this width if larger

# FRAME: 5%
FRAME_RATIO         = 0.05     # 5% frame -> photo is ~90% width
PHOTO_WIDTH_PCT     = 1.0 - 2 * FRAME_RATIO   # 0.90

SIGIL_WIDTH_PCT     = 0.20     # 20% of canvas width (centered, below photo)

# BADGE WIDTH + MARGIN
BADGE_WIDTH_PCT     = 0.10     # 10% badge width
BADGE_MARGIN_PCT    = 0.00     # 0% margin from edges

# Drop shadow geometry
SHADOW_OFFSET = (8, 8)         # (x,y) pixels
SHADOW_BLUR   = 10             # Gaussian blur radius
BASE_SHADOW_ALPHA  = int(255 * 0.70)  # 70% baseline opacity

# Base colors (RGB)
AUNTIE_BG_RGB       = (0, 0, 0)
AUNTIE_DOT_RGB      = (255, 255, 255)
AUNTIE_SHADOW_RGB   = (229, 9, 20)   # #E50914

EMPORIUM_BG_RGB     = (0, 0, 0)        # still black
EMPORIUM_DOT_RGB    = (255, 0, 0)      # red dots
EMPORIUM_SHADOW_RGB = (255, 255, 255)  # white shadow

# Profile config: colors + badge corner
# corner: 1=TR, 2=BR, 3=BL, 4=TL
PROFILES = {
    1: {
        "name": "Your Favorite Transbian Auntie",
        "bg_rgb": AUNTIE_BG_RGB,
        "dot_rgb": AUNTIE_DOT_RGB,
        "shadow_rgb": AUNTIE_SHADOW_RGB,
        "badge_corner": 2,  # bottom-right
    },
    2: {
        "name": "Auntie's Overstock Meme Emporium",
        "bg_rgb": EMPORIUM_BG_RGB,
        "dot_rgb": EMPORIUM_DOT_RGB,
        "shadow_rgb": EMPORIUM_SHADOW_RGB,
        "badge_corner": 2,  # bottom-left
    },
}

# Jitter ranges ---------------------------------------------------
# Color jitter (background)
BG_RGB_JITTER           = 4      # ±4 per channel
BG_HUE_JITTER_DEG       = 2      # ±2°
BG_SAT_JITTER_PCT       = 5      # ±5%
BG_LIGHT_JITTER_PCT     = 4      # ±4%

# Color jitter (dots)
DOT_RGB_JITTER          = 6      # ±6 per channel
DOT_HUE_JITTER_DEG      = 3      # ±3°
DOT_SAT_JITTER_PCT      = 4      # ±4%
DOT_LIGHT_JITTER_PCT    = 4      # ±4%

# Color jitter (drop shadow color)
SHADOW_RGB_JITTER          = 6   # ±6 per channel
SHADOW_HUE_JITTER_DEG      = 3   # ±3°
SHADOW_SAT_JITTER_PCT      = 6   # ±6%
SHADOW_LIGHT_JITTER_PCT    = 4   # ±4%

# Shadow opacity multiplier around baseline (0.9x–1.1x)
SHADOW_ALPHA_MULT_MIN   = 0.90
SHADOW_ALPHA_MULT_MAX   = 1.10

# Dot geometry jitter
DOT_RADIUS_SCALE_MIN    = 0.92
DOT_RADIUS_SCALE_MAX    = 1.08
TILE_SCALE_MIN          = 0.95
TILE_SCALE_MAX          = 1.05

# Frame-only global treatment
SAT_MULT_MIN            = 0.96
SAT_MULT_MAX            = 1.04
CONTRAST_MULT_MIN       = 0.97
CONTRAST_MULT_MAX       = 1.03
BRIGHT_MULT_MIN         = 0.98
BRIGHT_MULT_MAX         = 1.02

# I/O
ALLOWED_INPUT_EXTS = (".jpg", ".jpeg", ".png", ".webp")
EXCLUDE_STEMS      = {"logo", "badge", "sigil"}
# ----------------------------------------------------------------


def find_asset(folder: Path, base_names, exts) -> Path:
    for base in base_names:
        for ext in exts:
            p = folder / f"{base}{ext}"
            if p.exists():
                return p
    raise SystemExit(f"[ERROR] Missing one of {', '.join(base_names)} with extensions {exts} in the folder")


def find_logo(folder: Path) -> Path:
    return find_asset(folder, ("logo", "badge"), (".png", ".jpg", ".jpeg"))


def find_sigil(folder: Path) -> Path:
    return find_asset(folder, ("sigil",), (".png", ".jpg", ".jpeg"))


def list_images(folder: Path):
    imgs = sorted(
        [
            p
            for p in folder.iterdir()
            if p.suffix.lower() in ALLOWED_INPUT_EXTS
            and p.stem.lower() not in EXCLUDE_STEMS
        ]
    )
    if not imgs:
        raise SystemExit(
            f"[ERROR] No images found. Allowed extensions: {ALLOWED_INPUT_EXTS}. "
            f"Make sure your file isn't named {tuple(EXCLUDE_STEMS)}.*"
        )
    return imgs


def scale_to_width(img: Image.Image, target_w: int) -> Image.Image:
    w, h = img.size
    if w == target_w:
        return img.copy()
    new_h = int(round(h * (target_w / float(w))))
    return img.resize((target_w, new_h), Image.LANCZOS)


def center_xy(base_wh: Tuple[int, int], top_wh: Tuple[int, int]) -> Tuple[int, int]:
    bw, bh = base_wh
    tw, th = top_wh
    return (bw - tw) // 2, (bh - th) // 2


def add_drop_shadow(canvas: Image.Image,
                    rect_xy: Tuple[int, int],
                    rect_wh: Tuple[int, int],
                    shadow_rgba: Tuple[int, int, int, int]) -> None:
    """Draw a blurred drop shadow behind the photo rectangle."""
    x, y = rect_xy
    tw, th = rect_wh
    offx, offy = SHADOW_OFFSET
    rect = Image.new("RGBA", (tw, th), shadow_rgba)
    blurred = rect.filter(ImageFilter.GaussianBlur(max(1, int(SHADOW_BLUR))))
    canvas.alpha_composite(blurred, dest=(x + offx, y + offy))


def _jitter_color(
    base_rgb: Tuple[int, int, int],
    rgb_max_delta: int,
    hue_deg_delta: float,
    sat_pct_delta: float,
    light_pct_delta: float,
    rng: random.Random,
) -> Tuple[int, int, int]:
    """Apply small HSL + RGB jitter around a base RGB color."""
    r, g, b = base_rgb
    # Convert to HLS (note: colorsys uses H, L, S in [0,1])
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    # HSL jitter
    if hue_deg_delta > 0:
        h += rng.uniform(-hue_deg_delta, hue_deg_delta) / 360.0
        h %= 1.0
    if sat_pct_delta > 0:
        s += rng.uniform(-sat_pct_delta, sat_pct_delta) / 100.0
        s = max(0.0, min(1.0, s))
    if light_pct_delta > 0:
        l += rng.uniform(-light_pct_delta, light_pct_delta) / 100.0
        l = max(0.0, min(1.0, l))

    r_f, g_f, b_f = colorsys.hls_to_rgb(h, l, s)
    r2 = int(round(r_f * 255))
    g2 = int(round(g_f * 255))
    b2 = int(round(b_f * 255))

    # RGB jitter on top
    if rgb_max_delta > 0:
        r2 += rng.randint(-rgb_max_delta, rgb_max_delta)
        g2 += rng.randint(-rgb_max_delta, rgb_max_delta)
        b2 += rng.randint(-rgb_max_delta, rgb_max_delta)

    r2 = max(0, min(255, r2))
    g2 = max(0, min(255, g2))
    b2 = max(0, min(255, b2))
    return r2, g2, b2


def make_variation(
    base_bg_rgb: Tuple[int, int, int],
    base_dot_rgb: Tuple[int, int, int],
    base_shadow_rgb: Tuple[int, int, int],
    rng: Optional[random.Random] = None,
) -> Dict[str, object]:
    """
    Create a variation config dictionary that defines:
    - bg_rgba: background color (RGBA)
    - dot_rgba: dot color (RGBA)
    - shadow_rgba: drop shadow color (RGBA)
    - dot_radius_scale: float
    - tile_scale: float
    - sat_mult, contrast_mult, bright_mult: floats
    """
    if rng is None:
        rng = random.Random()

    # Background & dots
    bg_r, bg_g, bg_b = _jitter_color(
        base_bg_rgb,
        BG_RGB_JITTER,
        BG_HUE_JITTER_DEG,
        BG_SAT_JITTER_PCT,
        BG_LIGHT_JITTER_PCT,
        rng,
    )
    dot_r, dot_g, dot_b = _jitter_color(
        base_dot_rgb,
        DOT_RGB_JITTER,
        DOT_HUE_JITTER_DEG,
        DOT_SAT_JITTER_PCT,
        DOT_LIGHT_JITTER_PCT,
        rng,
    )

    # Shadow color + opacity
    sh_r, sh_g, sh_b = _jitter_color(
        base_shadow_rgb,
        SHADOW_RGB_JITTER,
        SHADOW_HUE_JITTER_DEG,
        SHADOW_SAT_JITTER_PCT,
        SHADOW_LIGHT_JITTER_PCT,
        rng,
    )
    alpha_mult = rng.uniform(SHADOW_ALPHA_MULT_MIN, SHADOW_ALPHA_MULT_MAX)
    sh_alpha = int(round(BASE_SHADOW_ALPHA * alpha_mult))
    sh_alpha = max(0, min(255, sh_alpha))

    # Geometry
    dot_radius_scale = rng.uniform(DOT_RADIUS_SCALE_MIN, DOT_RADIUS_SCALE_MAX)
    tile_scale       = rng.uniform(TILE_SCALE_MIN, TILE_SCALE_MAX)

    # Frame treatment
    sat_mult      = rng.uniform(SAT_MULT_MIN, SAT_MULT_MAX)
    contrast_mult = rng.uniform(CONTRAST_MULT_MIN, CONTRAST_MULT_MAX)
    bright_mult   = rng.uniform(BRIGHT_MULT_MIN, BRIGHT_MULT_MAX)

    return {
        "bg_rgba": (bg_r, bg_g, bg_b, 255),
        "dot_rgba": (dot_r, dot_g, dot_b, 255),
        "shadow_rgba": (sh_r, sh_g, sh_b, sh_alpha),
        "dot_radius_scale": dot_radius_scale,
        "tile_scale": tile_scale,
        "sat_mult": sat_mult,
        "contrast_mult": contrast_mult,
        "bright_mult": bright_mult,
    }


def draw_polka_layer(size_wh: Tuple[int, int], variation: Dict[str, object]) -> Image.Image:
    """Uniform hex-staggered polka dots with jittered size/spacing."""
    W, H = size_wh
    # Reconstruct previous settings for reference (old frame = 10% of width)
    T_old     = int(round(W * 0.10))
    dot_old   = max(12, int(round(T_old / 3.0)))
    tile_old  = max(dot_old + 8, int(round(dot_old * 1.6)))

    # New geometry with jitter
    dot_d_base = max(12, int(round(1.5 * dot_old)))  # +50% size
    dot_d  = max(12, int(round(dot_d_base * float(variation["dot_radius_scale"]))))
    tile_base = max(dot_d_base + 8, int(round(tile_old * 1.4142)))  # ~half density
    tile   = max(dot_d + 8, int(round(tile_base * float(variation["tile_scale"]))))

    layer = Image.new("RGBA", (W, H), variation["bg_rgba"])
    draw  = ImageDraw.Draw(layer)
    r = dot_d // 2

    dot_color = variation["dot_rgba"]

    for row_y in range(-tile, H + tile, tile):
        # Stagger every other row by half a tile
        offset_x = 0 if ((row_y // tile) % 2 == 0) else (tile // 2)
        for col_x in range(-tile, W + tile, tile):
            cx = col_x + offset_x
            cy = row_y
            bbox = (cx - r, cy - r, cx + r, cy + r)
            draw.ellipse(bbox, fill=dot_color)

    return layer


def enhance_frame_layer(frame_rgba: Image.Image, variation: Dict[str, object]) -> Image.Image:
    """Apply saturation/contrast/brightness tweaks to the frame layer only."""
    sat_mult      = float(variation["sat_mult"])
    contrast_mult = float(variation["contrast_mult"])
    bright_mult   = float(variation["bright_mult"])

    rgb = frame_rgba.convert("RGB")
    if sat_mult != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(sat_mult)
    if contrast_mult != 1.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(contrast_mult)
    if bright_mult != 1.0:
        rgb = ImageEnhance.Brightness(rgb).enhance(bright_mult)

    out = Image.new("RGBA", rgb.size)
    out.paste(rgb, (0, 0))
    return out


def paste_watermark(base: Image.Image,
                    top: Image.Image,
                    corner: int,
                    margin_px: int = 0) -> None:
    """
    Paste 'top' onto 'base' at the specified corner with margin.
    corner: 1=TR, 2=BR, 3=BL, 4=TL
    """
    bw, bh = base.size
    tw, th = top.size

    if corner == 1:   # top-right
        x = bw - tw - margin_px
        y = margin_px
    elif corner == 2: # bottom-right
        x = bw - tw - margin_px
        y = bh - th - margin_px
    elif corner == 3: # bottom-left
        x = margin_px
        y = bh - th - margin_px
    else:             # top-left
        x = margin_px
        y = margin_px

    base.alpha_composite(top, dest=(x, y))


def process_one(
    img_index: int,
    img_path: Path,
    logo_path: Path,
    sigil_path: Path,
    out_dir: Path,
    variation: Dict[str, object],
    badge_corner: int,
) -> None:
    """Process a single image with the given variation config."""
    with Image.open(img_path) as im:
        exif_bytes = im.info.get("exif", b"")  # may be empty
        photo_rgba = im.convert("RGBA")

    W, H = photo_rgba.size
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # Background polka frame
    polka = draw_polka_layer((W, H), variation)
    polka = enhance_frame_layer(polka, variation)
    canvas.alpha_composite(polka, dest=(0, 0))

    # Sigil centered (20% width), below the photo layer
    sigil_img = Image.open(sigil_path).convert("RGBA")
    sigil_w = max(1, int(round(W * SIGIL_WIDTH_PCT)))
    sigil_scaled = scale_to_width(sigil_img, sigil_w)
    sx, sy = center_xy((W, H), sigil_scaled.size)
    canvas.alpha_composite(sigil_scaled, dest=(sx, sy))

    # Photo on top at ~90% width, centered + shadow
    target_w = max(1, int(round(W * PHOTO_WIDTH_PCT)))
    photo_scaled = scale_to_width(photo_rgba, target_w)
    px, py = center_xy((W, H), photo_scaled.size)
    add_drop_shadow(canvas, (px, py), photo_scaled.size, variation["shadow_rgba"])
    canvas.alpha_composite(photo_scaled, dest=(px, py))

    # Badge (watermark) at profile corner (10% width, 0% margin)
    badge_rgba = Image.open(logo_path).convert("RGBA")
    badge_w = max(1, int(round(W * BADGE_WIDTH_PCT)))
    badge_scaled = scale_to_width(badge_rgba, badge_w)
    margin = int(round(W * BADGE_MARGIN_PCT))  # = 0

    paste_watermark(canvas, badge_scaled, corner=badge_corner, margin_px=margin)

    # Final resize
    out_img = canvas
    if isinstance(MAX_OUTPUT_WIDTH, int) and MAX_OUTPUT_WIDTH > 0 and out_img.width > MAX_OUTPUT_WIDTH:
        new_h = int(round(out_img.height * (MAX_OUTPUT_WIDTH / float(out_img.width))))
        out_img = out_img.resize((MAX_OUTPUT_WIDTH, new_h), Image.LANCZOS)

    # Save
    out_path = img_path if OVERWRITE_ORIGINALS else (out_dir / img_path.name)
    result_rgb = out_img.convert("RGB")
    save_kwargs = dict(quality=90, optimize=True, progressive=True)
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes
    result_rgb.save(out_path, "JPEG", **save_kwargs)


def choose_profile() -> Dict[str, object]:
    print("Select profile:")
    print("  1 - Your Favorite Transbian Auntie")
    print("  2 - Auntie's Overstock Meme Emporium")
    raw = input("Enter 1 or 2 (default 1): ").strip()
    try:
        choice = int(raw)
    except ValueError:
        choice = 1
    if choice not in PROFILES:
        choice = 1
    profile = PROFILES[choice]
    print(f"\n[Profile] {profile['name']}\n")
    return profile


def main():
    folder = Path(__file__).resolve().parent
    # Locate assets
    logo_path  = find_logo(folder)
    sigil_path = find_sigil(folder)
    images = list_images(folder)

    print(f"Found {len(images)} image(s):")
    for i, p in enumerate(images, 1):
        print(f"  {i}. {p.name}")

    # Choose profile (Auntie vs Emporium)
    profile = choose_profile()

    # Single question: carousel mode?
    print("Are we running a carousel?")
    ans = input("Type 'y' for Yes (same frame variant for all), anything else for No: ").strip().lower()
    is_carousel = ans in ("y", "yes")

    if OVERWRITE_ORIGINALS:
        out_dir = folder
    else:
        out_dir = folder / "processed"
        out_dir.mkdir(exist_ok=True)

    base_bg   = profile["bg_rgb"]
    base_dot  = profile["dot_rgb"]
    base_shad = profile["shadow_rgb"]
    badge_corner = profile["badge_corner"]

    if is_carousel:
        # One variation shared for all images in this run
        rng = random.Random()
        variation = make_variation(base_bg, base_dot, base_shad, rng)
        print("\n[Mode] Carousel: all images share the same randomized frame.\n")
        for idx, img in enumerate(images, 1):
            try:
                process_one(idx, img, logo_path, sigil_path, out_dir, variation, badge_corner)
                print(f"[OK] {img.name}")
            except Exception as e:
                print(f"[ERROR] {img.name}: {e}")
    else:
        print("\n[Mode] Non-carousel: each image gets its own randomized frame.\n")
        for idx, img in enumerate(images, 1):
            try:
                rng = random.Random()
                variation = make_variation(base_bg, base_dot, base_shad, rng)
                process_one(idx, img, logo_path, sigil_path, out_dir, variation, badge_corner)
                print(f"[OK] {img.name}")
            except Exception as e:
                print(f"[ERROR] {img.name}: {e}")

    if not OVERWRITE_ORIGINALS:
        print("\nDone. Check the 'processed' folder for results.")
    else:
        print("\nDone. Originals have been overwritten with framed versions.")


if __name__ == "__main__":
    main()
