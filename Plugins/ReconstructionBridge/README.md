# ReconstructionBridge

언리얼 에디터에서 이미지/데이터셋을 받아 [ExMesh](https://github.com/moumee/ExMesh)로 메쉬를 복원하고,
Auto LOD까지 만들어 프로젝트로 임포트하는 에디터 플러그인입니다.

## 폴더 구성

```
ReconstructionBridge/
├─ Content/
│  ├─ EUW_ReconstructionBridge.uasset   # 플러그인 창 (Editor Utility Widget)
│  └─ Python/
│     ├─ init_unreal.py                 # 에디터 시작 시 Tools 메뉴/툴바 버튼 등록
│     ├─ reconstruction_bridge_menu.py  # 메뉴 등록 + 창 열기
│     └─ reconstruction_bridge.py ...   # 브리지 로직
├─ ThirdParty/ExMesh/                   # ExMesh (git submodule)
└─ Setup/setup_exmesh_env.bat           # ExMesh용 conda 환경 설치
```

## 처음 설치

1. **submodule 받기** (ExMesh가 비어 있으면 플러그인이 동작하지 않음)
   ```bash
   git clone --recurse-submodules https://github.com/moumee/ue5-img2mesh.git
   # 이미 클론했다면
   git submodule update --init --recursive
   ```
2. **Python 환경 설치**: Miniconda, CUDA Toolkit 12.1, VS 2022 C++ Build Tools를 먼저 설치한 뒤
   ```bat
   Plugins\ReconstructionBridge\Setup\setup_exmesh_env.bat
   ```
   이미 `exmesh` conda 환경이 있다면 그 환경을 그대로 재사용합니다(지우지 않음).
3. **데이터셋**: `ThirdParty/ExMesh/workdir/` 아래에 두거나(`git`에는 안 올라감),
   다른 곳에 있다면 `EXMESH_WORKDIR` 환경변수로 지정합니다.

## 창 열기

에디터 상단 **Tools → Reconstruction Bridge**, 또는 레벨 에디터 툴바의 **Reconstruction Bridge** 버튼을 누르면 됩니다.

## 경로 설정 (PC별, 선택)

기본값으로 동작하지 않을 때만 환경변수로 덮어씁니다. 설정한 뒤에는 에디터를 재시작해야 합니다.

| 환경변수 | 의미 | 기본값 |
|---|---|---|
| `EXMESH_ROOT` | ExMesh 소스 폴더 | `ThirdParty/ExMesh` (submodule) |
| `EXMESH_PYTHON` | exmesh conda 환경의 `python.exe` | 일반적인 conda 설치 위치에서 `envs/exmesh` 자동 탐색 |
| `EXMESH_WORKDIR` | 데이터셋 폴더 | `<EXMESH_ROOT>/workdir` |
| `EXMESH_OUTPUT_ROOT` | 학습/익스포트 결과 | `<프로젝트>/Saved/ReconstructionBridge/outputs` |

```bat
setx EXMESH_WORKDIR "D:\data\ExMesh\workdir"
```

## ExMesh 버전 올리기

```bash
cd Plugins/ReconstructionBridge/ThirdParty/ExMesh
git fetch && git checkout <커밋 또는 브랜치>
cd ../../../..
git add Plugins/ReconstructionBridge/ThirdParty/ExMesh
git commit -m "Bump ExMesh"
```
