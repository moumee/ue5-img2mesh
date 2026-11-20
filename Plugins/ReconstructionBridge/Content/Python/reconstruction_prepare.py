"""Automatic dataset preparation (COLMAP + masks + Depth Anything 3).

If the dataset path given to the ReconstructionBridge window is a video file
or a folder of photos (instead of a prepared ExMesh dataset), the bridge calls
resolve_or_prepare(), which runs prepare_dataset_external.py in the "rb_prep"
conda env in the background and continues the original action when it is done.

Prepared datasets are cached in <Project>/Saved/ReconstructionBridge/datasets/
and reused as long as the source file/folder has not changed.

Manual use from the Unreal Python console:
    import reconstruction_prepare as rp
    rp.start_prepare(r"D:\\videos\\bear.mp4", num_frames=80)
    rp.cancel_prepare()
"""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import unreal

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
PREPARE_SCRIPT = Path(__file__).resolve().parent / "prepare_dataset_external.py"
MARKER_NAME = "prepared.json"
MIN_MARKER_VERSION = 3  # v2 added mesh.ply, v3 switched to DA3-BASE
LOG_NAME = "prepare.log"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}

POLL_SECONDS = 0.5

if "_job" not in globals():
    _job = None
    _tick_handle = None
    _last_poll = 0.0


# -----------------------------------------------------------------------------
# configuration
# -----------------------------------------------------------------------------

def _env_path(name):
    value = os.environ.get(name, "").strip().strip('"')
    return Path(value) if value else None


def _find_conda_env_python(env_name):
    home = Path.home()
    bases = []
    conda_exe = _env_path("CONDA_EXE")
    if conda_exe is not None:
        bases.append(conda_exe.parent.parent)
    for base in ("miniconda3", "anaconda3", "miniforge3", "mambaforge"):
        bases.append(home / base)
        bases.append(Path("C:/ProgramData") / base)
    bases.append(home / "AppData" / "Local" / "miniconda3")
    bases.append(home / ".conda")
    for base in bases:
        candidate = base / "envs" / env_name / "python.exe"
        if candidate.is_file():
            return candidate
    return home / "miniconda3" / "envs" / env_name / "python.exe"


def prep_python():
    return _env_path("RB_PREP_PYTHON") or _find_conda_env_python("rb_prep")


def colmap_executable():
    explicit = _env_path("COLMAP_EXE")
    if explicit is not None:
        return explicit
    bundled = PLUGIN_ROOT / "ThirdParty" / "COLMAP"
    for candidate in (bundled / "COLMAP.bat", bundled / "bin" / "colmap.exe"):
        if candidate.is_file():
            return candidate
    return None


def datasets_root():
    explicit = _env_path("RB_DATASETS_ROOT")
    if explicit is not None:
        return explicit
    try:
        saved = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
        return Path(saved) / "ReconstructionBridge" / "datasets"
    except Exception:
        return PLUGIN_ROOT.parents[1] / "Saved" / "ReconstructionBridge" / "datasets"


# -----------------------------------------------------------------------------
# input classification
# -----------------------------------------------------------------------------

