# Logo to STL Tool — V8 Final Test Report

**Version:** v8.0  
**Test date:** 2026-08-18

## Scope

The V8 review covered the two production source modules:

- `logo_inlay_app.py`
- `logo_inlay_core.py`

The goal was to regression-test the main user workflows and geometry/export pipeline before marking V8 as the final release candidate.

## Syntax / Import

Passed:

- Python compilation of application module
- Python compilation of core module
- clean module imports
- application title/version check

## Physical Size Tests

A synthetic `200 × 100 px` image was created with a printable `100 × 50 px` logo centered inside large transparent margins.

### Locked aspect ratio

Requested:

```text
Width: 80 mm
```

Result:

```text
Final STL Width: 80.000 mm
Final proportional Height: approximately 39.9 mm
```

The transparent source-image margins no longer reduce the physical STL size.

### Unlocked aspect ratio

Requested:

```text
Width: 80 mm
Height: 30 mm
```

Result:

```text
Final STL Width: 80.000 mm
Final STL Height: 30.000 mm
```

### Additional size matrix

Exact unlocked sizing was verified with:

```text
73.25 × 31.75 mm
```

across:

- Straight / crisp contours
- Smooth curves
- Maximum-detail contour mode
- smoothing 0.00 mm
- smoothing 0.10 mm
- smoothing 0.22 mm
- smoothing 0.45 mm

Partition missing area and overlap remained within numerical tolerance.

## Width / Height UI

Passed:

- Width updates Height while aspect lock is enabled
- Height updates Width while aspect lock is enabled
- Width and Height remain independent when aspect lock is disabled
- size edits mark STL Preview dirty
- final vector Height is written back to locked Height
- final dimensions are displayed in STL Preview
- profile loading does not trigger Width / Height trace conflicts

## Core Geometry

Passed:

- safe output filename generation
- English output color names
- color quantization
- similar-color merging
- transparent background handling
- white background handling
- corner-color background handling
- outer-connected background removal
- explicit BG region removal
- enclosed BG holes
- AUTO local redistribution
- isolated AUTO fallback
- geometry-grid upscaling
- exact color partition invariants
- no measurable missing partition area
- no measurable partition overlap
- contour modes
- physical edge smoothing
- polygon extrusion
- simple-manifold mesh validation
- STL file round-trip loading
- clearance geometry

## Wrong-Color Line Regression

The UNO-style regression case used during the V7.7 geometry fix was rerun.

Result:

```text
White islands: 7
Red islands: 3
Yellow islands: 4
Black islands: 18
Missing partition area: ~0
Overlap area: 0
```

The prior wrong-color red-fragment regression remains fixed.

## Manual Editor

Passed:

- Brush
- continuous fast brush strokes
- live on-screen brush overlay
- no full bitmap rebuild during mouse-drag events
- one consolidation redraw after completed stroke
- Line
- Fill Area
- Eyedropper
- Undo
- zoom
- zoom reset
- Manual draft stays separate from committed STL state
- AUTO remains unresolved until Calculate
- Calculate resolves AUTO
- Calculate commits Manual state

A synthetic `1600 × 1600` Manual image with hundreds of brush movement events was used for the responsiveness regression.

## GUI / Compact Display

Passed:

- default expanded sections
- default collapsed sections
- left settings scrollbar
- left settings mouse wheel
- detected-color mouse wheel
- collapsible Quick Workflow
- draggable Preview / Colors divider
- visible resize grip
- normal cursor outside resize grip
- responsive logo preview
- STL Preview mouse-wheel scrolling
- dynamically generated STL cards receive wheel bindings
- Final Preview rendering
- output-folder renaming from Project Name

Window-layout smoke tests were performed at:

```text
1000 × 600
1120 × 720
1600 × 900
```

## Background Processing

Passed:

- threaded color analysis
- threaded STL Preview
- threaded STL export
- analysis settings are snapshotted
- export/preview use the analysis settings that produced the current label map
- background workers do not read Tk variables directly
- worker results are returned through the main-thread UI queue
- conflicting long-running jobs are guarded

## Real STL Export Regression

A complete export produced:

- separate color STL files
- complete cutout STL
- clearance STL
- preview PNG
- info JSON

Verified:

- requested final dimensions
- English STL output names
- partition integrity metadata
- readable STL files
- clearance body larger than the exact cutout body

## New Image / State Reset

Passed:

- old analysis cleared
- old color rows cleared
- old Manual data cleared
- committed Manual state cleared
- STL Preview state reset

## Automated Coverage

Measured statement coverage during the combined automated regression run:

```text
logo_inlay_app.py   73%
logo_inlay_core.py  77%
Combined            74%
```

Coverage measures which statements were executed by the automated tests. It does not guarantee that software is completely free of defects.

## Windows EXE

The final `.exe` is not compiled in the Linux test environment.

The included Windows build script is configured to create:

```text
dist/Logo to STL Tool 8.0.exe
```

The project previously built successfully with PyInstaller on Windows. The V8 executable should receive one final smoke test on the target Windows machine after building.

## Result

All automated V8 Final regression suites passed after the fixes documented above.
