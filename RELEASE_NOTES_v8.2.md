# Logo to STL Tool v8.2

V8.2 fixes the remaining isolated wrong-color pixel problem at an earlier point in the pipeline.

## Root Cause

The previous fixes concentrated on AUTO and vector/STL geometry.

The newly supplied close-up examples showed another failure mode: Blue or Black micro-components could already exist in the **calculated raster color assignment** before the STL vector partition was built.

That meant vector-gap repair alone could not fully solve the problem.

## Raster-Level Despeckle

`Calculate` now runs:

```text
tiny-color cleanup
→ AUTO resolution
→ tiny-color cleanup
→ commit Manual result
```

The cleaned raster is immediately visible in Manual and is the same state used by the later previews/export.

## Local-Only Replacement

A tiny wrong-color component can move only to a stable print color that shares a real 4-neighbor edge with it.

Selection priority:

1. most shared horizontal/vertical pixel edges
2. local stable-color majority only for an exact tie

Never used as candidates:

- diagonal-only colors
- remote colors
- RGB-nearest colors
- globally largest colors
- other tiny/unstable noise components

Small isolated details surrounded by background are preserved.

## Before AUTO

The cleanup runs before AUTO as well.

This prevents a stray one-pixel Blue/Black/Red artifact from becoming a valid AUTO seed and spreading that color into an otherwise correct transition area.

## Geometry Safety Net Remains

V8.2 retains the V8.1 strict local vector rules:

- direct 4-neighbor raster majority for vector gaps
- true vector-edge contact when required
- no global/remote fallback
- Min. Island Area vector cleanup
- zero-gap / zero-overlap partition invariants

## Regression Tests

A screenshot-like logical raster contained:

- a large legitimate Blue region
- four isolated one/two-pixel Blue artifacts along a Black/White boundary

With a physical `Min. Island Area` corresponding to 8 source pixels:

```text
Blue components before: 5
Blue components after:  1
Changed pixels:         8
```

The legitimate Blue region remained unchanged.

A GUI Calculate test confirmed that those pixels are removed from the **committed Manual raster itself**, not only from STL Preview.

The status reported:

```text
Calculation complete. AUTO was resolved and 8 stray pixel(s)
in approximately 4 tiny region(s) were reassigned...
```

## Attached Close-Up Regression

The supplied close-up images were also analyzed as zoomed raster examples.

Using a zoom-normalized component threshold:

- isolated Blue blocks were removed from both examples
- the first example's separated Black micro-components collapsed back to the single legitimate Black region
- surrounding White/Green/Black/Red main regions were preserved

The screenshots are zoomed displays rather than original source rasters, so this test verifies component/neighborhood behavior rather than physical mm² calibration.

## Broader Regression Suite

V8.2 also passed:

- all 12 contour/smoothing geometry combinations
- exact `73.25 × 31.75 mm` sizing
- real `80 × 30 mm` multi-color STL export
- partition missing area ~0
- partition overlap area ~0
- STL round-trip loading
- threaded Analyze
- threaded STL Preview
- Final Preview
- STL Preview mouse-wheel scrolling
- strict AUTO diagonal exclusion

## Windows

Build with:

```text
build_exe.bat
```

Output:

```text
dist/Logo to STL Tool 8.2.exe
```

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
