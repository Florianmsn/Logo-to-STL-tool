# Logo to STL Tool — V8 Final

**Version:** v8.0  
**Build:** Corrected Final

## Final Preview Fix

- Final Preview refreshes after Analyze Colors
- Final Preview refreshes after Manual → Calculate
- stale `Analyze colors first.` placeholder no longer remains after a valid analysis
- German decimal-comma values are accepted
- oversized logos can still be rendered relative to the target surface
- BG / non-printing regions remain transparent in the placement preview
- invalid preview inputs now show an explicit message

## Tiny Color-Island Fix

The STL partitioning received two additional protections:

- vectorization gaps now favor the strongest shared local boundary
- weak one-pixel raster votes cannot override a much stronger geometric neighbor
- `Min. Island Area (mm²)` now applies to embedded color islands
- sub-threshold embedded specks are reassigned to the strongest stable neighboring print color
- isolated details without a neighboring print color remain intact
- reassignment transfers the exact geometry, preserving a gap-free / overlap-free partition

## Regression Result

A synthetic stress case was created with:

- one legitimate main green region
- one intentionally isolated green detail
- dozens of tiny green artifacts embedded in another color

Before the new island cleanup the test produced **52 green islands**.

The corrected geometry produces **2 green islands**:

- the real main green region
- the deliberately isolated green detail

Missing partition area: **0**  
Overlap area: **0**

The prior UNO wrong-color regression also remains fixed.

## Preserved V8 Improvements

- exact final STL Width / Height
- bidirectional aspect-ratio synchronization
- shared Preview / Export geometry path
- real-time Manual brush
- Calculate-only commit behavior
- AUTO resolution on Calculate
- compact-display layout
- mouse-wheel scrolling in STL Preview
- threaded analysis, preview and export safeguards

## Windows

Build with:

```text
build_exe.bat
```

Result:

```text
dist/Logo to STL Tool 8.0.exe
```

---

Developed by **Florian Hesse** with development assistance from **ChatGPT by OpenAI**.
