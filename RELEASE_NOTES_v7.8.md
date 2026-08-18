# Logo to STL Tool v7.8

V7.8 focuses on a much smoother Manual editing experience and improved navigation in the STL Preview.

## What's New

### Real-Time Manual Brush

- Brush painting now stays visually responsive while the mouse is moving
- The painted color is shown immediately with a lightweight live stroke overlay
- The program no longer rebuilds and rescales the complete Manual preview for every mouse-move event
- Only the small local image region around the current brush segment is modified
- Fast mouse movements are connected into continuous strokes, preventing gaps between mouse events
- The full Manual preview is consolidated only once when the stroke ends

### Calculate Workflow Preserved

The existing workflow has **not** changed:

- Manual edits remain draft-only while editing
- Other previews and STL export continue using the last calculated state
- **Calculate** remains the action that commits Manual edits to the rest of the application
- AUTO pixels are still resolved only when Calculate is pressed

### Mouse-Wheel Scrolling in STL Preview

- STL Preview can now be scrolled with the mouse wheel
- Scrolling works while hovering over preview images, labels, integrity checks and group cards
- The normal scrollbar remains available

## Performance Test

A synthetic Manual test using a **1600 × 1600** editable label image and **300 brush movement events** completed the drag-processing portion in approximately **0.01 seconds** in the automated test environment.

During those 300 drag events:

- full Manual bitmap rebuilds: **0**
- full bitmap rebuild after the completed stroke: **1**

## Regression Checks

V7.7 local color partitioning remains intact:

- UNO-style red islands: **3**
- missing partition area: approximately **0**
- overlap area: **0**

A complete STL export regression test also passed with zero measured partition gaps and overlaps.

## Existing Highlights

- Automatic color detection and grouping
- AUTO assignment for transition / anti-aliasing pixels
- Manual pixel-level editing
- Local color-aware STL partitioning
- STL geometry preview
- Integrity preview
- Separate STL files for each print color
- Complete cutout and clearance STL generation
- Compact-display friendly layout
- Scrollable left settings panel
- Draggable preview / color divider

## Quick Start

**Load a logo → (Start) Analyze Colors → assign colors → Manual corrections → Calculate → STL Preview → (Finish) Generate STLs**

## Windows

Build the standalone Windows executable with:

```text
build_exe.bat
```

The resulting executable is:

```text
Logo to STL Tool 7.8.exe
```

No separate Python installation is required on the target Windows PC.

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
