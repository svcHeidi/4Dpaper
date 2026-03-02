"""
ParaView headless rendering injector.

MUST be run with pvpython (ParaView's bundled Python), NOT the project venv.

Usage:
    /Applications/ParaView-5.13.3.app/Contents/bin/pvpython \\
        dashboard/paraview_render.py \\
        <pvsm_path> <foam_path> <camera_json_path> <output_png> [width] [height]

Example:
    pvpython dashboard/paraview_render.py \\
        /path/to/example_state.pvsm \\
        /path/to/Niederer.foam \\
        state/camera_state.json \\
        state/render_output.png \\
        3840 2160
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def inject_and_render(
    pvsm_path: str,
    foam_path: str,
    camera_state_path: str,
    output_path: str,
    resolution: tuple[int, int] = (3840, 2160),
) -> None:
    """
    Load a ParaView state file, inject the target foam path and camera,
    then render a high-resolution screenshot.

    Parameters
    ----------
    pvsm_path:
        Absolute path to the master .pvsm state file.
    foam_path:
        Absolute path to the .foam marker file for the target case.
    camera_state_path:
        Path to camera_state.json (written by the "Save Camera" button).
    output_path:
        Where to write the output PNG.
    resolution:
        (width, height) in pixels. Default is 4K (3840×2160).
    """
    # Deferred import: only works inside pvpython
    from paraview.simple import (
        FindSource,
        GetActiveViewOrCreate,
        LoadState,
        SaveScreenshot,
    )

    # 1. Load the master pipeline state
    print(f"[paraview_render] Loading state: {pvsm_path}")
    LoadState(
        pvsm_path,
        LoadStateDataFileOptions="Use File Names From State",
    )

    # 2. Redirect the OpenFOAMReader to the target case
    reader = FindSource("OpenFOAMReader")
    if reader is None:
        raise RuntimeError(
            "OpenFOAMReader proxy not found in the loaded PVSM state. "
            "Ensure the master PVSM was saved with an OpenFOAM reader active."
        )
    reader.FileName = str(foam_path)
    reader.UpdatePipeline()
    print(f"[paraview_render] Data path set to: {foam_path}")

    # 3. Apply camera state from JSON
    with open(camera_state_path) as fh:
        cam = json.load(fh)

    view = GetActiveViewOrCreate("RenderView")
    view.CameraPosition   = cam["position"]
    view.CameraFocalPoint = cam["focal_point"]
    view.CameraViewUp     = cam["view_up"]
    if "parallel_scale" in cam:
        view.CameraParallelScale = cam["parallel_scale"]
    print(f"[paraview_render] Camera applied from: {camera_state_path}")

    # 4. Headless render at target resolution
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    SaveScreenshot(
        output_path,
        ImageResolution=list(resolution),
        OverrideColorPalette="PrintBackground",
    )
    print(
        f"[paraview_render] Rendered {resolution[0]}x{resolution[1]} px"
        f" → {output_path}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(
            "Usage: pvpython paraview_render.py "
            "<pvsm> <foam> <camera_json> <output_png> [W] [H]"
        )
        sys.exit(1)

    _res = (
        (int(sys.argv[5]), int(sys.argv[6]))
        if len(sys.argv) > 6
        else (3840, 2160)
    )
    inject_and_render(
        pvsm_path=sys.argv[1],
        foam_path=sys.argv[2],
        camera_state_path=sys.argv[3],
        output_path=sys.argv[4],
        resolution=_res,
    )
