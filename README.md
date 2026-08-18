# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

## Current Version

**v8.2**

## Main Features

- Automatic color detection and grouping
- Manual color assignment
- `AUTO` for anti-aliased / transition pixels
- `BG` for true background areas
- Manual Brush, Line, Fill Area and Eyedropper
- Real-time responsive Manual brush
- Undo, Reset, zoom and pan
- Exact final STL Width / Height controls
- Adjustable geometry resolution, smoothing and contour mode
- STL geometry and integrity preview
- Final Preview on a configurable target surface
- Separate STL export for each print color
- Complete cutout STL
- Negative / clearance STL
- Compact-display friendly layout and mouse-wheel scrolling

## V8.2 — Raster Despeckle Before STL Geometry

V8.2 fixes a deeper source of isolated wrong-color pixels.

Previous releases concentrated on:

- strict AUTO adjacency
- vector-gap ownership
- tiny vector islands

Those protections happen at or after geometry generation.

The remaining issue could already exist **inside the calculated Manual color raster itself**: a one/few-pixel Blue, Black, Red, etc. component could survive color grouping and later become a real STL island.

V8.2 therefore moves the important cleanup earlier.

### Calculate now performs three stages

When **Calculate** is pressed:

1. tiny already-assigned wrong-color components are cleaned
2. AUTO is resolved
3. the tiny-color cleanup runs a second time

The cleaned result becomes the actual committed Manual raster.

You can therefore see the correction immediately in the **Manual** tab after Calculate. STL Preview and STL export then start from the same cleaned raster.

## Strict Local Despeckle Rules

A small color component below `Min. Island Area (mm²)` can be reassigned only when another stable print color shares a real horizontal or vertical pixel edge with it.

For every tiny component:

1. all true 4-neighbor edge contacts are counted
2. only directly touching stable print colors are candidates
3. the color with the highest shared-edge count wins
4. if the edge count is exactly tied, the local stable-color majority is used
5. diagonal-only colors are ignored
6. colors elsewhere in the logo are ignored

A small detail surrounded only by true background is preserved.

Tiny unstable components are not allowed to vote for one another, which prevents chains of noise pixels from simply changing into another wrong color.

## Why the V8.1 Geometry Cleanup Was Not Enough

`Min. Island Area` was already used as a geometry safety net.

However, if the wrong-color pixel was visible in the Manual raster, waiting until vectorization meant:

- Manual still looked wrong
- an incorrect pixel could become an AUTO neighbor/seed
- later smoothing and contour operations had to repair a problem that should have been removed earlier

V8.2 uses the same physical island-area concept at the source-raster stage and keeps the later geometry cleanup as an additional safety net.

## AUTO Behavior

AUTO remains strict:

- only colors sharing a real horizontal/vertical pixel edge with the connected AUTO region are candidates
- diagonal-only colors are ignored
- non-touching colors elsewhere in the logo cannot enter the AUTO region
- propagation stays inside the same connected AUTO region
- isolated AUTO is reported instead of being guessed

The new raster cleanup also runs **before AUTO**, so a tiny stray Blue/Black/Red pixel cannot incorrectly become an AUTO seed if it can first be identified as a local artifact.

## Min. Island Area

`Min. Island Area (mm²)` now affects both:

- **Calculate / Manual raster cleanup**
- final STL geometry cleanup

The physical threshold is converted into source-image pixels using the requested final Logo Width / Height.

If your logo intentionally contains extremely small embedded details, reduce `Min. Island Area`.

## Exact STL Dimensions

`Logo Width (mm)` and `Logo Height (mm)` control the final STL footprint.

With **Lock aspect ratio** enabled:

- Width updates Height
- Height updates Width
- scaling remains proportional

With the lock disabled, Width and Height are independent.

Transparent source-image margins do not reduce the requested final dimensions.

## Compact Display Support

- collapsible Quick Workflow
- draggable Preview / Colors divider
- visible resize grip
- automatically resizing logo preview
- scrollable settings
- scrollable detected-color list
- mouse-wheel scrolling in STL Preview

## Typical Workflow

1. Load a logo
2. Click **(Start) Analyze Colors**
3. Assign detected colors
4. Use AUTO where useful
5. Correct pixels in **Manual**
6. Click **Calculate**
7. Check the cleaned Manual result
8. Review **STL Preview**
9. Review **Final Preview**
10. Click **(Finish) Generate STLs**

## Build the Windows EXE

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run:

```text
build_exe.bat
```

Output:

```text
dist/Logo to STL Tool 8.2.exe
```

## Testing

See:

[TEST_REPORT_V8_2.md](TEST_REPORT_V8_2.md)

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

## License

MIT License. See [LICENSE](LICENSE).
