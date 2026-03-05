#!/usr/bin/env python3
"""Frame Maker v2 - standalone GUI batch framer.

Expected folder layout (next to this script):
- sigil.jpg
- logo.png
- Cracked Egg Logo.png
- Input/
- Output/
"""

from __future__ import annotations

import random
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw

APP_VERSION = "2.0.0"

PALETTE = ((0, 0, 0), (255, 255, 255), (255, 0, 0))  # black, white, red
ALLOWED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

BORDER_WIDTH = 10
BACKGROUND_SCALE = 1.15
SIGIL_SCALE = 0.50
LOGO_SCALE = 0.22
POLKA_PRIMARY_WEIGHT = 0.85

PATTERN_POLKA = "polka"
PATTERN_SPLATTER = "splatter"
PATTERN_MIXED = "mixed"


def find_file_case_insensitive(folder: Path, wanted_name: str) -> Path:
    wanted = wanted_name.lower()
    for p in folder.iterdir():
        if p.is_file() and p.name.lower() == wanted:
            return p
    raise FileNotFoundError(f"Missing required file: {wanted_name}")


def list_input_images(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError("Missing Input folder next to frames2.py")

    images = [
        p for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in ALLOWED_INPUT_EXTS
    ]
    if not images:
        raise FileNotFoundError("No supported images found in Input folder")
    return images


def scale_to_fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    w, h = img.size
    ratio = min(max_w / max(w, 1), max_h / max(h, 1))
    ratio = max(ratio, 0.0001)
    nw = max(1, int(round(w * ratio)))
    nh = max(1, int(round(h * ratio)))
    return img.resize((nw, nh), Image.LANCZOS)


def create_splatter_background(size: tuple[int, int], bg_color: tuple[int, int, int], dot_color: tuple[int, int, int]) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, bg_color + (255,))
    draw = ImageDraw.Draw(layer)

    density = random.uniform(0.0009, 0.0025)
    count = max(80, int(w * h * density))
    min_r = max(2, int(min(w, h) * 0.004))
    max_r = max(min_r + 1, int(min(w, h) * random.uniform(0.012, 0.03)))

    for _ in range(count):
        r = random.randint(min_r, max_r)
        x = random.randint(-r, w + r)
        y = random.randint(-r, h + r)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=dot_color + (255,))

    return layer


