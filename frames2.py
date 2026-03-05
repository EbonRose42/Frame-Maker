#!/usr/bin/env python3
"""Frame Maker v2 - standalone GUI framer with preview."""

from __future__ import annotations

import random
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw, ImageTk

APP_VERSION = "2.2.0"

PALETTE = ((0, 0, 0), (255, 255, 255), (255, 0, 0))  # black, white, red
ALLOWED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

BORDER_WIDTH = 10
BACKGROUND_SCALE = 1.15
SIGIL_SCALE = 0.50
ICON_SCALE_OPTIONS = (0.10, 0.15, 0.20)
POLKA_PRIMARY_WEIGHT = 0.85
PREVIEW_MAX_SIZE = (460, 460)

PATTERN_POLKA = "polka"
PATTERN_SPLATTER = "splatter"
PATTERN_MIXED = "mixed"


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


def paste_corner_logo(base: Image.Image, logo: Image.Image, side: str, icon_scale: float) -> None:
    cw, ch = base.size
    logo_target_w = max(1, int(round(cw * icon_scale)))
    scaled = scale_to_fit(logo, logo_target_w, max(1, int(round(ch * 0.30))))
    lw, lh = scaled.size

    frame_left = 0
    frame_right = cw - 1
    frame_bottom = ch - 1

    if side == "right":
        x = frame_right - lw + 1
    else:
        x = frame_left
    y = frame_bottom - lh + 1

    base.alpha_composite(scaled, (x, y))


def render_frame(
    img_path: Path,
    sigil: Image.Image,
    logo_right: Image.Image,
    logo_left: Image.Image,
    pattern_mode: str,
    icon_scale: float,
) -> tuple[Image.Image, str]:
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

    paste_corner_logo(canvas, logo_right, "right", icon_scale)
    paste_corner_logo(canvas, logo_left, "left", icon_scale)
    return canvas, used_pattern


def process_one(
    img_path: Path,
    output_dir: Path,
    sigil: Image.Image,
    logo_right: Image.Image,
    logo_left: Image.Image,
    pattern_mode: str,
    icon_scale: float,
) -> tuple[Path, str]:
    canvas, used_pattern = render_frame(img_path, sigil, logo_right, logo_left, pattern_mode, icon_scale)
    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f"{img_path.stem}_framed.png"
    canvas.convert("RGB").save(out_path, "PNG")
    return out_path, used_pattern


class FrameMakerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Frame Maker v{APP_VERSION}")
        self.root.geometry("1040x760")

        self.base_dir = Path(__file__).resolve().parent
        self.status_var = tk.StringVar(value="Ready. Select one image, preview it, then process.")
        self.asset_pool: list[Path] = []
        self.preview_photo: ImageTk.PhotoImage | None = None

        tk.Label(root, text="Frame Maker", font=("Arial", 16, "bold")).pack(pady=(10, 4))
        tk.Label(root, text="Preview first, then save one framed image at a time", font=("Arial", 10)).pack(pady=(0, 10))

        top = tk.Frame(root)
        top.pack(fill="both", expand=True, padx=12)

        controls = tk.Frame(top)
        controls.pack(side="left", fill="y", padx=(0, 10))

        self.input_image_var = tk.StringVar(value="")
        tk.Label(controls, text="Input image:").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        self.input_image_menu = tk.OptionMenu(controls, self.input_image_var, "")
        self.input_image_menu.grid(row=0, column=1, padx=4, pady=4, sticky="we")

        self.pattern_mode_var = tk.StringVar(value=PATTERN_POLKA)
        tk.Label(controls, text="Dot pattern:").grid(row=1, column=0, padx=4, pady=4, sticky="w")
        tk.OptionMenu(controls, self.pattern_mode_var, PATTERN_POLKA, PATTERN_MIXED, PATTERN_SPLATTER).grid(row=1, column=1, padx=4, pady=4, sticky="we")

        self.icon_scale_var = tk.StringVar(value="15%")
        tk.Label(controls, text="Icon size:").grid(row=2, column=0, padx=4, pady=4, sticky="w")
        tk.OptionMenu(controls, self.icon_scale_var, "10%", "15%", "20%").grid(row=2, column=1, padx=4, pady=4, sticky="we")

        self.sigil_var = tk.StringVar(value="Random")
        tk.Label(controls, text="Center sigil:").grid(row=3, column=0, padx=4, pady=4, sticky="w")
        self.sigil_menu = tk.OptionMenu(controls, self.sigil_var, "Random")
        self.sigil_menu.grid(row=3, column=1, padx=4, pady=4, sticky="we")

        self.logo_right_var = tk.StringVar(value="Random")
        tk.Label(controls, text="Bottom-right logo:").grid(row=4, column=0, padx=4, pady=4, sticky="w")
        self.logo_right_menu = tk.OptionMenu(controls, self.logo_right_var, "Random")
        self.logo_right_menu.grid(row=4, column=1, padx=4, pady=4, sticky="we")

        self.logo_left_var = tk.StringVar(value="Random")
        tk.Label(controls, text="Bottom-left logo:").grid(row=5, column=0, padx=4, pady=4, sticky="w")
        self.logo_left_menu = tk.OptionMenu(controls, self.logo_left_var, "Random")
        self.logo_left_menu.grid(row=5, column=1, padx=4, pady=4, sticky="we")

        controls.grid_columnconfigure(1, weight=1)

        buttons_row = tk.Frame(controls)
        buttons_row.grid(row=6, column=0, columnspan=2, pady=(8, 2), sticky="we")
        self.refresh_button = tk.Button(buttons_row, text="Refresh Inputs", command=self.refresh_options, width=16)
        self.refresh_button.pack(side="left", padx=4)
        self.preview_button = tk.Button(buttons_row, text="Generate Preview", command=self.generate_preview, width=16)
        self.preview_button.pack(side="left", padx=4)

        self.run_button = tk.Button(
            controls,
            text="Process Selected Image",
            command=self.start_processing,
            width=32,
            height=2,
        )
        self.run_button.grid(row=7, column=0, columnspan=2, pady=(8, 4), sticky="we")

        preview_container = tk.Frame(top, bd=1, relief="sunken")
        preview_container.pack(side="left", fill="both", expand=True)
        tk.Label(preview_container, text="Preview", font=("Arial", 11, "bold")).pack(pady=(6, 2))
        self.preview_label = tk.Label(preview_container, text="Click Generate Preview", bg="#f3f3f3")
        self.preview_label.pack(fill="both", expand=True, padx=8, pady=8)

        tk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12)

        self.log = tk.Text(root, height=12, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=12)
        self.log.configure(state="disabled")

        self.refresh_options()

    def _set_option_values(self, option_menu: tk.OptionMenu, variable: tk.StringVar, values: list[str], default_value: str) -> None:
        menu = option_menu["menu"]
        menu.delete(0, "end")
        for value in values:
            menu.add_command(label=value, command=tk._setit(variable, value))
        variable.set(default_value)

    def refresh_options(self) -> None:
        try:
            input_images = list_input_images(self.base_dir / "Input")
            image_names = [p.name for p in input_images]
            selected_image = self.input_image_var.get() if self.input_image_var.get() in image_names else image_names[0]
            self._set_option_values(self.input_image_menu, self.input_image_var, image_names, selected_image)

            self.asset_pool = [p for p in sorted(self.base_dir.iterdir()) if p.is_file() and p.suffix.lower() in ALLOWED_INPUT_EXTS]
            asset_names = ["Random"] + [p.name for p in self.asset_pool]
            self._set_option_values(self.sigil_menu, self.sigil_var, asset_names, "Random")
            self._set_option_values(self.logo_right_menu, self.logo_right_var, asset_names, "Random")
            self._set_option_values(self.logo_left_menu, self.logo_left_var, asset_names, "Random")

            self.status_var.set(f"Ready. {len(input_images)} input image(s) found.")
        except Exception as exc:
            self.status_var.set("Refresh failed. See log.")
            self.append_log(f"ERROR refreshing inputs/assets: {exc}")

    def _choose_asset_path(self, selection: str) -> Path:
        if selection == "Random":
            if not self.asset_pool:
                raise FileNotFoundError("No image assets found next to frames2.py")
            return random.choice(self.asset_pool)
        chosen = self.base_dir / selection
        if not chosen.exists():
            raise FileNotFoundError(f"Asset not found: {selection}")
        return chosen

    def _current_selection(self) -> tuple[Path, Path, Path, Path, str, float]:
        image_name = self.input_image_var.get().strip()
        if not image_name:
            raise ValueError("No input image selected")

        img_path = self.base_dir / "Input" / image_name
        if not img_path.exists():
            raise FileNotFoundError(f"Selected image not found: {img_path}")

        sigil_path = self._choose_asset_path(self.sigil_var.get())
        logo_path = self._choose_asset_path(self.logo_right_var.get())
        cracked_logo_path = self._choose_asset_path(self.logo_left_var.get())
        pattern_mode = self.pattern_mode_var.get()
        icon_scale = int(self.icon_scale_var.get().replace("%", "")) / 100.0
        return img_path, sigil_path, logo_path, cracked_logo_path, pattern_mode, icon_scale

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def generate_preview(self) -> None:
        try:
            img_path, sigil_path, logo_path, cracked_logo_path, pattern_mode, icon_scale = self._current_selection()
            with Image.open(sigil_path) as s:
                sigil = s.convert("RGBA")
            with Image.open(logo_path) as lr:
                logo_right = lr.convert("RGBA")
            with Image.open(cracked_logo_path) as ll:
                logo_left = ll.convert("RGBA")

            preview_image, used_pattern = render_frame(img_path, sigil, logo_right, logo_left, pattern_mode, icon_scale)
            preview_resized = scale_to_fit(preview_image.convert("RGB"), PREVIEW_MAX_SIZE[0], PREVIEW_MAX_SIZE[1])
            self.preview_photo = ImageTk.PhotoImage(preview_resized)
            self.preview_label.configure(image=self.preview_photo, text="")

            self.append_log(f"Preview: {img_path.name} | pattern={used_pattern} | icon={int(icon_scale * 100)}%")
            self.status_var.set("Preview updated.")
        except Exception as exc:
            self.append_log(f"ERROR previewing image: {exc}")
            self.status_var.set("Preview failed. See log.")

    def start_processing(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        self.append_log(f"Frame Maker v{APP_VERSION}")
        self.run_button.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.status_var.set("Processing...")
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self) -> None:
        try:
            self.append_log(f"Base folder: {self.base_dir}")
            img_path, sigil_path, logo_path, cracked_logo_path, pattern_mode, icon_scale = self._current_selection()
            output_dir = self.base_dir / "Output"

            with Image.open(sigil_path) as s:
                sigil = s.convert("RGBA")
            with Image.open(logo_path) as lr:
                logo_right = lr.convert("RGBA")
            with Image.open(cracked_logo_path) as ll:
                logo_left = ll.convert("RGBA")

            self.append_log(f"Input image: {img_path.name}")
            self.append_log(f"Sigil: {sigil_path.name} | Right: {logo_path.name} | Left: {cracked_logo_path.name}")
            self.append_log(f"Pattern mode: {pattern_mode}")
            self.append_log(f"Icon size: {int(icon_scale * 100)}%")

            out_path, used_pattern = process_one(img_path, output_dir, sigil, logo_right, logo_left, pattern_mode, icon_scale)
            self.append_log(f"✓ {img_path.name} -> {out_path.name} ({used_pattern})")

            self.status_var.set("Done. Wrote 1 file to Output.")
            self.root.after(0, lambda: messagebox.showinfo("Frame Maker", f"Done! Processed {img_path.name}."))
        except Exception as exc:
            err_msg = str(exc)
            self.status_var.set("Failed. See log.")
            self.append_log(f"ERROR: {err_msg}")
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Frame Maker", m))
        finally:
            self.root.after(0, lambda: self.run_button.configure(state="normal"))
            self.root.after(0, lambda: self.preview_button.configure(state="normal"))
            self.root.after(0, lambda: self.refresh_button.configure(state="normal"))


def main() -> None:
    root = tk.Tk()
    FrameMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
