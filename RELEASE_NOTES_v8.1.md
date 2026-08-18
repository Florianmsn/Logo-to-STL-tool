# Logo to STL Tool v8.1

V8.1 focuses on eliminating the remaining wrong-color micro-pixels and micro-islands that could appear during STL geometry generation.

## Strict Local Raster Cleanup

Tiny color components are now cleaned before vectorization.

A small component below `Min. Island Area` may be reassigned only to a stable color sharing a real **4-neighbor pixel edge**.

The color with the highest number of shared edges wins.

If two valid neighboring colors have exactly the same edge count, the local stable-color majority is used as a tie-breaker.

Diagonal or non-touching colors can never become candidates.

## Strict Local Vector-Gap Filling

Microscopic gaps created by contour simplification now use the cleaned raster partition as the primary local reference.

The gap owner is selected from:

1. direct 4-neighbor raster colors around the gap
2. the most represented direct neighbor
3. shared vector-boundary length only as a tie-breaker between those same candidates
4. a true shared vector edge if the raster representation is too small to decide

Removed from the pipeline:

- global nearest-color fallback
- RGB-based remote fallback
- largest-color fallback
- non-touching "near color" fallback

If no physically adjacent owner exists, V8.1 reports the unresolved gap instead of inserting a random color.

## Reproduced V8 Regression

A direct regression test was created in which:

- Black was the dominant local neighbor
- Red was a weaker local neighbor
- the older V8 logic still selected Red because an internal raster vote overrode the stronger local boundary

Measured direct raster neighborhood:

```text
Black: 33
Red:   11
```

Result:

```text
Previous V8 owner: Red
V8.1 owner:        Black
```

## Micro-Speck Stress Test

A synthetic logo contained:

- one legitimate Red region
- one legitimate Green region
- 160 injected one-pixel Red artifacts

V8.1 result:

```text
Black islands: 1
White islands: 1
Red islands:   1
Green islands: 1
Missing area:  0
Overlap area:  0
```

## Large Raster Cleanup Performance

A `1600 × 1600` test image with 2,500 injected color specks was processed.

Automated test result in the available environment:

```text
Cleanup time: approximately 0.20 seconds
Remaining injected specks outside legitimate areas: 0
```

## Geometry Regression Matrix

Passed all combinations of:

- Straight / crisp contours
- Smooth curves
- Maximum detail
- smoothing `0.00 mm`
- smoothing `0.10 mm`
- smoothing `0.22 mm`
- smoothing `0.45 mm`

Total:

```text
12 geometry combinations
```

All retained:

```text
Missing partition area: ~0
Overlap area: ~0
```

## Preserved Functionality

V8.1 also retains:

- strict AUTO edge-adjacency behavior
- real-time Manual brush
- Calculate-only commit behavior
- exact STL Width / Height
- threaded Analyze / STL Preview workflow
- Final Preview
- STL Preview mouse-wheel scrolling
- compact-display controls
- complete STL / cutout / clearance export

## Windows

Build with:

```text
build_exe.bat
```

Output:

```text
dist/Logo to STL Tool 8.1.exe
```

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
