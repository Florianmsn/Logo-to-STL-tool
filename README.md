# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

The tool detects colors, lets you group and manually correct them, previews the final STL geometry, and exports one STL per print color together with matching cutout / clearance geometry.

## Current Version

**v7.8**

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
- Real-time responsive brush painting
- Adjustable geometry resolution and contour smoothing
- STL geometry preview before export
- Integrity preview for the complete color partition
- Mouse-wheel scrolling in the STL Preview
- Separate STL export for each print color
- Complete cutout STL
- Negative / clearance STL
- Automatic project-specific output folder
- English UI and output filenames

## V7.8 Manual Editor Performance

V7.8 changes how brush painting is displayed and applied.

Earlier versions rebuilt and rescaled the complete Manual preview for almost every mouse-move event. Large analysis images could therefore stutter even though the expensive `Calculate` / STL processing had not started yet.

V7.8 now uses two lightweight mechanisms while painting:

1. the editable label data is updated immediately using only a **small local region around the current brush segment**,
2. a lightweight Canvas stroke shows the painted color **live while the mouse moves**.

The complete Manual bitmap is rebuilt only once when the brush stroke ends.

Fast mouse movements are also connected as continuous brush segments, so the stroke does not leave accidental gaps between individual mouse events.

### Calculate Behavior Is Unchanged

Manual edits are still draft-only until **Calculate** is pressed.

While painting:

- the Manual tab updates immediately,
- the draft label data changes immediately,
- the other previews and STL export continue to use the last calculated state.

When **Calculate** is pressed:

- all Manual edits are committed,
- AUTO regions are resolved,
- Edit / STL / Final Preview use the newly calculated result.

## V7.8 STL Preview Scrolling

The **STL Preview** tab can now be scrolled with the mouse wheel.

Mouse-wheel scrolling also works while the pointer is over dynamically generated:

- preview images,
- group cards,
- labels,
- integrity-check sections.

The normal scrollbar remains available.

## V7.7 Geometry Improvement

V7.7 improved how microscopic gaps created during contour simplification are assigned.

Instead of assigning the entire vectorization remainder to the globally largest color, leftover regions are assigned to the most plausible locally adjacent / locally matching color.

This reduces thin wrong-color artifacts and unnecessary islands while preserving:

- gap-free color partitioning,
- non-overlapping color regions,
- exact shared STL boundaries.

## Compact Display Support

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
4. Open **Manual** and make any required corrections.
5. Click **Calculate** to commit Manual changes and resolve AUTO pixels.
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
dist/Logo to STL Tool 7.8.exe
```

The compiled executable can be run on another Windows PC without a separate Python installation.

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used for code generation, debugging, UI refinement, geometry logic, regression testing, and workflow development.

## License

Licensed under the **MIT License**.

See [LICENSE](LICENSE) for details.
