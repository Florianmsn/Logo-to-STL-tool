# Logo to STL Tool — V8 Final Test Report

**Version:** v8.0 — corrected final build  
**Test date:** 2026-08-18

## Corrected Final Preview Regression

Passed:

- real threaded color analysis
- Final Preview automatically refreshes after analysis
- Final Preview remains valid after Manual → Calculate
- German decimal commas `68,7` and `97,5` are parsed correctly
- settings can be saved while comma-formatted values are present
- a logo larger than the target surface still renders safely
- stale `Analyze colors first.` text is removed after a valid analysis

Result:

```text
FINAL_PREVIEW_REGRESSION_OK
```

## Tiny Wrong-Color Island Regression

A synthetic stress test contained a valid main green region, an intentionally isolated green detail and dozens of embedded green micro-specks.

Corrected result:

```text
Green islands: 2
```

Those two islands are the intended main green region and the intentionally isolated detail.

The embedded micro-specks were reassigned to their surrounding stable colors.

Partition integrity:

```text
Missing area: 0
Overlap area: 0
```

Core output:

```text
MICRO_ISLAND_REGRESSION_OK {'schwarz': 1, 'weiss': 1, 'gruen': 2}
PARTITION_OK 0.0 0.0
REAL_EXPORT_OK
```

## Exact Size / Export Regression

Passed:

- exact `80 × 30 mm` final vector preview
- zero measured partition gaps
- zero measured partition overlap
- complete STL export
- output STL files exist
- clearance export still works

## Preserved V8 Regressions

The corrected source retains the V8 features already tested previously, including:

- exact Width / Height sizing
- aspect-ratio synchronization
- Manual draft / Calculate separation
- real-time brush path
- AUTO handling
- local vector-gap assignment
- STL Preview mouse-wheel scrolling
- compact-display layout
- background worker safeguards

## Windows EXE

The Windows executable must still be built on Windows with:

```text
build_exe.bat
```

The build target remains:

```text
dist/Logo to STL Tool 8.0.exe
```

## Result

All targeted corrected-V8 regression tests passed.
