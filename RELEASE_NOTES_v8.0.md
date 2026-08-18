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



## AUTO Adjacency Regression Fix

AUTO distribution has been rewritten to remove the remaining non-adjacent color regression.

The previous resolver used 8-neighbor connectivity and a global safety fallback. This meant a diagonally placed color could be treated as a neighbor, and an isolated AUTO region could eventually be assigned to a remote color.

The corrected behavior is strict:

- only colors sharing a real pixel **edge** with the AUTO region are valid candidates
- diagonal-only colors are ignored
- separate AUTO patches that touch only diagonally remain separate
- propagation is geodesic inside the same AUTO region
- a non-touching color elsewhere in the logo can never jump into the region
- isolated AUTO is left unresolved instead of being guessed

If isolated AUTO remains, the application now reports the number of isolated regions and pixels and asks for manual assignment.

### Regression reproduction

A test case was built where one AUTO pixel touched:

- Red by a real edge
- White by a real edge
- Blue only diagonally

The previous V8 resolver selected **Blue** because diagonal contact was accepted and the AUTO RGB was blue-like.

The corrected resolver selected only **Red or White**. Blue was completely excluded from the candidate set.

Additional tests verified that:

- a nearby but non-touching color never receives AUTO pixels
- diagonally touching AUTO patches do not contaminate one another
- safely resolved AUTO rows are removed from STL export
- isolated AUTO is blocked before STL Preview / Export instead of being guessed
- Manual → Calculate follows the same strict rule
- a 1600 × 1600 synthetic AUTO stress test with many components completed successfully
