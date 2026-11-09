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
│     ├─ reconstruction_prepare.py      # 영상/사진 → 데이터셋 자동 전처리 (언리얼 쪽)
│     └─ prepare_dataset_external.py    # 전처리 본체 (rb_prep 환경에서 실행)
├─ ThirdParty/ExMesh/                   # ExMesh (git submodule)
├─ ThirdParty/COLMAP/                   # COLMAP 4.2.1 (설치 스크립트가 받음, git 제외)
└─ Setup/setup_exmesh_env.bat           # conda 환경 + COLMAP 설치
```

## 처음 설치

1. **submodule 받기** (ExMesh가 비어 있으면 플러그인이 동작하지 않음)
   ```bash
   git clone --recurse-submodules https://github.com/moumee/ue5-img2mesh.git
   # 이미 클론했다면
   git submodule update --init --recursive
   ```
2. **환경 설치**: Miniconda, CUDA Toolkit 12.1, VS 2022 C++ Build Tools를 먼저 설치한 뒤
   ```bat
   Plugins\ReconstructionBridge\Setup\setup_exmesh_env.bat          :: 전부
   Plugins\ReconstructionBridge\Setup\setup_exmesh_env.bat prep     :: 전처리 환경만
   Plugins\ReconstructionBridge\Setup\setup_exmesh_env.bat colmap   :: COLMAP만
   ```
   - `exmesh`: ExMesh 학습 환경
   - `rb_prep`: 전처리 환경 (Depth Anything 3 + rembg)
   - `ThirdParty/COLMAP`: COLMAP (약 400MB 다운로드)

   이미 있는 conda 환경은 지우지 않고 그대로 재사용합니다. 모델 가중치(DA3 약 1.4GB, rembg 약 220MB)는 처음 전처리할 때 자동으로 받습니다.
3. **데이터셋**: 영상/사진 폴더는 아래 자동 전처리를 쓰면 됩니다. 이미 전처리된 데이터셋(DTU 등)은
   `ThirdParty/ExMesh/workdir/` 아래에 두거나(`git`에는 안 올라감), 다른 곳이면 `EXMESH_WORKDIR`로 지정합니다.

## 영상 / 사진 폴더로 바로 돌리기 (자동 전처리)

위젯의 데이터셋 경로에 **영상 파일**(`.mp4`, `.mov` 등)이나 **사진 폴더**를 넣고 실행하면,
학습 전에 아래 전처리가 백그라운드에서 자동으로 돌아갑니다. 진행 상황은 Output Log의 `ReconstructionBridge prep:` 줄에 나옵니다.

| 단계 | 내용 | 결과 |
|---|---|---|
| frames | 영상에서 120프레임 균등 추출 (사진 폴더는 전부), 긴 변 1600px로 축소 | `input/` |
| colmap | COLMAP SfM, 왜곡 보정 | `images/`, `sparse/0/` |
| mask | rembg(`birefnet-general-lite`)로 물체 마스크 → `images/`의 알파 채널에도 기록 | `mask/` |
| hull | 마스크 실루엣 + 카메라로 visual hull을 깎아 ExMesh 초기 메쉬 생성 | `mesh.ply` |
| da3 | Depth Anything 3(`DA3-LARGE-1.1`), COLMAP 카메라를 넣어 depth 추정 | `mono_priors/da3/` |

- 결과는 `<프로젝트>/Saved/ReconstructionBridge/datasets/<이름>_<해시>/`에 저장되고, 원본이 바뀌지 않으면 다음 실행 때 재사용합니다.
- **Validate** 버튼은 영상/사진 폴더면 전처리 계획과 빠진 설치 항목을 보여 줍니다.
- 마스크는 `video2multiview/multiview_dataset_generator.py`의 rembg 로직을 그대로 쓰지만, **512 정사각형 크롭은 하지 않습니다**. 사진마다 다르게 자르면 COLMAP 카메라와 안 맞기 때문입니다.
- 촬영 팁: 물체 주위를 천천히 한 바퀴 이상 돌고, 바닥/배경에 무늬가 있으면 COLMAP이 훨씬 잘 됩니다. 등록된 사진이 30% 미만이면 전처리가 실패로 끝납니다.
- 파이썬 콘솔에서 직접 실행/취소:
  ```python
  import reconstruction_prepare as rp
  rp.start_prepare(r"D:\videos\bear.mp4", num_frames=150)
  rp.cancel_prepare()
  ```
- 명령줄에서 단독 실행(전처리 환경의 python 사용):
  ```bat
  %USERPROFILE%\miniconda3\envs\rb_prep\python.exe Plugins\ReconstructionBridge\Content\Python\prepare_dataset_external.py -i bear.mp4 -o D:\data\bear
  ```

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
| `RB_PREP_PYTHON` | 전처리 환경의 `python.exe` | `envs/rb_prep` 자동 탐색 |
| `COLMAP_EXE` | COLMAP 실행 파일 | `ThirdParty/COLMAP/COLMAP.bat` |
| `RB_DATASETS_ROOT` | 전처리된 데이터셋 저장 위치 | `<프로젝트>/Saved/ReconstructionBridge/datasets` |

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
