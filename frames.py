#!/usr/bin/env python3
"""Frame Maker with randomized 3-color dotted backgrounds and GUI launcher."""

from __future__ import annotations

import random
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw

PALETTE = ((0, 0, 0), (255, 255, 255), (255, 0, 0))  # black, white, red
ALLOWED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
BORDER_WIDTH = 10
BACKGROUND_SCALE = 1.15
SIGIL_SCALE = 0.50
LOGO_SCALE = 0.18
LOGO_OVERLAP = 0.15


def find_file_case_insensitive(folder: Path, wanted_name: str) -> Path:
    wanted = wanted_name.lower()
    for p in folder.iterdir():
        if p.is_file() and p.name.lower() == wanted:
            return p
    raise FileNotFoundError(f"Missing required file: {wanted_name}")


def list_input_images(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError("Missing Input folder next to frames.py")
    images = [
        p
        for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in ALLOWED_INPUT_EXTS
    ]
    if not images:
        raise FileNotFoundError("No supported images found in Input folder")
    return images


def scale_to_fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    w, h = img.size
    ratio = min(max_w / w, max_h / h)
    ratio = max(ratio, 0.0001)
    return img.resize((max(1, int(round(w * ratio))), max(1, int(round(h * ratio)))), Image.LANCZOS)


def create_dotted_background(size: tuple[int, int], bg_color: tuple[int, int, int], dot_color: tuple[int, int, int]) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, bg_color + (255,))
    draw = ImageDraw.Draw(layer)

    density = random.uniform(0.0008, 0.0022)
    count = max(80, int(w * h * density))
    min_r = max(2, int(min(w, h) * 0.004))
    max_r = max(min_r + 1, int(min(w, h) * random.uniform(0.012, 0.03)))

    for _ in range(count):
        r = random.randint(min_r, max_r)
        x = random.randint(-r, w + r)
        y = random.randint(-r, h + r)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=dot_color + (255,))

    return layer


def choose_color_roles() -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    colors = list(PALETTE)
    random.shuffle(colors)
    return colors[0], colors[1], colors[2]  # background, dots, border


def corner_logo(base: Image.Image, logo: Image.Image, photo_xy: tuple[int, int], photo_wh: tuple[int, int], side: str) -> None:
    px, py = photo_xy
    pw, ph = photo_wh

    logo_target_w = max(1, int(round(pw * LOGO_SCALE)))
    scaled = scale_to_fit(logo, logo_target_w, max(1, int(round(ph * 0.25))))
    lw, lh = scaled.size

    inset_x = int(round(lw * LOGO_OVERLAP))
    inset_y = int(round(lh * LOGO_OVERLAP))

    if side == "right":
        x = px + pw - inset_x - lw
    else:
        x = px - lw + inset_x
    y = py + ph - lh + inset_y

    base.alpha_composite(scaled, (x, y))


def process_image(img_path: Path, output_dir: Path, sigil: Image.Image, logo_r: Image.Image, logo_l: Image.Image) -> Path:
    with Image.open(img_path) as source:
        src = source.convert("RGBA")

    sw, sh = src.size
    cw = max(sw + 2 * BORDER_WIDTH, int(round(sw * BACKGROUND_SCALE)))
    ch = max(sh + 2 * BORDER_WIDTH, int(round(sh * BACKGROUND_SCALE)))

    bg_color, dot_color, border_color = choose_color_roles()
    canvas = create_dotted_background((cw, ch), bg_color, dot_color)

    sigil_scaled = scale_to_fit(sigil, int(round(sw * SIGIL_SCALE)), int(round(sh * SIGIL_SCALE)))
    sx = (cw - sigil_scaled.width) // 2
    sy = (ch - sigil_scaled.height) // 2
    canvas.alpha_composite(sigil_scaled, (sx, sy))

    px = (cw - sw) // 2
    py = (ch - sh) // 2
    canvas.alpha_composite(src, (px, py))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((px - BORDER_WIDTH, py - BORDER_WIDTH, px + sw + BORDER_WIDTH - 1, py + sh + BORDER_WIDTH - 1), outline=border_color + (255,), width=BORDER_WIDTH)

    corner_logo(canvas, logo_r, (px, py), (sw, sh), "right")
    corner_logo(canvas, logo_l, (px, py), (sw, sh), "left")

    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f"{img_path.stem}_framed.png"
    canvas.convert("RGB").save(out_path, "PNG")
    return out_path


class FrameMakerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Frame Maker")
        self.root.geometry("700x420")

        self.base_dir = Path(__file__).resolve().parent
        self.status_var = tk.StringVar(value="Ready. Click Generate Frames.")

        tk.Label(root, text="Frame Maker", font=("Arial", 16, "bold")).pack(pady=(10, 4))
        tk.Label(root, text="Uses ./Input images and writes to ./Output", font=("Arial", 10)).pack(pady=(0, 10))

        self.run_button = tk.Button(root, text="Generate Frames", command=self.start_processing, width=24, height=2)
        self.run_button.pack(pady=8)

        tk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12)

        self.log = tk.Text(root, height=16, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=12)
        self.log.configure(state="disabled")

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_processing(self) -> None:
        self.run_button.configure(state="disabled")
        self.status_var.set("Processing...")
        worker = threading.Thread(target=self._process, daemon=True)
        worker.start()

    def _process(self) -> None:
        try:
            self.append_log(f"Base folder: {self.base_dir}")
            sigil_path = find_file_case_insensitive(self.base_dir, "sigil.jpg")
            logo_path = find_file_case_insensitive(self.base_dir, "logo.png")
            cracked_logo_path = find_file_case_insensitive(self.base_dir, "Cracked Egg Logo.png")

            input_dir = self.base_dir / "Input"
            output_dir = self.base_dir / "Output"
            images = list_input_images(input_dir)

            with Image.open(sigil_path) as s:
                sigil = s.convert("RGBA")
            with Image.open(logo_path) as lr:
                logo_r = lr.convert("RGBA")
            with Image.open(cracked_logo_path) as ll:
                logo_l = ll.convert("RGBA")

            self.append_log(f"Found {len(images)} images in Input")
            for img in images:
                out = process_image(img, output_dir, sigil, logo_r, logo_l)
                self.append_log(f"✓ {img.name} -> {out.name}")

            self.status_var.set(f"Done. Wrote {len(images)} file(s) to Output.")
            self.root.after(0, lambda: messagebox.showinfo("Frame Maker", f"Done! Processed {len(images)} image(s)."))
        except Exception as exc:
            self.status_var.set("Failed. See log.")
            self.append_log(f"ERROR: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Frame Maker", str(exc)))
        finally:
            self.root.after(0, lambda: self.run_button.configure(state="normal"))


def main() -> None:
    root = tk.Tk()
    FrameMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
