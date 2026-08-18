# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

## Current Version

**v8.1**

## Main Features

- Automatic color detection and grouping
- Manual color assignment
- `AUTO` for anti-aliased / transition pixels
- `BG` for true background areas
- Manual Brush, Line, Fill Area and Eyedropper
- Real-time responsive Manual brush
- Undo, Reset, zoom and pan
- Exact final STL Width / Height
- Adjustable geometry resolution
- Adjustable contour simplification and edge smoothing
- STL geometry and integrity preview
- Final Preview on a configurable target surface
- Separate STL files for each print color
- Complete cutout STL
- Negative / clearance STL
- Compact-display layout with mouse-wheel scrolling

## V8.1 — Strict Local Color Repair

V8.1 fixes the remaining wrong-color micro-pixel / micro-island problem in the STL geometry.

There are now two cleanup stages.

### 1. Raster cleanup before vectorization

Tiny color components below `Min. Island Area` are handled before contours are created.

A tiny component may be reassigned only to a **stable print color that shares a real horizontal or vertical pixel edge with it**.

The decision is:

1. count the shared pixel edges for every valid neighboring color
2. choose the color with the highest count
3. if the edge count is exactly tied, use the local stable-color majority around the same component

Important:

- diagonal-only colors are not candidates
- colors elsewhere in the logo are not candidates
- one tiny artifact cannot pull another tiny artifact into a new color
- a tiny detail surrounded only by true background is preserved

### 2. Strict vector-gap filling

Contour simplification can create microscopic geometric gaps.

V8.1 fills them using only proven physical adjacency:

1. inspect the direct 4-neighbor raster ring around the gap
2. choose the most represented directly adjacent color
3. if there is an exact tie, use shared vector-boundary length between those same candidates
4. if the raster ring cannot decide, a true shared vector edge may be used
5. if no physical adjacency can be proven, the program does **not** invent a color

There is no longer any:

- global nearest-color fallback
- RGB-based remote-color fallback
- globally largest-color fallback
- "nearby but not touching" color fallback

If an unusual vector gap cannot be assigned locally, the application reports it instead of silently inserting the wrong color.

## AUTO Behavior

AUTO remains separate from the vector-gap cleanup.

AUTO uses strict 4-neighbor connectivity:

- only print colors sharing a real pixel edge with the connected AUTO region are valid candidates
- diagonal-only colors are ignored
- colors elsewhere in the logo cannot enter the AUTO region
- AUTO propagates geodesically from the real contact edges
- an isolated AUTO region is left unresolved instead of being guessed

`Calculate` remains the point at which AUTO is resolved and Manual changes are committed.

## Min. Island Area

`Min. Island Area (mm²)` controls the physical threshold for tiny color islands.

For example, with the default-style value around `0.08 mm²`, embedded single-pixel / micro-artifact regions are usually transferred to their strongest surrounding stable color.

Set the value lower if a logo intentionally contains extremely small embedded details.

A small detail that is isolated in true background is preserved because it has no neighboring print color to absorb it.

## Exact STL Dimensions

`Logo Width (mm)` and `Logo Height (mm)` control the final STL footprint.

With **Lock aspect ratio** enabled:

- Width updates Height
- Height updates Width
- the logo remains proportional

With the lock disabled, Width and Height are independent.

Transparent source-image margins do not reduce the requested final STL dimensions.

## Manual Workflow

Manual changes remain draft-only while editing.

- Brush / Line / Fill update the Manual view
- other previews and STL export continue using the last calculated state
- `Calculate` commits Manual changes
- AUTO is resolved on Calculate

## Compact Display Support

- collapsible Quick Workflow
- draggable Preview / Colors divider
- visible resize grip
- automatically resizing logo preview
- scrollable settings
- scrollable detected-color list
- mouse-wheel scrolling in STL Preview

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
3. Assign detected colors
4. Use AUTO where useful
5. Correct pixels in **Manual**
6. Click **Calculate**
7. Review **STL Preview**
8. Review **Final Preview**
9. Click **(Finish) Generate STLs**

## Build the Windows EXE

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Then run:

```text
build_exe.bat
```

The Windows build target is:

```text
dist/Logo to STL Tool 8.1.exe
```

## Testing

See:

[TEST_REPORT_V8_1.md](TEST_REPORT_V8_1.md)

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

## License

MIT License. See [LICENSE](LICENSE).
