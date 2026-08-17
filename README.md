# Logo-to-STL Tool

A Windows desktop tool for converting raster logos into separate STL files for multi-color 3D printing.

The application detects colors in a logo, lets you group them into printable color regions, provides manual pixel-level cleanup, and generates separate STL files for each color together with matching cutout geometry.

## Features

- Load PNG, JPG, JPEG, WEBP, and BMP logos
- Automatic color detection and grouping
- Assign detected colors to print groups
- `AUTO` mode for distributing anti-aliased or transitional pixels to neighboring print colors
- `BG` mode for removing regions from the printable logo
- Manual editor with Brush, Line, Fill Area and Eyedropper
- Undo, Reset, zoom and pan
- Adjustable geometry quality and contour smoothing
- STL geometry preview
- Final target-surface preview
- Separate STL export for every print color
- Complete cutout STL
- Negative / clearance STL
- Automatic project-specific output folder
- English UI and output filenames

## Compact Display Features

V7.6 improves the workflow on smaller screens:

- **Collapsible Quick Workflow** in the Edit tab
- A clearly visible **DRAG TO RESIZE PREVIEW / COLORS** grip
- Draggable divider between the logo preview and detected-color list
- The logo preview automatically scales with the available pane size
- The complete logo remains visible instead of being cropped
- The entire left settings column is vertically scrollable
- Mouse-wheel scrolling works on the left settings column
- Mouse-wheel scrolling also works in the detected-color list

### Default Settings Sections

Open by default:

- File & Export
- Logo & Analysis
- Color Analysis

Collapsed by default:

- Profile
- Target Surface & Fit
- Geometry Quality

## Typical Workflow

1. Load your logo and click **(Start) Analyze Colors**.
2. Click **Show** next to a detected color, then assign it to a print group.
3. Use **AUTO** for transition or anti-aliasing shades.
4. Open **Manual** and click **Calculate** to resolve AUTO pixels.
5. Make pixel-level corrections if required and click **Calculate** again.
6. Review the result in **STL Preview**.
7. Click **(Finish) Generate STLs**.

## Output Files

For a project named `Monopoly`, the output folder is automatically created as:

```text
Monopoly_STL/
```

Example files:

```text
Monopoly_color_01_black.stl
Monopoly_color_02_white.stl
Monopoly_complete_cutout.stl
Monopoly_negative_clearance_0_00mm.stl
```

## Run from Source

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start:

```bash
python logo_inlay_app.py
```

or use:

```text
start_app.bat
```

## Build a Standalone Windows EXE

Run:

```text
build_exe.bat
```

The standalone executable is created in:

```text
dist/
```

## Development

This project was created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used throughout the project for code generation, debugging, UI refinement, testing ideas, and workflow development.

## License

This project is licensed under the **MIT License**.

See [LICENSE](LICENSE) for details.
