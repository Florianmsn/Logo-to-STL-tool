# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

## Current Version

**v8.3**

## Main Features

- Automatic color detection and grouping
- Manual color assignment
- `AUTO` for anti-aliased / transition pixels
- `BG` for true background areas
- Manual Brush, Line, Fill Area and Eyedropper
- Real-time responsive Manual brush
- Undo, Reset, zoom and pan
- Exact final STL Width / Height
- Adjustable geometry resolution, smoothing and contour mode
- STL geometry and integrity preview
- Final Preview on a configurable target surface
- Separate STL export for each print color
- Complete cutout STL
- Negative / clearance STL
- Compact-display friendly layout and mouse-wheel scrolling

## V8.3 — Source-of-Truth Gap Filling

V8.3 changes how vectorization gaps are repaired.

Earlier strict versions could stop STL Preview / Export when contour simplification produced a gap that had no immediately detectable vector neighbor.

V8.3 no longer aborts solely because of such a gap.

The cleaned raster assignment is treated as the source of truth.

### Gap-owner priority

For every leftover vector region:

1. **Direct 4-neighbor raster ring**  
   The most represented print color directly around the gap wins.

2. **Raster colors directly under the gap**  
   If vector simplification created a gap over pixels that already have a clean print-color assignment, that underlying raster assignment is used.

3. **First non-empty expanding local raster ring**  
   The search expands one source pixel at a time and stops as soon as any print color is found. A farther color can therefore never beat a closer local color.

4. **True shared vector edge**  
   Used when rasterization cannot represent a sub-pixel boundary.

5. **Nearest existing vector piece**  
   Emergency deterministic fallback only, so Preview / Export does not abort because of a contour pathology.

The first three stages are raster-local majority decisions.

## BG Is Hard-Protected

`BG` is never a candidate for print-color gap filling.

The same smoothed BG mask used to remove geometry from the master body is also removed from all raster voting.

After all gap and island repair, every print-color geometry is clipped again to the BG-protected master `total`.

Therefore a region explicitly assigned to `BG` cannot be restored by:

- AUTO
- raster despeckle
- vector-gap filling
- tiny-island repair
- polygon validity repair

## Polygon Validity Repair

Aggressive smoothing, contour simplification and non-uniform Width / Height scaling can expose rare Shapely ring self-intersections.

V8.3 now:

- runs `make_valid` on polygonal geometry when required
- discards non-polygonal repair fragments
- rebuilds an exact non-overlapping color partition
- clips all repaired colors to the BG-protected master geometry
- performs another validity normalization after non-uniform physical scaling

This prevents errors such as:

```text
TopologyException: unable to assign free hole to a shell
```

## Raster Despeckle

The V8.2 raster cleanup remains active.

When **Calculate** is pressed:

1. tiny already-assigned wrong-color components are cleaned
2. AUTO is resolved
3. tiny-color cleanup runs again
4. the cleaned Manual raster is committed

A tiny component may move only to a stable print color that shares a real horizontal or vertical pixel edge with it.

The color with the strongest shared-edge count wins.

## AUTO

AUTO remains strict:

- only real horizontal / vertical edge neighbors are candidates
- diagonal-only colors are ignored
- remote colors are ignored
- propagation stays inside the same connected AUTO region
- isolated AUTO is reported instead of being globally guessed

## Min. Island Area

`Min. Island Area (mm²)` affects both:

- calculated Manual raster cleanup
- final vector/STL island cleanup

Reduce the value if a logo intentionally contains extremely small embedded print details.

## Exact STL Dimensions

`Logo Width (mm)` and `Logo Height (mm)` describe the final STL footprint.

With **Lock aspect ratio** enabled:

- Width updates Height
- Height updates Width
- scaling remains proportional

With the lock disabled, Width and Height are independent.

## Compact Display Support

- collapsible Quick Workflow
- draggable Preview / Colors divider
- visible resize grip
- responsive logo preview
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
7. Review **STL Preview**
8. Review **Final Preview**
9. Click **(Finish) Generate STLs**

## Build the Windows EXE

Run:

```text
build_exe.bat
```

The builder automatically checks:

1. `py -3`
2. `python`
3. `python3`

and reports success only if a new executable was actually created.

Output:

```text
dist/Logo to STL Tool 8.3.exe
```

## Testing

See:

[TEST_REPORT_V8_3.md](TEST_REPORT_V8_3.md)

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

## License

MIT License. See [LICENSE](LICENSE).
