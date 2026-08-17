# Logo-to-STL Tool

A Windows desktop tool for converting raster logos into separate STL files for multi-color 3D printing.

The application detects colors in a logo, lets you group them into printable color regions, provides manual pixel-level cleanup, and generates separate STL files for each color together with matching cutout geometry.

## Features

- Load PNG, JPG, JPEG, WEBP, and BMP logos
- Automatic color detection and grouping
- Assign detected colors to print groups
- `AUTO` mode for distributing anti-aliased or transitional pixels to neighboring print colors
- `BG` mode for removing regions from the printable logo
- Manual editor with:
  - Brush
  - Line
  - Fill Area
  - Eyedropper
  - Undo
  - Reset
  - Zoom and pan
- Adjustable geometry quality and contour smoothing
- STL geometry preview
- Final target-surface preview
- Separate STL export for every print color
- Complete cutout STL
- Negative / clearance STL
- Automatic project-specific output folder
- English UI and output filenames
- Small-display friendly Edit layout:
  - Collapsible Quick Workflow
  - Draggable divider between logo preview and color list
  - Mouse-wheel scrolling in the detected-color list

## Typical Workflow

1. Load your logo and click **(Start) Analyze Colors**.
2. Click **Show** next to a detected color, then assign it to a print group using the color buttons.
3. Use **AUTO** for transition or anti-aliasing shades that should be distributed between neighboring print colors.
4. Open the **Manual** tab and click **Calculate** to resolve AUTO pixels.
5. Make any pixel-level corrections if needed, then click **Calculate** again.
6. Review the result in **STL Preview**.
7. Click **(Finish) Generate STLs**.

## Small Display Tips

The **Quick Workflow** section in the Edit tab can be collapsed to free vertical space.

The divider between **Preview & Highlight** and **Select & Group Detected Colors** can be dragged up or down. This lets you reduce the logo preview and give more room to the detected-color list.

When the mouse pointer is over the detected-color list, the **mouse wheel** scrolls the list. The scrollbar remains available as well.

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

The tool attempts to generate watertight/manifold geometry. If a remaining topology issue is detected, the STL is still exported and the application warns you that your slicer's repair function may be required.

## Run from Source

### Requirements

- Windows 10 or Windows 11
- Python 3
- Packages listed in `requirements.txt`

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the application:

```bash
python logo_inlay_app.py
```

Or use:

```text
start_app.bat
```

## Build a Standalone Windows EXE

Run:

```text
build_exe.bat
```

The script installs the required packages and uses PyInstaller to create a standalone Windows executable.

The resulting EXE is placed in:

```text
dist/
```

The compiled EXE can be copied to another Windows PC without requiring a separate Python installation.

## Notes

- The tool is designed primarily for flat logo inlays and multi-color 3D printing.
- Raster logos with clearly separated color regions usually produce the best results.
- Small details, compression artifacts, and anti-aliasing may require manual cleanup.
- Minor STL topology warnings can usually be repaired by the slicer.

## Development

This project was created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used throughout the project for code generation, debugging, UI refinement, testing ideas, and workflow development.

## License

This project is licensed under the **MIT License**.

See [LICENSE](LICENSE) for details.
