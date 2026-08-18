# Logo to STL Tool — V8.1 Test Report

**Version:** v8.1  
**Test date:** 2026-08-18

## 1. Reproduced Wrong-Color Gap Regression

A synthetic vector-gap case reproduced the remaining V8 behavior.

Local direct raster edge counts:

```text
Black: 33
Red:   11
```

The previous V8 gap owner selected:

```text
Red
```

V8.1 selected:

```text
Black
```

This verifies that the strongest direct local neighborhood now has priority.

## 2. Direct Raster Micro-Island Rules

Verified:

- tiny Red component embedded in Black -> Black
- tiny Red component at a Black / White border -> majority Black
- Green touching only diagonally -> ignored
- tiny Red detail isolated in true background -> preserved
- legitimate large Red region -> preserved

## 3. Full Micro-Speck Partition Regression

Synthetic input:

- Black base
- White region
- legitimate Red region
- legitimate Green region
- 160 injected one-pixel Red artifacts

Final V8.1 geometry:

```text
Black islands: 1
White islands: 1
Red islands:   1
Green islands: 1
```

Partition integrity:

```text
Missing area: 0
Overlap area: 0
```

## 4. High-Resolution Cleanup Performance

Synthetic raster:

```text
1600 × 1600 px
2,500 injected micro-specks
```

Measured in the automated environment:

```text
Cleanup time: ~0.20 s
Remaining injected specks outside legitimate areas: 0
```

The cleanup processes each tiny component in its local bounding box instead of allocating an image-sized mask per component.

## 5. Geometry Matrix

Tested all 12 combinations:

```text
Contour mode:
- Straight / crisp
- Smooth curves
- Maximum detail

Edge smoothing:
- 0.00 mm
- 0.10 mm
- 0.22 mm
- 0.45 mm
```

All cases passed with:

```text
Exact requested Width / Height
Missing area < numerical tolerance
Overlap area < numerical tolerance
```

## 6. Real STL Export

A complete multi-color export was generated and verified.

Passed:

- separate color STL files
- complete cutout STL
- clearance STL
- exact requested dimensions
- partition integrity metadata
- exported files exist
- all generated STL files load successfully through `trimesh`

## 7. AUTO Regression

Verified:

- Red / White sharing true pixel edges are valid AUTO candidates
- Blue touching only diagonally is excluded
- isolated AUTO remains unresolved
- no remote-color AUTO fallback
- Manual Calculate uses the same strict AUTO rules

## 8. GUI Regression

Passed:

- application title `Logo to STL Tool 8.1`
- compact-display default sections
- resize cursor only on the resize grip
- threaded Analyze
- Final Preview after analysis
- bidirectional Width / Height sync while aspect ratio is locked
- independent Width / Height when unlocked
- Manual draft remains separate until Calculate
- Calculate commits Manual changes
- threaded STL Preview
- STL Preview mouse-wheel bindings
- Final Preview remains functional

## 9. Explicit Background

Verified that an enclosed `BG` / true-background region remains a hole in the final total geometry.

## 10. Strict Local-Only Policy

The V8.1 gap owner contains no:

- global-distance fallback
- global-largest-color fallback
- RGB remote-color fallback
- non-touching near-color fallback

A gap is assigned only when physical local adjacency can be proven.

If no local owner can be proven, geometry generation stops with a descriptive error instead of silently choosing a wrong color.

## Result

All targeted V8.1 regression tests passed.
