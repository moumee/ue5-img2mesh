import argparse
import json
from pathlib import Path

from PIL import Image


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff"
}


def find_images(folder):
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file()
        and not path.name.startswith("._")
        and path.suffix.lower() in IMAGE_EXTENSIONS
    )

def normalize_file_stem(path):
    stem = path.stem

    if stem.endswith("_mask"):
        stem = stem[:-5]

    if stem.isdigit():
        return str(int(stem))

    return stem

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()

    dataset = Path(args.dataset)
    images_folder = dataset / "images"
    masks_folder = dataset / "mask"

    if not images_folder.is_dir():
        raise FileNotFoundError(
            f"Images folder not found: {images_folder}"
        )

    if not masks_folder.is_dir():
        raise FileNotFoundError(
            f"Mask folder not found: {masks_folder}"
        )

    image_files = find_images(images_folder)
    mask_files = find_images(masks_folder)


    mask_lookup = {
        normalize_file_stem(mask): mask
        for mask in mask_files
    }

    image_sizes = set()
    missing_masks = []
    size_mismatches = []

    for image_path in image_files:
        with Image.open(image_path) as image:
            image_size = image.size

        image_sizes.add(
            f"{image_size[0]}x{image_size[1]}"
        )

        mask_path = mask_lookup.get(
            normalize_file_stem(image_path)
        )

        if mask_path is None:
            missing_masks.append(image_path.name)
            continue

        with Image.open(mask_path) as mask:
            mask_size = mask.size

        if image_size != mask_size:
            size_mismatches.append({
                "image": image_path.name,
                "image_size": list(image_size),
                "mask": mask_path.name,
                "mask_size": list(mask_size)
            })

    report = {
        "dataset": str(dataset),
        "image_count": len(image_files),
        "mask_count": len(mask_files),
        "image_sizes": sorted(image_sizes),
        "missing_mask_count": len(missing_masks),
        "missing_mask_samples": missing_masks[:5],
        "size_mismatch_count": len(size_mismatches),
        "size_mismatch_samples": size_mismatches[:5]
    }

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()