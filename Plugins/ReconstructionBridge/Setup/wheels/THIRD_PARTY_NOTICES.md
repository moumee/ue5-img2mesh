# Third-party notices for the prebuilt wheels

The wheels in this folder are compiled, unmodified builds of the projects below
(Python 3.11, torch 2.5.1+cu121, Windows x64), built with `../build_exmesh_wheels.bat`.
They are redistributed under each project's own license; full texts are in `licenses/`.

| Wheel | Source | License |
|---|---|---|
| `simple_knn-0.0.0` | ExMesh `PGSR/submodules/simple-knn` (Copyright (C) 2023, Inria) | Gaussian-Splatting License, non-commercial: `licenses/gaussian-splatting-LICENSE.md` |
| `diff_plane_rasterization-0.0.0` | ExMesh `PGSR/submodules/diff-plane-rasterization` (Inria / MPII, ZJU 3D Vision Group) | Gaussian-Splatting License, non-commercial: `licenses/gaussian-splatting-LICENSE.md`; PGSR (educational, research and non-profit only): `licenses/PGSR-LICENSE.md` |
| `nvdiffrast-0.4.0` | https://github.com/NVlabs/nvdiffrast @ v0.4.0 (Copyright (c) NVIDIA Corporation) | NVIDIA Source Code License, research/evaluation use only: `licenses/nvdiffrast-LICENSE.txt` |
| `pytorch3d-0.7.9` | https://github.com/facebookresearch/pytorch3d @ v0.7.9 (Copyright (c) Meta Platforms, Inc.) | BSD-3-Clause: `licenses/pytorch3d-LICENSE.txt`, `licenses/pytorch3d-LICENSE-3RD-PARTY.txt` |

Because of the non-commercial licenses above, these wheels (and the ExMesh
pipeline that needs them) may only be used for non-commercial research,
evaluation and educational purposes.
