@echo off
rem ---------------------------------------------------------------------------
rem  ReconstructionBridge - ExMesh conda environment setup (Windows)
rem
rem  Requirements (install first):
rem    - Miniconda / Anaconda
rem    - NVIDIA CUDA Toolkit 12.1  (CUDA_PATH must point to it)
rem    - Visual Studio 2022 Build Tools with "Desktop development with C++"
rem      (needed to compile the CUDA rasterizer extensions)
rem
rem  Usage:  setup_exmesh_env.bat [env_name]        (default env name: exmesh)
rem  An existing environment with the same name is reused, never deleted.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions

set "ENV_NAME=%~1"
if "%ENV_NAME%"=="" set "ENV_NAME=exmesh"

set "EXMESH=%~dp0..\ThirdParty\ExMesh"
if not exist "%EXMESH%\train.py" (
    echo [ERROR] ExMesh submodule not found: %EXMESH%
    echo         Run in the project root:  git submodule update --init --recursive
    exit /b 1
)

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

if not defined CUDA_PATH (
    echo [WARN] CUDA_PATH is not set. Compiling the CUDA extensions will likely fail.
) else (
    set "CUDA_HOME=%CUDA_PATH%"
)

rem ---- create env (only if missing) -------------------------------------------
set "ENV_LIST=%TEMP%\rb_conda_envs_%RANDOM%.txt"
call "%CONDA%" env list > "%ENV_LIST%" 2>nul
findstr /R /C:"^%ENV_NAME% " "%ENV_LIST%" >nul
set "ENV_MISSING=%ERRORLEVEL%"
del "%ENV_LIST%" >nul 2>nul
if not "%ENV_MISSING%"=="0" (
    echo Creating conda env "%ENV_NAME%" ...
    call "%CONDA%" create -y -n %ENV_NAME% python=3.11 || goto :fail
) else (
    echo Conda env "%ENV_NAME%" already exists - installing into it.
)

set "RUN=call "%CONDA%" run -n %ENV_NAME% --no-capture-output"

pushd "%EXMESH%" || goto :fail

echo.
echo === PyTorch (CUDA 12.1) ===
%RUN% python -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121 || goto :fail_pop

echo.
echo === requirements.txt ===
%RUN% python -m pip install -r requirements.txt || goto :fail_pop

echo.
echo === CUDA extensions ===
%RUN% python -m pip install git+https://github.com/NVlabs/nvdiffrast/ --no-build-isolation || goto :fail_pop
%RUN% python -m pip install "git+https://github.com/facebookresearch/pytorch3d.git" --no-build-isolation || goto :fail_pop
%RUN% python -m pip install PGSR/submodules/diff-plane-rasterization --no-build-isolation || goto :fail_pop
%RUN% python -m pip install PGSR/submodules/simple-knn --no-build-isolation || goto :fail_pop

popd

echo.
echo === Check ===
%RUN% python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

echo.
echo Done. The plugin auto-detects "%ENV_NAME%" under common conda locations.
if /I not "%ENV_NAME%"=="exmesh" (
    echo Because you used a custom env name, set EXMESH_PYTHON to its python.exe, e.g.
    echo     setx EXMESH_PYTHON "%%USERPROFILE%%\miniconda3\envs\%ENV_NAME%\python.exe"
)
exit /b 0

:fail_pop
popd
:fail
echo.
echo [ERROR] Setup failed. See the messages above.
exit /b 1
