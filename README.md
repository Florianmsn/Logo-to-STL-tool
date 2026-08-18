# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

The tool detects colors, lets you group and manually correct them, previews the final vector geometry, and exports one STL per print color together with matching cutout and clearance geometry.

## Current Version

**V8 Final / v8.0**

## Main Features

- PNG, JPG, JPEG, WEBP and BMP input
- Automatic color detection and grouping
- Manual assignment of detected shades to print-color groups
- `AUTO` for anti-aliased / transitional pixels
- `BG` for true background regions
- Manual editor with Brush, Line, Fill Area and Eyedropper
- Undo, Reset, zoom and pan
- Real-time responsive brush painting
- Adjustable geometry resolution and edge smoothing
- Straight, smooth and maximum-detail contour modes
- STL geometry preview and integrity check
- Mouse-wheel scrolling in settings, detected colors and STL Preview
- Separate STL export for every print color
- Complete cutout STL
- Negative / clearance STL
- Automatic project-specific output folder
- Compact-display friendly layout

## V8 Final — Exact STL Dimensions

`Logo Width (mm)` and `Logo Height (mm)` now describe the **final STL footprint**, not the complete raster-image canvas.

Transparent or removed margins around a source image therefore no longer make the exported logo smaller than the requested value.

### Lock aspect ratio enabled

- Entering a new **Width** automatically updates **Height**
- Entering a new **Height** automatically updates **Width**
- Scaling remains proportional
- Width is applied exactly to the final vector/STL geometry
- After final vectorization, Height is synchronized to the actual proportional final height

### Lock aspect ratio disabled

Width and Height are independent and both are applied exactly to the final STL geometry.

The STL Preview shows the calculated physical footprint directly, for example:

```text
Final Geometry — 80.00 × 39.90 mm
```

## V8 Final — Stability Improvements

The complete workflow was reviewed for the V8 release.

Notable changes:

- Width / Height edits invalidate STL geometry correctly
- Preview and export use the same shared geometry-preparation path
- Analysis settings are remembered from the analysis that produced the current label map
- Changing analysis controls does not silently reinterpret an older analysis; changes take effect after **Analyze Colors**
- Selecting a new image clears old analysis, Manual and STL state
- Background workers no longer read Tkinter variables directly
- Worker results are passed back through a main-thread UI queue
- Duplicate/conflicting analysis, preview and export jobs are guarded
- Physical and analysis inputs receive additional validation
- Profiles apply Width / Height atomically so aspect-lock traces cannot overwrite profile values
- Local output folders are no longer stored inside reusable profiles

For backward compatibility, the existing settings directory is intentionally retained:

```text
~/.logo_inlay_tool/
```

This preserves existing profiles and settings after the application rename.

## Manual Editing

Brush painting is displayed immediately while dragging without rebuilding and rescaling the complete Manual bitmap for every mouse event.

The editable label map is updated through small local regions, while a lightweight Canvas stroke provides immediate visual feedback.

`Calculate` behavior remains deliberate:

- Manual edits stay local/draft-only while editing
- Other previews and STL export continue to use the last calculated state
- `Calculate` commits Manual changes
- AUTO regions are resolved when `Calculate` is pressed

## Local Color-Aware STL Partitioning

Microscopic vectorization gaps are assigned to the most plausible locally adjacent color instead of being given to the globally largest color.

This reduces thin wrong-color artifacts around lettering while preserving:

- gap-free color partitioning
- non-overlapping color regions
- shared STL boundaries

## Compact Display Support

The Edit tab includes:

- collapsible **Quick Workflow**
- visible **DRAG TO RESIZE PREVIEW / COLORS** grip
- draggable divider between preview and detected colors
- automatically resizing logo preview
- scrollable detected-color list
- mouse-wheel scrolling

The complete left settings column is also vertically scrollable.

### Open by default

- File & Export
- Logo & Analysis
- Color Analysis

### Collapsed by default

- Profile
- Target Surface & Fit
- Geometry Quality

## Typical Workflow

1. Load a logo
2. Click **(Start) Analyze Colors**
3. Assign detected colors to print groups
4. Use `AUTO` for transition / anti-aliasing shades when useful
5. Open **Manual** and make corrections
6. Click **Calculate**
7. Review **STL Preview**
8. Click **(Finish) Generate STLs**

## Output Example

For a project named `Monopoly`:

```text
Monopoly_STL/
├── monopoly_color_01_black.stl
├── monopoly_color_02_white.stl
├── monopoly_complete_cutout.stl
├── monopoly_negative_clearance_0_00mm.stl
├── monopoly_preview.png
└── monopoly_info.json
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

Run:

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
dist/Logo to STL Tool 8.0.exe
```

The compiled executable can then be copied to another Windows PC without requiring a separate Python installation.

## Testing

V8 Final received a broad automated regression pass covering the main Core and GUI workflows.

See [TEST_REPORT_V8_FINAL.md](TEST_REPORT_V8_FINAL.md).

The automated suite measured approximately **74% statement coverage** across the application and core modules. Coverage is useful as a regression metric, but it is not a guarantee that software can never contain a bug.

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used for code generation, debugging, UI refinement, geometry logic, regression testing and workflow development.

## License

Licensed under the **MIT License**.

See [LICENSE](LICENSE) for details.
