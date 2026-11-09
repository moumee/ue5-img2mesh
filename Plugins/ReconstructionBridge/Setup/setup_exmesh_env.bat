@echo off
rem ---------------------------------------------------------------------------
rem  ReconstructionBridge - one-time setup (Windows)
rem
rem  Installs:
rem    exmesh   conda env for ExMesh training (PyTorch + CUDA extensions)
rem    prep     conda env "rb_prep" for preprocessing (Depth Anything 3 + rembg)
rem    colmap   COLMAP 4.2.1 (CUDA build) into ThirdParty\COLMAP
rem
rem  Requirements (install first):
rem    - Miniconda / Anaconda
rem    - NVIDIA driver; for "exmesh" also CUDA Toolkit 12.1 (CUDA_PATH)
rem      and Visual Studio 2022 Build Tools ("Desktop development with C++")
rem
rem  Usage:  setup_exmesh_env.bat [all^|exmesh^|prep^|colmap]   (default: all)
rem  Existing conda envs are reused, never deleted.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=all"

set "EXMESH_ENV=exmesh"
set "PREP_ENV=rb_prep"
set "PLUGIN_DIR=%~dp0.."
set "EXMESH=%PLUGIN_DIR%\ThirdParty\ExMesh"
set "COLMAP_DIR=%PLUGIN_DIR%\ThirdParty\COLMAP"
set "COLMAP_URL=https://github.com/colmap/colmap/releases/download/4.2.1/colmap-x64-windows-cuda.zip"
set "DA3_REF=3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
set "TORCH_PKGS=torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1"
set "TORCH_INDEX=https://download.pytorch.org/whl/cu121"

if /I "%TARGET%"=="colmap" goto :colmap_only

rem ---- locate conda -----------------------------------------------------------
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
    echo [ERROR] conda not found. Install Miniconda first.
    exit /b 1
)
echo Using conda: %CONDA%

if /I "%TARGET%"=="all" (
    call :setup_exmesh || goto :fail
    call :setup_prep || goto :fail
    call :setup_colmap || goto :fail
) else if /I "%TARGET%"=="exmesh" (
    call :setup_exmesh || goto :fail
) else if /I "%TARGET%"=="prep" (
    call :setup_prep || goto :fail
) else (
    echo [ERROR] unknown target "%TARGET%". Use all, exmesh, prep or colmap.
    exit /b 1
)
echo.
echo Setup finished.
exit /b 0

:colmap_only
call :setup_colmap || goto :fail
echo.
echo Setup finished.
exit /b 0

rem ===========================================================================
:ensure_env
rem %1 = env name
set "ENV_LIST=%TEMP%\rb_conda_envs_%RANDOM%.txt"
call "%CONDA%" env list > "%ENV_LIST%" 2>nul
findstr /R /C:"^%~1 " "%ENV_LIST%" >nul
set "ENV_MISSING=%ERRORLEVEL%"
del "%ENV_LIST%" >nul 2>nul
if not "%ENV_MISSING%"=="0" (
    echo Creating conda env "%~1" ...
    call "%CONDA%" create -y -n %~1 python=3.11 || exit /b 1
) else (
    echo Conda env "%~1" already exists - installing into it.
)
exit /b 0

