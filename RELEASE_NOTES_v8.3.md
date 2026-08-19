# Logo to STL Tool v8.3

V8.3 focuses on robust vector-gap filling and hard BG protection.

## No More Vector-Gap Abort

The previous strict geometry logic could show an error such as:

```text
Local partitioning found a vectorization gap ... with no physically adjacent print color
```

V8.3 no longer aborts solely because contour simplification created a leftover region.

Instead, the cleaned raster assignment is used as the source of truth.

## Gap Filling Priority

Each vector gap is resolved in this order:

1. direct 4-neighbor raster majority
2. raster color majority directly under the gap
3. first non-empty expanding local raster ring
4. true shared vector boundary
5. nearest existing vector color as a deterministic emergency fallback

The expanding search stops at the first radius containing a print color, so a farther color cannot beat a closer local one.

## BG Protection

BG is now protected at every relevant stage.

- smoothed BG pixels are removed from the raster candidate map
- BG never participates in color votes
- the master `total` geometry has BG subtracted before color-gap repair
- every repaired color geometry is clipped back to `total`
- the final validity repair is also constrained to `total`

A dedicated regression test assigned an enclosed opaque color region explicitly to `BG`.

Result:

```text
BG overlap with all print colors: 0
Missing printable partition area: 0
Overlap between print colors: 0
```

## Polygon Validity Fix

Stress testing found another rare issue unrelated to color ownership:

```text
TopologyException: unable to assign free hole to a shell
```

It occurred after aggressive smoothing / simplification combined with non-uniform physical scaling.

V8.3 now performs polygonal `make_valid` normalization:

- before the final partition is returned
- again after final Width / Height scaling when needed

The repaired partition is reconstructed overlap-free inside the BG-protected master geometry.

## Stress Tests

### Pure geometry matrix

Tested:

```text
3 contour modes
× 4 smoothing values
× 4 simplification values
= 48 aggressive geometry combinations
```

All passed with:

```text
Valid polygons
Missing area ~0
Overlap area ~0
BG overlap ~0
```

### Realistic preview stress

A complex five-color logo with an enclosed transparent hole was tested with four increasingly aggressive geometry settings.

All four STL Previews completed successfully.

### Real STL export

A complete multi-color export at:

```text
85.702 × 28.54 mm
```

completed successfully.

Generated STL files were loaded back through `trimesh`.

### GUI

Verified:

- threaded Analyze
- Calculate
- Final Preview
- threaded STL Preview
- no old vector-gap Preview error
- STL Preview mouse-wheel binding

## Preserved Improvements

V8.3 retains:

- V8.2 raster despeckle before and after AUTO
- strict AUTO edge adjacency
- local tiny-island cleanup
- exact final Width / Height
- compact-display layout
- improved Windows EXE build script

## Windows

Run:

```text
build_exe.bat
```

Output:

```text
dist/Logo to STL Tool 8.3.exe
```

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
