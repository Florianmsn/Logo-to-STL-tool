# Logo-to-STL Tool

A Windows desktop tool for converting raster logos into separate STL files for multi-color 3D printing.

The application detects colors in a logo, lets you group them into printable color regions, provides manual pixel-level cleanup, and generates separate STL files for each color together with matching cutout geometry.

## Features

* Load PNG, JPG, JPEG, WEBP, and BMP logos
* Automatic color detection and grouping
* Assign detected colors to print groups
* `AUTO` mode for distributing anti-aliased or transitional pixels to neighboring print colors
* `BG` mode for removing regions from the printable logo
* Manual editor with:

  * Brush
  * Line
  * Fill Area
  * Eyedropper
  * Undo
  * Reset
  * Zoom and pan
* Adjustable geometry quality and contour smoothing
* Final STL geometry preview
* Target surface preview
* Separate STL export for every print color
* Complete cutout STL
* Negative / clearance STL
* Automatic project-specific output folder
* English UI and output filenames

## Typical Workflow

1. Load your logo and click **(Start) Analyze Colors**.
2. Click **Show** next to a detected color, then assign it to a print group using the color buttons.
3. Use **AUTO** for transition or anti-aliasing shades that should be distributed between neighboring print colors.
4. Open the **Manual** tab and click **Calculate** to resolve AUTO pixels.
5. Make any pixel-level corrections if needed, then click **Calculate** again.
6. Review the result in **STL Preview**.
7. Click **(Finish) Generate STLs**.

## Output Files

For a project named `Monopoly`, the output folder is automatically created as:

```text
Monopoly\_STL/
```

Example files:

```text
Monopoly\_color\_01\_black.stl
Monopoly\_color\_02\_white.stl
Monopoly\_complete\_cutout.stl
Monopoly\_negative\_clearance\_0\_00mm.stl
```

The tool attempts to generate watertight/manifold geometry. If a remaining topology issue is detected, the STL is still exported and the application warns you that your slicer's repair function may be required.

## Run from Source

### Requirements

* Windows 10 or Windows 11
* Python 3
* Packages listed in `requirements.txt`

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Then start the application:

```bash
python logo\_inlay\_app.py
```

You can also use:

```text
start\_app.bat
```

## Build a Standalone Windows EXE

Run:

```text
build\_exe.bat
```

The script installs the required Python packages and uses PyInstaller to create a standalone Windows executable.

The resulting file will be placed in:

```text
dist/
```

The compiled EXE can then be copied to another Windows PC without requiring a separate Python installation.

## Notes

* The tool is designed primarily for flat logo inlays and multi-color 3D printing.
* Raster logos with clear color regions usually produce the best results.
* Very small details, compression artifacts, and anti-aliasing may require manual cleanup.
* STL repair warnings do not necessarily mean the model is unusable. Many slicers can automatically repair minor mesh issues.

## Development

This project was created by **Florian Hofmann Hesse** with development assistance from **ChatGPT by OpenAI**.

ChatGPT was used throughout the project for code generation, debugging, UI refinement, testing ideas, and workflow development.

## License

This project is licensed under the **License**.

See [LICENSE](LICENSE) for details.

