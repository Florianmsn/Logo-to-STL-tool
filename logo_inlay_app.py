
import json
import os
import threading
import traceback
import re
import colorsys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

from PIL import Image, ImageTk
import numpy as np

from logo_inlay_core import analyze_colors, generate_logo_stls, build_partition_preview, redistribute_auto_groups

try:
    from logo_inlay_core import guess_color_name
except ImportError:
    from logo_inlay_core import closest_color_name as guess_color_name


APP_TITLE = "Logo Inlay Tool 7.5"
MANUAL_AUTO_LABEL = -2147483000
APP_DIR = Path.home() / ".logo_inlay_tool"
SETTINGS_FILE = APP_DIR / "settings.json"
PROFILES_FILE = APP_DIR / "profiles.json"

BACKGROUND_DISPLAY = {
    "Transparent background": "transparent",
    "Remove white background": "white",
    "Remove corner color as background": "corner",
    "Remove outer connected color": "edge",
    "Keep everything": "all",
}
BACKGROUND_INTERNAL = {v: k for k, v in BACKGROUND_DISPLAY.items()}

CONTOUR_DISPLAY = {
    "Straight / crisp": "straight",
    "Smooth curves": "smooth",
    "Maximum detail": "detail",
}
CONTOUR_INTERNAL = {v: k for k, v in CONTOUR_DISPLAY.items()}

EDGE_SMOOTHING_MIGRATION = {
    "Aus": "Off",
    "Leicht": "Light",
    "Mittel": "Medium",
    "Stark": "Strong",
    "Off": "Off",
    "Light": "Light",
    "Medium": "Medium",
    "Strong": "Strong",
}

PROFILE_NAME_MIGRATION = {
    "Kartenspiel Inlay": "Card Inlay",
    "Fein detailliertes Logo": "Fine Detail Logo",
    "Schneller Entwurf": "Quick Draft",
}

GROUP_PREVIEW_COLORS = {
    "schwarz": [34, 34, 34],
    "weiss": [245, 245, 245],
    "weiß": [245, 245, 245],
    "gelb": [251, 192, 45],
    "gruen": [56, 142, 60],
    "grün": [56, 142, 60],
    "blau": [25, 118, 210],
    "hellblau": [3, 169, 244],
    "rot": [211, 47, 47],
    "orange": [245, 124, 0],
    "grau": [128, 128, 128],
    "lila": [123, 31, 162],
    "pink": [216, 27, 96],
    "braun": [121, 85, 72],
    "beige": [210, 180, 140],
    "auto verteilen": [150, 150, 150],
    "zu hintergrund": [220, 220, 220],
}

GROUP_DISPLAY_NAMES = {
    "schwarz": "Black",
    "weiss": "White",
    "weiß": "White",
    "gelb": "Yellow",
    "gruen": "Green",
    "grün": "Green",
    "blau": "Blue",
    "hellblau": "Light Blue",
    "rot": "Red",
    "orange": "Orange",
    "grau": "Gray",
    "lila": "Purple",
    "pink": "Pink",
    "braun": "Brown",
    "beige": "Beige",
    "auto verteilen": "AUTO",
    "zu hintergrund": "Background",
}

def display_group_name(name):
    text = str(name or "").strip()
    lower = text.lower()
    if lower in GROUP_DISPLAY_NAMES:
        return GROUP_DISPLAY_NAMES[lower]

    # Preserve numbered groups such as "rot 2" -> "Red 2".
    m = re.match(r"^(.*?)(\s+\d+)$", lower)
    if m and m.group(1) in GROUP_DISPLAY_NAMES:
        return GROUP_DISPLAY_NAMES[m.group(1)] + m.group(2)
    return text


DEFAULT_PROFILES = {
    "Card Inlay": {
        "target_w": 70.0,
        "target_h": 45.0,
        "keep_aspect": True,
        "detect_colors": 4,
        "height": 0.8,
        "cut": 0.8,
        "clearance": 0.0,
        "smooth": 0.06,
        "edge_smoothing": "Medium",
        "geometry_pixels": 1600,
        "min_area": 0.05,
        "white_threshold": 245,
        "working_pixels": 1800,
        "contour_mode": "smooth",
        "auto_merge": True,
        "merge_distance": 18.0,
        "background": "transparent",
        "deck_color": "#fcfcfc",
        "deckel_w": 110.0,
        "deckel_h": 80.0,
    },
    "Fine Detail Logo": {
        "target_w": 70.0,
        "target_h": 45.0,
        "keep_aspect": True,
        "detect_colors": 8,
        "height": 0.8,
        "cut": 0.8,
        "clearance": 0.0,
        "smooth": 0.02,
        "edge_smoothing": "Light",
        "geometry_pixels": 2000,
        "min_area": 0.03,
        "white_threshold": 245,
        "working_pixels": 2200,
        "contour_mode": "detail",
        "auto_merge": True,
        "merge_distance": 12.0,
        "background": "transparent",
        "deck_color": "#fcfcfc",
        "deckel_w": 110.0,
        "deckel_h": 80.0,
    },
    "Quick Draft": {
        "target_w": 70.0,
        "target_h": 45.0,
        "keep_aspect": True,
        "detect_colors": 4,
        "height": 0.8,
        "cut": 0.8,
        "clearance": 0.0,
        "smooth": 0.08,
        "edge_smoothing": "Medium",
        "geometry_pixels": 1200,
        "min_area": 0.2,
        "white_threshold": 245,
        "working_pixels": 1000,
        "contour_mode": "straight",
        "auto_merge": True,
        "merge_distance": 22.0,
        "background": "transparent",
        "deck_color": "#fcfcfc",
        "deckel_w": 110.0,
        "deckel_h": 80.0,
    },
}

TIP = {
    "target": "Final logo size in millimeters. With Lock aspect ratio enabled, the width controls the proportional size. If disabled, width and height are applied independently.",
    "colors": "Number of colors to detect in the source image. Higher values can capture more shades, but may also detect anti-aliasing and compression artifacts as separate colors.",
    "height": "Height of the printable logo/inlay parts in millimeters.",
    "cut": "Depth of the cutout / negative body. For a flush insert, this is usually the same as the part height.",
    "clearance": "Extra clearance around the cutout. 0 creates an exact fit; higher values make the opening looser.",
    "background": "Defines what is treated as background. Transparent uses the alpha channel. White removes bright white. Corner color uses the image corners. Outer connected color removes only the matching color connected to the image edge.",
    "contour": "Controls how vector edges are generated. Straight / crisp is usually best for logos and lettering. Smooth curves favors rounded shapes. Maximum detail keeps more small features but can produce noisier contours.",
    "smooth": "Simplifies the final vector contour. Higher values reduce tiny edge variations but may remove fine details.",
    "min_area": "Removes very small isolated regions. Increasing this value reduces tiny artifacts and can simplify the final mesh.",
    "deck": "Dimensions of the target surface in millimeters. Used for the final placement preview only.",
}


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 24
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text, justify="left", relief="solid", borderwidth=1, padx=8, pady=5, wraplength=420)
        lbl.pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")



def better_color_name(rgb):
    """Filament oriented color name using RGB thresholds plus HSV.

    Important: very dark colors are always black, even if one RGB channel is slightly higher.
    This prevents dark black areas with blue anti aliasing from being named blau.
    """
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    mx = max(r, g, b)
    mn = min(r, g, b)

    # Strong neutral checks first
    if mx <= 70 and (mx - mn) <= 38:
        return "schwarz"
    if mx <= 45:
        return "schwarz"
    if mn >= 235 and (mx - mn) <= 35:
        return "weiss"

    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue = h * 360.0

    # Low saturation should stay neutral. This fixes many greys and blacks.
    if s < 0.18:
        if v < 0.32:
            return "schwarz"
        if v > 0.82:
            return "weiss"
        return "grau"

    # If it is still very dark, prefer black over a hue.
    if v < 0.22:
        return "schwarz"

    # Browns and beige are orange/yellow with lower brightness or lower saturation.
    if 18 <= hue < 50 and v < 0.62:
        return "braun"
    if 35 <= hue < 70 and s < 0.40 and v > 0.55:
        return "beige"

    if hue < 15 or hue >= 345:
        return "rot"
    if 15 <= hue < 45:
        return "orange"
    if 45 <= hue < 75:
        return "gelb"
    if 75 <= hue < 170:
        return "gruen"
    if 170 <= hue < 205:
        return "hellblau"
    if 205 <= hue < 255:
        return "blau"
    if 255 <= hue < 295:
        return "lila"
    if 295 <= hue < 345:
        return "pink"
    return "grau"