def create_polka_background(size: tuple[int, int], bg_color: tuple[int, int, int], dot_color: tuple[int, int, int]) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, bg_color + (255,))
    draw = ImageDraw.Draw(layer)

    base = min(w, h)
    dot_radius = random.randint(max(3, int(base * 0.010)), max(5, int(base * 0.022)))
    gap = random.randint(max(4, dot_radius // 2), max(8, dot_radius * 2))
    tile = max(dot_radius * 2 + gap, dot_radius * 3)

    diagonal = random.random() < 0.5
    row_offset = tile // 2 if diagonal else 0

    for y in range(-tile, h + tile, tile):
        row_idx = (y + tile) // tile
        x_offset = row_offset if diagonal and (row_idx % 2) else 0
        for x in range(-tile, w + tile, tile):
            cx = x + x_offset
            cy = y
            draw.ellipse((cx - dot_radius, cy - dot_radius, cx + dot_radius, cy + dot_radius), fill=dot_color + (255,))

    return layer


def create_dotted_background(
    size: tuple[int, int],
    bg_color: tuple[int, int, int],
    dot_color: tuple[int, int, int],
    pattern_mode: str,
) -> tuple[Image.Image, str]:
    if pattern_mode == PATTERN_POLKA:
        return create_polka_background(size, bg_color, dot_color), PATTERN_POLKA
    if pattern_mode == PATTERN_SPLATTER:
        return create_splatter_background(size, bg_color, dot_color), PATTERN_SPLATTER

    if random.random() < POLKA_PRIMARY_WEIGHT:
        return create_polka_background(size, bg_color, dot_color), PATTERN_POLKA
    return create_splatter_background(size, bg_color, dot_color), PATTERN_SPLATTER


def choose_color_roles() -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    colors = list(PALETTE)
    random.shuffle(colors)
    return colors[0], colors[1], colors[2]  # background, dots, border


def paste_corner_logo(base: Image.Image, logo: Image.Image, photo_xy: tuple[int, int], photo_wh: tuple[int, int], side: str) -> None:
    px, py = photo_xy
    pw, ph = photo_wh

    logo_target_w = max(1, int(round(pw * LOGO_SCALE)))
    scaled = scale_to_fit(logo, logo_target_w, max(1, int(round(ph * 0.30))))
    lw, lh = scaled.size

    frame_left = px - BORDER_WIDTH
    frame_right = px + pw + BORDER_WIDTH - 1
    frame_bottom = py + ph + BORDER_WIDTH - 1

    if side == "right":
        x = frame_right - lw + 1
    else:
        x = frame_left
    y = frame_bottom - lh + 1

    base.alpha_composite(scaled, (x, y))


def process_one(
    img_path: Path,
    output_dir: Path,
    sigil: Image.Image,
    logo_right: Image.Image,
    logo_left: Image.Image,
    pattern_mode: str,
) -> tuple[Path, str]:
    with Image.open(img_path) as source:
        src = source.convert("RGBA")

    sw, sh = src.size
    cw = max(sw + 2 * BORDER_WIDTH, int(round(sw * BACKGROUND_SCALE)))
    ch = max(sh + 2 * BORDER_WIDTH, int(round(sh * BACKGROUND_SCALE)))

    bg_color, dot_color, border_color = choose_color_roles()
    canvas, used_pattern = create_dotted_background((cw, ch), bg_color, dot_color, pattern_mode)

    sigil_scaled = scale_to_fit(sigil, int(round(sw * SIGIL_SCALE)), int(round(sh * SIGIL_SCALE)))
    sx = (cw - sigil_scaled.width) // 2
    sy = (ch - sigil_scaled.height) // 2
    canvas.alpha_composite(sigil_scaled, (sx, sy))

    px = (cw - sw) // 2
    py = (ch - sh) // 2
    canvas.alpha_composite(src, (px, py))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle(
        (px - BORDER_WIDTH, py - BORDER_WIDTH, px + sw + BORDER_WIDTH - 1, py + sh + BORDER_WIDTH - 1),
        outline=border_color + (255,),
        width=BORDER_WIDTH,
    )

    paste_corner_logo(canvas, logo_right, (px, py), (sw, sh), "right")
    paste_corner_logo(canvas, logo_left, (px, py), (sw, sh), "left")

    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f"{img_path.stem}_framed.png"
    canvas.convert("RGB").save(out_path, "PNG")
    return out_path, used_pattern


class FrameMakerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Frame Maker v{APP_VERSION}")
        self.root.geometry("720x460")

        self.base_dir = Path(__file__).resolve().parent
        self.status_var = tk.StringVar(value="Ready. Click Generate Frames.")

        tk.Label(root, text="Frame Maker", font=("Arial", 16, "bold")).pack(pady=(10, 4))
        tk.Label(root, text="Uses ./Input images and writes to ./Output", font=("Arial", 10)).pack(pady=(0, 10))

        self.run_button = tk.Button(root, text="Generate Frames", command=self.start_processing, width=24, height=2)
        self.run_button.pack(pady=8)

        self.pattern_mode_var = tk.StringVar(value=PATTERN_POLKA)
        pattern_row = tk.Frame(root)
        pattern_row.pack(pady=(0, 8))
        tk.Label(pattern_row, text="Dot pattern:").pack(side="left")
        tk.OptionMenu(pattern_row, self.pattern_mode_var, PATTERN_POLKA, PATTERN_MIXED, PATTERN_SPLATTER).pack(side="left")

        tk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12)

        self.log = tk.Text(root, height=17, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=12)
        self.log.configure(state="disabled")

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_processing(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        self.append_log(f"Frame Maker v{APP_VERSION}")
        self.run_button.configure(state="disabled")
        self.status_var.set("Processing...")
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self) -> None:
        try:
            self.append_log(f"Base folder: {self.base_dir}")

            sigil_path = find_file_case_insensitive(self.base_dir, "sigil.jpg")
            logo_path = find_file_case_insensitive(self.base_dir, "logo.png")
            cracked_logo_path = find_file_case_insensitive(self.base_dir, "Cracked Egg Logo.png")

            images = list_input_images(self.base_dir / "Input")
            output_dir = self.base_dir / "Output"
            pattern_mode = self.pattern_mode_var.get()

            with Image.open(sigil_path) as s:
                sigil = s.convert("RGBA")
            with Image.open(logo_path) as lr:
                logo_right = lr.convert("RGBA")
            with Image.open(cracked_logo_path) as ll:
                logo_left = ll.convert("RGBA")

            self.append_log(f"Found {len(images)} image(s) in Input")
            self.append_log(f"Pattern mode: {pattern_mode}")

            for img in images:
                out_path, used_pattern = process_one(img, output_dir, sigil, logo_right, logo_left, pattern_mode)
                self.append_log(f"✓ {img.name} -> {out_path.name} ({used_pattern})")

            self.status_var.set(f"Done. Wrote {len(images)} file(s) to Output.")
            self.root.after(0, lambda: messagebox.showinfo("Frame Maker", f"Done! Processed {len(images)} image(s)."))
        except Exception as exc:
            err_msg = str(exc)
            self.status_var.set("Failed. See log.")
            self.append_log(f"ERROR: {err_msg}")
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Frame Maker", m))
        finally:
            self.root.after(0, lambda: self.run_button.configure(state="normal"))


def main() -> None:
    root = tk.Tk()
    FrameMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
