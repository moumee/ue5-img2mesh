@echo off
rem ---------------------------------------------------------------------------
rem  ReconstructionBridge - Pixal3D quick generation (Windows)
rem
rem  Lets the quick mode (Run Quick LOD) generate with Pixal3D instead of TripoSR.
rem  Usually run by setup_exmesh_env.bat (Tools > Reconstruction Bridge Setup),
rem  which installs it with everything else ("all") or alone ("pixal3d").
rem  Installs:
rem    ComfyUI v0.46.0     ThirdParty\ComfyUI (native TRELLIS.2 / Pixal3D nodes)
rem    conda env "comfyui" Python 3.13, PyTorch cu130, ComfyUI requirements, trimesh
rem    weights (int8)      about 10 GB into ThirdParty\ComfyUI\models
rem                        "trellis2" also downloads the TRELLIS.2 model (5.3 GB)
rem
rem  The quick mode finds these locations by itself. To use another ComfyUI or env,
rem  set "comfyui_repo" / "comfyui_python" in Saved\ExMeshLOD\settings.json.
rem  Requirements: Miniconda, git, curl (Windows 10+), NVIDIA GPU with driver 580 or newer (CUDA 13).
rem
rem  Usage:  setup_pixal3d.bat [trellis2]     re-running skips what is installed
rem ---------------------------------------------------------------------------
setlocal EnableExtensions

set "PLUGIN_DIR=%~dp0.."
set "COMFY_DIR=%PLUGIN_DIR%\ThirdParty\ComfyUI"
set "COMFY_TAG=v0.46.0"
set "ENV_NAME=comfyui"
set "TORCH_INDEX=https://download.pytorch.org/whl/cu130"
rem Another Python 3.13 on the machine shares the user site-packages; keep pip and ComfyUI out of it.
set "PYTHONNOUSERSITE=1"

rem ---- locate conda (same search as setup_exmesh_env.bat) --------------------
set "CONDA="
for %%D in (
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\anaconda3"
    "%USERPROFILE%\miniforge3"
    "%LOCALAPPDATA%\miniconda3"
    "C:\ProgramData\miniconda3"
    "C:\ProgramData\anaconda3"
) do if not defined CONDA if exist "%%~D\condabin\conda.bat" set "CONDA=%%~D\condabin\conda.bat"
if not defined CONDA for /f "delims=" %%C in ('where conda.bat 2^>nul') do if not defined CONDA set "CONDA=%%C"
if not defined CONDA (
    echo [ERROR] conda not found. Install Miniconda first:
    echo         https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)
echo Using conda: %CONDA%

rem ---- ComfyUI ------------------------------------------------------------------
echo.
echo ===== ComfyUI %COMFY_TAG% =====
if exist "%COMFY_DIR%\main.py" (
    echo ComfyUI already present: %COMFY_DIR%
) else (
    where git >nul 2>nul || (
        echo [ERROR] git not found.
        exit /b 1
    )
    git clone --depth 1 --branch %COMFY_TAG% https://github.com/Comfy-Org/ComfyUI.git "%COMFY_DIR%" || goto :fail
)

rem ---- conda env ----------------------------------------------------------------
echo.
echo ===== conda env "%ENV_NAME%" =====
set "ENV_LIST=%TEMP%\rb_conda_envs_%RANDOM%.txt"
call "%CONDA%" env list > "%ENV_LIST%" 2>nul
findstr /R /C:"^%ENV_NAME% " "%ENV_LIST%" >nul
set "ENV_MISSING=%ERRORLEVEL%"
del "%ENV_LIST%" >nul 2>nul
if not "%ENV_MISSING%"=="0" (
    echo Creating conda env "%ENV_NAME%" ...
    call "%CONDA%" create -y -n %ENV_NAME% python=3.13 || goto :fail
) else (
    echo Conda env "%ENV_NAME%" already exists - installing into it.
)
set "RUN=call "%CONDA%" run -n %ENV_NAME% --no-capture-output"
%RUN% python -m pip install torch torchvision torchaudio --index-url %TORCH_INDEX% || goto :fail
%RUN% python -m pip install -r "%COMFY_DIR%\requirements.txt" trimesh || goto :fail

rem ---- weights ------------------------------------------------------------------
echo.
echo ===== model weights =====
call :weight Comfy-Org/Pixal3D diffusion_models pixal3d_int8_convrot.safetensors || goto :fail
call :weight Comfy-Org/Pixal3D vae trellis_2_shape_vae_bf16.safetensors || goto :fail
call :weight Comfy-Org/Pixal3D vae trellis_2_texture_vae_bf16.safetensors || goto :fail
call :weight Comfy-Org/Pixal3D clip_vision dino_v3_L_naf_fp32.safetensors || goto :fail
call :weight Comfy-Org/BiRefNet background_removal birefnet.safetensors || goto :fail
call :weight Comfy-Org/MoGe geometry_estimation moge_2_vitl_normal_fp16.safetensors || goto :fail
if /I "%~1"=="trellis2" (
    call :weight Comfy-Org/TRELLIS.2 diffusion_models trellis_2_int8_convrot.safetensors || goto :fail
)

echo.
%RUN% python -c "import torch, trimesh; print('torch', torch.__version__, 'CUDA available:', torch.cuda.is_available())" || goto :fail
echo.
echo Pixal3D setup finished. Run Quick LOD generates with Pixal3D now.
exit /b 0

rem ===========================================================================
:weight
rem %1 = Hugging Face repo, %2 = models subfolder, %3 = file name
set "DEST=%COMFY_DIR%\models\%~2\%~3"
if exist "%DEST%" (
    echo   have %~2\%~3
    exit /b 0
)
if not exist "%COMFY_DIR%\models\%~2" mkdir "%COMFY_DIR%\models\%~2"
echo   downloading %~1/%~2/%~3 ...
curl -L --fail --retry 5 -C - -o "%DEST%.part" "https://huggingface.co/%~1/resolve/main/%~2/%~3" || exit /b 1
move /y "%DEST%.part" "%DEST%" >nul || exit /b 1
exit /b 0

:fail
echo.
echo [ERROR] Pixal3D setup failed.
exit /b 1
