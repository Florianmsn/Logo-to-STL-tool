# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

## Current Version

**v9.0**

V9 is a major internal architecture rewrite. The central rule is:

> **After Calculate, color ownership is frozen.**

STL Preview, Final Preview and STL export all use the same immutable final color map. Geometry generation is no longer allowed to decide, smooth, repair or reassign colors.

## Why V9 Was Rebuilt

Older versions had accumulated several independent color-repair stages:

- color cleanup
- AUTO redistribution
- smoothing
- separate vectorization of every color
- overlap repair
- vector-gap filling
- tiny vector-island reassignment
- post-scaling geometry repair

This meant a region that looked correct in Manual could still be assigned to another color later during STL generation.

V9 removes that architecture.

## New V9 Pipeline

```text
Source Image
    ↓
Analyze Colors
    ↓
Assign detected shades to print groups / AUTO / BG
    ↓
Manual corrections
    ↓
Calculate
    ├─ clean tiny automatic raster artifacts
    ├─ resolve AUTO using real edge-adjacent colors only
    └─ freeze one FINAL COLOR MAP
    ↓
Exact raster-cell geometry
    ↓
STL Preview / Final Preview / STL Export
```

There is no color decision after the final map has been frozen.

## Final Color Map

The final map contains only:

```text
-1      Background / no print
0..N    Final print-color group IDs
```

After a successful Calculate:

- the map is copied into committed state
- the committed NumPy array is made **read-only**
- geometry workers receive copies
- STL code never receives detected color clusters or AUTO rules
- geometry code cannot recolor a pixel

Changing a color assignment or making a new Manual edit marks the result as pending again until Calculate is pressed.

## Manual Editing

The Manual tab edits the color assignment directly.

Tools:

- Brush
- Line
- Fill Area
- Eyedropper
- Undo
- Reset
- Zoom
- middle-mouse pan

### Manual lock

A print-color pixel that you deliberately paint in Manual is protected.

Automatic tiny-artifact cleanup may not remove that manually painted pixel.

A manually painted tiny detail is preserved, but it is **not promoted into a cleanup seed that can grow and absorb neighboring noise**.

## AUTO

AUTO is resolved only when Calculate is pressed.

Rules:

- only horizontal / vertical pixel-edge contact counts
- diagonal-only colors are not candidates
- non-touching colors elsewhere in the logo are not candidates
- each connected AUTO region is processed independently
- valid neighboring print colors propagate geodesically through that AUTO region
- an isolated AUTO region with no real print-color edge is reported instead of being assigned to an unrelated color

There is no global nearest-color or RGB-based AUTO fallback.

## Tiny Artifact Cleanup

`Min. Island Area (mm²)` is applied during Calculate, before the map is frozen.

A tiny automatic print-color component may move only to a sufficiently stable print-color region that shares a real horizontal / vertical edge.

Selection:

1. most shared edges
2. local stable-color majority only for an exact tie

The following cannot become replacement candidates:

- diagonal-only colors
- remote colors
- other tiny unstable components

Manually locked print pixels and isolated details surrounded only by Background are preserved.

## Exact Raster-Cell Geometry

This is the biggest change in V9.

Older versions vectorized every print color independently. Independent contour approximation could create small gaps or overlaps that then needed additional color decisions.

V9 instead treats every final raster pixel as an exact rectangular cell.

For example:

```text
R R R W W
R R R W W
R R B B B
```

already has a mathematically exact owner for every printable cell.

The geometry builder:

1. crops the frozen final map to its printable bounding box
2. merges identical horizontal pixel runs vertically into larger rectangles
3. unions those exact rectangles for each print group
4. applies the requested physical Width / Height
5. extrudes the resulting geometry

Adjacent colors therefore share the same cell boundaries by construction.

The geometry stage contains no:

- Gaussian color smoothing
- contour-based recoloring
- vector-gap owner
- nearest-color fallback
- largest-color fallback
- vector-island recoloring
- post-scale color reassignment

## Geometry & Cleanup Controls

The old geometry controls that caused independent contour approximation were intentionally removed.

V9 no longer exposes:

- Edge Smoothing
- Geometry Resolution
- Contour Simplification
- Contour Mode

The important controls are now simpler:

- **Analysis Resolution**
- **Min. Island Area**
- final Width / Height
- Part Height
- Cutout Depth
- Clearance

