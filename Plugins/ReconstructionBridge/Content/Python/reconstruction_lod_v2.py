"""Editor-only PPQ / TripoSR LOD pipeline for ReconstructionBridge.

Copy next to reconstruction_bridge.py. Configure once with configure_lod_v2().
The existing ExMesh training/export and legacy Auto LOD commands are unchanged.
"""

import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import unreal
import reconstruction_bridge as bridge


_SETTINGS = (Path(unreal.Paths.convert_relative_path_to_full(
    unreal.Paths.project_saved_dir())) / "ExMeshLOD" / "settings.json")
_STATE_FILE = _SETTINGS.parent / "latest_state.json"
_job = None
_tick_handle = None


def _absolute(value, label):
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path: {path}")
    return path


def configure_lod_v2(exmesh_python, exmesh_root, triposr_python=None,
                     triposr_repo=None, hf_home=None, u2net_home=None,
                     work_dir=None):
    """Persist local machine paths. Run again to change them."""
    data = {
        "exmesh_python": str(_absolute(exmesh_python, "ExMeshPython")),
        "exmesh_root": str(_absolute(exmesh_root, "ExMeshRoot")),
        "work_dir": str(_absolute(
            work_dir or _SETTINGS.parent, "WorkDir")),
    }
    for key, value in (("triposr_python", triposr_python),
                       ("triposr_repo", triposr_repo),
                       ("hf_home", hf_home), ("u2net_home", u2net_home)):
        if value:
            data[key] = str(_absolute(value, key))
    _SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    unreal.log(f"LOD v2 settings saved: {_SETTINGS}")
    return data


def _settings():
    if not _SETTINGS.is_file():
        raise RuntimeError("Configure paths first: configure_lod_v2(...)")
    data = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    for key in ("exmesh_python", "exmesh_root", "work_dir"):
        if not data.get(key):
            raise RuntimeError(f"Missing LOD v2 setting: {key}")
    return data


def _exists(path):
    path = Path(path)
    return path.is_file() and path.stat().st_size > 0


def _files(*paths):
    return all(_exists(p) for p in paths)


def _triple(obj):
    obj = Path(obj)
    return (obj, obj.with_suffix(".mtl"),
            obj.with_name(obj.stem + "_texture.png"))


def _fingerprint(*paths):
    digest = hashlib.sha256()
    for path in paths:
        path = Path(path)
        stat = path.stat()
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii"))
    return digest.hexdigest()[:20]


