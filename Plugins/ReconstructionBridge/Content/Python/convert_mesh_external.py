import argparse
import json
from pathlib import Path

import trimesh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
    "--scale",
    type=float,
    default=100.0
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input mesh not found: {input_path}"
        )

    loaded = trimesh.load(
        input_path,
        process=False
    )

    if isinstance(loaded, trimesh.Scene):
        geometries = list(
            loaded.geometry.values()
        )

        if not geometries:
            raise RuntimeError(
                "No mesh geometry was found."
            )

        mesh = trimesh.util.concatenate(
            geometries
        )

    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded

    else:
        raise TypeError(
            f"Unsupported mesh type: {type(loaded)}"
        )
    
    mesh.apply_scale(
    args.scale
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    mesh.export(
        output_path,
        file_type="obj"
    )

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "scale": args.scale,
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "extents": [
            float(value)
            for value in mesh.extents
        ]
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