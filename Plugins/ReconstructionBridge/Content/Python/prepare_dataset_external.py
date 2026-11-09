"""Turn a video or a folder of photos into an ExMesh-ready dataset.

Runs OUTSIDE Unreal, in the "rb_prep" conda env (see Setup/setup_exmesh_env.bat).

    <out>/
      input/                 extracted RGB frames (COLMAP input)
      distorted/             COLMAP work folder (database + raw sparse models)
      images/                undistorted RGBA frames (alpha = object mask)
      mask/                  object masks (white = object)
      sparse/0/              undistorted PINHOLE COLMAP model
      mono_priors/da3/       Depth Anything 3 depth per image (*.npz)
      mesh.ply               visual hull used by ExMesh as the initial mesh
      prepared.json          marker written when every step succeeded

Steps (all run by default, each can be selected with --steps):
  frames  video/photos -> input/
  colmap  COLMAP SfM + undistortion -> images/, sparse/0/
  mask    rembg object masks -> mask/, alpha channel of images/
          (mask logic from video2multiview/multiview_dataset_generator.py,
           but kept full-frame: cropping per image would break the cameras)
  hull    visual hull from masks + cameras -> mesh.ply (ExMesh initial mesh;
          without it ExMesh starts from a unit sphere at the origin, which only
          works for normalized datasets such as DTU)
  da3     Depth Anything 3 (pose-conditioned) -> mono_priors/da3/

Progress lines start with "[RB] " so the Unreal side can show them.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
ALL_STEPS = ("frames", "colmap", "mask", "hull", "da3")
MARKER_NAME = "prepared.json"
MARKER_VERSION = 3  # v3: DA3-BASE + CUDA masks


def log(message):
    print(f"[RB] {message}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True, help="video file or photo folder")
    parser.add_argument("--out", "-o", required=True, help="dataset folder to create")
    parser.add_argument("--steps", default=",".join(ALL_STEPS),
                        help="comma separated subset of: " + ",".join(ALL_STEPS))
    parser.add_argument("--num", "-n", type=int, default=None,
                        help="frames to sample (video default 120, folder default: all)")
    parser.add_argument("--max-size", type=int, default=1600,
                        help="longest image side after extraction (0 = keep)")
    # COLMAP
    parser.add_argument("--colmap", default=os.environ.get("COLMAP_EXE", ""),
                        help="COLMAP executable (COLMAP.bat / colmap.exe)")
    parser.add_argument("--camera", default="OPENCV", help="COLMAP camera model")
    parser.add_argument("--matcher", default="auto", choices=("auto", "exhaustive", "sequential"),
                        help="auto = exhaustive up to 200 images, sequential above")
    parser.add_argument("--sift-peak", type=float, default=0.002,
                        help="SIFT peak threshold (COLMAP default 0.00667; lower = more features "
                             "on low-texture objects)")
    parser.add_argument("--no-gpu", action="store_true", help="COLMAP SIFT on CPU")
    # mask
    parser.add_argument("--mask-model", default="birefnet-general-lite", help="rembg model name")
    parser.add_argument("--erode", type=int, default=2, help="mask erosion in pixels")
    # hull
    parser.add_argument("--hull-res", type=int, default=160, help="voxel grid resolution")
    parser.add_argument("--hull-faces", type=int, default=30000, help="target face count")
    # DA3
    parser.add_argument("--da3-model", default="depth-anything/DA3-BASE",
                        help="DA3-BASE / DA3-SMALL are Apache-2.0; LARGE/GIANT are CC BY-NC")
    parser.add_argument("--da3-chunk", type=int, default=16, help="views per DA3 forward pass")
    parser.add_argument("--da3-res", type=int, default=504, help="DA3 processing resolution")
    return parser.parse_args()


# -----------------------------------------------------------------------------
# frames  (sampling logic from video2multiview)
# -----------------------------------------------------------------------------

def select_indices(total, num):
    if num is None or num >= total:
        return list(range(total))
    idx = np.linspace(0, total - 1, num).round().astype(int)
    return sorted(set(idx.tolist()))


def natural_key(path):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", path.name.lower())]


def _resize(img, max_size):
    if max_size and max(img.size) > max_size:
        scale = max_size / max(img.size)
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    return img


def iter_video(path, num):
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        raise RuntimeError(f"unknown frame count: {path}")
    selected = set(select_indices(total, num))
    last = max(selected)
    frame_idx = 0
    while frame_idx <= last:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx in selected:
            yield f"frame {frame_idx}", Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        frame_idx += 1
    cap.release()


def iter_photos(folder, num):
    files = sorted((p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS), key=natural_key)
    if not files:
        raise RuntimeError(f"no images in folder: {folder}")
    for i in select_indices(len(files), num):
        with Image.open(files[i]) as img:
            yield files[i].name, ImageOps.exif_transpose(img).convert("RGB")


def step_frames(args, src, out):
    input_dir = out / "input"
    if input_dir.exists():
        shutil.rmtree(input_dir)
    input_dir.mkdir(parents=True)

    if src.is_file():
        frames = iter_video(src, args.num or 120)
    else:
        frames = iter_photos(src, args.num)

    mapping = []
    first_size = None
    for i, (source, img) in enumerate(frames):
        img = _resize(img, args.max_size)
        if first_size is None:
            first_size = img.size
        elif img.size != first_size:
            raise RuntimeError(f"image size differs: {source} {img.size} (first {first_size})")
        name = f"{i:04d}.png"
        img.save(input_dir / name)
        mapping.append(f"{name}\t{source}")
        if i % 10 == 0:
            log(f"frames: {i + 1} ({source})")
    if len(mapping) < 3:
        raise RuntimeError("need at least 3 images")
    (out / "mapping.txt").write_text("\n".join(mapping), encoding="utf-8")
    log(f"frames: {len(mapping)} images, {first_size[0]}x{first_size[1]}")


# -----------------------------------------------------------------------------
# COLMAP
# -----------------------------------------------------------------------------

def _find_colmap(explicit):
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    plugin_root = Path(__file__).resolve().parents[2]
    bundled = plugin_root / "ThirdParty" / "COLMAP"
    candidates += [bundled / "COLMAP.bat", bundled / "bin" / "colmap.exe"]
    candidates += [p for p in bundled.glob("*/COLMAP.bat")]
    candidates += [p for p in bundled.glob("*/bin/colmap.exe")]
    for c in candidates:
        if c.is_file():
            return str(c)
    found = shutil.which("colmap")
    if found:
        return found
    raise RuntimeError(
        "COLMAP not found. Run Setup/setup_exmesh_env.bat or set COLMAP_EXE."
    )


def _run(cmd, what):
    log(f"{what}: " + " ".join(str(c) for c in cmd[:2]) + " ...")
    start = time.time()
    proc = subprocess.run([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-40:])
        raise RuntimeError(f"{what} failed (exit {proc.returncode}):\n{tail}")
    log(f"{what}: done in {time.time() - start:.0f}s")
    return proc.stdout


def _count_registered(model_dir):
    images_bin = model_dir / "images.bin"
    if not images_bin.is_file():
        return 0
    with images_bin.open("rb") as f:
        return int(np.frombuffer(f.read(8), dtype=np.uint64)[0])


def step_colmap(args, src, out):
    colmap = _find_colmap(args.colmap)
    log(f"colmap: using {colmap}")
    input_dir = out / "input"
    if not any(input_dir.glob("*.png")):
        raise RuntimeError(f"no frames in {input_dir} (run the frames step first)")

    work = out / "distorted"
    if work.exists():
        shutil.rmtree(work)
    (work / "sparse").mkdir(parents=True)
    db = work / "database.db"
    gpu = "0" if args.no_gpu else "1"

    _run([colmap, "feature_extractor",
          "--database_path", db,
          "--image_path", input_dir,
          "--ImageReader.single_camera", "1",
          "--ImageReader.camera_model", args.camera,
          "--SiftExtraction.peak_threshold", str(args.sift_peak),
          "--FeatureExtraction.use_gpu", gpu], "colmap feature_extractor")

    num_frames = len(list(input_dir.glob("*.png")))
    matcher = args.matcher
    if matcher == "auto":
        matcher = "exhaustive" if num_frames <= 200 else "sequential"
    match_cmd = [colmap, f"{matcher}_matcher", "--database_path", db,
                 "--FeatureMatching.use_gpu", gpu]
    if matcher == "sequential":
        match_cmd += ["--SequentialMatching.overlap", "20"]
    _run(match_cmd, f"colmap {matcher}_matcher")

    _run([colmap, "mapper",
          "--database_path", db,
          "--image_path", input_dir,
          "--output_path", work / "sparse",
          "--Mapper.init_min_num_inliers", "50",
          "--Mapper.abs_pose_min_num_inliers", "15",
          "--Mapper.ba_global_function_tolerance", "0.000001"], "colmap mapper")

    models = [d for d in (work / "sparse").iterdir() if d.is_dir()]
    if not models:
        raise RuntimeError("COLMAP could not reconstruct any camera. "
                           "Use more overlapping photos / slower camera motion.")
    best = max(models, key=_count_registered)
    registered = _count_registered(best)
    total = num_frames
    log(f"colmap: model {best.name} registered {registered}/{total} images")
    if registered < max(3, int(total * 0.3)):
        raise RuntimeError(
            f"COLMAP registered only {registered}/{total} images. Use more frames "
            "(slower camera motion / more overlap) or a more textured background.")
    if registered < total * 0.7:
        log("colmap: WARNING only part of the images were registered")

    for name in ("images", "sparse"):
        if (out / name).exists():
            shutil.rmtree(out / name)
    _run([colmap, "image_undistorter",
          "--image_path", input_dir,
          "--input_path", best,
          "--output_path", out,
          "--output_type", "COLMAP"], "colmap image_undistorter")

    # image_undistorter writes sparse/*.bin -> move into sparse/0
    sparse = out / "sparse"
    (sparse / "0").mkdir(exist_ok=True)
    for f in sparse.iterdir():
        if f.is_file():
            shutil.move(str(f), str(sparse / "0" / f.name))
    for extra in ("stereo", "run-colmap-geometric.sh", "run-colmap-photometric.sh"):
        p = out / extra
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()
    log(f"colmap: undistorted dataset written to {out}")


# -----------------------------------------------------------------------------
# masks  (rembg logic from video2multiview, full-frame output)
# -----------------------------------------------------------------------------

def _create_rembg_session(model):
    try:
        import torch  # noqa: F401  loads the CUDA/cuDNN DLLs onnxruntime-gpu needs
    except Exception:
        pass
    from rembg import new_session

    providers = ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
    try:
        import onnxruntime

        available = set(onnxruntime.get_available_providers())
        providers = [p for p in providers if p in available] or ["CPUExecutionProvider"]
    except Exception:
        pass
    log(f"mask: rembg model {model}, providers {providers}")
    try:
        return new_session(model, providers=providers)
    except TypeError:
        return new_session(model)


def make_mask(rgb, session, erode_px):
    import cv2
    from rembg import remove

    soft = remove(Image.fromarray(rgb), session=session, only_mask=True, post_process_mask=True)
    mask = (np.array(soft) > 127).astype(np.uint8)
    if erode_px > 0:
        k = 2 * erode_px + 1
        mask = cv2.erode(mask, np.ones((k, k), np.uint8))
    return mask * 255


def step_mask(args, src, out):
    images_dir = out / "images"
    files = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        raise RuntimeError(f"no undistorted images in {images_dir} (run the colmap step first)")
    mask_dir = out / "mask"
    mask_dir.mkdir(exist_ok=True)
    session = _create_rembg_session(args.mask_model)

    empty = 0
    for i, path in enumerate(files):
        with Image.open(path) as img:
            rgb = np.array(img.convert("RGB"))
        mask = make_mask(rgb, session, args.erode)
        if not mask.any():
            empty += 1
        Image.fromarray(mask.astype(np.uint8), "L").save(mask_dir / f"{path.stem}.png")
        # Keep the exact file name COLMAP knows; alpha = mask (ExMesh reads it).
        Image.fromarray(np.dstack([rgb, mask]).astype(np.uint8), "RGBA").save(path, format="PNG")
        if i % 10 == 0 or i == len(files) - 1:
            log(f"mask: {i + 1}/{len(files)}")
    if empty:
        log(f"mask: WARNING {empty} image(s) produced an empty mask")


# -----------------------------------------------------------------------------
# visual hull -> mesh.ply
# -----------------------------------------------------------------------------

def _load_cameras(out):
    from depth_anything_3.utils.read_write_model import read_model

    cameras, images, points3d = read_model(str(out / "sparse" / "0"))
    views = []
    for image_id, data in sorted(images.items(), key=lambda x: x[1].name):
        cam = cameras[data.camera_id]
        if cam.model == "PINHOLE":
            fx, fy, cx, cy = cam.params[:4]
        elif cam.model == "SIMPLE_PINHOLE":
            fx = fy = cam.params[0]
            cx, cy = cam.params[1:3]
        else:
            raise RuntimeError(f"unexpected camera model: {cam.model}")
        views.append({
            "id": image_id, "name": data.name,
            "R": data.qvec2rotmat(), "t": np.asarray(data.tvec, dtype=np.float64),
            "K": (fx, fy, cx, cy), "w": cam.width, "h": cam.height,
        })
    return views, points3d


def _project(view, pts):
    cam = pts @ view["R"].T + view["t"]
    z = cam[:, 2]
    fx, fy, cx, cy = view["K"]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = fx * cam[:, 0] / z + cx
        v = fy * cam[:, 1] / z + cy
    inside = (z > 1e-6) & (u >= 0) & (v >= 0) & (u < view["w"] - 0.5) & (v < view["h"] - 0.5)
    return u, v, inside


def _load_masks(out, views, dilate_px=4):
    import cv2

    masks = []
    kernel = np.ones((2 * dilate_px + 1, 2 * dilate_px + 1), np.uint8)
    for view in views:
        with Image.open(out / "mask" / f"{Path(view['name']).stem}.png") as img:
            m = np.array(img.convert("L")) > 127
        masks.append(cv2.dilate(m.astype(np.uint8), kernel) > 0)
    return masks


def _object_bounds(views, masks, points3d):
    """Bounding cube of sparse points that land inside the masks."""
    by_id = {v["id"]: (v, m) for v, m in zip(views, masks)}
    obj = []
    for p in points3d.values():
        hits = total = 0
        for image_id in set(p.image_ids.tolist()):
            if image_id not in by_id:
                continue
            view, mask = by_id[image_id]
            u, v, inside = _project(view, p.xyz[None, :])
            total += 1
            if inside[0] and mask[int(v[0]), int(u[0])]:
                hits += 1
        if total >= 3 and hits >= 0.8 * total:
            obj.append(p.xyz)
    if len(obj) >= 30:
        obj = np.asarray(obj)
        lo, hi = np.percentile(obj, 1, axis=0), np.percentile(obj, 99, axis=0)
        center = (lo + hi) / 2
        half = (hi - lo).max() / 2 * 1.6
        log(f"hull: {len(obj)} sparse points on the object")
        return center, half
    # Fallback: point closest to all optical axes, size from camera distance.
    log("hull: few object points, using camera convergence point")
    A = np.zeros((3, 3))
    b = np.zeros(3)
    centers = []
    for view in views:
        c = -view["R"].T @ view["t"]
        d = view["R"].T @ np.array([0.0, 0.0, 1.0])
        P = np.eye(3) - np.outer(d, d)
        A += P
        b += P @ c
        centers.append(c)
    center = np.linalg.solve(A, b)
    half = 0.35 * np.median(np.linalg.norm(np.asarray(centers) - center, axis=1))
    return center, half


def step_hull(args, src, out):
    import open3d as o3d
    from scipy import ndimage
    from skimage import measure

    views, points3d = _load_cameras(out)
    masks = _load_masks(out, views)
    center, half = _object_bounds(views, masks, points3d)

    res = int(args.hull_res)
    axis = np.linspace(-half, half, res)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1).reshape(-1, 3) + center
    seen = np.zeros(len(grid), np.int32)
    outside = np.zeros(len(grid), np.int32)
    for view, mask in zip(views, masks):
        u, v, inside = _project(view, grid)
        idx = np.nonzero(inside)[0]
        seen[idx] += 1
        hit = mask[v[idx].astype(np.int32), u[idx].astype(np.int32)]
        outside[idx[~hit]] += 1
    n = len(views)
    # Carve a voxel when it falls outside the silhouette in more than ~3% of the
    # views that see it (tolerates a few bad masks); require enough coverage.
    tolerance = np.maximum(1, (0.03 * seen).astype(np.int32))
    occupied = (seen >= max(3, int(0.3 * n))) & (outside <= tolerance)
    vol = occupied.reshape(res, res, res)
    if vol.sum() < 50:
        raise RuntimeError("visual hull is empty (masks and cameras do not agree)")
    labels, count = ndimage.label(vol)
    if count > 1:
        sizes = ndimage.sum(vol, labels, range(1, count + 1))
        vol = labels == (int(np.argmax(sizes)) + 1)
    if (vol[0].any() or vol[-1].any() or vol[:, 0].any() or vol[:, -1].any()
            or vol[:, :, 0].any() or vol[:, :, -1].any()):
        log("hull: WARNING hull touches the bounding box (object may be cut off)")

    smooth = ndimage.gaussian_filter(vol.astype(np.float32), 1.0)
    padded = np.pad(smooth, 1)
    step = axis[1] - axis[0]
    verts, faces, _, _ = measure.marching_cubes(padded, 0.5, spacing=(step, step, step))
    verts = verts - step + (center - half)

    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(verts.astype(np.float64)),
        o3d.utility.Vector3iVector(faces.astype(np.int32)),
    )
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    if len(mesh.triangles) > args.hull_faces:
        mesh = mesh.simplify_quadric_decimation(args.hull_faces)
    mesh.compute_vertex_normals()
    # Normals must point outward: flip the winding if most of them point inward.
    vertices = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    outward = np.mean(np.sum((vertices - vertices.mean(0)) * normals, axis=1) > 0)
    if outward < 0.5:
        mesh.triangles = o3d.utility.Vector3iVector(np.asarray(mesh.triangles)[:, ::-1].copy())
        mesh.compute_vertex_normals()
    mesh.vertex_colors = o3d.utility.Vector3dVector(np.full((len(mesh.vertices), 3), 0.5))
    o3d.io.write_triangle_mesh(str(out / "mesh.ply"), mesh)
    extent = np.ptp(np.asarray(mesh.vertices), axis=0)
    log(f"hull: mesh.ply {len(mesh.vertices)} vertices, {len(mesh.triangles)} faces, "
        f"size {extent[0]:.3f} x {extent[1]:.3f} x {extent[2]:.3f}")


# -----------------------------------------------------------------------------
# Depth Anything 3
# -----------------------------------------------------------------------------

def step_da3(args, src, out):
    import torch
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.read_write_model import read_model

    sparse_dir = out / "sparse" / "0"
    cameras, colmap_images, _ = read_model(str(sparse_dir))
    entries = []
    for _, data in sorted(colmap_images.items(), key=lambda x: x[1].name):
        image_path = out / "images" / data.name
        if not image_path.is_file():
            continue
        extrinsic = np.eye(4)
        extrinsic[:3, :3] = data.qvec2rotmat()
        extrinsic[:3, 3] = data.tvec
        cam = cameras[data.camera_id]
        if cam.model == "PINHOLE":
            fx, fy, cx, cy = cam.params[:4]
        elif cam.model == "SIMPLE_PINHOLE":
            f, cx, cy = cam.params[:3]
            fx = fy = f
        else:
            raise RuntimeError(f"unexpected camera model after undistortion: {cam.model}")
        intrinsic = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        entries.append((image_path, extrinsic, intrinsic))
    if not entries:
        raise RuntimeError(f"no images listed in {sparse_dir}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"da3: loading {args.da3_model} on {device} (first run downloads weights)")
    model = DepthAnything3.from_pretrained(args.da3_model).to(device)
    model.eval()

    out_dir = out / "mono_priors" / "da3"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    chunk = max(1, args.da3_chunk)
    for start in range(0, len(entries), chunk):
        batch = entries[start:start + chunk]
        rgbs = []
        for p, _, _ in batch:
            with Image.open(p) as img:
                rgbs.append(np.array(img.convert("RGB")))
        ext = np.stack([e for _, e, _ in batch]).astype(np.float32)
        ixt = np.stack([k for _, _, k in batch]).astype(np.float32)
        with torch.inference_mode():
            pred = model.inference(rgbs, extrinsics=ext, intrinsics=ixt, process_res=args.da3_res)
        for j, (p, _, _) in enumerate(batch):
            save = {"depth": np.round(pred.depth[j], 6)}
            if getattr(pred, "conf", None) is not None:
                save["conf"] = np.round(pred.conf[j], 2)
            np.savez_compressed(out_dir / f"{p.stem}.npz", **save)
        log(f"da3: {min(start + chunk, len(entries))}/{len(entries)}")
        if device.type == "cuda":
            torch.cuda.empty_cache()


# -----------------------------------------------------------------------------

STEP_FUNCS = {"frames": step_frames, "colmap": step_colmap, "mask": step_mask,
              "hull": step_hull, "da3": step_da3}


def _dataset_complete(out):
    images = [p for p in (out / "images").glob("*") if p.suffix.lower() in IMAGE_EXTS]
    if not images or not (out / "sparse" / "0" / "images.bin").is_file() or not (out / "mesh.ply").is_file():
        return False
    stems = {p.stem for p in images}
    masks = {p.stem for p in (out / "mask").glob("*.png")}
    depths = {p.stem for p in (out / "mono_priors" / "da3").glob("*.npz")}
    return stems <= masks and stems <= depths


def main():
    args = parse_args()
    src = Path(args.input.strip().strip('"'))
    out = Path(args.out.strip().strip('"'))
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    unknown = [s for s in steps if s not in STEP_FUNCS]
    if unknown:
        raise SystemExit(f"unknown step(s): {unknown}")
    if "frames" in steps and not src.exists():
        raise SystemExit(f"input not found: {src}")

    out.mkdir(parents=True, exist_ok=True)
    marker = out / MARKER_NAME
    if marker.exists():
        marker.unlink()

    total_start = time.time()
    for i, step in enumerate(s for s in ALL_STEPS if s in steps):
        log(f"STEP {step} ({i + 1}/{len(steps)})")
        STEP_FUNCS[step](args, src, out)

    if all(s in steps for s in ALL_STEPS) or _dataset_complete(out):
        marker.write_text(json.dumps({
            "version": MARKER_VERSION,
            "source": str(src.resolve()),
            "source_mtime": src.stat().st_mtime if src.exists() else None,
            "num": args.num,
            "max_size": args.max_size,
            "mask_model": args.mask_model,
            "da3_model": args.da3_model,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
    log(f"DONE in {time.time() - total_start:.0f}s -> {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # report a single readable line to Unreal
        log(f"ERROR {exc}")
        raise
