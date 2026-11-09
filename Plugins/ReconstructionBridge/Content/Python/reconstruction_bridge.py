import json



import subprocess



from datetime import datetime



from pathlib import Path







import unreal











import os

# -----------------------------------------------------------------------------
# Path configuration
#
# ExMesh is bundled with the plugin as a git submodule:
#   Plugins/ReconstructionBridge/ThirdParty/ExMesh
# Every path below can be overridden per PC with an environment variable:
#   EXMESH_ROOT         ExMesh source folder        (default: bundled submodule)
#   EXMESH_PYTHON       python.exe of the conda env (default: auto-detect "exmesh")
#   EXMESH_WORKDIR      dataset folder              (default: <EXMESH_ROOT>/workdir)
#   EXMESH_OUTPUT_ROOT  training/export results     (default: <Project>/Saved/ReconstructionBridge/outputs)
# -----------------------------------------------------------------------------

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

BUNDLED_EXMESH_ROOT = PLUGIN_ROOT / "ThirdParty" / "ExMesh"


def _env_path(name):
    value = os.environ.get(name, "").strip().strip('"')
    return Path(value) if value else None


def _find_external_python():
    env_python = _env_path("EXMESH_PYTHON")
    if env_python is not None:
        return str(env_python)
    home = Path.home()
    candidates = []
    conda_prefix_root = _env_path("CONDA_EXE")
    if conda_prefix_root is not None:
        # .../miniconda3/Scripts/conda.exe -> .../miniconda3
        candidates.append(conda_prefix_root.parent.parent)
    for base in ("miniconda3", "anaconda3", "miniforge3", "mambaforge"):
        candidates.append(home / base)
        candidates.append(Path("C:/ProgramData") / base)
    candidates.append(home / "AppData" / "Local" / "miniconda3")
    candidates.append(home / ".conda")
    for base in candidates:
        python_exe = base / "envs" / "exmesh" / "python.exe"
        if python_exe.is_file():
            return str(python_exe)
    # Not found: return the conventional location so the error message
    # tells the user where it was expected.
    return str(home / "miniconda3" / "envs" / "exmesh" / "python.exe")


def _default_output_root():
    try:
        saved_dir = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_saved_dir()
        )
        return Path(saved_dir) / "ReconstructionBridge" / "outputs"
    except Exception:
        # Plugins/ReconstructionBridge -> <Project>
        return PLUGIN_ROOT.parents[1] / "Saved" / "ReconstructionBridge" / "outputs"


EXTERNAL_PYTHON = _find_external_python()

EXMESH_ROOT = _env_path("EXMESH_ROOT") or BUNDLED_EXMESH_ROOT

EXMESH_WORKDIR = _env_path("EXMESH_WORKDIR") or (EXMESH_ROOT / "workdir")

OUTPUT_ROOT = _env_path("EXMESH_OUTPUT_ROOT") or _default_output_root()

DATASET_PATH = EXMESH_WORKDIR / "DTU" / "scan24"

RUN_STATE_PATH = OUTPUT_ROOT / "reconstruction_bridge_run_state.json"

UI_STATE_PATH = OUTPUT_ROOT / "reconstruction_bridge_ui_state.json"

TRAIN_SCRIPT = EXMESH_ROOT / "train.py"


def _widget_number(value):
    """Accept numbers formatted by the widget's Format Text node.

    Unreal formats 3000 as "3,000" (digit grouping). Pass numbers to Python
    as quoted strings, e.g. iterations="{Iterations}", and they are parsed here.
    """
    if isinstance(value, str):
        return value.replace(",", "").replace("\u00a0", "").strip()
    return value







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



    # Video / photo folder input: explain the automatic preprocessing,
    # or validate the already prepared dataset for it.
    import reconstruction_prepare
    _raw_message = reconstruction_prepare.describe_input(dataset_path)
    if _raw_message is not None:
        unreal.log(_raw_message)
        unreal.EditorDialog.show_message(
            "Dataset", _raw_message, unreal.AppMsgType.OK
        )
        return
    dataset_path = reconstruction_prepare.use_cached(dataset_path)
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











