# Logo to STL Tool — V8 Final

**Version:** v8.0

V8 Final focuses on predictable physical sizing, consistency between preview and export, and overall application stability.

## Final STL Size Controls

`Logo Width (mm)` and `Logo Height (mm)` now control the final STL footprint itself.

Previously, physical scale was derived from the full raster canvas. Logos with transparent or removed margins could therefore export smaller than the Width value suggested.

V8 now bases sizing on printable content and performs a final vector fit.

### Aspect ratio locked

- Width and Height are synchronized
- editing Width updates Height
- editing Height updates Width
- proportional scaling is preserved
- Width is exact on the final STL
- the final calculated Height is shown in the UI and STL Preview

### Aspect ratio unlocked

- Width and Height can be edited independently
- both dimensions are applied exactly to the final STL

## STL Preview

- Size changes correctly invalidate the STL preview
- when STL Preview is visible, size changes trigger a delayed refresh
- calculated physical dimensions are displayed directly
- Preview and Export share the same geometry-preparation path
- mouse-wheel scrolling remains available throughout the tab

## Analysis / State Consistency

V8 remembers the analysis parameters that created the current label map.

Changing `Colors to detect`, Analysis Resolution, Background mode or other analysis settings does not silently reinterpret an old Manual result. Those changes take effect only after **(Start) Analyze Colors** is run again.

Selecting a new source image clears the previous color analysis, Manual draft, committed Manual result and STL Preview state.

## Background Worker Stability

Analysis, STL Preview and STL Export snapshot their required UI values before starting.

Background threads no longer read Tkinter variables directly. Worker results are returned through a main-thread UI queue.

The application also prevents conflicting calculations from being started at the same time.

## Profile and Validation Fixes

- Profiles are applied atomically
- Width / Height synchronization cannot corrupt profile loading
- local output-base directory is not stored in reusable profiles
- additional validation covers physical sizes and analysis/geometry controls

## Preserved Improvements

V8 retains:

- real-time responsive Manual brush
- draft-only Manual changes until Calculate
- AUTO resolution on Calculate
- local color-aware vector-gap assignment
- exact gap-free color partitioning
- manifold diagnostics without blocking STL export
- compact-display layout
- collapsible workflow
- draggable Preview / Colors split
- scrollable settings and detected colors
- mouse-wheel scrolling in STL Preview

## Regression Testing

Automated V8 tests covered:

- exact target dimensions with transparent image padding
- locked and unlocked aspect-ratio behavior
- bidirectional Width / Height synchronization
- all contour modes
- multiple smoothing levels
- color analysis and grouping
- AUTO resolution
- background handling
- Manual Brush / Line / Fill / Eyedropper / Undo / Calculate
- live Manual brush performance
- STL partition integrity
- STL extrusion / manifold checks
- real STL file export
- clearance geometry
- threaded analysis
- threaded STL Preview
- threaded STL export
- compact-display scrolling and resize controls
- profiles
- output-folder naming
- new-image state reset

Automated statement coverage was approximately:

- application module: **73%**
- core module: **77%**
- combined: **74%**

See `TEST_REPORT_V8_FINAL.md` for details.

## Windows Build

Run:

```text
build_exe.bat
```

The output is:

```text
dist/Logo to STL Tool 8.0.exe
```

The Windows EXE itself must be built on Windows. The source/runtime regression suite was executed in the available Linux test environment.

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
