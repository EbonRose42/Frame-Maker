#!/usr/bin/env python3
"""Frame Maker v2 - standalone GUI framer with live preview and full controls."""

from __future__ import annotations

import random
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw, ImageTk

APP_VERSION = "2.4.0"

PALETTE = ((0, 0, 0), (255, 255, 255), (255, 0, 0))
ALLOWED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PREVIEW_MAX_SIZE = (520, 520)

PATTERN_POLKA = "polka"
PATTERN_SPLATTER = "splatter"
PATTERN_MIXED = "mixed"
CORNER_OPTIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
ORIENTATION_RANDOM = "random"
ORIENTATION_GRID = "grid"
ORIENTATION_DIAGONAL = "diagonal"


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


def choose_color_roles() -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    colors = list(PALETTE)
    random.shuffle(colors)
    return colors[0], colors[1], colors[2]


def apply_opacity(layer: Image.Image, opacity_percent: int) -> Image.Image:
    opacity = max(0, min(100, opacity_percent)) / 100.0
    if opacity >= 0.999:
        return layer
    adjusted = layer.copy()
    alpha = adjusted.getchannel("A")
    alpha = alpha.point(lambda a: int(a * opacity))
    adjusted.putalpha(alpha)
    return adjusted


def corner_position(canvas_wh: tuple[int, int], overlay_wh: tuple[int, int], corner: str) -> tuple[int, int]:
    cw, ch = canvas_wh
    ow, oh = overlay_wh
    left_x = 0
    right_x = cw - ow
    top_y = 0
    bottom_y = ch - oh

    if corner == "top-left":
        return left_x, top_y
    if corner == "top-right":
        return right_x, top_y
    if corner == "bottom-left":
        return left_x, bottom_y
    return right_x, bottom_y


def paste_corner_logo(base: Image.Image, logo: Image.Image, corner: str, icon_scale_percent: int) -> None:
    cw, ch = base.size
    icon_scale = max(1, min(20, icon_scale_percent)) / 100.0
    logo_target_w = max(1, int(round(cw * icon_scale)))
    scaled = scale_to_fit(logo, logo_target_w, max(1, int(round(ch * 0.35))))
    base.alpha_composite(scaled, corner_position(base.size, scaled.size, corner))


def create_splatter_background(
    size: tuple[int, int],
    bg_color: tuple[int, int, int],
    dot_color: tuple[int, int, int],
    dot_size_percent: int,
    dot_gap_percent: int,
    dot_size_random: bool,
    dot_gap_random: bool,
) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, bg_color + (255,))
    draw = ImageDraw.Draw(layer)

    base = min(w, h)
    size_factor = (random.randint(5, 100) if dot_size_random else dot_size_percent) / 100.0
    gap_factor = (random.randint(5, 100) if dot_gap_random else dot_gap_percent) / 100.0

    min_r = max(1, int(base * (0.002 + 0.016 * size_factor)))
    max_r = max(min_r + 1, int(base * (0.006 + 0.040 * size_factor)))

    # higher gap => lower density
    density = max(0.00015, 0.0042 * (1.05 - gap_factor))
    count = max(30, int(w * h * density))

    for _ in range(count):
        r = random.randint(min_r, max_r)
        x = random.randint(-r, w + r)
        y = random.randint(-r, h + r)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=dot_color + (255,))

    return layer


