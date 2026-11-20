@echo off
rem ---------------------------------------------------------------------------
rem  ReconstructionBridge - build the prebuilt CUDA extension wheels (maintainers)
rem
rem  Teammates do NOT run this. It compiles the four CUDA extensions ExMesh needs
rem  once, so setup_exmesh_env.bat can install them without CUDA Toolkit or
rem  Visual Studio Build Tools on every PC.
rem
rem  Requirements: the "exmesh" conda env (setup_exmesh_env.bat exmesh-src),
rem                CUDA Toolkit 12.1 (CUDA_PATH), VS 2022 C++ Build Tools.
rem  Output:       Setup\wheels\*.whl  (committed to git; setup_exmesh_env.bat
rem                installs them). Update WHEELS there if the file names change.
rem
rem  The wheels only work with: Python 3.11, torch 2.5.1+cu121, and the GPU
rem  architectures in TORCH_CUDA_ARCH_LIST below. Rebuild if any of these change.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions

set "ENV_NAME=exmesh"
set "PLUGIN_DIR=%~dp0.."
set "EXMESH=%PLUGIN_DIR%\ThirdParty\ExMesh"
set "OUT=%~dp0wheels"
set "NVDIFFRAST_REF=v0.4.0"
set "PYTORCH3D_REF=v0.7.9"

rem RTX 20 (7.5), A100 (8.0), RTX 30 (8.6), RTX 40 (8.9), H100 (9.0) + PTX for newer.
set "TORCH_CUDA_ARCH_LIST=7.5;8.0;8.6;8.9;9.0+PTX"
set "FORCE_CUDA=1"
set "DISTUTILS_USE_SDK=1"

if not defined CUDA_PATH (
    echo [ERROR] CUDA_PATH is not set. Install CUDA Toolkit 12.1 first.
    exit /b 1
)
set "CUDA_HOME=%CUDA_PATH%"

set "CONDA="
for %%D in (
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\anaconda3"
    "%USERPROFILE%\miniforge3"
    "%LOCALAPPDATA%\miniconda3"
    "C:\ProgramData\miniconda3"
    "C:\ProgramData\anaconda3"
) do if not defined CONDA if exist "%%~D\condabin\conda.bat" set "CONDA=%%~D\condabin\conda.bat"
if not defined CONDA (
    echo [ERROR] conda not found.
    exit /b 1
)

rem Compile inside a VS 2022 developer environment so cl.exe / link.exe are found.
rem nvcc 12.1 only accepts MSVC up to 14.39, so prefer that toolset when a VS 2022
rem install has it (VS 2026 / newer 2022 toolsets are rejected by nvcc 12.1).
set "VCVARS="
set "VCVER="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
    for /f "usebackq delims=" %%I in (`"%VSWHERE%" -all -products * -version [17.0^,18.0^) -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
        if exist "%%I\VC\Auxiliary\Build\vcvars64.bat" (
            if not defined VCVARS set "VCVARS=%%I\VC\Auxiliary\Build\vcvars64.bat"
            for /d %%T in ("%%I\VC\Tools\MSVC\14.39*") do if not defined VCVER (
                set "VCVARS=%%I\VC\Auxiliary\Build\vcvars64.bat"
                set "VCVER=14.39"
            )
        )
    )
)
if not defined VCVARS (
    echo [ERROR] Visual Studio 2022 C++ Build Tools not found.
    exit /b 1
)
if defined VCVER (
    call "%VCVARS%" -vcvars_ver=%VCVER% >nul || goto :fail
) else (
    echo [WARN] MSVC 14.39 toolset not found; using the default VS 2022 toolset.
    call "%VCVARS%" >nul || goto :fail
    set "NVCC_APPEND_FLAGS=-allow-unsupported-compiler -D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH"
)
where cl.exe

if not exist "%OUT%" mkdir "%OUT%"
set "RUN=call "%CONDA%" run -n %ENV_NAME% --no-capture-output"
set "WHEEL=%RUN% python -m pip wheel --no-deps --no-build-isolation -w "%OUT%""

%RUN% python -m pip install wheel setuptools ninja || goto :fail
%WHEEL% "%EXMESH%\PGSR\submodules\simple-knn" || goto :fail
%WHEEL% "%EXMESH%\PGSR\submodules\diff-plane-rasterization" || goto :fail
%WHEEL% "git+https://github.com/NVlabs/nvdiffrast.git@%NVDIFFRAST_REF%" || goto :fail
%WHEEL% "git+https://github.com/facebookresearch/pytorch3d.git@%PYTORCH3D_REF%" || goto :fail

echo.
echo Wheels written to %OUT%:
dir /b "%OUT%\*.whl"
exit /b 0

:fail
echo.
echo [ERROR] Wheel build failed. See the messages above.
exit /b 1
