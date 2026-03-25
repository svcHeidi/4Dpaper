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
    p.add_argument("--all-times",  action="store_true",
               help="Export scalar .bin files for all time steps (mutually exclusive with --time)")
    p.add_argument("--scalar",     default=None,
               help="Scalar field name to extract in --all-times mode")
    return p.parse_args()


def _die(msg: str) -> None:
    print(f"[pvsm_render] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    args = _parse_args()

    pvsm_path = Path(args.pvsm)
    if not pvsm_path.exists():
        _die(f"PVSM file not found: {pvsm_path}")

    if args.all_times and args.time is not None:
        _die("--all-times and --time are mutually exclusive")
    if args.all_times and not args.scalar:
        _die("--all-times requires --scalar <field_name>")

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
    elif args.all_times:
        scene = GetAnimationScene()
        all_times = list(scene.TimeKeeper.TimestepValues)
        if not all_times:
            _die("--all-times: no time steps found in animation scene")
        scene.AnimationTime = all_times[0]
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

    # Ensure client-side data is populated before we try to read it.
    last_source.UpdatePipeline()

    # 5. Export geometry as .vtu using client-side VTK XML writers.
    # ParaView's SaveData / CreateWriter may not have .vtu registered depending on
    # the pipeline output type (e.g. vtkMultiBlockDataSet from OpenFOAM readers).
    # We bypass the factory entirely: pull the data from the algorithm's client-side
    # object, flatten multiblock datasets if needed, and write with vtkmodules directly.
    print(f"[pvsm_render] Saving geometry -> {out_vtu}", file=sys.stderr)
    try:
        import vtkmodules.vtkIOXML as xmlio
        import vtkmodules.vtkFiltersCore as vtkfc

        csobj = last_source.SMProxy.GetClientSideObject()
        if csobj is None:
            _die(f"GetClientSideObject() returned None for {last_source.GetXMLName()}")

        raw = csobj.GetOutputDataObject(0)
        if raw is None:
            _die("Pipeline output data object is None; UpdatePipeline may be needed.")

        data_class = raw.GetClassName()
        print(f"[pvsm_render] Output data type: {data_class}", file=sys.stderr)

        # Flatten composite/multiblock to a single dataset
        if "MultiBlock" in data_class or "Composite" in data_class:
            # Collect all leaf blocks, preferring UnstructuredGrid
            leaves = []
            it = raw.NewIterator()
            it.InitTraversal()
            while not it.IsDoneWithTraversal():
                ds = it.GetCurrentDataObject()
                if ds is not None and ds.GetNumberOfPoints() > 0:
                    leaves.append(ds)
                it.GoToNextItem()
            if not leaves:
                _die("MultiBlock dataset has no non-empty leaf blocks.")
            if len(leaves) == 1:
                data = leaves[0]
            else:
                # Append all blocks into one UnstructuredGrid
                appender = vtkfc.vtkAppendFilter()
                for leaf in leaves:
                    appender.AddInputDataObject(leaf)
                appender.MergePointsOff()
                appender.Update()
                data = appender.GetOutput()
        else:
            data = raw

        data_class = data.GetClassName()
        if "PolyData" in data_class:
            writer = xmlio.vtkXMLPolyDataWriter()
            out_actual = out_vtu.with_suffix(".vtp")
        else:
            writer = xmlio.vtkXMLUnstructuredGridWriter()
            out_actual = out_vtu

        writer.SetFileName(str(out_actual))
        writer.SetInputDataObject(data)
        ret = writer.Write()
        if ret == 0:
            _die(f"VTK XML writer returned 0 (failure) for {out_actual}")

        if out_actual != out_vtu:
            import shutil
            shutil.copy2(str(out_actual), str(out_vtu))

    except SystemExit:
        raise
    except Exception as exc:
        _die(f"Could not write geometry to {out_vtu}: {exc}")

    # Verify the file has geometry
    if not out_vtu.exists():
        _die(f"Geometry file was not produced: {out_vtu}")
    vtu_text = out_vtu.read_text(errors="replace")
    if 'NumberOfPoints="0"' in vtu_text:
        _die(f"Geometry file has 0 points: {out_vtu}")

    # 5b. All-times: extract per-step scalar .bin files
    if args.all_times:
        import vtkmodules.vtkFiltersCore as _vtkfc
        fig_id_stem = Path(args.out_vtu).stem.replace("-pipeline", "")
        figures_dir = Path(args.out_vtu).parent
        scalar_name = args.scalar

        def _extract_scalar_array(leaf_src):
            """Return the scalar array as a list of floats from the leaf source output."""
            csobj = leaf_src.SMProxy.GetClientSideObject()
            raw = csobj.GetOutputDataObject(0)
            data_class = raw.GetClassName()
            if "MultiBlock" in data_class or "Composite" in data_class:
                blocks = []
                it = raw.NewIterator()
                it.InitTraversal()
                while not it.IsDoneWithTraversal():
                    ds = it.GetCurrentDataObject()
                    if ds is not None and ds.GetNumberOfPoints() > 0:
                        blocks.append(ds)
                    it.GoToNextItem()
                if not blocks:
                    return None
                if len(blocks) == 1:
                    data = blocks[0]
                else:
                    app = _vtkfc.vtkAppendFilter()
                    for b in blocks:
                        app.AddInputDataObject(b)
                    app.MergePointsOff()
                    app.Update()
                    data = app.GetOutput()
            else:
                data = raw
            vtk_arr = data.GetPointData().GetArray(scalar_name)
            if vtk_arr is None:
                return None
            n = vtk_arr.GetNumberOfTuples()
            return [vtk_arr.GetValue(j) for j in range(n)]

        for i, t in enumerate(all_times):
            scene.AnimationTime = t
            view.Update()
            last_source.UpdatePipeline()
            arr = _extract_scalar_array(last_source)
            if arr is None:
                _die(f"--all-times: scalar '{scalar_name}' not found at time {t} (step {i})")
            import struct as _struct
            bin_path = figures_dir / f"{fig_id_stem}-scalars-t{i}.bin"
            bin_path.write_bytes(_struct.pack(f"<{len(arr)}f", *arr))
            print(f"[pvsm_render] t={t}: wrote {len(arr)} values -> {bin_path.name}",
                  file=sys.stderr)

        times_json = figures_dir / f"{fig_id_stem}-times.json"
        times_json.write_text(json.dumps([str(t) for t in all_times]))
        print(f"[pvsm_render] Wrote {len(all_times)} time steps -> {times_json.name}",
              file=sys.stderr)

        # Move to last time for screenshot
        scene.AnimationTime = all_times[-1]
        view.Update()
        last_source.UpdatePipeline()

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
