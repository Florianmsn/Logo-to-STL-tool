# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

The tool detects colors, lets you group and manually correct them, previews the final STL geometry, and exports one STL per print color together with matching cutout / clearance geometry.

## Current Version

**v7.7**

## Features

- Load PNG, JPG, JPEG, WEBP, and BMP logos
- Automatic color detection and grouping
- Assign detected shades to print colors
- `AUTO` mode for anti-aliased / transitional pixels
- `BG` mode for true background regions
- Manual pixel-level editor:
  - Brush
  - Line
  - Fill Area
  - Eyedropper
  - Undo
  - Reset
- Zoom and pan in the manual editor
- Adjustable geometry resolution and contour smoothing
- STL geometry preview before export
- Integrity preview for the complete color partition
- Separate STL export for each print color
- Complete cutout STL
- Negative / clearance STL
- Automatic project-specific output folder
- English UI and output filenames

## V7.7 Geometry Improvement

V7.7 changes how microscopic gaps created during contour simplification are assigned.

Earlier versions kept the color STLs gap-free by assigning the complete vectorization remainder to the globally largest color. On some logos this could create thin wrong-color lines or many tiny islands around letters and detailed boundaries.

V7.7 now:

1. vectorizes every active color individually,
2. resolves overlaps while preserving smaller detail groups,
3. identifies only the true leftover vectorization gaps,
4. assigns each leftover region to a **locally adjacent / locally matching color**,
5. keeps the complete partition gap-free and non-overlapping.

This significantly reduces incorrect thin color artifacts around lettering while preserving the exact shared STL boundaries.

## Compact Display Support

The Edit tab is designed to work on smaller screens:

- **Quick Workflow** can be collapsed
- visible **DRAG TO RESIZE PREVIEW / COLORS** grip
- draggable divider between logo preview and detected-color list
- logo preview automatically scales to the available space
- complete logo remains visible instead of being cropped
- left settings column is vertically scrollable
- mouse-wheel scrolling works on the left settings column
- mouse-wheel scrolling works in the detected-color list

### Default Expanded Sections

- File & Export
- Logo & Analysis
- Color Analysis

### Default Collapsed Sections

- Profile
- Target Surface & Fit
- Geometry Quality

## Typical Workflow

1. Load a logo and click **(Start) Analyze Colors**.
2. Assign detected colors to the desired print groups.
3. Use **AUTO** for transition / anti-aliasing shades when useful.
4. Open **Manual** and click **Calculate** to resolve AUTO pixels.
5. Make any required pixel-level corrections and click **Calculate** again.
6. Review the geometry in **STL Preview**.
7. Click **(Finish) Generate STLs**.

## Output Example

For a project named `Monopoly`:

```text
Monopoly_STL/
├── Monopoly_color_01_black.stl
├── Monopoly_color_02_white.stl
├── Monopoly_complete_cutout.stl
└── Monopoly_negative_clearance_0_00mm.stl
```

The exporter performs topology checks. If a remaining mesh issue is detected, the STL is still written and the application reports that slicer repair may be required.

## Run from Source

### Requirements

- Windows 10 or Windows 11
- Python 3
- packages listed in `requirements.txt`

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the application:

```bash
python logo_inlay_app.py
```

or:

```text
start_app.bat
```

## Build the Standalone Windows EXE

Run:

```text
build_exe.bat
```

PyInstaller creates:

```text
dist/Logo to STL Tool 7.7.exe
```

The compiled executable can be run on another Windows PC without a separate Python installation.

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used for code generation, debugging, UI refinement, geometry logic, regression testing, and workflow development.

## License

Licensed under the **MIT License**.

See [LICENSE](LICENSE) for details.