def start_exmesh_run(
    iterations,
    dataset_path=None,
    train_script=None,
    repo_root=None
):



    # Video / photo folder input: run COLMAP + masks + DA3 first, then retry.
    import reconstruction_prepare
    _proceed, dataset_path = reconstruction_prepare.resolve_or_prepare(
        dataset_path,
        lambda prepared: start_exmesh_run(
            iterations, prepared, train_script, repo_root
        ),
    )
    if not _proceed:
        return
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



            float(_widget_number(iterations))



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







    selected_train_script = (
        Path(train_script)
        if train_script is not None
        else TRAIN_SCRIPT
    )

    selected_repo_root = (
        Path(repo_root)
        if repo_root is not None
        else EXMESH_ROOT
    )

    if not selected_train_script.is_file():



        unreal.log_error(



            f"train.py not found: {selected_train_script}"



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



        OUTPUT_ROOT



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



        str(selected_train_script),



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



                cwd=str(selected_repo_root),



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



        OUTPUT_ROOT



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



    output_root = OUTPUT_ROOT







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







def create_material_for_selected_wildmesh(

    static_mesh=None,

    texture=None

):



    if static_mesh is None or texture is None:

        selected_assets = (

            unreal.EditorUtilityLibrary.get_selected_assets()

        )



        static_mesh = next(

            (

                asset

                for asset in selected_assets

                if isinstance(asset, unreal.StaticMesh)

            ),

            None

        )



        texture = next(

            (

                asset

                for asset in selected_assets

                if isinstance(asset, unreal.Texture2D)

            ),

            None

        )







    if static_mesh is None or texture is None:



        unreal.log_error(



            "Select one Static Mesh and one Texture2D "



            "in the Content Browser."



        )



        return







    mesh_path = static_mesh.get_path_name()



    destination_path = mesh_path.rsplit("/", 1)[0]



    material_name = f"M_{static_mesh.get_name()}_Auto"



    material_path = (



        f"{destination_path}/{material_name}"



    )







    material = unreal.EditorAssetLibrary.load_asset(



        material_path



    )







    if material is None:



        asset_tools = (



            unreal.AssetToolsHelpers.get_asset_tools()



        )







        material = asset_tools.create_asset(



            material_name,



            destination_path,



            unreal.Material,



            unreal.MaterialFactoryNew()



        )



    else:



        unreal.MaterialEditingLibrary.delete_all_material_expressions(



            material



        )







    texture_sample = (



        unreal.MaterialEditingLibrary



        .create_material_expression(



            material,



            unreal.MaterialExpressionTextureSample,



            -300,



            0



        )



    )







    texture_sample.set_editor_property(



        "texture",



        texture



    )







    unreal.MaterialEditingLibrary.connect_material_property(



        texture_sample,



        "RGB",



        unreal.MaterialProperty.MP_BASE_COLOR



    )







    roughness = (



        unreal.MaterialEditingLibrary



        .create_material_expression(



            material,



            unreal.MaterialExpressionConstant,



            -300,



            200



        )



    )







    roughness.set_editor_property("r", 0.7)







    unreal.MaterialEditingLibrary.connect_material_property(



        roughness,



        "",



        unreal.MaterialProperty.MP_ROUGHNESS



    )







    unreal.MaterialEditingLibrary.recompile_material(



        material



    )







    static_mesh.set_material(0, material)







    unreal.EditorAssetLibrary.save_loaded_asset(



        material



    )







    unreal.EditorAssetLibrary.save_loaded_asset(



        static_mesh



    )







    unreal.log(



        "WildMesh material created and assigned"



    )



    unreal.log(



        f"Mesh: {static_mesh.get_path_name()}"



    )



    unreal.log(



        f"Texture: {texture.get_path_name()}"



    )



    unreal.log(



        f"Material: {material.get_path_name()}"



    )







def _create_scaled_obj_for_unreal(



    source_obj,



    scale=100.0



):



    source_obj = Path(source_obj)







    scaled_obj = source_obj.with_name(



        source_obj.stem + "_ue.obj"



    )







    output_lines = []







    for line in source_obj.read_text(



        encoding="utf-8",



        errors="replace"



    ).splitlines():







        if line.startswith("v "):



            values = line.split()







            if len(values) >= 4:



                x = float(values[1]) * scale



                y = float(values[2]) * scale



                z = float(values[3]) * scale







                remaining = values[4:]







                line = " ".join(



                    [



                        "v",



                        str(x),



                        str(y),



                        str(z),



                        *remaining



                    ]



                )







        output_lines.append(line)







    scaled_obj.write_text(



        "\n".join(output_lines) + "\n",



        encoding="utf-8"



    )







    return scaled_obj











def _import_external_asset(



    filename,



    destination_path,



    destination_name



):



    task = unreal.AssetImportTask()







    task.set_editor_property(



        "filename",



        str(filename)



    )



    task.set_editor_property(



        "destination_path",



        destination_path



    )



    task.set_editor_property(



        "destination_name",



        destination_name



    )



    task.set_editor_property(



        "automated",



        True



    )



    task.set_editor_property(



        "replace_existing",



        True



    )



    task.set_editor_property(



        "save",



        True



    )







    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(



        [task]



    )







    return [



        unreal.EditorAssetLibrary.load_asset(path)



        for path in task.get_editor_property(



            "imported_object_paths"



        )



    ]











def import_latest_wildmesh_result():



    candidates = []







    for run_folder in (



        OUTPUT_ROOT



    ).glob("plugin_run_*"):







        export_folder = run_folder / "export"







        if not export_folder.is_dir():



            continue







        result_paths = list(

            export_folder.glob("mesh_iter_*_wild_r???.obj")

        )

        result_paths.extend(

            export_folder.glob("*_simplified.obj")

        )



        for obj_path in result_paths:



            texture_path = obj_path.with_name(



                obj_path.stem + "_texture.png"



            )







            if texture_path.is_file():



                candidates.append(



                    (



                        obj_path.stat().st_mtime,



                        run_folder,



                        obj_path,



                        texture_path



                    )



                )







    if not candidates:



        unreal.log_error(



            "No completed WildMesh result was found."



        )



        return







    (



        _,



        run_folder,



        obj_path,



        texture_path



    ) = max(



        candidates,



        key=lambda item: item[0]



    )







    unreal.log(



        f"Selected WildMesh result: {obj_path}"



    )







    scaled_obj = _create_scaled_obj_for_unreal(



        obj_path,



        scale=100.0



    )







    destination_path = (



        "/Game/ReconstructionBridge/Generated"



    )







    run_name = run_folder.name.replace(



        "plugin_run_",



        ""



    )







    if "_wild_" in obj_path.stem:

        result_label = obj_path.stem.rsplit(

            "_wild_",

            1

        )[-1]

    else:

        result_label = "legacy"



    texture_name = (

        f"T_WildMesh_{run_name}_{result_label}"

    )



    mesh_name = (

        f"SM_WildMesh_{run_name}_{result_label}"

    )







    texture_assets = _import_external_asset(



        texture_path,



        destination_path,



        texture_name



    )







    mesh_assets = _import_external_asset(



        scaled_obj,



        destination_path,



        mesh_name



    )







    texture = next(



        (



            asset



            for asset in texture_assets



            if isinstance(asset, unreal.Texture2D)



        ),



        None



    )







    static_mesh = next(



        (



            asset



            for asset in mesh_assets



            if isinstance(asset, unreal.StaticMesh)



        ),



        None



    )







    if static_mesh is None:



        unreal.log_error(



            "WildMesh OBJ import failed."



        )



        return







    if texture is None:



        unreal.log_error(



            "WildMesh texture import failed."



        )



        return







    unreal.EditorAssetLibrary.sync_browser_to_objects(



        [



            static_mesh.get_path_name(),



            texture.get_path_name()



        ]



    )







    create_material_for_selected_wildmesh(

        static_mesh,

        texture

    )







    unreal.log(



        "WildMesh automatic import complete"



    )







def import_latest_exmesh_export():

    export_result = export_latest_exmesh_for_wildmesh()



    if export_result is None:

        unreal.log_error(

            "Original ExMesh import failed because export failed."

        )

        return



    model_path, obj_path, texture_path = export_result



    scaled_obj = _create_scaled_obj_for_unreal(

        obj_path,

        scale=UNREAL_UNIT_SCALE

    )



    run_name = model_path.name.replace(

        "plugin_run_",

        ""

    )



    texture_name = f"T_ExMesh_Original_{run_name}"

    mesh_name = f"SM_ExMesh_Original_{run_name}"



    texture_assets = _import_external_asset(

        texture_path,

        UNREAL_DESTINATION_PATH,

        texture_name

    )



    mesh_assets = _import_external_asset(

        scaled_obj,

        UNREAL_DESTINATION_PATH,

        mesh_name

    )



    texture = next(

        (

            asset

            for asset in texture_assets

            if isinstance(asset, unreal.Texture2D)

        ),

        None

    )



    static_mesh = next(

        (

            asset

            for asset in mesh_assets

            if isinstance(asset, unreal.StaticMesh)

        ),

        None

    )



    if static_mesh is None or texture is None:

        unreal.log_error(

            "Original ExMesh mesh or texture import failed."

        )

        return



    create_material_for_selected_wildmesh(

        static_mesh,

        texture

    )



    unreal.EditorAssetLibrary.sync_browser_to_objects(

        [static_mesh.get_path_name()]

    )



    unreal.log("Original ExMesh import complete")

    unreal.log(f"Mesh: {static_mesh.get_path_name()}")

    unreal.log(f"Texture: {texture.get_path_name()}")





def start_wildmesh_simplification(ratio=0.1):



    import os







    current_info = get_wildmesh_status()







    if current_info["status"] == "RUNNING":



        unreal.log_warning(



            "WildMesh is already running."



        )







        unreal.EditorDialog.show_message(



            "WildMesh",



            "WildMesh is already running.",



            unreal.AppMsgType.OK



        )



        return







    if not 0.0 < ratio < 1.0:



        unreal.log_error(



            "WildMesh ratio must be between 0 and 1."



        )



        return







    exmesh_repo = EXMESH_ROOT







    wildmesh_script = (



        exmesh_repo



        / "simplification"



        / "wild_simplify_xatlas.py"



    )







    if not wildmesh_script.is_file():



        unreal.log_error(



            f"WildMesh script not found: {wildmesh_script}"



        )



        return







    export_result = export_latest_exmesh_for_wildmesh()



    if export_result is None:

        unreal.log_error(

            "WildMesh cannot start because ExMesh export failed."

        )

        return



    _, obj_path, texture_path = export_result







    ratio_tag = (

        f"r{int(round(float(ratio) * 100)):03d}"

    )



    output_path = obj_path.with_name(

        f"{obj_path.stem}_wild_{ratio_tag}.obj"

    )



    log_path = (

        obj_path.parent

        / f"wildmesh_{ratio_tag}.log"

    )







    command = [



        EXTERNAL_PYTHON,



        "-u",



        str(wildmesh_script),



        "--input",



        str(obj_path),



        "--output",



        str(output_path),



        "--texture",



        str(texture_path),



        "--ratio",



        str(ratio)



    ]







    environment = os.environ.copy()







    existing_pythonpath = environment.get(



        "PYTHONPATH",



        ""



    )







    environment["PYTHONPATH"] = (



        str(exmesh_repo)



        + os.pathsep



        + existing_pythonpath



    )







    try:



        with log_path.open(



            "w",



            encoding="utf-8"



        ) as log_file:



            process = subprocess.Popen(



                command,



                cwd=str(exmesh_repo),



                stdout=log_file,



                stderr=subprocess.STDOUT,



                text=True,



                env=environment,



                creationflags=getattr(



                    subprocess,



                    "CREATE_NO_WINDOW",



                    0



                )



            )







        state = {



            "pid": process.pid,



            "ratio": ratio,



            "input": str(obj_path),



            "output": str(output_path),



            "texture": str(texture_path),



            "log": str(log_path),



            "started_at": datetime.now().isoformat()



        }







        state_path = (



            OUTPUT_ROOT



            / "wildmesh_run_state.json"



        )







        state_path.write_text(



            json.dumps(



                state,



                ensure_ascii=False,



                indent=2



            ),



            encoding="utf-8"



        )







        unreal.log(



            "WildMesh simplification started"



        )



        unreal.log(



            f"Ratio: {ratio}"



        )



        unreal.log(



            f"Process ID: {process.pid}"



        )



        unreal.log(



            f"Input: {obj_path}"



        )



        unreal.log(



            f"Output: {output_path}"



        )



        unreal.log(



            f"Log: {log_path}"



        )







        start_wildmesh_monitoring()







    except Exception as error:



        unreal.log_error(



            f"Failed to start WildMesh: {error}"



        )











# WildMesh status and monitoring







if "_wildmesh_tick_handle" not in globals():



    _wildmesh_tick_handle = None







if "_wildmesh_last_poll_time" not in globals():



    _wildmesh_last_poll_time = 0.0















def _wildmesh_state_path():



    return (



        OUTPUT_ROOT



        / "wildmesh_run_state.json"



    )











def _is_process_running(pid):



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







    return f'"{pid}"' in result.stdout











def get_wildmesh_status():



    state_path = _wildmesh_state_path()







    if not state_path.is_file():



        return {



            "status": "NOT_FOUND",



            "latest_log": "No WildMesh run state."



        }







    try:



        state = json.loads(



            state_path.read_text(



                encoding="utf-8"



            )



        )



    except Exception as error:



        return {



            "status": "FAILED",



            "latest_log": str(error)



        }







    log_path = Path(state["log"])



    log_text = ""







    if log_path.is_file():



        log_text = log_path.read_text(



            encoding="utf-8",



            errors="replace"



        )







    log_lines = [



        line.strip()



        for line in log_text.splitlines()



        if line.strip()



    ]







    latest_log = (



        log_lines[-1]



        if log_lines



        else "Waiting for WildMesh output..."



    )







    if "[done]" in log_text:



        status = "COMPLETE"



    elif _is_process_running(state["pid"]):



        status = "RUNNING"



    else:



        status = "FAILED"







    return {



        **state,



        "status": status,



        "latest_log": latest_log



    }











def check_wildmesh_status():



    info = get_wildmesh_status()







    message = (



        f"Status: {info['status']}\n\n"



        f"Latest log:\n{info['latest_log']}"



    )







    unreal.log(



        f"WildMesh status: {info['status']}"



    )



    unreal.log(



        f"Latest log: {info['latest_log']}"



    )







    unreal.EditorDialog.show_message(



        "WildMesh Status",



        message,



        unreal.AppMsgType.OK



    )











def _wildmesh_tick(delta_seconds):



    import time







    global _wildmesh_tick_handle



    global _wildmesh_last_poll_time







    current_time = time.monotonic()







    if (



        current_time - _wildmesh_last_poll_time



        < 2.0



    ):



        return







    _wildmesh_last_poll_time = current_time







    info = get_wildmesh_status()



    status = info["status"]







    if status == "RUNNING":



        return







    if _wildmesh_tick_handle is not None:



        unreal.unregister_slate_post_tick_callback(



            _wildmesh_tick_handle



        )



        _wildmesh_tick_handle = None







    if status == "COMPLETE":



        unreal.EditorDialog.show_message(



            "WildMesh Complete",



            (



                "WildMesh simplification completed.\n\n"



                f"{info['latest_log']}"



            ),



            unreal.AppMsgType.OK



        )



        unreal.log(



            "WildMesh automatic monitoring complete"



        )







    elif status == "FAILED":



        unreal.EditorDialog.show_message(



            "WildMesh Failed",



            (



                "WildMesh process ended without "



                "a completion message.\n\n"



                f"{info['latest_log']}"



            ),



            unreal.AppMsgType.OK



        )



        unreal.log_error(



            "WildMesh simplification failed"



        )











def start_wildmesh_monitoring():



    global _wildmesh_tick_handle







    if _wildmesh_tick_handle is not None:



        unreal.log_warning(



            "WildMesh monitoring is already active."



        )



        return







    _wildmesh_tick_handle = (



        unreal.register_slate_post_tick_callback(



            _wildmesh_tick



        )



    )







    unreal.log(



        "WildMesh completion monitoring started"



    )















def export_latest_exmesh_for_wildmesh():



    import os







    exmesh_repo = EXMESH_ROOT



    export_script = (



        exmesh_repo



        / "scripts"



        / "export_obj.py"



    )







    if not export_script.is_file():



        unreal.log_error(



            f"Export script not found: {export_script}"



        )



        return None







    candidates = []







    for run_folder in (



        OUTPUT_ROOT



    ).glob("plugin_run_*"):







        if not run_folder.is_dir():



            continue







        training_log = run_folder / "training.log"







        if not training_log.is_file():



            continue







        log_text = training_log.read_text(



            encoding="utf-8",



            errors="replace"



        )







        if "Training complete." not in log_text:



            continue







        point_cloud_folder = (



            run_folder / "point_cloud"



        )







        if not point_cloud_folder.is_dir():



            continue







        iterations = []







        for iteration_folder in (



            point_cloud_folder.glob("iteration_*")



        ):



            try:



                iteration = int(



                    iteration_folder.name.split(



                        "_"



                    )[-1]



                )



                iterations.append(iteration)



            except ValueError:



                continue







        if iterations:



            candidates.append(



                (



                    run_folder.stat().st_mtime,



                    run_folder,



                    max(iterations)



                )



            )







    if not candidates:



        unreal.log_error(



            "No completed ExMesh checkpoint found."



        )



        return None







    _, model_path, iteration = max(



        candidates,



        key=lambda item: item[0]



    )







    output_dir = model_path / "export"



    obj_path = (



        output_dir



        / f"mesh_iter_{iteration}.obj"



    )



    texture_path = (



        output_dir



        / f"mesh_iter_{iteration}.png"



    )







    if obj_path.is_file() and texture_path.is_file():



        unreal.log(



            "ExMesh export already exists."



        )



        unreal.log(



            f"OBJ: {obj_path}"



        )



        unreal.log(



            f"Texture: {texture_path}"



        )







        return model_path, obj_path, texture_path







    environment = os.environ.copy()



    environment["PYTHONPATH"] = (



        str(exmesh_repo)



        + os.pathsep



        + environment.get("PYTHONPATH", "")



    )







    command = [



        EXTERNAL_PYTHON,



        str(export_script),



        "--model_path",



        str(model_path),



        "--iteration",



        str(iteration),



        "--output_dir",



        str(output_dir)



    ]







    unreal.log(



        "Exporting latest ExMesh checkpoint..."



    )



    unreal.log(



        f"Model: {model_path}"



    )



    unreal.log(



        f"Iteration: {iteration}"



    )







    result = subprocess.run(



        command,



        cwd=str(exmesh_repo),



        capture_output=True,



        text=True,



        encoding="utf-8",



        errors="replace",



        env=environment,



        creationflags=getattr(



            subprocess,



            "CREATE_NO_WINDOW",



            0



        )



    )







    if result.returncode != 0:



        unreal.log_error(



            "ExMesh export failed:\n"



            + result.stdout



            + "\n"



            + result.stderr



        )



        return None







    if not obj_path.is_file():



        unreal.log_error(



            f"Exported OBJ not found: {obj_path}"



        )



        return None







    if not texture_path.is_file():



        unreal.log_error(



            f"Exported texture not found: {texture_path}"



        )



        return None







    unreal.log(



        "ExMesh OBJ, MTL and texture export complete"



    )



    unreal.log(



        f"OBJ: {obj_path}"



    )



    unreal.log(



        f"Texture: {texture_path}"



    )







    return model_path, obj_path, texture_path





def import_modified_wildmesh_comparison():

    result_root = (
        OUTPUT_ROOT / "modified_importance_100iter" / "export"
    )



    destination_path = (

        "/Game/ReconstructionBridge/Comparison/Modified"

    )



    unreal.EditorAssetLibrary.make_directory(

        destination_path

    )



    variants = [

        (

            "L0",

            result_root / "mesh_iter_100_mod_r010_l0.obj"

        ),

        (

            "L1",

            result_root / "mesh_iter_100_mod_r010_l1.obj"

        ),

        (

            "L4",

            result_root / "mesh_iter_100_mod_r010_l4.obj"

        ),

    ]



    imported_paths = []



    for label, obj_path in variants:

        texture_path = obj_path.with_name(

            obj_path.stem + "_texture.png"

        )



        if not obj_path.is_file():

            unreal.log_error(

                f"Modified WildMesh OBJ not found: {obj_path}"

            )

            continue



        if not texture_path.is_file():

            unreal.log_error(

                f"Modified WildMesh texture not found: "

                f"{texture_path}"

            )

            continue



        scaled_obj = _create_scaled_obj_for_unreal(

            obj_path,

            scale=100.0

        )



        mesh_name = f"SM_WildMod_R010_{label}"

        texture_name = f"T_WildMod_R010_{label}"



        texture_assets = _import_external_asset(

            texture_path,

            destination_path,

            texture_name

        )



        mesh_assets = _import_external_asset(

            scaled_obj,

            destination_path,

            mesh_name

        )



        texture = next(

            (

                asset

                for asset in texture_assets

                if isinstance(asset, unreal.Texture2D)

            ),

            None

        )



        static_mesh = next(

            (

                asset

                for asset in mesh_assets

                if isinstance(asset, unreal.StaticMesh)

            ),

            None

        )



        if static_mesh is None:

            unreal.log_error(

                f"{label}: mesh import failed."

            )

            continue



        if texture is None:

            unreal.log_error(

                f"{label}: texture import failed."

            )

            continue



        create_material_for_selected_wildmesh(

            static_mesh,

            texture

        )



        imported_paths.extend(

            [

                static_mesh.get_path_name(),

                texture.get_path_name()

            ]

        )



        unreal.log(

            f"Modified WildMesh {label} imported successfully"

        )



    if imported_paths:

        unreal.EditorAssetLibrary.sync_browser_to_objects(

            imported_paths

        )



        unreal.log(

            "Modified WildMesh comparison import complete"

        )

    else:

        unreal.log_error(

            "No modified WildMesh assets were imported."

        )



#

def create_modified_wildmesh_auto_lod():

    export_folder = (
        OUTPUT_ROOT / "modified_importance_100iter" / "export"
    )



    original_obj = export_folder / "mesh_iter_100.obj"

    original_texture = export_folder / "mesh_iter_100.png"



    if not original_obj.is_file():

        unreal.log_error(

            f"LOD0 OBJ not found: {original_obj}"

        )

        return



    if not original_texture.is_file():

        unreal.log_error(

            f"LOD0 texture not found: {original_texture}"

        )

        return



    lod1_asset_path = (

        "/Game/ReconstructionBridge/Comparison/Modified/"

        "SM_WildMod_R010_L4.SM_WildMod_R010_L4"

    )



    lod1_mesh = unreal.EditorAssetLibrary.load_asset(

        lod1_asset_path

    )



    if not isinstance(lod1_mesh, unreal.StaticMesh):

        unreal.log_error(

            f"LOD1 mesh not found: {lod1_asset_path}"

        )

        return



    destination_path = (

        "/Game/ReconstructionBridge/AutoLOD"

    )



    # ExMesh 좌표 단위 → Unreal 센티미터 단위

    scaled_original_obj = _create_scaled_obj_for_unreal(

        original_obj,

        scale=100.0

    )



    texture_assets = _import_external_asset(

        original_texture,

        destination_path,

        "T_ExMesh_AutoLOD"

    )



    mesh_assets = _import_external_asset(

        scaled_original_obj,

        destination_path,

        "SM_ExMesh_AutoLOD"

    )



    texture = next(

        (

            asset for asset in texture_assets

            if isinstance(asset, unreal.Texture2D)

        ),

        None

    )



    base_mesh = next(

        (

            asset for asset in mesh_assets

            if isinstance(asset, unreal.StaticMesh)

        ),

        None

    )



    if base_mesh is None or texture is None:

        unreal.log_error(

            "Failed to import Auto LOD base assets."

        )

        return



    # LOD0용 원본 텍스처 머티리얼 생성

    create_material_for_selected_wildmesh(

        base_mesh,

        texture

    )



    subsystem = unreal.get_editor_subsystem(

        unreal.StaticMeshEditorSubsystem

    )



    # λ4 WildMesh의 LOD0 형상을 base mesh의 LOD1으로 복사

    # False: λ4 전용 머티리얼 슬롯도 새로 추가

    result_index = subsystem.set_lod_from_static_mesh(

        base_mesh,

        1,

        lod1_mesh,

        0,

        False

    )



    if result_index < 0:

        unreal.log_error(

            "Failed to create LOD1."

        )

        return



    # LOD0은 가까이, LOD1은 화면 점유율 35% 이하에서 사용

    screen_result = subsystem.set_lod_screen_sizes(

        base_mesh,

        [1.0, 0.35]

    )



    unreal.EditorAssetLibrary.save_loaded_asset(

        base_mesh

    )



    unreal.EditorAssetLibrary.sync_browser_to_objects(

        [base_mesh.get_path_name()]

    )



    unreal.log(

        "Modified WildMesh Auto LOD created"

    )

    unreal.log(

        f"Asset: {base_mesh.get_path_name()}"

    )

    unreal.log(

        f"LOD1 index: {result_index}"

    )

    unreal.log(

        f"Screen sizes set: {screen_result}"

    )


# -----------------------------------------------------------------------------
# End-to-end modified WildMesh Auto LOD pipeline
# -----------------------------------------------------------------------------

MODIFIED_EXMESH_REPO = EXMESH_ROOT
MODIFIED_TRAIN_SCRIPT = MODIFIED_EXMESH_REPO / "train.py"
MODIFIED_EXPORT_SCRIPT = MODIFIED_EXMESH_REPO / "scripts" / "export_obj.py"
MODIFIED_WILDMESH_MODULE = "simplification.wild_simplify_xatlas_modified"
AUTO_LOD_STATE_PATH = OUTPUT_ROOT / "auto_lod_pipeline_state.json"

if "_auto_lod_pipeline" not in globals():
    _auto_lod_pipeline = None
if "_auto_lod_tick_handle" not in globals():
    _auto_lod_tick_handle = None
if "_auto_lod_last_poll_time" not in globals():
    _auto_lod_last_poll_time = 0.0


def _write_auto_lod_state():
    if _auto_lod_pipeline is None:
        return
    serializable = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in _auto_lod_pipeline.items()
        if key != "process"
    }
    AUTO_LOD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTO_LOD_STATE_PATH.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _auto_lod_fail(message, log_path=None):
    global _auto_lod_tick_handle
    unreal.log_error(f"Auto LOD pipeline failed: {message}")
    _update_status_widgets("Auto LOD Failed - Check Log")
    if _auto_lod_pipeline is not None:
        _auto_lod_pipeline["stage"] = "FAILED"
        _auto_lod_pipeline["error"] = str(message)
        _write_auto_lod_state()
    if _auto_lod_tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_auto_lod_tick_handle)
        _auto_lod_tick_handle = None
    detail = str(message)
    if log_path is not None:
        detail += f"\n\nLog:\n{log_path}"
    unreal.EditorDialog.show_message(
        "Auto LOD Pipeline Failed",
        detail,
        unreal.AppMsgType.OK
    )