def create_polka_background(
    size: tuple[int, int],
    bg_color: tuple[int, int, int],
    dot_color: tuple[int, int, int],
    dot_size_percent: int,
    dot_gap_percent: int,
    orientation_mode: str,
    dot_size_random: bool,
    dot_gap_random: bool,
    orientation_random: bool,
) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, bg_color + (255,))
    draw = ImageDraw.Draw(layer)

    base = min(w, h)
    size_factor = (random.randint(5, 100) if dot_size_random else dot_size_percent) / 100.0
    gap_factor = (random.randint(5, 100) if dot_gap_random else dot_gap_percent) / 100.0

    dot_radius = max(1, int(base * (0.004 + 0.024 * size_factor)))
    gap = max(1, int(base * (0.005 + 0.050 * gap_factor)))
    tile = max(dot_radius * 2 + gap, dot_radius * 3)

    if orientation_random:
        diagonal = random.random() < 0.5
    else:
        diagonal = orientation_mode == ORIENTATION_DIAGONAL

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
    polka_primary_weight: float,
    dot_size_percent: int,
    dot_gap_percent: int,
    orientation_mode: str,
    dot_size_random: bool,
    dot_gap_random: bool,
    orientation_random: bool,
) -> tuple[Image.Image, str]:
    use_polka = pattern_mode == PATTERN_POLKA or (
        pattern_mode == PATTERN_MIXED and random.random() < polka_primary_weight
    )
    if use_polka:
        return (
            create_polka_background(
                size,
                bg_color,
                dot_color,
                dot_size_percent,
                dot_gap_percent,
                orientation_mode,
                dot_size_random,
                dot_gap_random,
                orientation_random,
            ),
            PATTERN_POLKA,
        )

    return (
        create_splatter_background(
            size,
            bg_color,
            dot_color,
            dot_size_percent,
            dot_gap_percent,
            dot_size_random,
            dot_gap_random,
        ),
        PATTERN_SPLATTER,
    )


def render_frame(
    img_path: Path,
    sigil: Image.Image,
    logo_a: Image.Image,
    logo_b: Image.Image,
    pattern_mode: str,
    polka_primary_weight: float,
    background_scale_percent: int,
    border_width: int,
    sigil_scale_percent: int,
    logo_a_corner: str,
    logo_b_corner: str,
    logo_a_scale_percent: int,
    logo_b_scale_percent: int,
    frame_opacity_percent: int,
    dot_size_percent: int,
    dot_gap_percent: int,
    dot_orientation: str,
    dot_size_random: bool,
    dot_gap_random: bool,
    dot_orientation_random: bool,
) -> tuple[Image.Image, str]:
    with Image.open(img_path) as source:
        src = source.convert("RGBA")

    sw, sh = src.size
    bg_scale = max(100, min(250, background_scale_percent)) / 100.0
    bw = max(1, border_width)
    sigil_scale = max(1, min(100, sigil_scale_percent)) / 100.0

    cw = max(sw + 2 * bw, int(round(sw * bg_scale)))
    ch = max(sh + 2 * bw, int(round(sh * bg_scale)))

    bg_color, dot_color, border_color = choose_color_roles()
    frame_layer, used_pattern = create_dotted_background(
        (cw, ch),
        bg_color,
        dot_color,
        pattern_mode,
        polka_primary_weight,
        dot_size_percent,
        dot_gap_percent,
        dot_orientation,
        dot_size_random,
        dot_gap_random,
        dot_orientation_random,
    )

    sigil_scaled = scale_to_fit(sigil, int(round(sw * sigil_scale)), int(round(sh * sigil_scale)))
    sx = (cw - sigil_scaled.width) // 2
    sy = (ch - sigil_scaled.height) // 2
    frame_layer.alpha_composite(sigil_scaled, (sx, sy))

    px = (cw - sw) // 2
    py = (ch - sh) // 2

    draw = ImageDraw.Draw(frame_layer)
    draw.rectangle(
        (px - bw, py - bw, px + sw + bw - 1, py + sh + bw - 1),
        outline=border_color + (255,),
        width=bw,
    )

    frame_layer = apply_opacity(frame_layer, frame_opacity_percent)

    canvas = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    canvas.alpha_composite(frame_layer)
    canvas.alpha_composite(src, (px, py))

    # Icons are always top-most.
    paste_corner_logo(canvas, logo_a, logo_a_corner, logo_a_scale_percent)
    paste_corner_logo(canvas, logo_b, logo_b_corner, logo_b_scale_percent)
    return canvas, used_pattern


def process_one(
    img_path: Path,
    output_dir: Path,
    sigil: Image.Image,
    logo_a: Image.Image,
    logo_b: Image.Image,
    **settings: int | float | str | bool,
) -> tuple[Path, str]:
    canvas, used_pattern = render_frame(img_path, sigil, logo_a, logo_b, **settings)
    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f"{img_path.stem}_framed.png"
    canvas.convert("RGB").save(out_path, "PNG")
    return out_path, used_pattern


class FrameMakerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Frame Maker v{APP_VERSION}")
        self.root.geometry("1180x900")

        self.base_dir = Path(__file__).resolve().parent
        self.status_var = tk.StringVar(value="Ready. Tune settings, preview, then process.")
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_render_cache: Image.Image | None = None
        self.preview_signature: tuple[str, tuple[tuple[str, object], ...]] | None = None
        self.preview_used_pattern: str | None = None
        self.processed_images: set[str] = set()

        tk.Label(root, text="Frame Maker", font=("Arial", 16, "bold")).pack(pady=(10, 4))
        tk.Label(root, text="Fixed sigil/icons assets + control panel + live preview", font=("Arial", 10)).pack(pady=(0, 10))

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

        self.logo_a_corner_var = tk.StringVar(value="bottom-right")
        tk.Label(controls, text="Logo corner (logo.png):").grid(row=2, column=0, padx=4, pady=4, sticky="w")
        tk.OptionMenu(controls, self.logo_a_corner_var, *CORNER_OPTIONS).grid(row=2, column=1, padx=4, pady=4, sticky="we")

        self.logo_b_corner_var = tk.StringVar(value="bottom-left")
        tk.Label(controls, text="Logo corner (Cracked Egg):").grid(row=3, column=0, padx=4, pady=4, sticky="w")
        tk.OptionMenu(controls, self.logo_b_corner_var, *CORNER_OPTIONS).grid(row=3, column=1, padx=4, pady=4, sticky="we")

        self.dot_orientation_var = tk.StringVar(value=ORIENTATION_DIAGONAL)
        tk.Label(controls, text="Dot orientation:").grid(row=4, column=0, padx=4, pady=4, sticky="w")
        tk.OptionMenu(controls, self.dot_orientation_var, ORIENTATION_GRID, ORIENTATION_DIAGONAL).grid(row=4, column=1, padx=4, pady=4, sticky="we")

        slider_box = tk.LabelFrame(controls, text="Variable Controls")
        slider_box.grid(row=5, column=0, columnspan=2, pady=(8, 6), sticky="we")

        self.logo_a_scale_var = tk.IntVar(value=15)
        tk.Label(slider_box, text="Logo.png scale % (1-20)").grid(row=0, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=1, to=20, orient="horizontal", variable=self.logo_a_scale_var).grid(row=1, column=0, sticky="we", padx=4)

        self.logo_b_scale_var = tk.IntVar(value=15)
        tk.Label(slider_box, text="Cracked Egg scale % (1-20)").grid(row=2, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=1, to=20, orient="horizontal", variable=self.logo_b_scale_var).grid(row=3, column=0, sticky="we", padx=4)

        self.border_width_var = tk.IntVar(value=10)
        tk.Label(slider_box, text="Border width (px)").grid(row=4, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=1, to=40, orient="horizontal", variable=self.border_width_var).grid(row=5, column=0, sticky="we", padx=4)

        self.background_scale_var = tk.IntVar(value=115)
        tk.Label(slider_box, text="Frame size % of image").grid(row=6, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=100, to=220, orient="horizontal", variable=self.background_scale_var).grid(row=7, column=0, sticky="we", padx=4)

        self.sigil_scale_var = tk.IntVar(value=50)
        tk.Label(slider_box, text="Sigil scale %").grid(row=8, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=10, to=100, orient="horizontal", variable=self.sigil_scale_var).grid(row=9, column=0, sticky="we", padx=4)

        self.frame_opacity_var = tk.IntVar(value=100)
        tk.Label(slider_box, text="Frame opacity %").grid(row=10, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=0, to=100, orient="horizontal", variable=self.frame_opacity_var).grid(row=11, column=0, sticky="we", padx=4)

        self.polka_weight_var = tk.IntVar(value=85)
        tk.Label(slider_box, text="Polka chance % (Mixed mode)").grid(row=12, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=0, to=100, orient="horizontal", variable=self.polka_weight_var).grid(row=13, column=0, sticky="we", padx=4)

        self.dot_size_var = tk.IntVar(value=35)
        tk.Label(slider_box, text="Dot size %").grid(row=14, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=1, to=100, orient="horizontal", variable=self.dot_size_var).grid(row=15, column=0, sticky="we", padx=4)
        self.dot_size_random_var = tk.BooleanVar(value=False)
        tk.Checkbutton(slider_box, text="Random dot size", variable=self.dot_size_random_var).grid(row=16, column=0, sticky="w", padx=4)

        self.dot_gap_var = tk.IntVar(value=40)
        tk.Label(slider_box, text="Dot distance %").grid(row=17, column=0, sticky="w", padx=4)
        tk.Scale(slider_box, from_=1, to=100, orient="horizontal", variable=self.dot_gap_var).grid(row=18, column=0, sticky="we", padx=4)
        self.dot_gap_random_var = tk.BooleanVar(value=False)
        tk.Checkbutton(slider_box, text="Random dot distance", variable=self.dot_gap_random_var).grid(row=19, column=0, sticky="w", padx=4)

        self.dot_orientation_random_var = tk.BooleanVar(value=False)
        tk.Checkbutton(slider_box, text="Random dot orientation", variable=self.dot_orientation_random_var).grid(row=20, column=0, sticky="w", padx=4)

        slider_box.grid_columnconfigure(0, weight=1)
        controls.grid_columnconfigure(1, weight=1)

        buttons_row = tk.Frame(controls)
        buttons_row.grid(row=6, column=0, columnspan=2, pady=(8, 2), sticky="we")
        self.refresh_button = tk.Button(buttons_row, text="Refresh Inputs", command=self.refresh_options, width=14)
        self.refresh_button.pack(side="left", padx=3)
        self.preview_button = tk.Button(buttons_row, text="Generate Preview", command=self.generate_preview, width=14)
        self.preview_button.pack(side="left", padx=3)

        self.run_button = tk.Button(controls, text="Process Image", command=self.start_processing, width=30, height=2)
        self.run_button.grid(row=7, column=0, columnspan=2, pady=(8, 4), sticky="we")

        preview_container = tk.Frame(top, bd=1, relief="sunken")
        preview_container.pack(side="left", fill="both", expand=True)
        tk.Label(preview_container, text="Preview", font=("Arial", 11, "bold")).pack(pady=(6, 2))
        self.preview_label = tk.Label(preview_container, text="Click Generate Preview", bg="#f3f3f3")
        self.preview_label.pack(fill="both", expand=True, padx=8, pady=8)

        tk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12)

        self.log = tk.Text(root, height=9, wrap="word")
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
            self.processed_images = {n for n in self.processed_images if n in image_names}
            selected = self.input_image_var.get() if self.input_image_var.get() in image_names else image_names[0]
            self._set_option_values(self.input_image_menu, self.input_image_var, image_names, selected)
            self.status_var.set(f"Ready. {len(image_names)} input image(s) found.")
        except Exception as exc:
            self.status_var.set("Refresh failed. See log.")
            self.append_log(f"ERROR refreshing inputs: {exc}")

    def _required_assets(self) -> tuple[Path, Path, Path]:
        sigil = find_file_case_insensitive(self.base_dir, "sigil.png")
        logo_a = find_file_case_insensitive(self.base_dir, "logo.png")
        logo_b = find_file_case_insensitive(self.base_dir, "Cracked Egg Logo.png")
        return sigil, logo_a, logo_b

    def _current_image(self) -> Path:
        image_name = self.input_image_var.get().strip()
        if not image_name:
            raise ValueError("No input image selected")
        img_path = self.base_dir / "Input" / image_name
        if not img_path.exists():
            raise FileNotFoundError(f"Selected image not found: {img_path}")
        return img_path

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _frame_settings(self) -> dict[str, int | float | str | bool]:
        return {
            "pattern_mode": self.pattern_mode_var.get(),
            "polka_primary_weight": self.polka_weight_var.get() / 100.0,
            "background_scale_percent": self.background_scale_var.get(),
            "border_width": self.border_width_var.get(),
            "sigil_scale_percent": self.sigil_scale_var.get(),
            "logo_a_corner": self.logo_a_corner_var.get(),
            "logo_b_corner": self.logo_b_corner_var.get(),
            "logo_a_scale_percent": self.logo_a_scale_var.get(),
            "logo_b_scale_percent": self.logo_b_scale_var.get(),
            "frame_opacity_percent": self.frame_opacity_var.get(),
            "dot_size_percent": self.dot_size_var.get(),
            "dot_gap_percent": self.dot_gap_var.get(),
            "dot_orientation": self.dot_orientation_var.get(),
            "dot_size_random": self.dot_size_random_var.get(),
            "dot_gap_random": self.dot_gap_random_var.get(),
            "dot_orientation_random": self.dot_orientation_random_var.get(),
        }
    def _selection_signature(self, img_path: Path, settings: dict[str, int | float | str | bool]) -> tuple[str, tuple[tuple[str, object], ...]]:
        ordered = tuple(sorted(settings.items()))
        return str(img_path.resolve()), ordered


    def generate_preview(self) -> None:
        try:
            img_path = self._current_image()
            sigil_path, logo_a_path, logo_b_path = self._required_assets()
            settings = self._frame_settings()

            with Image.open(sigil_path) as s:
                sigil = s.convert("RGBA")
            with Image.open(logo_a_path) as a:
                logo_a = a.convert("RGBA")
            with Image.open(logo_b_path) as b:
                logo_b = b.convert("RGBA")

            preview_image, used_pattern = render_frame(img_path, sigil, logo_a, logo_b, **settings)
            self.preview_render_cache = preview_image.copy()
            self.preview_signature = self._selection_signature(img_path, settings)
            self.preview_used_pattern = used_pattern

            preview_resized = scale_to_fit(preview_image.convert("RGB"), PREVIEW_MAX_SIZE[0], PREVIEW_MAX_SIZE[1])
            self.preview_photo = ImageTk.PhotoImage(preview_resized)
            self.preview_label.configure(image=self.preview_photo, text="")

            self.append_log(
                f"Preview: {img_path.name} | {used_pattern} | logo corners=({settings['logo_a_corner']}, {settings['logo_b_corner']})"
            )
            self.status_var.set("Preview updated.")
        except Exception as exc:
            self.append_log(f"ERROR previewing image: {exc}")
            self.status_var.set("Preview failed. See log.")

    def _advance_to_next_image(self, current_name: str) -> None:
        images = [p.name for p in list_input_images(self.base_dir / "Input")]
        self.processed_images.add(current_name)
        remaining = [name for name in images if name not in self.processed_images]
        if not remaining:
            self.status_var.set("All input images have been processed.")
            self.root.after(0, lambda: messagebox.showinfo("Frame Maker", "All images in Input have been processed."))
            return
        self.input_image_var.set(remaining[0])
        self.status_var.set(f"Next image selected: {remaining[0]}")

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
            img_path = self._current_image()
            sigil_path, logo_a_path, logo_b_path = self._required_assets()
            settings = self._frame_settings()

            with Image.open(sigil_path) as s:
                sigil = s.convert("RGBA")
            with Image.open(logo_a_path) as a:
                logo_a = a.convert("RGBA")
            with Image.open(logo_b_path) as b:
                logo_b = b.convert("RGBA")

            output_dir = self.base_dir / "Output"
            output_dir.mkdir(exist_ok=True)
            out_path = output_dir / f"{img_path.stem}_framed.png"

            current_signature = self._selection_signature(img_path, settings)
            if self.preview_render_cache is not None and self.preview_signature == current_signature:
                self.preview_render_cache.convert("RGB").save(out_path, "PNG")
                used_pattern = self.preview_used_pattern or "preview"
                self.append_log("Using cached preview render for exact output match.")
            else:
                _, used_pattern = process_one(img_path, output_dir, sigil, logo_a, logo_b, **settings)
                self.append_log("Preview was stale or missing; output rendered from current settings.")

            self.append_log(f"✓ {img_path.name} -> {out_path.name} ({used_pattern})")
            self.status_var.set("Done. Wrote 1 file to Output.")

            self.root.after(0, lambda: messagebox.showinfo("Frame Maker", f"Done! Processed {img_path.name}."))
            self.root.after(0, lambda n=img_path.name: self._advance_to_next_image(n))
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