def _save_state():
    if _job is None:
        return
    public = {k: v for k, v in _job.items()
              if k not in ("process", "lines", "queue", "steps", "log_handle")}
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(public, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def get_lod_v2_status(show_dialog=False):
    state = ({k: v for k, v in _job.items()
              if k in ("stage", "mode", "output_dir", "asset_path", "error")}
             if _job else json.loads(_STATE_FILE.read_text(encoding="utf-8"))
             if _STATE_FILE.is_file() else {"stage": "NOT_STARTED"})
    if show_dialog:
        tail = "\n".join(list(_job["lines"])[-15:]) if _job else ""
        unreal.EditorDialog.show_message(
            "LOD v2 Status",
            f"Stage: {state.get('stage')}\n{state.get('error', '')}\n\n{tail}",
            unreal.AppMsgType.OK)
    return state


def _stop_tick():
    global _tick_handle
    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None


def _finish(stage, error=None):
    _job["stage"] = stage
    _job["error"] = error
    _save_state()
    _stop_tick()
    if error:
        unreal.log_error(f"LOD v2 {stage}: {error}")
        detail = "\n".join(list(_job["lines"])[-20:])
        unreal.EditorDialog.show_message("LOD v2 Failed",
                                         f"{error}\n\n{detail}",
                                         unreal.AppMsgType.OK)
    else:
        unreal.log(f"LOD v2 complete: {_job['asset_path']}")
        unreal.EditorDialog.show_message("LOD v2 Complete",
                                         _job["asset_path"], unreal.AppMsgType.OK)


def cancel_lod_v2():
    if _job is None or _job.get("stage") in ("COMPLETE", "FAILED", "CANCELLED"):
        return False
    proc = _job.get("process")
    if proc and proc.poll() is None:
        proc.terminate()
    log = _job.get("log_handle")
    if log and not log.closed:
        log.flush()
        log.close()
    _finish("CANCELLED")
    return True


def _reader(process, events):
    try:
        for line in iter(process.stdout.readline, ""):
            events.put(line.rstrip("\r\n"))
    except (OSError, ValueError) as error:
        events.put(f"[reader] {error}")
    finally:
        if process.stdout:
            process.stdout.close()


def _run_step(step):
    config = _job["config"]
    root = Path(config["exmesh_root"])
    script = root / step["script"]
    python = Path(config["triposr_python"] if step["stage"] == "TRIPOSR"
                  else config["exmesh_python"])
    for path in (script, python):
        if not _exists(path):
            raise FileNotFoundError(path)
    for path in step["outputs"]:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
    if step["stage"] == "PPQ":
        Path(str(step["outputs"][0])).with_suffix(".json").unlink(missing_ok=True)
    command = [str(python), "-u", str(script), *step["args"]]
    env = os.environ.copy()
    if step["stage"] == "TRIPOSR":
        for setting, name in (("hf_home", "HF_HOME"),
                              ("u2net_home", "U2NET_HOME")):
            if config.get(setting):
                env[name] = config[setting]
    _job["stage"] = step["stage"]
    _job["step"] = step["name"]
    _job["log_path"] = str(Path(_job["output_dir"]) /
                           (step["name"] + ".log"))
    _job["log_handle"] = open(_job["log_path"], "w", encoding="utf-8")
    try:
        _job["process"] = subprocess.Popen(
            command, cwd=str(root), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        _job["log_handle"].close()
        raise
    _job["queue"] = queue.Queue()
    threading.Thread(target=_reader, args=(_job["process"], _job["queue"]),
                     daemon=True).start()
    _job["started_step_at"] = time.monotonic()
    _save_state()
    unreal.log(f"LOD v2 {step['name']} started (PID {_job['process'].pid})")


def _tick(_delta):
    if _job is None or _job.get("stage") in ("FAILED", "COMPLETE", "CANCELLED"):
        return
    try:
        events = _job.get("queue")
        while events:
            try:
                line = events.get_nowait()
            except queue.Empty:
                break
            _job["lines"].append(line)
            _job["log_handle"].write(line + "\n")
            unreal.log(f"LOD v2 [{_job['step']}] {line}")
        _job["log_handle"].flush()
        process = _job["process"]
        code = process.poll()
        if code is None or not events.empty():
            return
        _job["log_handle"].close()
        step = _job["steps"][_job["index"]]
        if code != 0 or not _files(*step["outputs"]):
            missing = [str(p) for p in step["outputs"] if not _exists(p)]
            raise RuntimeError(f"{step['name']} exit={code}; missing={missing}")
        _job["index"] += 1
        if _job["index"] == len(_job["steps"]):
            _job["stage"] = "IMPORT"
            _save_state()
            _import_meshes()
            _finish("COMPLETE")
        else:
            _run_step(_job["steps"][_job["index"]])
    except Exception as error:
        _finish("FAILED", str(error))


def _add_step(steps, stage, name, script, args, outputs):
    steps.append(dict(stage=stage, name=name, script=script,
                      args=[str(a) for a in args],
                      outputs=[str(p) for p in outputs]))


def _start(mode, source, ratios, screen_sizes, refine_mode, scale, height=None,
           ue_transform=None):
    global _job, _tick_handle
    if _job and _job.get("stage") not in ("COMPLETE", "FAILED", "CANCELLED"):
        raise RuntimeError("An LOD v2 job is already running")
    legacy = getattr(bridge, "_auto_lod_pipeline", None)
    if legacy and legacy.get("stage") in ("EXMESH", "WILDMESH", "IMPORTING"):
        active = legacy.get("process")
        if active is None or active.poll() is None:
            raise RuntimeError("Finish the existing Auto LOD job before starting v2")
    config = _settings()
    root = _absolute(config["exmesh_root"], "ExMeshRoot")
    python = _absolute(config["exmesh_python"], "ExMeshPython")
    if not root.is_dir() or not _exists(python):
        raise FileNotFoundError("ExMeshRoot or ExMeshPython is missing")
    ratios = [float(r) for r in ratios]
    if not ratios or any(not 0.0 < r <= 1.0 for r in ratios):
        raise ValueError("Ratios must be between 0 and 1")
    screen_sizes = [float(s) for s in screen_sizes]
    if (len(screen_sizes) != len(ratios) + 1
            or screen_sizes[0] != 1.0
            or any(not 0 < s < 1 for s in screen_sizes[1:])
            or any(a <= b for a, b in zip(screen_sizes, screen_sizes[1:]))):
        raise ValueError("Screen sizes must be decreasing: [1.0, ...]")
    if refine_mode not in ("off", "tex", "full"):
        raise ValueError("Refine mode: off, tex, or full")
    if float(scale) <= 0:
        raise ValueError("Scale must be positive")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    work = _absolute(config["work_dir"], "WorkDir") / f"{mode}_{stamp}"
    work.mkdir(parents=True, exist_ok=False)
    steps = []
    if mode == "accurate":
        # Keep the exact exported file for PPQ, simplification, and refinement.
        original_obj, original_texture, model = source
        model = _absolute(model, "model_dir")
        original_obj = _absolute(original_obj, "original_obj")
        original_texture = _absolute(original_texture, "original_texture")
        cameras = model / "cameras.json"
    else:
        photo = _absolute(source, "photo")
        if not _exists(photo):
            raise FileNotFoundError(photo)
        for key in ("triposr_python", "triposr_repo"):
            if not config.get(key):
                raise RuntimeError(f"Configure {key} for quick mode")
        if not Path(config["triposr_repo"]).is_dir():
            raise FileNotFoundError(config["triposr_repo"])
        original_obj = work / "quick" / "mesh.obj"
        original_texture = work / "quick" / "mesh_texture.png"
        complete = original_obj.with_suffix(".complete.json")
        args = ["--repo", config["triposr_repo"], "--image", photo,
                "--output", original_obj, "--up", "z"]
        if height is not None:
            if float(height) <= 0:
                raise ValueError("Height must be positive")
            args += ["--height", height]
        _add_step(steps, "TRIPOSR", "triposr",
                  "quick_generation/triposr_generate.py", args, [complete])
        cameras = None
    if mode == "accurate" and _exists(cameras):
        fingerprint = _fingerprint(original_obj, original_texture, cameras)
        energy = work.parent / "cache" / "ppq" / f"{fingerprint}.npy"
        energy.parent.mkdir(parents=True, exist_ok=True)
        if not _files(energy, energy.with_suffix(".json")):
            _add_step(steps, "PPQ", "ppq",
                      "simplification/photometric_quadric_weights.py",
                      ["--mesh", original_obj, "--texture", original_texture,
                       "--cameras", cameras, "--output", energy],
                      [energy, energy.with_suffix(".json")])
        method = "photometric"
    else:
        if mode == "accurate":
            unreal.log_warning("cameras.json missing: using Wild LOD")
        method = "wild"
        energy = None
    results = []
    for i, ratio in enumerate(ratios, 1):
        lod = work / f"lod{i}.obj"
        args = ["--input", original_obj, "--texture", original_texture,
                "--output", lod, "--ratio", ratio, "--method", method]
        if energy is not None:
            args += ["--face_energy", energy]
        _add_step(steps, "SIMPLIFY", f"lod{i}_simplify",
                  "simplification/wild_simplify_xatlas_verified.py", args,
                  [*_triple(lod), lod.with_suffix(".statistics.json"),
                   lod.with_suffix(".input_topology.json")])
        if refine_mode == "off":
            results.append((lod, lod.with_name(lod.stem + "_texture.png")))
        else:
            refined = work / f"lod{i}_refined.obj"
            _add_step(steps, "REFINE", f"lod{i}_refine",
                      "simplification/appearance_refine.py",
                      ["--reference", original_obj, "--reference_texture", original_texture,
                       "--input", lod, "--input_texture", lod.with_name(lod.stem + "_texture.png"),
                       "--output", refined, "--mode", refine_mode],
                      [refined.with_suffix(".complete.json")])
            results.append((refined, refined.with_name(refined.stem + "_texture.png")))
    from collections import deque
    _job = dict(stage="STARTING", mode=mode, output_dir=str(work),
                original_obj=str(original_obj), original_texture=str(original_texture),
                results=[(str(o), str(t)) for o, t in results],
                ratios=ratios, screen_sizes=screen_sizes, scale=float(scale),
                ue_transform=ue_transform,
                config=config, steps=steps, index=0, lines=deque(maxlen=50))
    _save_state()
    try:
        _run_step(steps[0])
        _tick_handle = unreal.register_slate_post_tick_callback(_tick)
    except Exception as error:
        _finish("FAILED", str(error))
        raise
    return str(work)


def start_accurate_lod_v2(model_dir, iteration=100, ratios=(0.5, 0.25, 0.1),
                          screen_sizes=(1.0, 0.35, 0.15, 0.05),
                          refine_mode="full", scale=100.0, ue_transform=None):
    """Use an existing ExMesh run after train.py and export_obj.py complete.

    ue_transform: optional {"R", "t", "s"} from
    reconstruction_bridge._compute_ue_transform (up/ground/height alignment);
    when given it replaces the plain scale for the Unreal copies.
    """
    model = _absolute(model_dir, "model_dir")
    export = model / "export"
    original = export / f"mesh_iter_{int(iteration)}.obj"
    texture = export / f"mesh_iter_{int(iteration)}.png"
    if not _files(original, texture):
        raise FileNotFoundError(f"Export original OBJ/PNG first: {original}")
    return _start_accurate(model, original, texture, ratios, screen_sizes,
                           refine_mode, scale, ue_transform)


def _start_accurate(model, obj, texture, ratios, sizes, refine, scale, ue_transform=None):
    # A tuple is used only to carry the immutable export pair into _start.
    return _start("accurate", (obj, texture, model), ratios, sizes, refine, scale,
                  ue_transform=ue_transform)


def start_quick_lod_v2(photo, height_cm=100, ratios=(0.1,),
                       screen_sizes=(1.0, 0.35), refine_mode="full"):
    return _start("quick", photo, ratios, screen_sizes, refine_mode, 1.0,
                  height=height_cm)


def _import_meshes():
    state = _job
    original = Path(state["original_obj"])
    texture = Path(state["original_texture"])
    if not _files(original, texture):
        raise FileNotFoundError("Original OBJ/texture missing during import")
    for obj_text, tex_text in state["results"]:
        if not _files(*_triple(obj_text), tex_text):
            raise FileNotFoundError(f"LOD triple incomplete: {obj_text}")
    tag = Path(state["output_dir"]).name
    folder = "/Game/ReconstructionBridge/AutoLOD"
    scale = state["scale"]

    def import_pair(obj, tex, name):
        if state.get("ue_transform"):
            scaled = bridge._create_transformed_obj_for_unreal(Path(obj), state["ue_transform"])
        else:
            scaled = bridge._create_scaled_obj_for_unreal(Path(obj), scale=scale)
        # This makes a copy for UE; PPQ/refine always receive the untouched export OBJ.
        tex_asset = next((x for x in bridge._import_external_asset(
            Path(tex), folder, "T_" + name) if isinstance(x, unreal.Texture2D)), None)
        mesh_asset = next((x for x in bridge._import_external_asset(
            Path(scaled), folder, "SM_" + name) if isinstance(x, unreal.StaticMesh)), None)
        if not mesh_asset or not tex_asset:
            raise RuntimeError(f"Unreal import failed: {name}")
        bridge.create_material_for_selected_wildmesh(mesh_asset, tex_asset)
        return mesh_asset

    base = import_pair(original, texture, tag)
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for index, (obj, tex) in enumerate(state["results"], 1):
        source = import_pair(Path(obj), Path(tex), f"{tag}_LOD{index}")
        if subsystem.set_lod_from_static_mesh(base, index, source, 0, False) < 0:
            raise RuntimeError(f"Could not create LOD{index}")
    if not subsystem.set_lod_screen_sizes(base, state["screen_sizes"]):
        raise RuntimeError("Could not set LOD screen sizes")
    count = subsystem.get_lod_count(base)
    if count != len(state["results"]) + 1:
        raise RuntimeError(f"Unexpected LOD count: {count}")
    state["asset_path"] = base.get_path_name()
    for asset in unreal.EditorAssetLibrary.list_assets(folder, recursive=False,
                                                       include_folder=False):
        if tag in asset and not unreal.EditorAssetLibrary.save_asset(asset):
            raise RuntimeError(f"Could not save: {asset}")
    unreal.EditorAssetLibrary.sync_browser_to_objects([state["asset_path"]])
    _save_state()