rem ===========================================================================
:setup_exmesh
echo.
echo ===== ExMesh training env "%EXMESH_ENV%" =====
if not exist "%EXMESH%\train.py" (
    echo [ERROR] ExMesh submodule not found: %EXMESH%
    echo         Run in the project root:  git submodule update --init --recursive
    exit /b 1
)
if not defined CUDA_PATH (
    echo [WARN] CUDA_PATH is not set. Compiling the CUDA extensions will likely fail.
) else (
    set "CUDA_HOME=%CUDA_PATH%"
)
call :ensure_env %EXMESH_ENV% || exit /b 1
set "RUN=call "%CONDA%" run -n %EXMESH_ENV% --no-capture-output"
pushd "%EXMESH%" || exit /b 1
%RUN% python -m pip install %TORCH_PKGS% --index-url %TORCH_INDEX% || goto :exmesh_fail
%RUN% python -m pip install -r requirements.txt || goto :exmesh_fail
%RUN% python -m pip install git+https://github.com/NVlabs/nvdiffrast/ --no-build-isolation || goto :exmesh_fail
%RUN% python -m pip install "git+https://github.com/facebookresearch/pytorch3d.git" --no-build-isolation || goto :exmesh_fail
%RUN% python -m pip install PGSR/submodules/diff-plane-rasterization --no-build-isolation || goto :exmesh_fail
%RUN% python -m pip install PGSR/submodules/simple-knn --no-build-isolation || goto :exmesh_fail
popd
%RUN% python -c "import torch; print('exmesh: torch', torch.__version__, 'cuda', torch.cuda.is_available())"
exit /b 0
:exmesh_fail
popd
exit /b 1

rem ===========================================================================
:setup_prep
echo.
echo ===== Preprocessing env "%PREP_ENV%" (Depth Anything 3 + rembg) =====
call :ensure_env %PREP_ENV% || exit /b 1
set "RUN=call "%CONDA%" run -n %PREP_ENV% --no-capture-output"
%RUN% python -m pip install %TORCH_PKGS% --index-url %TORCH_INDEX% || exit /b 1
rem DA3 without xformers (optional for DA3, no Windows wheel for torch 2.5.1)
%RUN% python -m pip install --no-deps "git+https://github.com/ByteDance-Seed/depth-anything-3.git@%DA3_REF%" || exit /b 1
%RUN% python -m pip install "numpy<2" addict trimesh einops huggingface_hub imageio opencv-python open3d fastapi uvicorn requests typer pillow omegaconf evo e3nn "moviepy==1.0.3" plyfile pillow_heif safetensors pycolmap || exit /b 1
rem rembg 2.0.69 is the newest release that still allows numpy<2 (needed by DA3).
rem onnxruntime-gpu 1.20.x = CUDA 12 + cuDNN 9 (DLLs come with torch cu121); about 4x faster
rem than onnxruntime-directml for the BiRefNet mask model.
%RUN% python -m pip uninstall -y onnxruntime onnxruntime-directml >nul 2>nul
%RUN% python -m pip install "rembg==2.0.69" "onnxruntime-gpu==1.20.2" "numpy<2" || exit /b 1
%RUN% python -W ignore -c "import torch, rembg, onnxruntime; from depth_anything_3.api import DepthAnything3; print('rb_prep: torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'onnx', onnxruntime.get_available_providers())"
exit /b 0

rem ===========================================================================
:setup_colmap
echo.
echo ===== COLMAP =====
if exist "%COLMAP_DIR%\COLMAP.bat" (
    echo COLMAP already installed: %COLMAP_DIR%
    exit /b 0
)
set "COLMAP_ZIP=%TEMP%\colmap-x64-windows-cuda.zip"
echo Downloading %COLMAP_URL% (about 400 MB) ...
curl.exe -L --fail -o "%COLMAP_ZIP%" "%COLMAP_URL%" || exit /b 1
if not exist "%COLMAP_DIR%" mkdir "%COLMAP_DIR%"
"%SystemRoot%\System32\tar.exe" -xf "%COLMAP_ZIP%" -C "%COLMAP_DIR%" || exit /b 1
del "%COLMAP_ZIP%" >nul 2>nul
if not exist "%COLMAP_DIR%\COLMAP.bat" (
    echo [ERROR] COLMAP.bat not found after extraction in %COLMAP_DIR%
    exit /b 1
)
echo COLMAP installed: %COLMAP_DIR%
exit /b 0

rem ===========================================================================
:fail
echo.
echo [ERROR] Setup failed. See the messages above.
exit /b 1