For finer physical edge detail, use a higher-quality source image and/or a higher Analysis Resolution, then run Analyze Colors again.

## Exact STL Dimensions

`Logo Width (mm)` and `Logo Height (mm)` describe the final printable footprint.

With **Lock aspect ratio** enabled:

- changing Width updates Height
- changing Height updates Width
- the printable final-map aspect ratio is preserved

With the lock disabled:

- Width and Height are independent
- both are applied exactly

Transparent / BG margins outside the printable content do not reduce the requested footprint.

## Background

BG is not a color.

BG cells are simply absent from the exact geometry.

Therefore BG cannot later be filled by:

- AUTO
- STL smoothing
- gap repair
- polygon recoloring

Those later color-repair stages do not exist in V9.

## STL Output

Example:

```text
my_project_STL/
├── my_project_color_01_black.stl
├── my_project_color_02_white.stl
├── my_project_color_03_red.stl
├── my_project_complete_cutout.stl
├── my_project_negative_clearance_0_08mm.stl
├── my_project_preview.png
├── my_project_info.json
└── my_project_original.png
```

The metadata JSON explicitly records:

```text
geometry_mode: exact_raster_cells
colors_frozen_after_calculate: true
```

Mesh manifold checks remain diagnostic. A mesh is still exported if a slicer repair warning is required.

## Compact Display Support

Retained from previous versions:

- collapsible Quick Workflow
- draggable Preview / Colors divider
- visible resize grip
- automatically resizing Edit preview
- scrollable left settings
- scrollable detected colors
- mouse-wheel scrolling in STL Preview

Default open sections:

- File & Export
- Logo & Analysis
- Color Analysis

Default collapsed sections:

- Profile
- Target Surface & Fit
- Geometry & Cleanup

## Typical Workflow

1. Load a logo
2. Click **(Start) Analyze Colors**
3. Assign detected shades to print groups, AUTO or BG
4. Correct anything necessary in **Manual**
5. Click **Calculate**
6. Inspect the frozen result in Manual
7. Review **STL Preview**
8. Optionally review **Final Preview**
9. Click **(Finish) Generate STLs**

If you make another Manual or grouping change, press Calculate again before exporting.

## Performance Changes

Color analysis now trains K-Means on a bounded deterministic sample and then classifies all visible pixels in chunks.

The final-map cleanup and exact-cell geometry avoid the repeated full-image smoothing and repeated Shapely difference/intersection repair chain used by older releases.

Indicative automated benchmark results in the development environment:

```text
1200 × 800 synthetic color analysis: ~0.5 s

1600 × 1000 final-map stress test:
finalize / cleanup: ~0.2 s
exact geometry:     ~0.06 s

640 × 420 five-color end-to-end benchmark:
analysis: ~0.28 s
finalize: ~0.03 s
STL export: ~1.16 s
7 STL files total: ~1.5 MB
manifold warnings: 0
```

These numbers depend on CPU, image complexity and source resolution.

## Profiles and Existing Settings

For backward compatibility V9 intentionally continues using:

```text
~/.logo_inlay_tool/
```

Old profiles/settings containing removed geometry keys are tolerated and the obsolete keys are ignored.

The internal Python source filenames are also retained as:

```text
logo_inlay_app.py
logo_inlay_core.py
```

This is intentional so an existing GitHub repository can replace the old files directly without leaving duplicate source files. The application name is **Logo to STL Tool**.

## Run from Source

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start:

```bash
python logo_inlay_app.py
```

or:

```text
start_app.bat
```

## Build the Windows EXE

Run:

```text
build_exe.bat
```

The builder checks for a real Python installation in this order:

1. `py -3`
2. `python`
3. `python3`

It verifies pip / PyInstaller and reports success only if the new executable actually exists.

Output:

```text
dist/Logo to STL Tool 9.0.exe
```

## Testing

See:

[TEST_REPORT_V9_0.md](TEST_REPORT_V9_0.md)

V9 received a broad automated Core + Tkinter GUI regression pass. This significantly reduces regression risk, but automated coverage is not a guarantee that software can never contain a bug. A real-world test with representative logos is still recommended before publishing the release.

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used for code generation, architecture work, debugging, UI refinement and regression testing.

## License

MIT License. See [LICENSE](LICENSE).
