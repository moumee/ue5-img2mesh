import json
import subprocess
from datetime import datetime
from pathlib import Path

import unreal


EXTERNAL_PYTHON = (
    r"C:\Users\pxvne\miniconda3\envs\exmesh\python.exe"
)

EXMESH_ROOT = Path(
    r"C:\Users\pxvne\ExMesh"
)

DATASET_PATH = (
    EXMESH_ROOT
    / "workdir"
    / "DTU"
    / "scan24"
)

RUN_STATE_PATH = (
    EXMESH_ROOT
    / "outputs"
    / "reconstruction_bridge_run_state.json"
)

UI_STATE_PATH = (
    EXMESH_ROOT
    / "outputs"
    / "reconstruction_bridge_ui_state.json"
)

TRAIN_SCRIPT = EXMESH_ROOT / "train.py"

PREFLIGHT_SCRIPT = (
    Path(__file__).with_name(
        "preflight_external.py"
    )
)

CONVERTER_SCRIPT = (
    Path(__file__).with_name(
        "convert_mesh_external.py"
    )
)

UNREAL_UNIT_SCALE = 100.0

UNREAL_DESTINATION_PATH = (
    "/Game/ReconstructionBridge/Generated"
)


def test_connection():
    unreal.log(
        "ReconstructionBridge Python connected"
    )


def test_external_python():
    result = subprocess.run(
        [
            EXTERNAL_PYTHON,
            "--version"
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0
        )
    )

    output = (
        result.stdout.strip()
        or result.stderr.strip()
    )

    if result.returncode == 0:
        unreal.log(
            "External ExMesh Python connected: "
            + output
        )
    else:
        unreal.log_error(
            "External Python failed: "
            + output
        )


def _resolve_dataset_path(dataset_path=None):
    if dataset_path is None:
        return DATASET_PATH

    dataset_text = str(dataset_path).strip()

    if not dataset_text:
        return DATASET_PATH

    if (
        len(dataset_text) >= 2
        and dataset_text[0] == dataset_text[-1]
        and dataset_text[0] in ('"', "'")
    ):
        dataset_text = dataset_text[1:-1].strip()

    if not dataset_text:
        return DATASET_PATH

    return Path(dataset_text)


def validate_dataset(dataset_path=None):
    selected_dataset = _resolve_dataset_path(
        dataset_path
    )

    if not selected_dataset.is_dir():
        message = (
            "Dataset not found:\n"
            + str(selected_dataset)
        )

        unreal.log_error(message)

        unreal.EditorDialog.show_message(
            "Dataset Error",
            message,
            unreal.AppMsgType.OK
        )
        return

    command = [
        EXTERNAL_PYTHON,
        str(PREFLIGHT_SCRIPT),
        "--dataset",
        str(selected_dataset)
    ]

    unreal.log(
        "ReconstructionBridge: "
        "dataset validation started"
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0
        )
    )

    if result.returncode != 0:
        unreal.log_error(
            "Dataset validation failed:\n"
            + result.stderr
        )
        return

    try:
        report = json.loads(
            result.stdout
        )
    except json.JSONDecodeError as error:
        unreal.log_error(
            "Invalid validation report:\n"
            + str(error)
            + "\n"
            + result.stdout
        )
        return

    unreal.log(
        "===== Reconstruction Dataset Report ====="
    )

    unreal.log(
        f"Images: {report['image_count']}"
    )

    unreal.log(
        f"Masks: {report['mask_count']}"
    )

    unreal.log(
        "Image sizes: "
        + ", ".join(
            report["image_sizes"]
        )
    )

    missing_count = (
        report["missing_mask_count"]
    )

    mismatch_count = (
        report["size_mismatch_count"]
    )

    if missing_count > 0:
        unreal.log_error(
            f"Missing masks: {missing_count}"
        )
    else:
        unreal.log(
            "Missing masks: 0"
        )

    if mismatch_count > 0:
        unreal.log_warning(
            f"Size mismatches: {mismatch_count}. "
            "Masks must be resized with "
            "nearest interpolation."
        )
    else:
        unreal.log(
            "Size mismatches: 0"
        )

    unreal.log(
        "========================================="
    )


def _is_process_running(pid):
    try:
        result = subprocess.run(
            [
                "tasklist",
                "/FI",
                f"PID eq {pid}",
                "/FO",
                "CSV",
                "/NH"
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0
            )
        )
    except OSError as error:
        unreal.log_warning(
            f"Could not check process {pid}: {error}"
        )
        return False

    return f'"{pid}"' in result.stdout


