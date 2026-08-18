# Logo to STL Tool

A Windows desktop application for converting raster logos into separate STL files for multi-color 3D printing.

## Current Version

**V8 Final / v8.0 — corrected final build**

## Main Features

- Automatic color detection and grouping
- Manual Brush, Line, Fill Area and Eyedropper
- AUTO assignment for anti-aliased / transition pixels
- BG handling for true background regions
- Real-time responsive Manual brush
- Exact final STL Width / Height controls
- Adjustable contour mode, geometry resolution and smoothing
- Local color-aware STL partitioning
- STL geometry and integrity preview
- Final Preview on a configurable target surface
- Separate STL files for each print color
- Complete cutout and clearance STL
- Mouse-wheel scrolling throughout compact-display workflows

## Final STL Dimensions

`Logo Width (mm)` and `Logo Height (mm)` control the final STL footprint.

With **Lock aspect ratio** enabled:

- Width updates Height automatically
- Height updates Width automatically
- proportional scaling is preserved
- the final vector geometry uses the requested Width exactly

With the lock disabled, Width and Height are independent and both are applied exactly.

## Corrected V8 Final — Final Preview

The Final Preview has been hardened:

- it refreshes immediately after a successful color analysis
- it refreshes after Manual → Calculate
- it no longer leaves a stale `Analyze colors first.` message when analysis exists
- German decimal-comma input such as `68,7` and `97,5` is accepted
- logos larger than the target surface can still be displayed safely
- true background / BG holes remain transparent so the target-surface color shows through
- invalid values now produce a meaningful preview message instead of silently returning

## Corrected V8 Final — Tiny Wrong-Color Islands

Two geometry safeguards are now combined.

### 1. Stronger local gap assignment

Microscopic vectorization gaps primarily follow the color with the strongest shared local boundary.

A weak raster vote can no longer override a much stronger neighboring color and create a tiny wrong-color speck.

### 2. Min. Island Area now cleans embedded color specks

`Min. Island Area (mm²)` now also applies to tiny color components inside the logo.

A sub-threshold embedded island is transferred to the strongest stable neighboring print color. Its exact geometry is transferred rather than deleted, so:

- no STL gap is created
- no overlap is created
- the overall cutout silhouette remains unchanged

A truly isolated small detail with no neighboring print color is preserved.

## Manual Workflow

Manual edits remain draft-only until **Calculate** is pressed.

While editing:

- the Manual preview updates immediately
- the committed STL state remains unchanged

When Calculate is pressed:

- Manual changes are committed
- AUTO regions are resolved
- STL Preview and Final Preview use the calculated state

## Compact Display Support

- collapsible Quick Workflow
- draggable Preview / Colors divider
- visible resize grip
- scrollable left settings
- scrollable detected-color list
- mouse-wheel scrolling in STL Preview
- responsive logo preview

## Typical Workflow

1. Load a logo
2. Click **(Start) Analyze Colors**
3. Assign detected colors
4. Fine-tune in **Manual**
5. Click **Calculate**
6. Review **STL Preview**
7. Review **Final Preview** if desired
8. Click **(Finish) Generate STLs**

## Build the Windows EXE

Run:

```text
build_exe.bat
```

Output:

```text
dist/Logo to STL Tool 8.0.exe
```

## Testing

See [TEST_REPORT_V8_FINAL.md](TEST_REPORT_V8_FINAL.md).

## Development

Created by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.

## License

MIT License. See [LICENSE](LICENSE).
