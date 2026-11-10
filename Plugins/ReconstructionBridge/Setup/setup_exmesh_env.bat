@echo off
rem ---------------------------------------------------------------------------
rem  ReconstructionBridge - one-time setup (Windows)
rem
rem  Usually started from the editor: Tools > Reconstruction Bridge Setup.
rem
rem  Installs:
rem    submodule  ThirdParty\ExMesh (git submodule update --init --recursive)
rem    exmesh     conda env for ExMesh training (PyTorch + prebuilt CUDA extensions)
rem    prep       conda env "rb_prep" for preprocessing (Depth Anything 3 + rembg)
rem    colmap     COLMAP 4.2.1 (CUDA build) into ThirdParty\COLMAP
rem
rem  Requirements (install first):
rem    - Miniconda (or Anaconda / Miniforge)
rem    - git, NVIDIA GPU (RTX 20 series or newer, RTX 50 not supported) + driver
rem
rem  The CUDA extensions (simple-knn, diff-plane-rasterization, nvdiffrast,
rem  pytorch3d) are installed from the prebuilt wheels in Setup\wheels (committed
rem  to git), so CUDA Toolkit and Visual Studio are NOT needed. "exmesh-src" compiles them from
rem  source instead (needs CUDA Toolkit 12.1 + VS 2022 C++ Build Tools).
rem
rem  Usage:  setup_exmesh_env.bat [all^|exmesh^|exmesh-src^|prep^|colmap]   (default: all)
rem  Existing conda envs are reused, never deleted.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=all"

set "EXMESH_ENV=exmesh"
set "PREP_ENV=rb_prep"
set "PLUGIN_DIR=%~dp0.."
set "PROJECT_DIR=%~dp0..\..\.."
set "EXMESH=%PLUGIN_DIR%\ThirdParty\ExMesh"
set "COLMAP_DIR=%PLUGIN_DIR%\ThirdParty\COLMAP"
set "COLMAP_URL=https://github.com/colmap/colmap/releases/download/4.2.1/colmap-x64-windows-cuda.zip"
set "DA3_REF=3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
set "TORCH_PKGS=torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1"
set "TORCH_INDEX=https://download.pytorch.org/whl/cu121"

rem Prebuilt CUDA extension wheels (built by Setup\build_exmesh_wheels.bat, committed to git).
set "WHEEL_DIR=%~dp0wheels"
set "WHEELS=simple_knn-0.0.0-cp311-cp311-win_amd64.whl diff_plane_rasterization-0.0.0-cp311-cp311-win_amd64.whl nvdiffrast-0.4.0-cp311-cp311-win_amd64.whl pytorch3d-0.7.9-cp311-cp311-win_amd64.whl"
set "NVDIFFRAST_REF=v0.4.0"
set "PYTORCH3D_REF=v0.7.9"

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
    echo [ERROR] conda not found. Install Miniconda first:
    echo         https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)
echo Using conda: %CONDA%

if /I "%TARGET%"=="all" (
    call :setup_exmesh || goto :fail
    call :setup_prep || goto :fail
    call :setup_colmap || goto :fail
) else if /I "%TARGET%"=="exmesh" (
    call :setup_exmesh || goto :fail
) else if /I "%TARGET%"=="exmesh-src" (
    set "FROM_SOURCE=1"
    call :setup_exmesh || goto :fail
) else if /I "%TARGET%"=="prep" (
    call :setup_prep || goto :fail
) else (
    echo [ERROR] unknown target "%TARGET%". Use all, exmesh, exmesh-src, prep or colmap.
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
:ensure_submodule
if exist "%EXMESH%\train.py" exit /b 0
echo ExMesh submodule is empty - fetching it ...
where git >nul 2>nul || (
    echo [ERROR] git not found. Install git, or run in the project root:
    echo         git submodule update --init --recursive
    exit /b 1
)
git -C "%PROJECT_DIR%" submodule update --init --recursive || exit /b 1
if not exist "%EXMESH%\train.py" (
    echo [ERROR] ExMesh submodule not found after update: %EXMESH%
    exit /b 1
)
exit /b 0

rem ===========================================================================
:setup_exmesh
echo.
echo ===== ExMesh training env "%EXMESH_ENV%" =====
call :ensure_submodule || exit /b 1
call :ensure_env %EXMESH_ENV% || exit /b 1
set "RUN=call "%CONDA%" run -n %EXMESH_ENV% --no-capture-output"
%RUN% python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" || (
    echo [ERROR] conda env "%EXMESH_ENV%" is not Python 3.11. The prebuilt wheels need 3.11.
    echo         Remove it with "conda env remove -n %EXMESH_ENV%" and run this again.
    exit /b 1
)
pushd "%EXMESH%" || exit /b 1
%RUN% python -m pip install %TORCH_PKGS% --index-url %TORCH_INDEX% || goto :exmesh_fail
%RUN% python -m pip install -r requirements.txt || goto :exmesh_fail
popd
if defined FROM_SOURCE (
    call :exmesh_ext_source || exit /b 1
) else (
    call :exmesh_ext_wheels || exit /b 1
)
%RUN% python -c "import torch, nvdiffrast.torch, pytorch3d, simple_knn._C, diff_plane_rasterization; print('exmesh: torch', torch.__version__, 'cuda', torch.cuda.is_available())" || (
    echo [ERROR] ExMesh CUDA extensions failed to import.
    exit /b 1
)
exit /b 0
:exmesh_fail
popd
exit /b 1

:exmesh_ext_wheels
set "WHEEL_FILES="
for %%W in (%WHEELS%) do (
    if not exist "%WHEEL_DIR%\%%W" (
        echo [ERROR] Prebuilt wheel not found: %WHEEL_DIR%\%%W
        echo         Pull the latest project, or use "setup_exmesh_env.bat exmesh-src".
        exit /b 1
    )
    call set "WHEEL_FILES=%%WHEEL_FILES%% "%WHEEL_DIR%\%%W""
)
%RUN% python -m pip install --force-reinstall --no-deps %WHEEL_FILES% || exit /b 1
rem pytorch3d runtime dependency (pulled in by --no-deps above otherwise).
%RUN% python -m pip install iopath || exit /b 1
exit /b 0

:exmesh_ext_source
if not defined CUDA_PATH (
    echo [WARN] CUDA_PATH is not set. Compiling the CUDA extensions will likely fail.
) else (
    set "CUDA_HOME=%CUDA_PATH%"
)
pushd "%EXMESH%" || exit /b 1
%RUN% python -m pip install "git+https://github.com/NVlabs/nvdiffrast.git@%NVDIFFRAST_REF%" --no-build-isolation || goto :exmesh_fail
%RUN% python -m pip install "git+https://github.com/facebookresearch/pytorch3d.git@%PYTORCH3D_REF%" --no-build-isolation || goto :exmesh_fail
%RUN% python -m pip install PGSR/submodules/diff-plane-rasterization --no-build-isolation || goto :exmesh_fail
%RUN% python -m pip install PGSR/submodules/simple-knn --no-build-isolation || goto :exmesh_fail
popd
exit /b 0

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