def _read_run_state():
    if not RUN_STATE_PATH.is_file():
        return None

    try:
        return json.loads(
            RUN_STATE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        unreal.log_warning(
            f"Could not read previous run state: {error}"
        )
        return None


def register_status_widgets(
    throbber_path,
    status_text_path
):
    """Remember the live EUW widget paths for async status updates."""
    UI_STATE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    ui_state = {
        "throbber_path": str(throbber_path),
        "status_text_path": str(status_text_path)
    }

    UI_STATE_PATH.write_text(
        json.dumps(
            ui_state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    unreal.log(
        "ReconstructionBridge status widgets registered"
    )


def _read_ui_state():
    if not UI_STATE_PATH.is_file():
        return None

    try:
        return json.loads(
            UI_STATE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        unreal.log_warning(
            f"Could not read UI state: {error}"
        )
        return None


def _update_status_widgets(status_text):
    ui_state = _read_ui_state()

    if ui_state is None:
        unreal.log_warning(
            "Status widgets are not registered yet"
        )
        return

    try:
        throbber = unreal.find_object(
            None,
            ui_state.get("throbber_path", "")
        )
        status_widget = unreal.find_object(
            None,
            ui_state.get("status_text_path", "")
        )

        if throbber is not None:
            throbber.set_visibility(
                unreal.SlateVisibility.COLLAPSED
            )
        else:
            unreal.log_warning(
                "Registered ExMesh Throbber was not found"
            )

        if status_widget is not None:
            status_widget.set_text(status_text)
        else:
            unreal.log_warning(
                "Registered ExMesh status TextBlock was not found"
            )

    except Exception as error:
        unreal.log_warning(
            f"Could not update status widgets: {error}"
        )


def _register_completion_monitor(
    process,
    output_dir,
    log_path
):
    monitor_state = {
        "elapsed": 0.0,
        "handle": None
    }

    def monitor_tick(delta_time):
        monitor_state["elapsed"] += float(
            delta_time
        )

        if monitor_state["elapsed"] < 1.0:
            return

        monitor_state["elapsed"] = 0.0

        return_code = process.poll()

        if return_code is None:
            return

        callback_handle = monitor_state.get(
            "handle"
        )

        if callback_handle is not None:
            unreal.unregister_slate_post_tick_callback(
                callback_handle
            )
            monitor_state["handle"] = None

        try:
            log_text = log_path.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except OSError as error:
            log_text = (
                "Could not read training log: "
                + str(error)
            )

        completed = (
            return_code == 0
            and "Training complete." in log_text
        )

        if completed:
            _update_status_widgets(
                "Complete — Ready to Import"
            )
            title = "ExMesh Complete"
            message = (
                "ExMesh training completed.\n\n"
                f"Output:\n{output_dir}\n\n"
                "You can now import the latest mesh."
            )
            unreal.log(
                "ExMesh completion monitor: COMPLETE"
            )
        else:
            _update_status_widgets(
                "Failed — Check Output Log"
            )
            title = "ExMesh Failed"
            message = (
                "ExMesh stopped without completing.\n\n"
                f"Exit code: {return_code}\n"
                f"Log:\n{log_path}"
            )
            unreal.log_error(
                "ExMesh completion monitor: FAILED"
            )

        unreal.EditorDialog.show_message(
            title,
            message,
            unreal.AppMsgType.OK
        )

    monitor_state["handle"] = (
        unreal.register_slate_post_tick_callback(
            monitor_tick
        )
    )

    unreal.log(
        "ExMesh completion monitor registered"
    )


def start_exmesh_run(iterations, dataset_path=None):
    previous_state = _read_run_state()

    if previous_state is not None:
        try:
            previous_pid = int(
                previous_state.get("pid", -1)
            )
        except (TypeError, ValueError):
            previous_pid = -1

        if (
            previous_pid > 0
            and _is_process_running(previous_pid)
        ):
            previous_output = previous_state.get(
                "output",
                "Unknown"
            )

            message = (
                "ExMesh is already running.\n\n"
                f"PID: {previous_pid}\n"
                f"Output: {previous_output}"
            )

            unreal.log_warning(message)

            unreal.EditorDialog.show_message(
                "ExMesh Already Running",
                message,
                unreal.AppMsgType.OK
            )
            return

    try:
        iterations = int(
            float(iterations)
        )
    except (TypeError, ValueError):
        unreal.log_error(
            f"Invalid iteration value: {iterations}"
        )
        return

    if iterations < 1 or iterations > 30000:
        unreal.log_error(
            "Iterations must be between "
            "1 and 30000."
        )
        return

    if not TRAIN_SCRIPT.is_file():
        unreal.log_error(
            f"train.py not found: {TRAIN_SCRIPT}"
        )
        return

    selected_dataset = _resolve_dataset_path(
        dataset_path
    )

    if not selected_dataset.is_dir():
        message = (
            "Dataset not found:\n"
            + str(selected_dataset)
        )

        unreal.log_error(message)

        unreal.EditorDialog.show_message(
            "Dataset Error",
            message,
            unreal.AppMsgType.OK
        )
        return

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    output_dir = (
        EXMESH_ROOT
        / "outputs"
        / (
            f"plugin_run_{timestamp}_"
            f"{iterations}iter"
        )
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=False
    )

    log_path = (
        output_dir
        / "training.log"
    )

    command = [
        EXTERNAL_PYTHON,
        "-u",
        str(TRAIN_SCRIPT),
        "-s",
        str(selected_dataset),
        "-m",
        str(output_dir),
        "--iterations",
        str(iterations)
    ]

    try:
        with log_path.open(
            "w",
            encoding="utf-8"
        ) as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(EXMESH_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0
                )
            )

        run_state = {
            "pid": process.pid,
            "iterations": iterations,
            "dataset": str(selected_dataset),
            "output": str(output_dir),
            "log": str(log_path),
            "started_at": datetime.now().isoformat()
        }

        RUN_STATE_PATH.write_text(
            json.dumps(
                run_state,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        _register_completion_monitor(
            process,
            output_dir,
            log_path
        )

        unreal.log(
            "ExMesh run started"
        )

        unreal.log(
            f"Iterations: {iterations}"
        )

        unreal.log(
            f"Process ID: {process.pid}"
        )

        unreal.log(
            f"Output: {output_dir}"
        )

        unreal.log(
            f"Log: {log_path}"
        )

    except Exception as error:
        unreal.log_error(
            f"Failed to start ExMesh: {error}"
        )


def start_exmesh_smoke_test(dataset_path=None):
    start_exmesh_run(
        1,
        dataset_path
    )


def import_latest_exmesh_mesh():
    output_root = (
        EXMESH_ROOT
        / "outputs"
    )

    candidate_folders = []

    for pattern in (
        "plugin_smoke_*",
        "plugin_run_*"
    ):
        candidate_folders.extend(
            output_root.glob(pattern)
        )

    completed_folders = []

    for path in candidate_folders:
        if not path.is_dir():
            continue

        log_path = (
            path
            / "training.log"
        )

        if not log_path.is_file():
            continue

        try:
            log_text = log_path.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except OSError:
            continue

        if "Training complete." in log_text:
            completed_folders.append(
                path
            )

    if not completed_folders:
        unreal.log_error(
            "No completed ExMesh output "
            "was found."
        )
        return

    latest_folder = max(
        completed_folders,
        key=lambda path: (
            path.stat().st_mtime
        )
    )

    mesh_folder = (
        latest_folder
        / "mesh"
    )

    ply_files = list(
        mesh_folder.glob(
            "auto_mesh_iter_*.ply"
        )
    )

    if not ply_files:
        unreal.log_error(
            "No PLY mesh was found in: "
            + str(mesh_folder)
        )
        return

    def iteration_number(path):
        try:
            return int(
                path.stem.rsplit(
                    "_",
                    1
                )[-1]
            )
        except ValueError:
            return -1

    latest_ply = max(
        ply_files,
        key=iteration_number
    )

    selected_iteration = (
        iteration_number(
            latest_ply
        )
    )

    obj_path = (
        latest_ply.with_suffix(
            ".obj"
        )
    )

    unreal.log(
        "Selected completed ExMesh output: "
        + str(latest_folder)
    )

    unreal.log(
        "Selected mesh iteration: "
        + str(selected_iteration)
    )

    conversion = subprocess.run(
        [
            EXTERNAL_PYTHON,
            str(CONVERTER_SCRIPT),
            "--input",
            str(latest_ply),
            "--output",
            str(obj_path),
            "--scale",
            str(UNREAL_UNIT_SCALE)
        ],
        cwd=str(EXMESH_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0
        )
    )

    if conversion.returncode != 0:
        unreal.log_error(
            "Mesh conversion failed:\n"
            + conversion.stderr
        )
        return

    if conversion.stdout.strip():
        unreal.log(
            "Mesh conversion report:\n"
            + conversion.stdout.strip()
        )

    folder_label = (
        latest_folder.name
    )

    for prefix in (
        "plugin_smoke_",
        "plugin_run_"
    ):
        if folder_label.startswith(
            prefix
        ):
            folder_label = (
                folder_label[
                    len(prefix):
                ]
            )
            break

    asset_name = (
        f"SM_ExMesh_{folder_label}"
    )

    import_task = (
        unreal.AssetImportTask()
    )

    import_task.set_editor_property(
        "filename",
        str(obj_path)
    )

    import_task.set_editor_property(
        "destination_path",
        UNREAL_DESTINATION_PATH
    )

    import_task.set_editor_property(
        "destination_name",
        asset_name
    )

    import_task.set_editor_property(
        "automated",
        True
    )

    import_task.set_editor_property(
        "replace_existing",
        True
    )

    import_task.set_editor_property(
        "save",
        True
    )

    asset_tools = (
        unreal.AssetToolsHelpers
        .get_asset_tools()
    )

    asset_tools.import_asset_tasks(
        [import_task]
    )

    imported_paths = (
        import_task.get_editor_property(
            "imported_object_paths"
        )
    )

    if not imported_paths:
        unreal.log_error(
            "OBJ conversion succeeded, "
            "but Unreal import failed."
        )
        return

    unreal.log(
        "ExMesh mesh imported successfully"
    )

    for imported_path in imported_paths:
        unreal.log(
            f"Imported asset: {imported_path}"
        )


def check_latest_exmesh_status():
    output_root = EXMESH_ROOT / "outputs"

    run_folders = [
        path
        for pattern in (
            "plugin_run_*",
            "plugin_smoke_*"
        )
        for path in output_root.glob(pattern)
        if path.is_dir()
    ]

    if not run_folders:
        unreal.log_error(
            "No ExMesh run was found."
        )
        return

    latest_folder = max(
        run_folders,
        key=lambda path: path.stat().st_mtime
    )

    log_path = latest_folder / "training.log"

    if not log_path.is_file():
        unreal.log_error(
            f"Training log was not found: {log_path}"
        )
        return

    log_text = log_path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    non_empty_lines = [
        line.strip()
        for line in log_text.splitlines()
        if line.strip()
    ]

    last_line = (
        non_empty_lines[-1]
        if non_empty_lines
        else "No log output yet."
    )

    if "Training complete." in log_text:
        status = "COMPLETE"
        unreal.log(
            "ExMesh status: COMPLETE"
        )
    elif (
        "Traceback (most recent call last):" in log_text
        or "RuntimeError:" in log_text
        or "CUDA out of memory" in log_text
    ):
        status = "FAILED"
        unreal.log_error(
            "ExMesh status: FAILED"
        )
    else:
        run_state = _read_run_state()
        state_matches_latest = False
        process_is_running = False

        if run_state is not None:
            state_output = run_state.get(
                "output",
                ""
            )

            state_matches_latest = (
                str(Path(state_output)).lower()
                == str(latest_folder).lower()
            )

            try:
                state_pid = int(
                    run_state.get("pid", -1)
                )
            except (TypeError, ValueError):
                state_pid = -1

            if (
                state_matches_latest
                and state_pid > 0
            ):
                process_is_running = (
                    _is_process_running(state_pid)
                )

        if process_is_running:
            status = "RUNNING"
            unreal.log(
                "ExMesh status: RUNNING"
            )
        else:
            status = "INTERRUPTED"
            unreal.log_warning(
                "ExMesh status: INTERRUPTED"
            )

    unreal.log(
        f"Run folder: {latest_folder}"
    )

    unreal.log(
        f"Latest log: {last_line}"
    )

    message = (
        f"Status: {status}\n\n"
        f"Run: {latest_folder.name}\n\n"
        f"Latest log:\n{last_line}"
    )

    unreal.EditorDialog.show_message(
        "ExMesh Status",
        message,
        unreal.AppMsgType.OK
    )

    return status