def _find_latest_checkpoint_iteration(model_path):
    point_cloud_folder = Path(model_path) / "point_cloud"
    candidates = []
    if not point_cloud_folder.is_dir():
        return None
    for folder in point_cloud_folder.glob("iteration_*"):
        if not folder.is_dir():
            continue
        try:
            candidates.append(int(folder.name.rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return max(candidates) if candidates else None


def _export_auto_lod_exmesh_result():
    import os
    state = _auto_lod_pipeline
    model_path = Path(state["output_dir"])
    iteration = _find_latest_checkpoint_iteration(model_path)
    if iteration is None:
        raise RuntimeError(f"No ExMesh checkpoint found in: {model_path}")

    face_importance = model_path / "face_importance.npy"
    if not face_importance.is_file():
        raise RuntimeError(
            "face_importance.npy was not generated. "
            "The modified D:\\GH\\ExMesh\\train.py must be used."
        )

    export_dir = model_path / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    obj_path = export_dir / f"mesh_iter_{iteration}.obj"
    texture_path = export_dir / f"mesh_iter_{iteration}.png"

    if not (obj_path.is_file() and texture_path.is_file()):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = (
            str(MODIFIED_EXMESH_REPO)
            + os.pathsep
            + environment.get("PYTHONPATH", "")
        )
        result = subprocess.run(
            [
                EXTERNAL_PYTHON,
                str(MODIFIED_EXPORT_SCRIPT),
                "--model_path", str(model_path),
                "--iteration", str(iteration),
                "--output_dir", str(export_dir)
            ],
            cwd=str(MODIFIED_EXMESH_REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if result.returncode != 0:
            raise RuntimeError(
                "ExMesh export failed:\n"
                + result.stdout + "\n" + result.stderr
            )

    if not obj_path.is_file():
        raise RuntimeError(f"Exported OBJ not found: {obj_path}")
    if not texture_path.is_file():
        raise RuntimeError(f"Exported texture not found: {texture_path}")

    state["iteration"] = iteration
    state["original_obj"] = obj_path
    state["original_texture"] = texture_path
    state["face_importance"] = face_importance
    _write_auto_lod_state()
    unreal.log("Auto LOD: ExMesh export complete")
    unreal.log(f"OBJ: {obj_path}")
    unreal.log(f"Texture: {texture_path}")
    unreal.log(f"Importance: {face_importance}")



def _ensure_lod_v2_configured():
    """Create Saved/ExMeshLOD/settings.json from the bridge paths if missing."""
    import reconstruction_lod_v2 as v2

    if v2._SETTINGS.is_file():
        return v2
    v2.configure_lod_v2(
        exmesh_python=EXTERNAL_PYTHON,
        exmesh_root=str(EXMESH_ROOT),
    )
    return v2


def _start_auto_lod_ppq():
    """Hand the exported ExMesh result to the PPQ LOD pipeline (lod_v2 accurate).

    PPQ weights -> photometric Wild simplification -> appearance refine ->
    Unreal import with LODs. The legacy tick stops here; lod_v2 has its own.
    """
    global _auto_lod_tick_handle
    state = _auto_lod_pipeline
    v2 = _ensure_lod_v2_configured()
    ratio = float(state["ratio"])
    screen_size = float(state["lod1_screen_size"])
    state["stage"] = "PPQ_V2"
    state["process"] = None
    _write_auto_lod_state()
    if _auto_lod_tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_auto_lod_tick_handle)
        _auto_lod_tick_handle = None
    work_dir = v2.start_accurate_lod_v2(
        str(state["output_dir"]),
        iteration=int(state["iteration"]),
        ratios=(ratio,),
        screen_sizes=(1.0, screen_size),
        refine_mode="full",
        scale=100.0,
    )
    state["ppq_work_dir"] = work_dir
    _write_auto_lod_state()
    _update_status_widgets("Auto LOD 2/3 - PPQ LOD (see Output Log)")
    unreal.log("Auto LOD: handed off to PPQ LOD pipeline (reconstruction_lod_v2)")
    unreal.log(f"PPQ work dir: {work_dir}")
    unreal.log("Status: import reconstruction_lod_v2 as v2; v2.get_lod_v2_status(True)")


def _start_auto_lod_modified_wildmesh():
    import os
    state = _auto_lod_pipeline
    obj_path = Path(state["original_obj"])
    texture_path = Path(state["original_texture"])
    importance_path = Path(state["face_importance"])
    ratio = float(state["ratio"])
    importance_lambda = float(state["importance_lambda"])
    ratio_tag = f"r{int(round(ratio * 100)):03d}"
    lambda_tag = f"l{importance_lambda:g}".replace(".", "p")
    result_stem = f"{obj_path.stem}_wildmod_{ratio_tag}_{lambda_tag}"
    output_obj = obj_path.with_name(result_stem + ".obj")
    output_texture = obj_path.with_name(result_stem + "_texture.png")
    log_path = obj_path.with_name(result_stem + ".log")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = (
        str(MODIFIED_EXMESH_REPO)
        + os.pathsep
        + environment.get("PYTHONPATH", "")
    )
    command = [
        EXTERNAL_PYTHON, "-u", "-m", MODIFIED_WILDMESH_MODULE,
        "--input", str(obj_path),
        "--output", str(output_obj),
        "--ratio", str(ratio),
        "--face_importance", str(importance_path),
        "--importance_lambda", str(importance_lambda),
        "--texture", str(texture_path)
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(MODIFIED_EXMESH_REPO),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    state["stage"] = "WILDMESH"
    state["process"] = process
    state["pid"] = process.pid
    state["wildmesh_obj"] = output_obj
    state["wildmesh_texture"] = output_texture
    state["wildmesh_log"] = log_path
    _write_auto_lod_state()
    _update_status_widgets("Auto LOD 2/3 - Simplifying Mesh")
    unreal.log("Auto LOD: modified WildMesh started")
    unreal.log(f"PID: {process.pid}")
    unreal.log(f"Output: {output_obj}")
    unreal.log(f"Log: {log_path}")


def _build_auto_lod_asset():
    state = _auto_lod_pipeline
    original_obj = Path(state["original_obj"])
    original_texture = Path(state["original_texture"])
    lod1_obj = Path(state["wildmesh_obj"])
    lod1_texture = Path(state["wildmesh_texture"])
    if not lod1_obj.is_file():
        raise RuntimeError(f"LOD1 OBJ not found: {lod1_obj}")
    if not lod1_texture.is_file():
        raise RuntimeError(f"LOD1 texture not found: {lod1_texture}")

    run_tag = state["run_tag"]
    destination_path = "/Game/ReconstructionBridge/AutoLOD"
    scaled_lod0 = _create_scaled_obj_for_unreal(original_obj, scale=100.0)
    scaled_lod1 = _create_scaled_obj_for_unreal(lod1_obj, scale=100.0)

    lod0_texture_assets = _import_external_asset(
        original_texture, destination_path, f"T_AutoLOD_{run_tag}_LOD0"
    )
    lod0_mesh_assets = _import_external_asset(
        scaled_lod0, destination_path, f"SM_AutoLOD_{run_tag}"
    )
    lod1_texture_assets = _import_external_asset(
        lod1_texture, destination_path, f"T_AutoLOD_{run_tag}_LOD1"
    )
    lod1_mesh_assets = _import_external_asset(
        scaled_lod1,
        destination_path,
        f"SM_AutoLODSource_{run_tag}_LOD1"
    )

    lod0_texture = next(
        (a for a in lod0_texture_assets if isinstance(a, unreal.Texture2D)),
        None
    )
    base_mesh = next(
        (a for a in lod0_mesh_assets if isinstance(a, unreal.StaticMesh)),
        None
    )
    lod1_texture_asset = next(
        (a for a in lod1_texture_assets if isinstance(a, unreal.Texture2D)),
        None
    )
    lod1_mesh = next(
        (a for a in lod1_mesh_assets if isinstance(a, unreal.StaticMesh)),
        None
    )
    if base_mesh is None or lod0_texture is None:
        raise RuntimeError("LOD0 Unreal import failed.")
    if lod1_mesh is None or lod1_texture_asset is None:
        raise RuntimeError("LOD1 Unreal import failed.")

    create_material_for_selected_wildmesh(base_mesh, lod0_texture)
    create_material_for_selected_wildmesh(lod1_mesh, lod1_texture_asset)

    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    lod_index = subsystem.set_lod_from_static_mesh(
        base_mesh, 1, lod1_mesh, 0, False
    )
    if lod_index < 0:
        raise RuntimeError("Unreal failed to register LOD1.")
    if not subsystem.set_lod_screen_sizes(
        base_mesh,
        [1.0, float(state["lod1_screen_size"])]
    ):
        raise RuntimeError("Unreal failed to set LOD screen sizes.")

    lod_count = subsystem.get_lod_count(base_mesh)
    lod0_slot = subsystem.get_lod_material_slot(base_mesh, 0, 0)
    lod1_slot = subsystem.get_lod_material_slot(base_mesh, 1, 0)
    if lod_count != 2:
        raise RuntimeError(f"Unexpected LOD count: {lod_count}")
    if lod0_slot == lod1_slot:
        raise RuntimeError("LOD0 and LOD1 use the same material slot.")

    unreal.EditorAssetLibrary.save_loaded_asset(base_mesh)
    unreal.EditorAssetLibrary.sync_browser_to_objects(
        [base_mesh.get_path_name()]
    )
    state["asset_path"] = base_mesh.get_path_name()
    state["lod_count"] = lod_count
    state["lod0_material_slot"] = lod0_slot
    state["lod1_material_slot"] = lod1_slot
    _write_auto_lod_state()
    unreal.log("Auto LOD asset created successfully")
    unreal.log(f"Asset: {base_mesh.get_path_name()}")
    unreal.log(f"LOD count: {lod_count}")
    unreal.log(f"LOD0 material slot: {lod0_slot}")
    unreal.log(f"LOD1 material slot: {lod1_slot}")


def _auto_lod_tick(delta_seconds):
    import time
    global _auto_lod_tick_handle
    global _auto_lod_last_poll_time

    if _auto_lod_pipeline is None:
        return
    current_time = time.monotonic()
    if current_time - _auto_lod_last_poll_time < 2.0:
        return
    _auto_lod_last_poll_time = current_time

    state = _auto_lod_pipeline
    process = state.get("process")
    if process is None:
        _auto_lod_fail("Pipeline process handle was lost.")
        return
    return_code = process.poll()
    if return_code is None:
        return
    stage = state.get("stage")

    try:
        if stage == "EXMESH":
            log_path = Path(state["training_log"])
            log_text = log_path.read_text(
                encoding="utf-8", errors="replace"
            ) if log_path.is_file() else ""
            if return_code != 0 or "Training complete." not in log_text:
                _auto_lod_fail(
                    f"ExMesh exited with code {return_code}.", log_path
                )
                return
            _update_status_widgets("Auto LOD 1/3 - Exporting ExMesh")
            _export_auto_lod_exmesh_result()
            # Sobel-weighted modified WildMesh is obsolete: continue with the
            # PPQ (photometric quadric) pipeline in reconstruction_lod_v2.
            _start_auto_lod_ppq()
            return

        if stage == "WILDMESH":
            log_path = Path(state["wildmesh_log"])
            log_text = log_path.read_text(
                encoding="utf-8", errors="replace"
            ) if log_path.is_file() else ""
            if return_code != 0 or "[done]" not in log_text:
                _auto_lod_fail(
                    f"Modified WildMesh exited with code {return_code}.",
                    log_path
                )
                return
            _update_status_widgets("Auto LOD 3/3 - Importing to Unreal")
            _build_auto_lod_asset()
            state["stage"] = "COMPLETE"
            state["completed_at"] = datetime.now().isoformat()
            _write_auto_lod_state()
            if _auto_lod_tick_handle is not None:
                unreal.unregister_slate_post_tick_callback(
                    _auto_lod_tick_handle
                )
                _auto_lod_tick_handle = None
            _update_status_widgets("Auto LOD Complete - Ready")
            unreal.EditorDialog.show_message(
                "Auto LOD Complete",
                (
                    "Modified WildMesh Auto LOD pipeline completed.\n\n"
                    f"Asset:\n{state['asset_path']}\n\n"
                    "LOD0: ExMesh original\n"
                    "LOD1: importance-aware WildMesh"
                ),
                unreal.AppMsgType.OK
            )
            return

        _auto_lod_fail(f"Unknown pipeline stage: {stage}")
    except Exception as error:
        _auto_lod_fail(
            str(error),
            state.get("training_log")
            if stage == "EXMESH"
            else state.get("wildmesh_log")
        )


def start_auto_lod_pipeline(
    iterations=100,
    ratio=0.1,
    importance_lambda=4.0,
    lod1_screen_size=0.35,
    dataset_path=None
):
    global _auto_lod_pipeline
    global _auto_lod_tick_handle
    global _auto_lod_last_poll_time

    # Video / photo folder input: run COLMAP + masks + DA3 first, then retry.
    import reconstruction_prepare
    _proceed, dataset_path = reconstruction_prepare.resolve_or_prepare(
        dataset_path,
        lambda prepared: start_auto_lod_pipeline(
            iterations, ratio, importance_lambda, lod1_screen_size, prepared
        ),
    )
    if not _proceed:
        return
    if (
        _auto_lod_pipeline is not None
        and _auto_lod_pipeline.get("stage") in {"EXMESH", "WILDMESH"}
    ):
        process = _auto_lod_pipeline.get("process")
        if process is not None and process.poll() is None:
            unreal.log_warning("Auto LOD pipeline is already running.")
            return

    try:
        iterations = int(float(_widget_number(iterations)))
        ratio = float(_widget_number(ratio))
        importance_lambda = float(_widget_number(importance_lambda))
        lod1_screen_size = float(_widget_number(lod1_screen_size))
    except (TypeError, ValueError):
        unreal.log_error("Invalid Auto LOD parameter value.")
        return

    if iterations < 1 or iterations > 30000:
        unreal.log_error("Iterations must be between 1 and 30000.")
        return
    if not 0.0 < ratio < 1.0:
        unreal.log_error("Ratio must be between 0 and 1.")
        return
    if importance_lambda < 0.0:
        unreal.log_error("Importance lambda must be zero or greater.")
        return
    if not 0.0 < lod1_screen_size < 1.0:
        unreal.log_error("LOD1 screen size must be between 0 and 1.")
        return

    required_files = [
        MODIFIED_TRAIN_SCRIPT,
        MODIFIED_EXPORT_SCRIPT,
        MODIFIED_EXMESH_REPO
        / "simplification"
        / "wild_simplify_xatlas_modified.py"
    ]
    missing_files = [path for path in required_files if not path.is_file()]
    if missing_files:
        unreal.log_error(
            "Auto LOD required file not found: " + str(missing_files[0])
        )
        return

    selected_dataset = _resolve_dataset_path(dataset_path)
    if not selected_dataset.is_dir():
        unreal.log_error(f"Dataset not found: {selected_dataset}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        OUTPUT_ROOT
        / f"auto_lod_run_{timestamp}_{iterations}iter"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    training_log = output_dir / "training.log"
    command = [
        EXTERNAL_PYTHON, "-u", str(MODIFIED_TRAIN_SCRIPT),
        "-s", str(selected_dataset),
        "-m", str(output_dir),
        "--iterations", str(iterations)
    ]

    try:
        with training_log.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(MODIFIED_EXMESH_REPO),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
    except Exception as error:
        unreal.log_error(f"Failed to start Auto LOD ExMesh: {error}")
        return

    _auto_lod_pipeline = {
        "stage": "EXMESH",
        "process": process,
        "pid": process.pid,
        "iterations": iterations,
        "ratio": ratio,
        "importance_lambda": importance_lambda,
        "lod1_screen_size": lod1_screen_size,
        "dataset": selected_dataset,
        "output_dir": output_dir,
        "training_log": training_log,
        "run_tag": run_tag,
        "started_at": datetime.now().isoformat()
    }
    _write_auto_lod_state()

    _auto_lod_last_poll_time = 0.0
    if _auto_lod_tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_auto_lod_tick_handle)
    _auto_lod_tick_handle = unreal.register_slate_post_tick_callback(
        _auto_lod_tick
    )
    _update_status_widgets("Auto LOD 1/3 - Running ExMesh")
    unreal.log("Auto LOD pipeline started")
    unreal.log(f"Iterations: {iterations}")
    unreal.log(f"Ratio: {ratio}")
    unreal.log(f"Importance lambda: {importance_lambda}")
    unreal.log(f"Process ID: {process.pid}")
    unreal.log(f"Output: {output_dir}")
    unreal.log(f"Log: {training_log}")


def get_auto_lod_pipeline_status():
    if _auto_lod_pipeline is not None:
        state = {
            key: value
            for key, value in _auto_lod_pipeline.items()
            if key != "process"
        }
    elif AUTO_LOD_STATE_PATH.is_file():
        try:
            state = json.loads(
                AUTO_LOD_STATE_PATH.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            state = {"stage": "UNKNOWN"}
    else:
        state = {"stage": "NOT_STARTED"}
    unreal.log(f"Auto LOD stage: {state.get('stage')}")
    if state.get("output_dir"):
        unreal.log(f"Output: {state['output_dir']}")
    if state.get("asset_path"):
        unreal.log(f"Asset: {state['asset_path']}")
    if state.get("error"):
        unreal.log_error(f"Error: {state['error']}")
    return state


def resume_auto_lod_import(
    output_dir=str(OUTPUT_ROOT / "auto_lod_run_20261005_155023_648727_100iter"),
    lod1_screen_size=0.35,
):
    """Create the Unreal LOD asset from a completed ExMesh/WildMesh run.

    This entry point performs no training or simplification. It is intended
    for recovery when the original Unreal import was interrupted.
    """
    import re
    import shutil

    global _auto_lod_pipeline
    run_dir = Path(output_dir)
    match = re.fullmatch(r"auto_lod_run_(\d{8}_\d{6})_\d+_\d+iter", run_dir.name)
    if not match:
        raise ValueError(f"Unexpected Auto LOD run directory: {run_dir}")
    if not 0.0 < float(lod1_screen_size) < 1.0:
        raise ValueError("LOD1 screen size must be between 0 and 1")

    run_tag = match.group(1)
    export_dir = run_dir / "export"
    original_obj = export_dir / "mesh_iter_100.obj"
    original_texture = export_dir / "mesh_iter_100.png"
    wildmesh_obj = export_dir / "mesh_iter_100_wildmod_r010_l4.obj"
    wildmesh_texture = export_dir / "mesh_iter_100_wildmod_r010_l4_texture.png"
    for required in (original_obj, original_texture, wildmesh_obj, wildmesh_texture):
        if not required.is_file() or required.stat().st_size == 0:
            raise FileNotFoundError(f"Missing or empty Auto LOD input: {required}")

    free_gb = shutil.disk_usage(run_dir.anchor).free / (1024 ** 3)
    if free_gb < 5.0:
        raise RuntimeError(f"Only {free_gb:.2f} GB free on {run_dir.anchor}; free at least 5 GB before import")

    asset_dir = "/Game/ReconstructionBridge/AutoLOD"
    asset_path = f"{asset_dir}/SM_AutoLOD_{run_tag}"
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise RuntimeError(f"Auto LOD asset already exists: {asset_path}")

    _auto_lod_pipeline = {
        "stage": "IMPORTING",
        "output_dir": run_dir,
        "run_tag": run_tag,
        "original_obj": original_obj,
        "original_texture": original_texture,
        "wildmesh_obj": wildmesh_obj,
        "wildmesh_texture": wildmesh_texture,
        "lod1_screen_size": float(lod1_screen_size),
    }
    _write_auto_lod_state()
    try:
        _build_auto_lod_asset()
        for path in unreal.EditorAssetLibrary.list_assets(asset_dir, recursive=False, include_folder=False):
            if run_tag in path:
                if not unreal.EditorAssetLibrary.save_asset(path):
                    raise RuntimeError(f"Could not save asset: {path}")
        _auto_lod_pipeline["stage"] = "COMPLETE"
        _write_auto_lod_state()
        unreal.log(f"Auto LOD recovery complete: {asset_path}")
        return asset_path
    except Exception as error:
        _auto_lod_pipeline["stage"] = "FAILED"
        _auto_lod_pipeline["error"] = str(error)
        _write_auto_lod_state()
        raise
