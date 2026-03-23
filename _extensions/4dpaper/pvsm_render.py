#!/usr/bin/env python3
"""
pvpython script: load a ParaView state file, export pipeline geometry and screenshot.

Run with pvpython (NOT regular python):
    pvpython pvsm_render.py --pvsm FILE --out-vtu FILE --out-png FILE [options]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay a PVSM and export geometry + screenshot.")
    p.add_argument("--pvsm",       required=True,  help="Path to .pvsm file")
    p.add_argument("--out-vtu",    required=True,  help="Output path for .vtu geometry")
    p.add_argument("--out-png",    required=True,  help="Output path for PNG screenshot")
    p.add_argument("--data",       default=None,   help="Override OpenFOAMReader FileName")
    p.add_argument("--time",       default=None,   help="Timestep: float, 'last', or 'mid'")
    p.add_argument("--camera",     default=None,   help="Path to camera JSON")
    p.add_argument("--resolution", nargs=2, type=int, default=[3840, 2160], metavar=("W", "H"))
    return p.parse_args()


def _die(msg: str) -> None:
    print(f"[pvsm_render] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    args = _parse_args()

    pvsm_path = Path(args.pvsm)
    if not pvsm_path.exists():
        _die(f"PVSM file not found: {pvsm_path}")

    out_vtu = Path(args.out_vtu)
    out_png = Path(args.out_png)
    out_vtu.parent.mkdir(parents=True, exist_ok=True)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    # Import paraview here so the script can be imported (for CLI tests) without pvpython.
    try:
        from paraview.simple import (
            LoadState, GetSources, GetAnimationScene,
            GetActiveViewOrCreate, SaveData, SaveScreenshot, Render,
        )
        import paraview.servermanager as sm
    except ImportError:
        _die("paraview.simple not available -- run with pvpython, not python.")

    # 1. Load PVSM
    print(f"[pvsm_render] Loading {pvsm_path}", file=sys.stderr)
    LoadState(str(pvsm_path))

    # 2. Patch OpenFOAMReader path if --data given
    if args.data:
        data_path = str(Path(args.data).resolve())
        sources = GetSources()
        patched = False
        for (name, sid), proxy in sources.items():
            if proxy.GetXMLName() == "OpenFOAMReader":
                proxy.FileName = data_path
                proxy.UpdatePipeline()
                print(f"[pvsm_render] Patched OpenFOAMReader '{name}' -> {data_path}", file=sys.stderr)
                if patched:
                    print(f"[pvsm_render] WARNING: multiple OpenFOAMReader proxies found; patched first only.", file=sys.stderr)
                patched = True
                break
        if not patched:
            print("[pvsm_render] WARNING: --data given but no OpenFOAMReader found in PVSM.", file=sys.stderr)

    # 3. Set animation time if --time given
    if args.time is not None:
        scene = GetAnimationScene()
        t = args.time.strip()
        if t == "last":
            scene.GoToLast()
        elif t == "mid":
            mid = (scene.StartTime + scene.EndTime) / 2.0
            scene.AnimationTime = mid
        else:
            try:
                scene.AnimationTime = float(t)
            except ValueError:
                _die(f"--time must be 'last', 'mid', or a float; got: {t!r}")
        view = GetActiveViewOrCreate("RenderView")
        view.Update()

    # 4. Find last visible filter (leaf source in visible pipeline)
    view = GetActiveViewOrCreate("RenderView")
    reps = list(view.Representations)
    visible_reps = [r for r in reps if getattr(r, "Visibility", 0) == 1]
    if not visible_reps:
        _die("No visible representations found in PVSM render view.")

    # Map rep -> its source proxy
    visible_sources = {}
    for rep in visible_reps:
        try:
            src = rep.Input[0]
            if src is not None:
                visible_sources[id(src)] = src
        except (IndexError, AttributeError):
            pass

    if not visible_sources:
        _die("Could not determine source proxies for visible representations.")

    # Find leaf: a visible source whose proxy id is not the Input of any other visible source
    all_input_ids = set()
    for src in visible_sources.values():
        try:
            inp = src.Input[0]
            if inp is not None:
                all_input_ids.add(id(inp))
        except (IndexError, AttributeError):
            pass

    leaves = [s for key, s in visible_sources.items() if key not in all_input_ids]
    if not leaves:
        # Fallback: take the first visible source
        leaves = list(visible_sources.values())

    last_source = leaves[-1]  # deepest leaf if multiple
    print(f"[pvsm_render] Using source: {last_source.GetXMLName()}", file=sys.stderr)

    # 5. Export geometry as .vtu
    print(f"[pvsm_render] Saving geometry -> {out_vtu}", file=sys.stderr)
    SaveData(str(out_vtu), proxy=last_source)

    # Verify the file has geometry
    vtu_text = out_vtu.read_text(errors="replace") if out_vtu.exists() else ""
    if 'NumberOfPoints="0"' in vtu_text or not out_vtu.exists():
        _die(f"SaveData produced an empty mesh (0 points): {out_vtu}")

    # 6. Apply camera override if --camera given
    if args.camera:
        cam_path = Path(args.camera)
        if cam_path.exists():
            try:
                cam = json.loads(cam_path.read_text())
                view.CameraPosition  = cam["position"]
                view.CameraFocalPoint = cam["focal_point"]
                view.CameraViewUp    = cam["view_up"]
                Render()
                print(f"[pvsm_render] Applied camera from {cam_path}", file=sys.stderr)
            except Exception as e:
                print(f"[pvsm_render] WARNING: could not apply camera JSON: {e}", file=sys.stderr)
        else:
            print(f"[pvsm_render] WARNING: camera file not found: {cam_path}", file=sys.stderr)

    # 7. Screenshot
    print(f"[pvsm_render] Saving screenshot -> {out_png}", file=sys.stderr)
    SaveScreenshot(str(out_png), view, ImageResolution=args.resolution)
    print("[pvsm_render] Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