class CollapsibleFrame(ttk.Frame):
    def __init__(self, parent, title, expanded=True):
        super().__init__(parent)
        self.title = title
        self.expanded = tk.BooleanVar(value=expanded)
        self.header = ttk.Button(self, command=self.toggle)
        self.header.pack(fill="x")
        self.body = ttk.Frame(self, padding=(8, 6, 8, 6))
        self.update_state()

    def toggle(self):
        self.expanded.set(not self.expanded.get())
        self.update_state()

    def update_state(self):
        if self.expanded.get():
            self.header.configure(text=f"▼ {self.title}")
            self.body.pack(fill="x")
        else:
            self.header.configure(text=f"▶ {self.title}")
            self.body.pack_forget()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1380x860")
        self.minsize(1000, 600)

        APP_DIR.mkdir(exist_ok=True)
        self.profiles = self.load_profiles()
        self.settings = self.load_settings()

        self.image_path = tk.StringVar(value=self.settings.get("image_path", ""))
        self.project = tk.StringVar(value=self.settings.get("project", "mein_logo"))
        self.out_dir = tk.StringVar(value=self.settings.get("out_dir", ""))
        saved_base = self.settings.get("output_base_dir", "")
        if saved_base:
            self.output_base_dir = Path(saved_base)
        elif self.image_path.get():
            try:
                self.output_base_dir = Path(self.image_path.get()).parent
            except Exception:
                self.output_base_dir = None
        elif self.out_dir.get():
            try:
                self.output_base_dir = Path(self.out_dir.get()).parent
            except Exception:
                self.output_base_dir = None
        else:
            self.output_base_dir = None
        self._auto_output_folder = True
        saved_profile = self.settings.get("profile_name", "Card Inlay")
        saved_profile = PROFILE_NAME_MIGRATION.get(saved_profile, saved_profile)
        self.profile_name = tk.StringVar(value=saved_profile)

        self.target_w = tk.DoubleVar(value=self.settings.get("target_w", 70.0))
        self.target_h = tk.DoubleVar(value=self.settings.get("target_h", 45.0))
        self.keep_aspect = tk.BooleanVar(value=self.settings.get("keep_aspect", True))
        self.detect_colors = tk.IntVar(value=self.settings.get("detect_colors", 4))

        self.height = tk.DoubleVar(value=self.settings.get("height", 0.8))
        self.cut = tk.DoubleVar(value=self.settings.get("cut", 0.8))
        self.clearance = tk.DoubleVar(value=self.settings.get("clearance", 0.0))

        self.background = tk.StringVar(value=self.settings.get("background", "transparent"))
        self.background_display = tk.StringVar(value=BACKGROUND_INTERNAL.get(self.background.get(), "Transparent background"))
        self.contour_mode = tk.StringVar(value=self.settings.get("contour_mode", "straight"))
        self.contour_display = tk.StringVar(value=CONTOUR_INTERNAL.get(self.contour_mode.get(), "Straight / crisp"))

        self.white_threshold = tk.IntVar(value=self.settings.get("white_threshold", 245))
        self.working_pixels = tk.IntVar(value=self.settings.get("working_pixels", 1600))
        self.smooth = tk.DoubleVar(value=self.settings.get("smooth", 0.06))
        saved_smoothing = self.settings.get("edge_smoothing", "Medium")
        self.edge_smoothing = tk.StringVar(value=EDGE_SMOOTHING_MIGRATION.get(saved_smoothing, "Medium"))
        self.geometry_pixels = tk.IntVar(value=self.settings.get("geometry_pixels", 1600))
        self.min_area = tk.DoubleVar(value=self.settings.get("min_area", 0.08))
        self.auto_merge = tk.BooleanVar(value=self.settings.get("auto_merge", True))
        self.merge_distance = tk.DoubleVar(value=self.settings.get("merge_distance", 18.0))

        self.deckel_w = tk.DoubleVar(value=self.settings.get("deckel_w", 110.0))
        self.deckel_h = tk.DoubleVar(value=self.settings.get("deckel_h", 80.0))
        self.deck_color = tk.StringVar(value=self.settings.get("deck_color", "#fcfcfc"))

        self.analysis = None
        self.color_rows = []
        self._highlighted = None
        self.status = tk.StringVar(value="Ready. Load an image and click Analyze Colors.")
        self.preview_photo = None
        self.original_preview_photo = None
        self.deckel_photo = None

        # V6 manual editor state
        self.manual_label_img = None
        self.manual_background_mask = None

        # "Committed" state is what all expensive processing / STL export uses.
        # manual_label_img/manual_background_mask are the fast editable draft.
        self.committed_manual_label_img = None
        self.committed_manual_background_mask = None
        self.manual_changes_pending = False
        self.manual_undo = []
        self.manual_target = tk.StringVar(value="")
        self.manual_tool = tk.StringVar(value="Brush")
        self.manual_brush_size = tk.IntVar(value=1)
        self.manual_target_buttons = {}
        self.manual_bg_color = tk.StringVar(value=self.settings.get("manual_bg_color", "#d8d8d8"))
        self.manual_photo = None
        self.manual_scale = 1.0
        self.manual_offset = (0, 0)
        self.manual_zoom = 1.0
        self.manual_pan_x = 0.0
        self.manual_pan_y = 0.0
        self._manual_pan_start = None
        self._manual_painting = False
        self._manual_line_start = None
        self._manual_line_preview_id = None
        self.final_preview_dirty = True
        self.final_preview_busy = False

        self.project.trace_add("write", self._project_name_changed)
        self.update_auto_output_folder()
        self.build_ui()
        self.bind_auto_preview_updates()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.image_path.get() and Path(self.image_path.get()).exists():
            self.show_original_preview(Path(self.image_path.get()))

    def bind_auto_preview_updates(self):
        for var in [self.target_w, self.target_h, self.keep_aspect, self.deckel_w, self.deckel_h, self.deck_color]:
            try:
                var.trace_add("write", lambda *args: self.update_deck_preview())
            except Exception:
                pass

    def load_profiles(self):
        if PROFILES_FILE.exists():
            try:
                data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))

                # Migrate the three former German built-in names to English.
                for old_name, new_name in PROFILE_NAME_MIGRATION.items():
                    if old_name in data:
                        if new_name not in data:
                            data[new_name] = data[old_name]
                        data.pop(old_name, None)

                for profile in data.values():
                    if isinstance(profile, dict) and "edge_smoothing" in profile:
                        profile["edge_smoothing"] = EDGE_SMOOTHING_MIGRATION.get(
                            profile["edge_smoothing"], profile["edge_smoothing"]
                        )

                merged = dict(DEFAULT_PROFILES)
                merged.update(data)
                return merged
            except Exception:
                pass
        PROFILES_FILE.write_text(
            json.dumps(DEFAULT_PROFILES, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return dict(DEFAULT_PROFILES)

    def save_profiles(self):
        PROFILES_FILE.write_text(json.dumps(self.profiles, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def current_settings(self):
        return {
            "image_path": self.image_path.get(),
            "project": self.project.get(),
            "out_dir": self.out_dir.get(),
            "output_base_dir": str(self.output_base_dir) if self.output_base_dir else "",
            "profile_name": self.profile_name.get(),
            "target_w": self.target_w.get(),
            "target_h": self.target_h.get(),
            "keep_aspect": self.keep_aspect.get(),
            "detect_colors": self.detect_colors.get(),
            "height": self.height.get(),
            "cut": self.cut.get(),
            "clearance": self.clearance.get(),
            "background": self.background.get(),
            "contour_mode": self.contour_mode.get(),
            "white_threshold": self.white_threshold.get(),
            "working_pixels": self.working_pixels.get(),
            "smooth": self.smooth.get(),
            "edge_smoothing": self.edge_smoothing.get(),
            "geometry_pixels": self.geometry_pixels.get(),
            "min_area": self.min_area.get(),
            "auto_merge": self.auto_merge.get(),
            "merge_distance": self.merge_distance.get(),
            "deckel_w": self.deckel_w.get(),
            "deckel_h": self.deckel_h.get(),
            "deck_color": self.deck_color.get(),
            "manual_bg_color": self.manual_bg_color.get(),
        }

    def save_settings(self):
        SETTINGS_FILE.write_text(json.dumps(self.current_settings(), indent=2, ensure_ascii=False), encoding="utf-8")

    def on_close(self):
        self.save_settings()
        self.destroy()

    def build_ui(self):
        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, width=390)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        right = ttk.Frame(main)
        right.pack(side="right", fill="both", expand=True)

        self.build_left(left)
        self.build_right(right)

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status).pack(anchor="w")

    def build_left(self, parent):
        root = ttk.Frame(parent)
        root.pack(fill="both", expand=True)

        file_sec = CollapsibleFrame(root, "File & Export", expanded=True)
        file_sec.pack(fill="x", pady=(0, 6))
        file_box = file_sec.body
        row = ttk.Frame(file_box)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Select Image", command=self.choose_image, width=14).pack(side="left")
        ttk.Entry(row, textvariable=self.image_path).pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.row_entry(file_box, "Project Name", self.project, "Name used for the export files and the automatic *_STL output folder.", width=20)
        outrow = ttk.Frame(file_box)
        outrow.pack(fill="x", pady=2)
        ttk.Entry(outrow, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(outrow, text="Folder", command=self.choose_out, width=8).pack(side="right", padx=(5, 0))

        prof_sec = CollapsibleFrame(root, "Profile", expanded=True)
        prof_sec.pack(fill="x", pady=(0, 6))
        prof = prof_sec.body
        prow = ttk.Frame(prof)
        prow.pack(fill="x")
        self.profile_combo = ttk.Combobox(
            prow, textvariable=self.profile_name,
            values=list(self.profiles.keys()), state="readonly", width=18
        )
        self.profile_combo.pack(side="left", fill="x", expand=True)
        self.profile_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_profile())
        ttk.Button(prow, text="Apply", command=self.apply_profile, width=9).pack(side="left", padx=3)
        ttk.Button(prow, text="Save", command=self.save_profile_as, width=9).pack(side="left")

        std_sec = CollapsibleFrame(root, "Logo & Analysis", expanded=True)
        std_sec.pack(fill="x", pady=(0, 6))
        std = std_sec.body
        self.row_entry(std, "Logo Width (mm)", self.target_w, TIP["target"])
        self.row_entry(std, "Logo Height (mm)", self.target_h, TIP["target"])
        ttk.Checkbutton(std, text="Lock aspect ratio", variable=self.keep_aspect).pack(anchor="w")
        self.row_entry(std, "Colors to detect", self.detect_colors, TIP["colors"])
        brow = ttk.Frame(std)
        brow.pack(fill="x", pady=(6, 0))
        ttk.Button(brow, text="(Start) Analyze Colors", command=self.start_analyze).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(brow, text="(Finish) Generate STLs", command=self.start_generate).pack(side="left", fill="x", expand=True, padx=(3, 0))

        geo_sec = CollapsibleFrame(root, "Target Surface & Fit", expanded=True)
        geo_sec.pack(fill="x", pady=(0, 6))
        geo = geo_sec.body
        self.row_entry(geo, "Part Height (mm)", self.height, TIP["height"])
        self.row_entry(geo, "Cutout Depth (mm)", self.cut, TIP["cut"])
        self.row_entry(geo, "Clearance (mm)", self.clearance, TIP["clearance"])

        quality_sec = CollapsibleFrame(root, "Geometry Quality", expanded=True)
        quality_sec.pack(fill="x", pady=(0, 6))
        quality = quality_sec.body

        qrow = ttk.Frame(quality)
        qrow.pack(fill="x", pady=2)
        self.label_with_tip(
            qrow, "Edge smoothing",
            "Smooths color boundaries, the outer silhouette, and background edges before vectorization. "
            "Light ≈ 0.10 mm, Medium ≈ 0.22 mm, Strong ≈ 0.45 mm. "
            "The strength is defined in real millimeters and is independent of analysis resolution."
        ).pack(side="left")
        ttk.Combobox(
            qrow, textvariable=self.edge_smoothing,
            values=["Off", "Light", "Medium", "Strong"],
            state="readonly", width=10
        ).pack(side="right")

        self.row_entry(
            quality, "Geometry Resolution (px)", self.geometry_pixels,
            "Resolution used only for final geometry. Small source images are upscaled for vectorization "
            "without recalculating color assignments. 1600 is a good default; use 2400 for very fine logos."
        )

        self.row_entry(
            quality, "Contour Simplification (mm)", self.smooth,
            "Reduces the number of points in the final vector contour. "
            "Higher values make long edges cleaner but can alter fine details and tight curves. "
            "Typical range: 0.04 to 0.12 mm."
        )
        self.row_entry(quality, "Min. Island Area (mm²)", self.min_area, TIP["min_area"])

        crow = ttk.Frame(quality)
        crow.pack(fill="x", pady=2)
        self.label_with_tip(crow, "Contour Mode", TIP["contour"]).pack(side="left")
        contour_combo = ttk.Combobox(
            crow, textvariable=self.contour_display,
            values=list(CONTOUR_DISPLAY.keys()), state="readonly", width=20
        )
        contour_combo.pack(side="right")
        contour_combo.bind("<<ComboboxSelected>>", lambda e: self.contour_mode.set(CONTOUR_DISPLAY[self.contour_display.get()]))

        ttk.Button(
            quality, text="Apply Geometry — Keep Color Assignments",
            command=self.apply_geometry_settings
        ).pack(fill="x", pady=(7, 0))

        analysis_sec = CollapsibleFrame(root, "Color Analysis", expanded=False)
        analysis_sec.pack(fill="x", pady=(0, 6))
        adv = analysis_sec.body
        self.row_entry(
            adv, "Analysis Resolution (px)", self.working_pixels,
            "Internal raster resolution used for color analysis. Changing it requires a new analysis "
            "and resets grouping and manual corrections."
        )
        self.row_entry(adv, "White Threshold", self.white_threshold, "Brightness threshold above which near-white pixels can be treated as white background.")
        self.row_entry(adv, "Color Distance", self.merge_distance, "Higher values merge more similar detected shades into the same initial color group.")
        merge_cb = ttk.Checkbutton(adv, text="Group similar colors automatically", variable=self.auto_merge)
        merge_cb.pack(anchor="w")
        ToolTip(merge_cb, "Changes color analysis. Click (Start) Analyze Colors again to apply.")

        bgrow = ttk.Frame(adv)
        bgrow.pack(fill="x", pady=2)
        self.label_with_tip(bgrow, "Background", TIP["background"]).pack(side="left")
        bg_combo = ttk.Combobox(
            bgrow, textvariable=self.background_display,
            values=list(BACKGROUND_DISPLAY.keys()), state="readonly", width=30
        )
        bg_combo.pack(side="right")
        bg_combo.bind("<<ComboboxSelected>>", lambda e: self.background.set(BACKGROUND_DISPLAY[self.background_display.get()]))

        ttk.Label(
            adv,
            text="These settings change color detection. Click (Start) Analyze Colors to apply them.",
            wraplength=330
        ).pack(fill="x", pady=(6, 0))


    def build_right(self, parent):
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)

        self.tab_edit = ttk.Frame(self.notebook, padding=6)
        self.tab_manual = ttk.Frame(self.notebook, padding=6)
        self.tab_stl = ttk.Frame(self.notebook, padding=6)
        self.tab_deck = ttk.Frame(self.notebook, padding=6)

        self.notebook.add(self.tab_edit, text="Edit")
        self.notebook.add(self.tab_manual, text="Manual")
        self.notebook.add(self.tab_stl, text="STL Preview")
        self.notebook.add(self.tab_deck, text="Final Preview")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Quick Workflow can be collapsed to free vertical space on smaller displays.
        self.workflow_section = CollapsibleFrame(
            self.tab_edit, "Quick Workflow", expanded=True
        )
        self.workflow_section.pack(fill="x", pady=(0, 6))
        workflow_box = self.workflow_section.body

        workflow_steps = [
            "1. Start — Load your logo, then click (Start) Analyze Colors.",
            (
                "2. Group colors — Click Show next to a detected color, then assign it to a print "
                "group using the color buttons below. If a detected shade should be shared between "
                "neighboring print colors instead of becoming its own group, assign it to AUTO."
            ),
            (
                "3. Fine-tune — Open the Manual tab and click Calculate first to resolve all AUTO "
                "pixels. Make any pixel-level corrections you need, then click Calculate again to "
                "apply those edits to the other previews."
            ),
            (
                "4. Finish — Review the final geometry in STL Preview. When everything looks right, "
                "click (Finish) Generate STLs."
            ),
        ]

        self.workflow_labels = []
        for step_text in workflow_steps:
            lbl = ttk.Label(
                workflow_box,
                text=step_text,
                justify="left",
                anchor="w",
                wraplength=900,
            )
            lbl.pack(fill="x", anchor="w", pady=(0, 3))
            self.workflow_labels.append(lbl)

        def resize_workflow(event):
            width = max(240, int(event.width) - 24)
            for label in self.workflow_labels:
                label.configure(wraplength=width)

        workflow_box.bind("<Configure>", resize_workflow)

        # Movable vertical splitter: drag the divider to give more space either
        # to the logo preview or to the detected-color list.
        self.edit_paned = ttk.Panedwindow(self.tab_edit, orient="vertical")
        self.edit_paned.pack(fill="both", expand=True)

        preview_pane = ttk.Frame(self.edit_paned)
        colors_pane = ttk.Frame(self.edit_paned)
        self.edit_paned.add(preview_pane, weight=3)
        self.edit_paned.add(colors_pane, weight=2)

        preview_box = ttk.LabelFrame(
            preview_pane, text="Preview & Highlight", padding=8
        )
        preview_box.pack(fill="both", expand=True)
        self.preview = ttk.Label(preview_box, relief="groove", anchor="center")
        self.preview.pack(fill="both", expand=True)

        colors_box = ttk.LabelFrame(
            colors_pane, text="Select & Group Detected Colors", padding=8
        )
        colors_box.pack(fill="both", expand=True)

        header = ttk.Frame(colors_box)
        header.pack(fill="x", pady=(0, 5))
        self.group_status = tk.StringVar(value="No colors detected yet.")
        ttk.Label(header, textvariable=self.group_status).pack(side="left")

        self.quick_frame = ttk.Frame(colors_box)
        self.quick_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(self.quick_frame, text="Assign:").grid(row=0, column=0, padx=(0, 4))
        quick_defs = [
            ("schwarz", "#222222", ""),
            ("weiss", "#f5f5f5", ""),
            ("gelb", "#fbc02d", ""),
            ("gruen", "#388e3c", ""),
            ("blau", "#1976d2", ""),
            ("rot", "#d32f2f", ""),
            ("orange", "#f57c00", ""),
        ]
        for idx, (name, color, label) in enumerate(quick_defs, start=1):
            btn = tk.Button(
                self.quick_frame, text=label, bg=color,
                width=2, height=1, relief="raised",
                command=lambda n=name: self.assign_selected_to_named_group(n)
            )
            btn.grid(row=0, column=idx, padx=2)
            ToolTip(btn, display_group_name(name))
        ttk.Button(
            self.quick_frame, text="AUTO", width=6,
            command=lambda: self.assign_selected_to_named_group("auto verteilen")
        ).grid(row=0, column=8, padx=(6, 2))
        ttk.Button(
            self.quick_frame, text="BG", width=4,
            command=lambda: self.assign_selected_to_named_group("zu Hintergrund")
        ).grid(row=0, column=9, padx=2)
        ToolTip(
            self.quick_frame.winfo_children()[-2],
            "AUTO: assign transition pixels locally to the most plausible neighboring print color when Calculate is pressed."
        )
        ToolTip(
            self.quick_frame.winfo_children()[-1],
            "BG: remove this region from the logo and treat it as background / target-surface color."
        )

        color_wrap = ttk.Frame(colors_box)
        color_wrap.pack(fill="both", expand=True)

        # The color list now expands with the pane instead of using a fixed height.
        self.colors_canvas = tk.Canvas(
            color_wrap, highlightthickness=0, height=120
        )
        self.colors_scroll = ttk.Scrollbar(
            color_wrap, orient="vertical", command=self.colors_canvas.yview
        )
        self.colors_inner = ttk.Frame(self.colors_canvas)
        self.colors_inner.bind(
            "<Configure>",
            lambda e: self.colors_canvas.configure(
                scrollregion=self.colors_canvas.bbox("all")
            )
        )
        self.colors_window = self.colors_canvas.create_window(
            (0, 0), window=self.colors_inner, anchor="nw"
        )
        self.colors_canvas.configure(yscrollcommand=self.colors_scroll.set)
        self.colors_canvas.pack(side="left", fill="both", expand=True)
        self.colors_scroll.pack(side="right", fill="y")

        # Keep the inner frame as wide as the visible canvas.
        self.colors_canvas.bind(
            "<Configure>",
            lambda e: self.colors_canvas.itemconfigure(
                self.colors_window, width=e.width
            )
        )

        # Mouse wheel scrolling works whenever the pointer is over the color list
        # or one of its child widgets. The normal scrollbar still works as before.
        self._bind_color_mousewheel(self.colors_canvas)
        self._bind_color_mousewheel(self.colors_inner)

        # Manual editor
        toolbar = ttk.LabelFrame(self.tab_manual, text="Manual Corrections", padding=8)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Tool").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.manual_tool, values=["Brush", "Line", "Fill Area", "Eyedropper"], state="readonly", width=14).pack(side="left", padx=5)
        ttk.Label(toolbar, text="Brush (px)").pack(side="left", padx=(10, 0))
        ttk.Spinbox(toolbar, from_=1, to=80, textvariable=self.manual_brush_size, width=5).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Undo", command=self.manual_undo_once).pack(side="left", padx=(10, 3))
        ttk.Button(toolbar, text="Reset", command=self.manual_reset).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Calculate", command=self.calculate_manual_result).pack(side="left", padx=(10, 3))
        ttk.Button(toolbar, text="Reset Zoom", command=self.manual_zoom_reset).pack(side="left", padx=(3, 3))

        target_bar = ttk.Frame(self.tab_manual)
        target_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(target_bar, text="Target:").pack(side="left", padx=(0, 5))
        self.manual_target_buttons_frame = ttk.Frame(target_bar)
        self.manual_target_buttons_frame.pack(side="left", fill="x", expand=True)

        manual_view = ttk.Frame(self.tab_manual)
        manual_view.pack(fill="x", pady=(0, 6))
        ttk.Button(
            manual_view, text="Background Color", command=self.choose_manual_bg_color
        ).pack(side="left")
        self.manual_bg_swatch = tk.Canvas(
            manual_view, width=26, height=18, highlightthickness=1,
            highlightbackground="#777"
        )
        self.manual_bg_swatch.pack(side="left", padx=(5, 12))
        ttk.Label(
            manual_view,
            text="Edit first → then Calculate   |   Zoom: mouse wheel   |   Pan: middle mouse button"
        ).pack(side="left")
        self.manual_pending_text = tk.StringVar(value="")
        ttk.Label(manual_view, textvariable=self.manual_pending_text).pack(side="right")

        mbox = ttk.LabelFrame(self.tab_manual, text="Paint Directly on Color Assignment", padding=6)
        mbox.pack(fill="both", expand=True)
        self.manual_canvas = tk.Canvas(mbox, bg="#dddddd", highlightthickness=1, highlightbackground="#888")
        self.manual_canvas.pack(fill="both", expand=True)
        self.manual_canvas.bind("<Button-1>", self.manual_mouse_down)
        self.manual_canvas.bind("<B1-Motion>", self.manual_mouse_drag)
        self.manual_canvas.bind("<ButtonRelease-1>", self.manual_mouse_up)
        self.manual_canvas.bind("<MouseWheel>", self.manual_zoom_wheel)
        self.manual_canvas.bind("<Button-4>", self.manual_zoom_wheel)
        self.manual_canvas.bind("<Button-5>", self.manual_zoom_wheel)
        self.manual_canvas.bind("<ButtonPress-2>", self.manual_pan_start)
        self.manual_canvas.bind("<B2-Motion>", self.manual_pan_move)
        self.manual_canvas.bind("<ButtonRelease-2>", self.manual_pan_end)
        self.manual_canvas.bind("<Configure>", lambda e: self.update_manual_preview())

        # Exact STL preview
        self.stl_scroll = ScrollFrame(self.tab_stl)
        self.stl_scroll.pack(fill="both", expand=True)
        self.final_preview_status = tk.StringVar(value="STL Preview is generated from the final vector geometry.")
        ttk.Label(self.stl_scroll.inner, textvariable=self.final_preview_status).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=8)

        # Deck settings moved into deck tab
        deck_controls = ttk.LabelFrame(self.tab_deck, text="Target Surface", padding=8)
        deck_controls.pack(fill="x", pady=(0, 6))
        ttk.Label(deck_controls, text="Width (mm)").pack(side="left")
        ttk.Entry(deck_controls, textvariable=self.deckel_w, width=8).pack(side="left", padx=4)
        ttk.Label(deck_controls, text="Height (mm)").pack(side="left", padx=(10, 0))
        ttk.Entry(deck_controls, textvariable=self.deckel_h, width=8).pack(side="left", padx=4)
        ttk.Label(deck_controls, text="Color").pack(side="left", padx=(10, 0))
        ttk.Entry(deck_controls, textvariable=self.deck_color, width=10).pack(side="left", padx=4)
        ttk.Button(deck_controls, text="Choose Color", command=self.choose_deck_color).pack(side="left", padx=4)

        deck_box = ttk.LabelFrame(self.tab_deck, text="Logo on Target Surface", padding=8)
        deck_box.pack(fill="both", expand=True)
        self.deck_preview = ttk.Label(deck_box, relief="groove", anchor="center")
        self.deck_preview.pack(fill="both", expand=True)

    def label_with_tip(self, parent, text, tip):
        lbl = ttk.Label(parent, text=text)
        ToolTip(lbl, tip)
        return lbl

    def row_entry(self, parent, label, variable, tip, width=9):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        self.label_with_tip(row, label, tip).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=width).pack(side="right")
        return row

    def edge_smoothing_mm(self):
        return {
            "Off": 0.0,
            "Light": 0.10,
            "Medium": 0.22,
            "Strong": 0.45,
            # backward compatibility for older saved profiles
            "Aus": 0.0,
            "Leicht": 0.10,
            "Mittel": 0.22,
            "Stark": 0.45,
        }.get(self.edge_smoothing.get(), 0.22)

    def apply_geometry_settings(self):
        if not self.analysis:
            messagebox.showinfo("No Analysis", "Please click (Start) Analyze Colors first.")
            return
        self.mark_preview_dirty()
        self.status.set(
            f"Recalculating geometry: {self.edge_smoothing.get()} "
            f"({self.edge_smoothing_mm():.2f} mm), {int(self.geometry_pixels.get())} px. "
            "Color assignments are preserved."
        )
        self.save_settings()

        # Bearbeiten/Manuell zeigen absichtlich die Rasterzuordnung.
        # Die Geometrieänderung ist im STL-Tab sichtbar.
        self.notebook.select(self.tab_stl)
        self.after(50, lambda: self.start_final_preview(force=True))

    def sanitized_project_folder_name(self):
        name = str(self.project.get()).strip() or "Projekt"
        name = re.sub(r'[<>:"/\\|?*]+', "_", name)
        name = name.rstrip(" .") or "Projekt"
        return f"{name}_STL"

    def update_auto_output_folder(self):
        if not self._auto_output_folder or not self.output_base_dir:
            return
        self.out_dir.set(str(Path(self.output_base_dir) / self.sanitized_project_folder_name()))

    def _project_name_changed(self, *args):
        self.update_auto_output_folder()

    def choose_image(self):
        p = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")]
        )
        if not p:
            return
        path = Path(p)
        self.output_base_dir = path.parent
        self._auto_output_folder = True
        self.image_path.set(str(path))
        self.project.set(path.stem)
        self.update_auto_output_folder()
        self.show_original_preview(path)
        self.status.set("Image loaded. Click (Start) Analyze Colors to continue.")
        self.save_settings()

    def choose_out(self):
        initial = self.output_base_dir
        if not initial and self.out_dir.get().strip():
            try:
                initial = Path(self.out_dir.get()).parent
            except Exception:
                initial = None

        p = filedialog.askdirectory(
            title="Choose Base Folder for STL Output",
            initialdir=str(initial) if initial else None
        )
        if p:
            self.output_base_dir = Path(p)
            self._auto_output_folder = True
            self.update_auto_output_folder()
            try:
                Path(self.out_dir.get()).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self.save_settings()

    def choose_deck_color(self):
        color = colorchooser.askcolor(color=self.deck_color.get(), title="Choose Target Surface Color")
        if color and color[1]:
            self.deck_color.set(color[1])
            self.update_deck_preview()
            self.save_settings()

    def show_original_preview(self, path):
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((720, 450), Image.Resampling.LANCZOS)
            self.original_preview_photo = ImageTk.PhotoImage(img)
            self.preview.configure(image=self.original_preview_photo, text="")
        except Exception as e:
            self.preview.configure(text=str(e), image="")

    def make_checker(self, h, w):
        y, x = np.indices((h, w))
        checker = ((x // 16 + y // 16) % 2).astype(np.uint8)
        arr = np.where(checker[:, :, None] == 0, 210, 238).astype(np.uint8)
        return np.repeat(arr, 3, axis=2)

    def show_np_preview(self, arr):
        img = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
        img.thumbnail((720, 450), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview.configure(image=self.preview_photo, text="")

    def start_analyze(self):
        if not self.image_path.get():
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        self.status.set("Analyzing colors...")
        threading.Thread(target=self.analyze_worker, daemon=True).start()

    def analyze_worker(self):
        try:
            self.analysis = analyze_colors(
                Path(self.image_path.get()),
                working_pixels=int(self.working_pixels.get()),
                detect_colors=int(self.detect_colors.get()),
                background_mode=self.background.get(),
                white_threshold=int(self.white_threshold.get()),
                auto_merge=bool(self.auto_merge.get()),
                merge_distance=float(self.merge_distance.get()),
            )
            self.after(0, self.render_colors)
        except Exception as e:
            detail = traceback.format_exc()
            try:
                log_path = Path(self.out_dir.get()) / "logo_inlay_error.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(detail, encoding="utf-8")
            except Exception:
                pass
            self.after(0, lambda: messagebox.showerror("Color Analysis Error", f"{e}\n\nSee logo_inlay_error.log in the output folder for details."))
            self.after(0, lambda: self.status.set("Color analysis failed."))

    def group_preview_rgb(self, group_name, fallback_rgb=None):
        key = (group_name or "").strip().lower()
        base_key = re.sub(r"\s+\d+$", "", key)
        if key in GROUP_PREVIEW_COLORS:
            return GROUP_PREVIEW_COLORS[key]
        if base_key in GROUP_PREVIEW_COLORS:
            return GROUP_PREVIEW_COLORS[base_key]
        if fallback_rgb is not None:
            return fallback_rgb
        return [160, 160, 160]

    def _on_colors_mousewheel(self, event):
        if not hasattr(self, "colors_canvas"):
            return "break"

        # Windows/macOS use event.delta; X11 commonly uses Button-4/Button-5.
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        else:
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return "break"
            # Windows normally reports multiples of 120.
            steps = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)

        self.colors_canvas.yview_scroll(steps, "units")
        return "break"

    def _bind_color_mousewheel(self, widget):
        """Bind wheel scrolling to a widget without taking over the whole app."""
        try:
            widget.bind("<MouseWheel>", self._on_colors_mousewheel, add="+")
            widget.bind("<Button-4>", self._on_colors_mousewheel, add="+")
            widget.bind("<Button-5>", self._on_colors_mousewheel, add="+")
        except Exception:
            pass

    def render_colors(self):
        for child in self.colors_inner.winfo_children():
            child.destroy()
        self.color_rows = []
        self._highlighted = None

        raw_colors = self.analysis.get("colors", self.analysis.get("clusters", []))
        clusters = raw_colors

        name_counts = {}
        for idx, c in enumerate(clusters):
            rgb = [int(x) for x in c["rgb"]]
            name = better_color_name(rgb)
            cluster_id = c["cluster"]

            if self.auto_merge.get():
                default_group = name
            else:
                name_counts[name] = name_counts.get(name, 0) + 1
                default_group = f"{name} {name_counts[name]}"

            col = idx % 3
            row_num = idx // 3

            row = ttk.Frame(self.colors_inner)
            row.grid(row=row_num, column=col, sticky="w", padx=(0, 16), pady=2)

            enabled = tk.BooleanVar(value=True)
            group = tk.StringVar(value=default_group)
            group_label = tk.StringVar(value=f"→ {display_group_name(default_group)}")

            ttk.Button(row, text="Show", width=8, command=lambda cid=cluster_id: self.toggle_highlight(cid)).pack(side="left", padx=(0, 4))

            swatch = tk.Canvas(row, width=22, height=16, highlightthickness=1, highlightbackground="#777")
            swatch.create_rectangle(0, 0, 22, 16, fill="#%02x%02x%02x" % tuple(rgb), outline="")
            swatch.pack(side="left", padx=(0, 4))

            ttk.Checkbutton(row, variable=enabled).pack(side="left", padx=(0, 3))
            ttk.Label(row, text=display_group_name(name), width=10).pack(side="left")
            ttk.Label(row, textvariable=group_label, width=15).pack(side="left")

            def changed(*args, self=self, g=group, lbl=group_label):
                lbl.set(f"→ {display_group_name(g.get())}")
                self.mark_preview_dirty()
                self.update_group_preview()

            enabled.trace_add("write", changed)
            group.trace_add("write", changed)

            self._bind_color_mousewheel(row)
            for child in row.winfo_children():
                self._bind_color_mousewheel(child)

            self.color_rows.append({
                "cluster": cluster_id,
                "rgb": rgb,
                "enabled": enabled,
                "group": group,
                "group_label": group_label,
            })

        for c in range(3):
            self.colors_inner.columnconfigure(c, weight=1)

        self.manual_label_img = self.analysis["label_img"].copy()
        self.manual_background_mask = np.zeros_like(self.manual_label_img, dtype=bool)
        self.committed_manual_label_img = self.manual_label_img.copy()
        self.committed_manual_background_mask = self.manual_background_mask.copy()
        self.manual_changes_pending = False
        self.manual_undo.clear()
        self.set_manual_pending(False)
        self.manual_zoom = 1.0
        self.manual_pan_x = 0.0
        self.manual_pan_y = 0.0
        self.refresh_manual_targets()

        self.status.set("Colors detected. Assign groups, then use Manual for fine adjustments if needed.")
        self.update_group_status()
        self.update_group_preview()
        self.update_manual_preview()
        self.mark_preview_dirty()

    def assign_selected_to_named_group(self, group_name):
        selected = self._highlighted
        if selected is None:
            messagebox.showinfo("No Color Selected", "Click Show on a detected color first.")
            return

        if group_name == "zu Hintergrund":
            for row in self.color_rows:
                if row["cluster"] == selected:
                    row["enabled"].set(True)
                    row["group"].set("zu Hintergrund")
                    row["group_label"].set("Group: Background")
                    break
            self.refresh_manual_targets()
            self.mark_preview_dirty()
            self.update_group_preview()
            self.status.set("Selected color assigned to background.")
            return

        for row in self.color_rows:
            if row["cluster"] == selected:
                row["group"].set(group_name)
                row["enabled"].set(True)
                row["group_label"].set(f"Group: {display_group_name(group_name)}")
                break
        self.refresh_manual_targets()
        self.mark_preview_dirty()
        self.update_group_preview()
        self.status.set(f"Selected color assigned to group {display_group_name(group_name)}.")

    def toggle_highlight(self, cluster_id):
        if self._highlighted == cluster_id:
            self._highlighted = None
            self.update_group_preview()
            return
        self._highlighted = cluster_id
        self.highlight_cluster(cluster_id)

    def highlight_cluster(self, cluster_id):
        label_img = self.analysis["label_img"]
        rgba = self.analysis["rgba"]
        out = np.array(rgba[:, :, :3], dtype=np.uint8)
        mask = label_img == cluster_id
        out[mask] = np.array([0, 170, 255], dtype=np.uint8)
        out[~mask] = (out[~mask] * 0.35 + 220 * 0.65).astype(np.uint8)
        self.show_np_preview(out)

    def get_color_plan(self):
        plan = []
        for row in self.color_rows:
            group = row["group"].get().strip() or better_color_name(row["rgb"])
            plan.append({
                "cluster": row["cluster"],
                "rgb": row["rgb"],
                "enabled": bool(row["enabled"].get()),
                "group": group,
                "name": group,
            })
        return plan

    def active_groups_count(self):
        groups = set()
        for item in self.get_color_plan():
            if item["enabled"] and str(item["group"]).strip().lower() not in ("zu hintergrund", "auto verteilen"):
                groups.add(item["group"])
        return len(groups), sorted(groups)

    def update_group_status(self):
        if not self.color_rows:
            self.group_status.set("No colors detected yet.")
            return
        active_count = sum(1 for row in self.color_rows if row["enabled"].get())
        group_count, groups = self.active_groups_count()
        display_groups = [display_group_name(g) for g in groups]
        self.group_status.set(
            f"Detected colors: {len(self.color_rows)}   Active: {active_count}   "
            f"Groups: {group_count} ({', '.join(display_groups)})"
        )

    def update_group_preview(self):
        if not self.analysis:
            return

        label_img = self.get_effective_label_img()
        if label_img is None:
            return
        h, w = label_img.shape
        arr = self.make_checker(h, w)

        for item in self.get_color_plan():
            group = str(item.get("group", "")).strip()
            group_key = group.lower()
            if not item.get("enabled", True) or group_key == "zu hintergrund":
                continue

            if group_key == "auto verteilen":
                rgb = [150, 150, 150]
            else:
                rgb = self.group_preview_rgb(
                    group, item.get("rgb", [160, 160, 160])
                )
            arr[label_img == int(item["cluster"])] = np.asarray(rgb, dtype=np.uint8)

        committed_bg = self.get_effective_background_mask()
        if committed_bg is not None:
            checker = self.make_checker(h, w)
            arr[committed_bg] = checker[committed_bg]

        self.show_np_preview(arr)
        self.update_group_status()
        self.update_deck_preview()
        self.update_manual_preview()
        self.update_auto_status()
        self.mark_preview_dirty()

    def get_effective_label_img(self):
        """Return the committed edit state used by previews/STL export."""
        if self.committed_manual_label_img is not None:
            return self.committed_manual_label_img
        if self.analysis is not None:
            return self.analysis["label_img"]
        return None

    def get_effective_background_mask(self):
        if self.committed_manual_background_mask is not None:
            return self.committed_manual_background_mask
        if self.analysis is not None:
            return np.zeros_like(self.analysis["label_img"], dtype=bool)
        return None

    def set_manual_pending(self, pending=True):
        self.manual_changes_pending = bool(pending)
        if hasattr(self, "manual_pending_text"):
            self.manual_pending_text.set(
                "Changes not calculated yet"
                if self.manual_changes_pending else
                "Calculated"
            )

    def update_auto_status(self):
        # compatibility helper; status is now about the whole manual draft
        self.set_manual_pending(self.manual_changes_pending)

    def commit_manual_edit(self, refresh_other_tabs=False):
        """Keep the manual draft local until the user presses Calculate."""
        self.set_manual_pending(True)
        self.update_manual_preview()


    def set_manual_target(self, target):
        self.manual_target.set(str(target))
        self.update_manual_target_button_states()

    def update_manual_target_button_states(self):
        selected = self.manual_target.get().strip()
        for group, btn in getattr(self, "manual_target_buttons", {}).items():
            try:
                if group == selected:
                    btn.configure(relief=tk.SUNKEN, bd=3)
                else:
                    btn.configure(relief=tk.RAISED, bd=1)
            except Exception:
                pass

    def refresh_manual_targets(self):
        if not hasattr(self, "manual_target_buttons_frame"):
            return
        for child in self.manual_target_buttons_frame.winfo_children():
            child.destroy()
        self.manual_target_buttons = {}

        groups = []
        representative_rgb = {}
        for item in self.get_color_plan():
            if not item.get("enabled", True):
                continue
            group = str(item.get("group", "")).strip()
            key = group.lower()
            if not group or key in ("auto verteilen", "zu hintergrund"):
                continue
            if group not in groups:
                groups.append(group)
                representative_rgb[group] = self.group_preview_rgb(
                    group, item.get("rgb", [160, 160, 160])
                )

        for group in groups:
            rgb = representative_rgb[group]
            color = "#%02x%02x%02x" % tuple(int(v) for v in rgb)
            btn = tk.Button(
                self.manual_target_buttons_frame,
                text="",
                bg=color,
                activebackground=color,
                width=2,
                height=1,
                relief=tk.RAISED,
                bd=1,
                command=lambda g=group: self.set_manual_target(g),
            )
            btn.pack(side="left", padx=2)
            ToolTip(btn, f"Target: {display_group_name(group)}")
            self.manual_target_buttons[group] = btn

        auto_btn = tk.Button(
            self.manual_target_buttons_frame,
            text="AUTO",
            bg="#969696",
            activebackground="#aaaaaa",
            width=5,
            height=1,
            relief=tk.RAISED,
            bd=1,
            command=lambda: self.set_manual_target("auto verteilen"),
        )
        auto_btn.pack(side="left", padx=(8, 2))
        ToolTip(auto_btn, "AUTO: when Calculate is pressed, distribute these pixels to the most plausible neighboring print color.")
        self.manual_target_buttons["auto verteilen"] = auto_btn

        bg_rgb = self.manual_background_rgb()
        bg_hex = "#%02x%02x%02x" % tuple(int(v) for v in bg_rgb)
        bg_btn = tk.Button(
            self.manual_target_buttons_frame,
            text="BG",
            bg=bg_hex,
            activebackground=bg_hex,
            width=4,
            height=1,
            relief=tk.RAISED,
            bd=1,
            command=lambda: self.set_manual_target("zu Hintergrund"),
        )
        bg_btn.pack(side="left", padx=2)
        ToolTip(bg_btn, "BG: assign this region to the background.")
        self.manual_target_buttons["zu Hintergrund"] = bg_btn

        valid = groups + ["auto verteilen", "zu Hintergrund"]
        if self.manual_target.get() not in valid:
            self.manual_target.set(groups[0] if groups else "auto verteilen")
        self.update_manual_target_button_states()

    def cluster_for_group(self, group_name):
        target = str(group_name).strip()
        for item in self.get_color_plan():
            if item["enabled"] and str(item["group"]).strip() == target:
                return int(item["cluster"])
        return None

    def save_manual_undo(self):
        if self.manual_label_img is None:
            return
        self.manual_undo.append((
            self.manual_label_img.copy(),
            self.manual_background_mask.copy() if self.manual_background_mask is not None else None
        ))
        self.manual_undo = self.manual_undo[-6:]

    def manual_undo_once(self):
        if not self.manual_undo:
            return
        labels, bg = self.manual_undo.pop()
        self.manual_label_img = labels
        self.manual_background_mask = bg
        self.set_manual_pending(True)
        self.update_manual_preview()

    def manual_reset(self):
        if not self.analysis:
            return
        self.save_manual_undo()

        # Reset the local draft to the last CALCULATED result, not to raw analysis.
        if self.committed_manual_label_img is not None:
            self.manual_label_img = self.committed_manual_label_img.copy()
        else:
            self.manual_label_img = self.analysis["label_img"].copy()

        if self.committed_manual_background_mask is not None:
            self.manual_background_mask = (
                self.committed_manual_background_mask.copy()
            )
        else:
            self.manual_background_mask = np.zeros_like(
                self.manual_label_img, dtype=bool
            )

        self.set_manual_pending(False)
        self.update_manual_preview()

    def calculate_manual_result(self):
        """Process the complete manual draft and publish it to the whole app.

        Until this button is pressed, Brush/Line/Fill/Undo/Reset remain local
        to the Manual tab. On press:
          1. all current manual edits are taken,
          2. all AUTO pixels are resolved,
          3. the resolved result replaces the manual draft,
          4. the same result becomes the committed state for every other tab
             and for STL export.
        """
        if self.manual_label_img is None:
            return False

        self.status.set("Calculating manual edits and AUTO regions…")

        try:
            draft = self.manual_label_img.copy()
            plan = self.get_color_plan()

            if np.any(draft == MANUAL_AUTO_LABEL):
                plan = list(plan) + [{
                    "cluster": MANUAL_AUTO_LABEL,
                    "rgb": [150, 150, 150],
                    "enabled": True,
                    "group": "auto verteilen",
                    "name": "auto verteilen",
                }]

            # Resolve AUTO only once, at calculation time.
            resolved, _ = redistribute_auto_groups(draft, plan)

            auto_ids = {
                int(item["cluster"])
                for item in plan
                if item.get("enabled", True)
                and str(item.get("group", "")).strip().lower() == "auto verteilen"
            }
            if auto_ids and np.any(np.isin(resolved, list(auto_ids))):
                raise ValueError(
                    "AUTO could not be fully resolved. Make sure at least one normal "
                    "print-color group is active next to the AUTO regions."
                )

            # The Manual tab must also display/use the calculated result afterwards.
            self.manual_label_img = resolved.copy()
            self.committed_manual_label_img = resolved.copy()

            if self.manual_background_mask is not None:
                self.committed_manual_background_mask = (
                    self.manual_background_mask.copy()
                )
            else:
                self.committed_manual_background_mask = None

            self.set_manual_pending(False)
            self.mark_preview_dirty()

            # Update all dependent views only now.
            self.update_manual_preview()
            self.update_group_preview()
            self.update_deck_preview()

            self.status.set(
                "Calculation complete. Manual edits and AUTO assignments were applied "
                "to all previews."
            )

            try:
                if self.notebook.tab(self.notebook.select(), "text") == "STL Preview":
                    self.start_final_preview(force=True)
            except Exception:
                pass

            return True

        except Exception as e:
            messagebox.showerror("Calculate", str(e))
            self.status.set("Calculation failed.")
            return False

    def manual_source_xy(self, event):
        if self.manual_label_img is None:
            return None
        ox, oy = self.manual_offset
        if self.manual_scale <= 0:
            return None
        x = int((event.x - ox) / self.manual_scale)
        y = int((event.y - oy) / self.manual_scale)
        h, w = self.manual_label_img.shape
        if 0 <= x < w and 0 <= y < h:
            return x, y
        return None

    def manual_mouse_down(self, event):
        if self.manual_label_img is None:
            return
        tool = self.manual_tool.get()
        pos = self.manual_source_xy(event)
        if pos is None:
            return

        if tool == "Eyedropper":
            self.manual_pick(pos)
            return

        self.save_manual_undo()

        if tool == "Line":
            self._manual_line_start = pos
            self._manual_painting = False
            self.manual_update_line_preview(pos)
            return

        self._manual_painting = True
        if tool == "Fill Area":
            self.manual_fill(pos)
            self._manual_painting = False
            self.commit_manual_edit(refresh_other_tabs=False)
        else:
            self.manual_paint(pos)

    def manual_mouse_drag(self, event):
        tool = self.manual_tool.get()

        if tool == "Line" and self._manual_line_start is not None:
            pos = self.manual_source_xy(event)
            if pos is not None:
                self.manual_update_line_preview(pos)
            return

        if self._manual_painting and tool == "Brush":
            pos = self.manual_source_xy(event)
            if pos is not None:
                self.manual_paint(pos, refresh=False)
                self.update_manual_preview()

    def manual_mouse_up(self, event):
        tool = self.manual_tool.get()

        if tool == "Line" and self._manual_line_start is not None:
            end_pos = self.manual_source_xy(event)
            if end_pos is not None:
                self.manual_draw_line(self._manual_line_start, end_pos)
            self._manual_line_start = None
            self.manual_clear_line_preview()
            self.update_manual_preview()
            self.commit_manual_edit(refresh_other_tabs=False)
            return

        if self._manual_painting:
            self._manual_painting = False
            self.update_manual_preview()
            self.commit_manual_edit(refresh_other_tabs=False)

    def manual_target_preview_rgb(self):
        target = self.manual_target.get().strip()
        if target == "zu Hintergrund":
            return self.manual_background_rgb()
        if target == "auto verteilen":
            return (150, 150, 150)
        for item in self.get_color_plan():
            if (
                item.get("enabled", True)
                and str(item.get("group", "")).strip() == target
            ):
                return tuple(self.group_preview_rgb(target, item.get("rgb")))
        return (120, 120, 120)

    def manual_canvas_xy(self, pos):
        x, y = pos
        ox, oy = self.manual_offset
        return (
            ox + (x + 0.5) * self.manual_scale,
            oy + (y + 0.5) * self.manual_scale,
        )

    def manual_clear_line_preview(self):
        if (
            self._manual_line_preview_id is not None
            and hasattr(self, "manual_canvas")
        ):
            try:
                self.manual_canvas.delete(self._manual_line_preview_id)
            except Exception:
                pass
        self._manual_line_preview_id = None

    def manual_update_line_preview(self, end_pos):
        if self._manual_line_start is None:
            return
        self.manual_clear_line_preview()
        x1, y1 = self.manual_canvas_xy(self._manual_line_start)
        x2, y2 = self.manual_canvas_xy(end_pos)
        rgb = self.manual_target_preview_rgb()
        color = "#%02x%02x%02x" % tuple(int(v) for v in rgb)
        px = max(1, int(self.manual_brush_size.get()))
        display_width = max(1, int(round(px * self.manual_scale)))
        self._manual_line_preview_id = self.manual_canvas.create_line(
            x1, y1, x2, y2,
            fill=color,
            width=display_width,
            capstyle=tk.ROUND,
        )

    def manual_draw_line(self, start_pos, end_pos):
        import cv2
        x1, y1 = start_pos
        x2, y2 = end_pos
        size = max(1, int(self.manual_brush_size.get()))
        mask = np.zeros(self.manual_label_img.shape, dtype=np.uint8)

        # LINE_8 with thickness 1 gives a true one-pixel raster line.
        cv2.line(
            mask,
            (x1, y1),
            (x2, y2),
            1,
            thickness=size,
            lineType=cv2.LINE_8,
        )
        self.manual_apply_mask(mask.astype(bool))
        self.update_auto_status()

    def manual_apply_mask(self, mask):
        if self.manual_label_img is None:
            return
        target = self.manual_target.get().strip()
        if not target:
            return
        if target == "zu Hintergrund":
            self.manual_background_mask[mask] = True
            return
        if target == "auto verteilen":
            self.manual_label_img[mask] = MANUAL_AUTO_LABEL
            self.manual_background_mask[mask] = False
            return
        cluster = self.cluster_for_group(target)
        if cluster is None:
            return
        self.manual_label_img[mask] = cluster
        self.manual_background_mask[mask] = False

    def manual_paint(self, pos, refresh=True):
        import cv2
        x, y = pos
        size = max(1, int(self.manual_brush_size.get()))
        mask = np.zeros(self.manual_label_img.shape, dtype=np.uint8)

        # Pinselgröße bedeutet jetzt ungefähr Durchmesser in Quellpixeln.
        # Größe 1 ist bewusst GENAU ein einzelnes Pixel.
        if size == 1:
            mask[y, x] = 1
        else:
            radius = max(1, int(round(size / 2.0)))
            cv2.circle(mask, (x, y), radius, 1, -1)

        self.manual_apply_mask(mask.astype(bool))
        if refresh:
            self.update_manual_preview()

    def manual_fill(self, pos):
        import cv2
        x, y = pos
        source_label = int(self.manual_label_img[y, x])
        source_bg = bool(self.manual_background_mask[y, x])

        if source_bg:
            source_mask = self.manual_background_mask.astype(np.uint8)
        else:
            source_mask = ((self.manual_label_img == source_label) & (~self.manual_background_mask)).astype(np.uint8)

        num, labels = cv2.connectedComponents(source_mask, 8)
        component = int(labels[y, x])
        if component <= 0:
            return
        mask = labels == component
        self.manual_apply_mask(mask)
        self.update_manual_preview()

    def manual_pick(self, pos):
        x, y = pos
        if self.manual_background_mask[y, x]:
            self.set_manual_target("zu Hintergrund")
            return
        cluster = int(self.manual_label_img[y, x])
        if cluster == MANUAL_AUTO_LABEL:
            self.set_manual_target("auto verteilen")
            return
        for item in self.get_color_plan():
            if int(item["cluster"]) == cluster:
                self.set_manual_target(str(item["group"]))
                return

    def manual_preview_array(self):
        """Fast draft preview.

        Important: no AUTO redistribution and no vector processing here.
        This keeps painting responsive. Expensive processing happens only after
        'Calculate'.
        """
        labels = self.manual_label_img
        if labels is None:
            return None

        h, w = labels.shape
        bg_rgb = np.asarray(self.manual_background_rgb(), dtype=np.uint8)
        arr = np.empty((h, w, 3), dtype=np.uint8)
        arr[:, :] = bg_rgb

        plan = self.get_color_plan()
        for item in plan:
            group = str(item.get("group", "")).strip()
            if not item.get("enabled", True):
                continue
            if group.lower() == "zu hintergrund":
                continue

            cluster = int(item["cluster"])
            # AUTO is intentionally neutral in the draft; final color assignment
            # is calculated once when changes are committed.
            if group.lower() == "auto verteilen":
                rgb = [150, 150, 150]
            else:
                rgb = self.group_preview_rgb(
                    group, item.get("rgb", [160, 160, 160])
                )
            arr[labels == cluster] = np.asarray(rgb, dtype=np.uint8)

        arr[labels == MANUAL_AUTO_LABEL] = np.asarray([150, 150, 150], dtype=np.uint8)

        if self.manual_background_mask is not None:
            arr[self.manual_background_mask] = bg_rgb

        return arr

    def manual_background_rgb(self):
        return self.parse_hex_color(self.manual_bg_color.get(), fallback=(216, 216, 216))

    def choose_manual_bg_color(self):
        color = colorchooser.askcolor(
            color=self.manual_bg_color.get(), title="Manual Background Color"
        )
        if color and color[1]:
            self.manual_bg_color.set(color[1])
            self.save_settings()
            self.refresh_manual_targets()
            self.update_manual_preview()

    def update_manual_bg_swatch(self):
        if not hasattr(self, "manual_bg_swatch"):
            return
        self.manual_bg_swatch.delete("all")
        self.manual_bg_swatch.create_rectangle(
            0, 0, 26, 18, fill=self.manual_bg_color.get(), outline=""
        )

    def manual_zoom_reset(self):
        self.manual_zoom = 1.0
        self.manual_pan_x = 0.0
        self.manual_pan_y = 0.0
        self.update_manual_preview()

    def manual_zoom_wheel(self, event):
        if self.manual_label_img is None:
            return
        old_scale = self.manual_scale
        if getattr(event, "delta", 0) > 0 or getattr(event, "num", None) == 4:
            factor = 1.25
        else:
            factor = 0.8
        self.manual_zoom = max(1.0, min(12.0, self.manual_zoom * factor))
        self.update_manual_preview()

    def manual_pan_start(self, event):
        self._manual_pan_start = (event.x, event.y, self.manual_pan_x, self.manual_pan_y)

    def manual_pan_move(self, event):
        if not self._manual_pan_start:
            return
        sx, sy, px, py = self._manual_pan_start
        self.manual_pan_x = px + (event.x - sx)
        self.manual_pan_y = py + (event.y - sy)
        self.update_manual_preview()

    def manual_pan_end(self, event):
        self._manual_pan_start = None

    def update_manual_preview(self):
        if not hasattr(self, "manual_canvas"):
            return
        self.update_manual_bg_swatch()
        arr = self.manual_preview_array()
        if arr is None:
            self.manual_canvas.delete("all")
            self.manual_canvas.create_text(20, 20, anchor="nw", text="Analyze colors first.")
            return

        cw = max(200, self.manual_canvas.winfo_width())
        ch = max(200, self.manual_canvas.winfo_height())
        h, w = arr.shape[:2]

        fit_scale = min((cw - 20) / w, (ch - 20) / h)
        fit_scale = max(0.05, fit_scale)
        scale = fit_scale * self.manual_zoom

        out = Image.fromarray(arr).resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.NEAREST
        )
        self.manual_photo = ImageTk.PhotoImage(out)

        ox = (cw - out.width) // 2 + int(self.manual_pan_x)
        oy = (ch - out.height) // 2 + int(self.manual_pan_y)
        self.manual_scale = scale
        self.manual_offset = (ox, oy)

        self.manual_canvas.delete("all")
        self.manual_canvas.create_image(ox, oy, anchor="nw", image=self.manual_photo)

    def mark_preview_dirty(self):
        self.final_preview_dirty = True

    def on_tab_changed(self, event=None):
        try:
            tab_text = self.notebook.tab(self.notebook.select(), "text")
        except Exception:
            return
        if tab_text == "STL Preview":
            self.start_final_preview()
        elif tab_text == "Manual":
            self.refresh_manual_targets()
            self.update_manual_preview()
        elif tab_text == "Final Preview":
            self.update_deck_preview()

    def start_final_preview(self, force=False):
        if not self.analysis or self.final_preview_busy:
            return
        if self.manual_changes_pending:
            self.final_preview_status.set(
                "Manual contains changes that have not been calculated yet. "
                "Open Manual and click Calculate first."
            )
            return
        if not self.final_preview_dirty and not force:
            return
        self.final_preview_busy = True
        self.final_preview_status.set("Calculating final vector geometry…")
        threading.Thread(target=self.final_preview_worker, daemon=True).start()

    def final_preview_worker(self):
        try:
            color_map = {}
            for item in self.get_color_plan():
                g = str(item["group"]).strip()
                safe = re.sub(r'[^A-Za-z0-9._-]+', '_', g).strip('_') or 'group'
                color_map[safe] = self.group_preview_rgb(g, item["rgb"])

            data = build_partition_preview(
                image_path=Path(self.image_path.get()),
                color_plan=self.get_color_plan(),
                manual_width_mm=float(self.target_w.get()),
                manual_height_mm=float(self.target_h.get()),
                keep_aspect=bool(self.keep_aspect.get()),
                detect_colors=int(self.detect_colors.get()),
                background_mode=self.background.get(),
                white_threshold=int(self.white_threshold.get()),
                working_pixels=int(self.working_pixels.get()),
                geometry_pixels=int(self.geometry_pixels.get()),
                min_area_mm2=float(self.min_area.get()),
                simplify_mm=float(self.smooth.get()),
                close_strength=0,
                auto_merge=bool(self.auto_merge.get()),
                merge_distance=float(self.merge_distance.get()),
                contour_mode=self.contour_mode.get(),
                edge_smoothing_mm=self.edge_smoothing_mm(),
                label_override=self.get_effective_label_img(),
                manual_background_mask=self.get_effective_background_mask(),
                group_colors=color_map,
            )
            data["_ui_geometry_settings"] = {
                "smoothing_name": self.edge_smoothing.get(),
                "smoothing_mm": self.edge_smoothing_mm(),
                "geometry_pixels": int(self.geometry_pixels.get()),
                "simplify_mm": float(self.smooth.get()),
                "contour_mode": self.contour_display.get(),
            }
            self.after(0, lambda d=data: self.render_final_preview(d))
        except Exception as e:
            detail = traceback.format_exc()
            self.after(0, lambda: self.final_preview_status.set(f"Preview error: {e}"))
        finally:
            self.after(0, self.finish_final_preview)

    def finish_final_preview(self):
        self.final_preview_busy = False

    def render_final_preview(self, data):
        for child in self.stl_scroll.inner.winfo_children():
            child.destroy()

        rgba = data["rgba"]
        settings = data.get("_ui_geometry_settings", {})
        title = (
            "Final Geometry — "
            f"{settings.get('smoothing_name', '?')} / "
            f"{settings.get('smoothing_mm', 0):.2f} mm / "
            f"{settings.get('geometry_pixels', '?')} px"
        )
        total = ttk.LabelFrame(self.stl_scroll.inner, text=title, padding=8)
        total.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=6)

        # Checker background for transparency
        h, w = rgba.shape[:2]
        checker = self.make_checker(h, w)
        comp = checker.copy()
        alpha = rgba[:, :, 3] > 0
        comp[alpha] = rgba[alpha, :3]
        missing = float(data.get("missing_area_mm2", 0.0))
        overlap = float(data.get("overlap_area_mm2", 0.0))
        if missing < 1e-6 and overlap < 1e-6:
            partition_status = "Integrity check: OK — no missing area and no overlap."
        else:
            partition_status = f"Integrity check: missing {missing:.6f} mm² | overlap {overlap:.6f} mm²"

        self.add_preview_card(
            total,
            comp,
            "This preview uses the same vector partition as the STL export.\n"
            + partition_status,
            max_size=(520, 340)
        )

        fill_card = ttk.LabelFrame(self.stl_scroll.inner, text="Integrity Check — All Colors as One Body", padding=8)
        fill_card.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        fill_img = self.make_checker(h, w)
        fill_img[data["total_mask"]] = np.asarray([60, 150, 80], dtype=np.uint8)
        self.add_preview_card(
            fill_card,
            fill_img,
            "All active color regions are intentionally shown as one solid color here. "
            "Only true background should remain transparent / checkerboard."
        )

        group_masks = data["group_masks"]
        total_pixels = max(1, sum(int(np.sum(m)) for m in group_masks.values()))
        for idx, (group, mask) in enumerate(group_masks.items()):
            arr = self.make_checker(h, w)
            rgb = None
            for item in self.get_color_plan():
                safe = re.sub(r'[^A-Za-z0-9._-]+', '_', str(item["group"])).strip('_') or 'group'
                if safe == group:
                    rgb = self.group_preview_rgb(str(item["group"]), item["rgb"])
                    break
            if rgb is None:
                rgb = [160, 160, 160]
            arr[mask] = np.asarray(rgb, dtype=np.uint8)
            percent = round(100 * int(np.sum(mask)) / total_pixels, 1)
            islands = self.count_islands(mask)
            card = ttk.LabelFrame(self.stl_scroll.inner, text=f"Group: {display_group_name(group)}", padding=8)
            card.grid(row=2 + idx // 2, column=idx % 2, sticky="nsew", padx=8, pady=6)
            self.add_preview_card(card, arr, f"Area: {percent} %\nIslands: {islands}")

        self.stl_scroll.inner.columnconfigure(0, weight=1)
        self.stl_scroll.inner.columnconfigure(1, weight=1)
        self.final_preview_dirty = False
        self.final_preview_status.set("Final geometry preview is up to date.")

    def count_islands(self, mask):
        try:
            import cv2
            count, _ = cv2.connectedComponents(mask.astype(np.uint8), 8)
            return max(0, int(count) - 1)
        except Exception:
            return 0

    def add_preview_card(self, parent, arr, text, max_size=(260, 170)):
        img = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        lbl = ttk.Label(parent, image=photo)
        lbl.image = photo
        lbl.pack(side="left", padx=(0, 10))
        ttk.Label(parent, text=text, wraplength=420, justify="left").pack(side="left", anchor="n")

    def parse_hex_color(self, value, fallback=(252, 252, 252)):
        try:
            text = value.strip().lstrip("#")
            return tuple(int(text[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            return fallback

    def logo_array_on_background(self, label_img, background_rgb):
        """Create deck preview. Unresolved AUTO remains grey until calculated."""
        h, w = label_img.shape
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        arr[:, :] = np.asarray(background_rgb, dtype=np.uint8)

        for item in self.get_color_plan():
            group = str(item.get("group", "")).strip()
            key = group.lower()
            if not item.get("enabled", True) or key == "zu hintergrund":
                continue

            if key == "auto verteilen":
                rgb = [150, 150, 150]
            else:
                rgb = self.group_preview_rgb(
                    group, item.get("rgb", [160, 160, 160])
                )
            arr[label_img == int(item["cluster"])] = np.asarray(rgb, dtype=np.uint8)

        committed_bg = self.get_effective_background_mask()
        if committed_bg is not None:
            arr[committed_bg] = np.asarray(background_rgb, dtype=np.uint8)
        return arr

    def update_deck_preview(self):
        if not self.analysis:
            return
        label_img = self.get_effective_label_img()
        h, w = label_img.shape

        deck_rgb = self.parse_hex_color(self.deck_color.get())
        logo = self.logo_array_on_background(label_img, deck_rgb)

        canvas_w, canvas_h = 760, 480
        deck_w = max(1.0, float(self.deckel_w.get()))
        deck_h = max(1.0, float(self.deckel_h.get()))
        scale = min((canvas_w - 80) / deck_w, (canvas_h - 80) / deck_h)
        dw, dh = int(deck_w * scale), int(deck_h * scale)

        bg = np.ones((canvas_h, canvas_w, 3), dtype=np.uint8) * 238
        x0, y0 = (canvas_w - dw)//2, (canvas_h - dh)//2
        bg[y0:y0+dh, x0:x0+dw] = np.array(deck_rgb, dtype=np.uint8)
        bg[y0:y0+2, x0:x0+dw] = 80
        bg[y0+dh-2:y0+dh, x0:x0+dw] = 80
        bg[y0:y0+dh, x0:x0+2] = 80
        bg[y0:y0+dh, x0+dw-2:x0+dw] = 80

        target_w = float(self.target_w.get())
        target_h = float(self.target_h.get())
        if self.keep_aspect.get():
            target_h = target_w / (w / max(1, h))

        lw, lh = max(1, int(target_w * scale)), max(1, int(target_h * scale))
        logo_img = Image.fromarray(logo).convert("RGBA")
        if self.keep_aspect.get():
            logo_img.thumbnail((lw, lh), Image.Resampling.LANCZOS)
        else:
            logo_img = logo_img.resize((lw, lh), Image.Resampling.LANCZOS)

        bg_img = Image.fromarray(bg).convert("RGBA")
        lx = x0 + (dw - logo_img.size[0]) // 2
        ly = y0 + (dh - logo_img.size[1]) // 2
        bg_img.alpha_composite(logo_img, (lx, ly))

        self.deckel_photo = ImageTk.PhotoImage(bg_img)
        self.deck_preview.configure(image=self.deckel_photo, text="")

    def start_generate(self):
        if not self.analysis:
            messagebox.showwarning("No Analysis", "Please click (Start) Analyze Colors first.")
            return
        if self.manual_changes_pending:
            ok = messagebox.askyesno(
                "Manual Changes Not Calculated",
                "Manual contains changes that have not been calculated yet.\n\n"
                "Calculate them now and then generate the STLs?"
            )
            if not ok:
                return
            if not self.calculate_manual_result():
                return

        group_count, groups = self.active_groups_count()
        if group_count > 4:
            ok = messagebox.askyesno(
                "Many Color Groups",
                f"You created {group_count} active print groups:\n{', '.join(display_group_name(g) for g in groups)}\n\n"
                "A typical AMS handles up to 4 colors at once. Export anyway?"
            )
            if not ok:
                return
        self.status.set("Generating STLs...")
        threading.Thread(target=self.generate_worker, daemon=True).start()

    def generate_worker(self):
        try:
            meta = generate_logo_stls(
                image_path=Path(self.image_path.get()),
                out_dir=Path(self.out_dir.get()),
                project_name=self.project.get(),
                color_plan=self.get_color_plan(),
                target_mode="manual",
                manual_width_mm=float(self.target_w.get()),
                manual_height_mm=float(self.target_h.get()),
                keep_aspect=bool(self.keep_aspect.get()),
                deck_width_mm=float(self.deckel_w.get()),
                deck_height_mm=float(self.deckel_h.get()),
                margin_mm=0.0,
                fit_percent=100.0,
                height_mm=float(self.height.get()),
                cut_depth_mm=float(self.cut.get()),
                clearance_mm=float(self.clearance.get()),
                detect_colors=int(self.detect_colors.get()),
                background_mode=self.background.get(),
                white_threshold=int(self.white_threshold.get()),
                working_pixels=int(self.working_pixels.get()),
                geometry_pixels=int(self.geometry_pixels.get()),
                min_area_mm2=float(self.min_area.get()),
                simplify_mm=float(self.smooth.get()),
                close_strength=0,
                auto_merge=bool(self.auto_merge.get()),
                merge_distance=float(self.merge_distance.get()),
                contour_mode=self.contour_mode.get(),
                edge_smoothing_mm=self.edge_smoothing_mm(),
                center_output=True,
                label_override=self.get_effective_label_img(),
                manual_background_mask=self.get_effective_background_mask(),
            )
            files = meta.get("files", []) if isinstance(meta, dict) else []
            warnings = meta.get("manifold_warnings", []) if isinstance(meta, dict) else []

            if warnings:
                def show_success_with_warning():
                    self.status.set(
                        f"Done. {len(files)} files created — "
                        f"{len(warnings)} may need slicer repair."
                    )
                    details = "\n".join(
                        f"• {w.get('file', '?')}: "
                        f"{w.get('bad_edges', 0)} problematic edges "
                        f"({w.get('boundary_edges', 0)} open)"
                        for w in warnings
                    )
                    messagebox.showwarning(
                        "Export Complete — Repair May Be Needed",
                        f"All files were created:\n{self.out_dir.get()}\n\n"
                        "The following STL files still contain topology warnings:\n\n"
                        f"{details}\n\n"
                        "If your slicer offers a repair function, you can use it as before."
                    )
                self.after(0, show_success_with_warning)
            else:
                self.after(0, lambda: self.status.set(
                    f"Done. {len(files)} files created without manifold warnings."
                ))
                self.after(0, lambda: messagebox.showinfo(
                    "Done", f"Export complete:\n{self.out_dir.get()}"
                ))
        except Exception as e:
            detail = traceback.format_exc()
            try:
                log_path = Path(self.out_dir.get()) / "logo_inlay_error.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(detail, encoding="utf-8")
            except Exception:
                pass
            self.after(0, lambda: messagebox.showerror("Export Error", f"{e}\n\nSee logo_inlay_error.log in the output folder for details."))
            self.after(0, lambda: self.status.set("Export failed."))

    def apply_profile(self):
        data = self.profiles.get(self.profile_name.get())
        if not data:
            return
        for key, value in data.items():
            if hasattr(self, key):
                var = getattr(self, key)
                try:
                    var.set(value)
                except Exception:
                    pass
        self.edge_smoothing.set(
            EDGE_SMOOTHING_MIGRATION.get(self.edge_smoothing.get(), self.edge_smoothing.get())
        )
        self.background_display.set(BACKGROUND_INTERNAL.get(self.background.get(), "Transparent background"))
        self.contour_display.set(CONTOUR_INTERNAL.get(self.contour_mode.get(), "Straight / crisp"))
        self.status.set(f"Profile applied: {self.profile_name.get()}")
        self.save_settings()

    def save_profile_as(self):
        name = simpledialog.askstring("Save Profile", "Name for the new profile:")
        if not name:
            return
        data = self.current_settings()
        for remove_key in ["image_path", "out_dir", "project", "profile_name"]:
            data.pop(remove_key, None)
        self.profiles[name] = data
        self.save_profiles()
        self.profile_combo["values"] = list(self.profiles.keys())
        self.profile_name.set(name)
        self.status.set(f"Profile saved: {name}")

if __name__ == "__main__":
    App().mainloop()
