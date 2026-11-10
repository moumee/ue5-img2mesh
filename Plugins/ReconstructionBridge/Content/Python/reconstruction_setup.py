"""One-click environment setup for ReconstructionBridge.

Checks what the plugin needs outside Unreal (ExMesh submodule, the "exmesh" and
"rb_prep" conda envs, COLMAP) and runs Setup/setup_exmesh_env.bat in a console
window to install whatever is missing. The only manual prerequisite is Miniconda.

Entry points:
    Tools > Reconstruction Bridge Setup...    -> run_setup()
    editor startup (once per session)         -> prompt_if_missing()
"""

import os
import shutil
import subprocess
from pathlib import Path

import unreal

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SETUP_BAT = PLUGIN_ROOT / "Setup" / "setup_exmesh_env.bat"
EXMESH_ROOT = PLUGIN_ROOT / "ThirdParty" / "ExMesh"
MINICONDA_URL = "https://docs.conda.io/en/latest/miniconda.html"
TITLE = "Reconstruction Bridge Setup"

if "_startup_tick" not in globals():
    _startup_tick = None


def _skip_prompt_flag():
    saved = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()))
    return saved / "ReconstructionBridge" / "skip_setup_prompt"


def find_conda():
    """Path of conda.bat, or None (same search order as setup_exmesh_env.bat)."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    for base in (
        home / "miniconda3",
        home / "anaconda3",
        home / "miniforge3",
        local / "miniconda3",
        Path("C:/ProgramData/miniconda3"),
        Path("C:/ProgramData/anaconda3"),
    ):
        candidate = base / "condabin" / "conda.bat"
        if candidate.is_file():
            return candidate
    found = shutil.which("conda.bat")
    return Path(found) if found else None


def missing_components():
    """Human readable list of what is not installed yet (empty = ready)."""
    import reconstruction_prepare

    exmesh_python = reconstruction_prepare._env_path("EXMESH_PYTHON") or (
        reconstruction_prepare._find_conda_env_python("exmesh")
    )
    missing = []
    if not (EXMESH_ROOT / "train.py").is_file():
        missing.append("ExMesh source (git submodule)")
    if not exmesh_python.is_file():
        missing.append('ExMesh training env ("exmesh" conda env)')
    if not reconstruction_prepare.prep_python().is_file():
        missing.append('Preprocessing env ("rb_prep" conda env)')
    if reconstruction_prepare.colmap_executable() is None:
        missing.append("COLMAP")
    return missing


def _ask_install_miniconda():
    answer = unreal.EditorDialog.show_message(
        TITLE,
        "Miniconda is required but was not found.\n\n"
        "Install Miniconda (default options, 'Just Me'), then run\n"
        "Tools > Reconstruction Bridge Setup... again.\n\n"
        "Open the Miniconda download page now?",
        unreal.AppMsgType.YES_NO,
    )
    if answer == unreal.AppReturnType.YES:
        unreal.SystemLibrary.launch_url(MINICONDA_URL)


def launch_setup(target="all"):
    """Run setup_exmesh_env.bat in a new console window (non-blocking)."""
    subprocess.Popen(
        ["cmd.exe", "/k", "call", str(SETUP_BAT), target],
        cwd=str(SETUP_BAT.parent),
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    unreal.log(f"ReconstructionBridge: started {SETUP_BAT.name} {target}")


def run_setup():
    """Menu entry: install or repair everything the plugin needs."""
    if find_conda() is None:
        _ask_install_miniconda()
        return
    missing = missing_components()
    if missing:
        status = "Missing:\n  - " + "\n  - ".join(missing)
    else:
        status = "Everything is already installed. Running setup again repairs/updates it."
    answer = unreal.EditorDialog.show_message(
        TITLE,
        status
        + "\n\nSetup opens a console window and downloads about 8-10 GB "
        "(PyTorch x2, COLMAP). It takes 10-30 minutes.\n"
        "Requires an NVIDIA GPU (RTX 20-40 series).\n\n"
        "When the console says \"Setup finished.\", restart the editor.\n\n"
        "Start setup now?",
        unreal.AppMsgType.YES_NO,
    )
    if answer == unreal.AppReturnType.YES:
        launch_setup("all")


def prompt_if_missing():
    """Ask once per editor session if something is missing (deferred to the first tick)."""
    global _startup_tick
    if _startup_tick is not None:
        return

    def _on_tick(_delta):
        global _startup_tick
        unreal.unregister_slate_post_tick_callback(_startup_tick)
        _startup_tick = None
        try:
            _prompt_now()
        except Exception as exc:
            unreal.log_warning(f"ReconstructionBridge: setup check failed: {exc}")

    _startup_tick = unreal.register_slate_post_tick_callback(_on_tick)


def _prompt_now():
    missing = missing_components()
    if not missing:
        return
    unreal.log_warning(
        "ReconstructionBridge: not installed yet ("
        + ", ".join(missing)
        + "). Run Tools > Reconstruction Bridge Setup..."
    )
    flag = _skip_prompt_flag()
    if flag.is_file():
        return
    answer = unreal.EditorDialog.show_message(
        TITLE,
        "Reconstruction Bridge is not set up on this PC yet.\n\nMissing:\n  - "
        + "\n  - ".join(missing)
        + "\n\nSet it up now?\n\n"
        "Yes: start setup   No: don't ask again   Cancel: ask next time\n"
        "(You can always run Tools > Reconstruction Bridge Setup...)",
        unreal.AppMsgType.YES_NO_CANCEL,
    )
    if answer == unreal.AppReturnType.YES:
        run_setup()
    elif answer == unreal.AppReturnType.NO:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("delete this file to get the setup prompt again\n", encoding="utf-8")
