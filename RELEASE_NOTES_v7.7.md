# Logo to STL Tool v7.7

V7.7 improves how the STL geometry is partitioned between print colors.

## What's New

- Renamed the application to **Logo to STL Tool**
- Improved local color partitioning for STL generation
- Microscopic vectorization gaps are no longer assigned to the globally largest color
- Leftover regions are now assigned to the most plausible **locally adjacent / locally matching color**
- This greatly reduces thin wrong-color lines and unnecessary tiny islands around lettering and detailed boundaries
- Gap-free and non-overlapping STL partitioning is preserved

## Regression Result

Using an UNO-style test case reconstructed from the manual preview:

- Red islands: **94 → 3**
- White islands: **23 → 7**
- Missing partition area: approximately **0**
- Overlap area: approximately **0**

## Existing Highlights

- Automatic color detection and grouping
- AUTO assignment for anti-aliased / transition pixels
- Manual pixel-level editing
- STL geometry preview
- Integrity preview for the complete color partition
- Separate STL files for each print color
- Complete cutout STL
- Negative / clearance STL
- Compact-display friendly Edit layout
- Collapsible workflow section
- Draggable preview / color divider
- Scrollable left settings panel
- Mouse-wheel scrolling in settings and detected colors

## Quick Start

**Load a logo → (Start) Analyze Colors → assign colors → Manual → Calculate → STL Preview → (Finish) Generate STLs**

## Windows

Build the standalone Windows executable with:

```text
build_exe.bat
```

The resulting executable is:

```text
Logo to STL Tool 7.7.exe
```

No separate Python installation is required on the target Windows PC.

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