def _clean(path_text):
    text = str(path_text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()
    return text


def is_prepared_dataset(path):
    path = Path(path)
    return (path / "sparse" / "0").is_dir() and (path / "images").is_dir()


def classify_input(path):
    """'dataset' | 'video' | 'photos' | None"""
    path = Path(path)
    if path.is_file():
        return "video" if path.suffix.lower() in VIDEO_EXTS else None
    if not path.is_dir():
        return None
    if is_prepared_dataset(path):
        return "dataset"
    if any(p.suffix.lower() in IMAGE_EXTS for p in path.iterdir() if p.is_file()):
        return "photos"
    return None


def dataset_dir_for(source):
    source = Path(source).resolve()
    digest = hashlib.md5(str(source).lower().encode("utf-8")).hexdigest()[:8]
    return datasets_root() / f"{source.stem}_{digest}"


def _source_mtime(source):
    source = Path(source)
    if source.is_file():
        return source.stat().st_mtime
    mtimes = [p.stat().st_mtime for p in source.iterdir() if p.is_file()]
    return max(mtimes + [source.stat().st_mtime])


def cached_dataset(source):
    """Return the prepared dataset folder for source if it is complete and up to date."""
    out = dataset_dir_for(source)
    marker = out / MARKER_NAME
    if not marker.is_file() or not is_prepared_dataset(out):
        return None
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return None
    if Path(info.get("source", "")) != Path(source).resolve():
        return None
    if int(info.get("version", 0)) < MIN_MARKER_VERSION or not (out / "mesh.ply").is_file():
        return None
    if info.get("source_mtime_tree") is not None and abs(info["source_mtime_tree"] - _source_mtime(source)) > 1:
        return None
    return out


def check_requirements():
    """List of human readable problems (empty when preprocessing can run)."""
    problems = []
    if not prep_python().is_file():
        problems.append(
            f"Preprocessing Python env not found: {prep_python()}\n"
            "  -> run Tools > Reconstruction Bridge Setup... (or set RB_PREP_PYTHON)"
        )
    if colmap_executable() is None:
        problems.append(
            "COLMAP not found in Plugins/ReconstructionBridge/ThirdParty/COLMAP\n"
            "  -> run Tools > Reconstruction Bridge Setup... (or set COLMAP_EXE)"
        )
    if not PREPARE_SCRIPT.is_file():
        problems.append(f"Missing script: {PREPARE_SCRIPT}")
    return problems


# -----------------------------------------------------------------------------
# entry points used by reconstruction_bridge
# -----------------------------------------------------------------------------

def resolve_or_prepare(dataset_path, on_ready, num_frames=None):
    """Decide what to do with the dataset path typed in the widget.

    Returns (proceed, path):
      (True, path)  -> continue now with path (unchanged input, or a cached
                       prepared dataset for a video / photo folder)
      (False, None) -> preprocessing was started (on_ready(prepared_path) is
                       called when it succeeds) or could not start (error shown)
    """
    if dataset_path is None:
        return True, dataset_path
    text = _clean(dataset_path)
    if not text:
        return True, dataset_path
    kind = classify_input(text)
    if kind in (None, "dataset"):
        return True, dataset_path  # let the bridge validate it as before

    cached = cached_dataset(text)
    if cached is not None:
        unreal.log(f"ReconstructionBridge: using prepared dataset {cached}")
        return True, str(cached)

    start_prepare(text, num_frames=num_frames, on_ready=on_ready)
    return False, None


def use_cached(dataset_path):
    """Map a video / photo folder to its prepared dataset if one exists."""
    if dataset_path is None:
        return dataset_path
    text = _clean(dataset_path)
    if text and classify_input(text) in ("video", "photos"):
        cached = cached_dataset(text)
        if cached is not None:
            return str(cached)
    return dataset_path


def describe_input(dataset_path):
    """Message for the Validate button when the path is raw input; None otherwise."""
    if dataset_path is None:
        return None
    text = _clean(dataset_path)
    kind = classify_input(text) if text else None
    if kind not in ("video", "photos"):
        return None
    cached = cached_dataset(text)
    if cached is not None:
        return None
    lines = [
        f"Input is a {'video' if kind == 'video' else 'photo folder'}, not a prepared dataset.",
        "It will be preprocessed automatically when you start a run:",
        "  frames -> COLMAP -> masks (rembg) -> visual hull -> Depth Anything 3",
        f"Output: {dataset_dir_for(text)}",
    ]
    problems = check_requirements()
    if problems:
        lines += ["", "Cannot preprocess yet:"] + problems
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# background job
# -----------------------------------------------------------------------------

def is_running():
    return _job is not None and _job["process"].poll() is None


def start_prepare(source, num_frames=None, on_ready=None, extra_args=None):
    global _job, _tick_handle

    source = Path(_clean(source))
    if is_running():
        _error("Dataset preprocessing is already running:\n" + str(_job["source"]))
        return False
    kind = classify_input(source)
    if kind not in ("video", "photos"):
        _error(f"Not a video file or photo folder:\n{source}")
        return False
    problems = check_requirements()
    if problems:
        _error("Cannot preprocess dataset:\n\n" + "\n".join(problems))
        return False

    out = dataset_dir_for(source)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / LOG_NAME
    command = [
        str(prep_python()), "-u", "-W", "ignore", str(PREPARE_SCRIPT),
        "--input", str(source),
        "--out", str(out),
        "--colmap", str(colmap_executable()),
    ]
    if num_frames:
        command += ["--num", str(int(num_frames))]
    command += list(extra_args or [])

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PYTHONPATH", None)   # do not leak Unreal's Python paths
    env.pop("PYTHONHOME", None)
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(out),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _job = {
        "process": process,
        "source": source,
        "out": out,
        "log_path": log_path,
        "log_file": log_file,
        "log_pos": 0,
        "on_ready": on_ready,
        "started": time.time(),
        "last_error": None,
    }
    unreal.log(f"ReconstructionBridge: preprocessing started ({kind}) {source}")
    unreal.log(f"ReconstructionBridge: output {out}  (log: {log_path})")
    if _tick_handle is None:
        _tick_handle = unreal.register_slate_post_tick_callback(_tick)
    return True


def cancel_prepare():
    if not is_running():
        unreal.log("ReconstructionBridge: no preprocessing running")
        return
    _job["process"].kill()
    _job["on_ready"] = None
    unreal.log_warning("ReconstructionBridge: preprocessing cancelled")


def _read_new_lines():
    try:
        with _job["log_path"].open("r", encoding="utf-8", errors="replace") as f:
            f.seek(_job["log_pos"])
            data = f.read()
            _job["log_pos"] = f.tell()
    except OSError:
        return
    for line in data.splitlines():
        if line.startswith("[RB] "):
            message = line[5:]
            if message.startswith("ERROR"):
                _job["last_error"] = message
                unreal.log_error(f"ReconstructionBridge prep: {message}")
            elif "WARNING" in message:
                unreal.log_warning(f"ReconstructionBridge prep: {message}")
            else:
                unreal.log(f"ReconstructionBridge prep: {message}")


def _tick(_delta):
    global _job, _tick_handle, _last_poll

    now = time.time()
    if now - _last_poll < POLL_SECONDS:
        return
    _last_poll = now
    if _job is None:
        _stop_tick()
        return
    _read_new_lines()
    code = _job["process"].poll()
    if code is None:
        return

    _read_new_lines()
    job = _job
    _job = None
    _stop_tick()
    try:
        job["log_file"].close()
    except Exception:
        pass

    elapsed = time.time() - job["started"]
    if code == 0 and is_prepared_dataset(job["out"]):
        _write_marker_mtime(job)
        unreal.log(f"ReconstructionBridge: preprocessing finished in {elapsed:.0f}s -> {job['out']}")
        if job["on_ready"] is not None:
            try:
                job["on_ready"](str(job["out"]))
            except Exception as exc:
                unreal.log_error(f"ReconstructionBridge: failed to continue after preprocessing: {exc}")
    else:
        detail = job["last_error"] or f"exit code {code}"
        _error(
            "Dataset preprocessing failed:\n"
            f"{detail}\n\nLog: {job['log_path']}"
        )


def _write_marker_mtime(job):
    marker = job["out"] / MARKER_NAME
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
        info["source_mtime_tree"] = _source_mtime(job["source"])
        marker.write_text(json.dumps(info, indent=2), encoding="utf-8")
    except Exception:
        pass


def _stop_tick():
    global _tick_handle
    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None


def _error(message):
    unreal.log_error(message)
    try:
        unreal.EditorDialog.show_message("Reconstruction Bridge", message, unreal.AppMsgType.OK)
    except Exception:
        pass
