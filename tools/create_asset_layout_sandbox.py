from __future__ import annotations

import argparse
import base64
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "asset_layout_sandbox"

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def write_text(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)


def create_standard_pipeline(root: Path) -> None:
    project = root / "standard_pipeline"
    write_text(project / "standard_pipeline_001.hipnc", "fake hip")

    shot = project / "shots" / "sh010"
    write_text(shot / "publish" / "animation" / "sh010_animation_v001.usd", "#usda")
    write_text(shot / "publish" / "lighting" / "sh010_lighting_v002.usd", "#usda")
    write_text(shot / "publish" / "layout" / "sh010_layout_v001.mp4", "fake video")
    write_png(shot / "preview" / "sh010_thumb.png")
    write_text(shot / "work" / "notes.txt", "fake work")

    for name in ("hero_tree", "hero_rock"):
        asset = project / "assets" / name
        write_text(asset / "publish" / "modeling" / f"{name}_geo_v001.usdnc", "#usda")
        write_text(asset / "publish" / "lookdev" / f"{name}_mat_v001.usdnc", "#usda")
        write_text(asset / "publish" / "payload.usdnc", "#usda")
        write_png(asset / "preview" / f"{name}.png")


def create_pipeline_plus_library(root: Path) -> None:
    project = root / "pipeline_plus_library"
    for name in ("lamp", "chair"):
        asset = project / "production_items" / name
        write_text(asset / "publish" / "modeling" / f"{name}_geo_v001.usdnc", "#usda")
        write_text(asset / "publish" / "lookdev" / f"{name}_mat_v001.usdnc", "#usda")
        write_png(asset / "preview" / f"{name}.png")

    for name, ext in (("lamp", "obj"), ("chair", "fbx"), ("table", "obj")):
        item = project / "incoming_models" / name
        write_text(item / f"{name}.{ext}", "fake source geometry")
        write_text(item / "Textures" / f"{name}_1001_BaseColor.exr", "fake exr")
        write_text(item / "Textures" / f"{name}_1001_Roughness.exr", "fake exr")


def create_library_only(root: Path) -> None:
    project = root / "library_only_vendor_drop"
    for name, ext in (("crate", "obj"), ("barrel", "fbx"), ("cloth_sheet", "abc")):
        item = project / "vendor_drop_2026" / name
        write_text(item / f"{name}.{ext}", "fake source geometry")
        write_text(item / "textures" / f"{name}_BaseColor.exr", "fake exr")
        write_text(item / "textures" / f"{name}_Normal.exr", "fake exr")


def create_mirrored_usd(root: Path) -> None:
    project = root / "mirrored_usd_layout"
    for name in ("counter", "neon_sign"):
        source = project / "source_models" / name
        write_text(source / f"{name}.obj", "fake source geometry")
        write_text(source / "Textures" / f"{name}_BaseColor.exr", "fake exr")
        mirror = project / "usd" / "assets" / name
        write_text(mirror / "payload.usdnc", "#usda")
        write_text(mirror / f"{name}.usd", "#usda")


def create_shots_only(root: Path) -> None:
    project = root / "shots_only_sequence"
    for name in ("sq010_sh010", "sq010_sh020"):
        shot = project / "seq" / name
        write_text(shot / "publish" / "animation" / f"{name}_anim_v001.usdc", "#usda")
        write_text(shot / "publish" / "layout" / f"{name}_layout_v002.usdc", "#usda")
        write_text(shot / "review" / f"{name}_playblast_v001.mov", "fake video")
        write_png(shot / "preview" / f"{name}.png")


def create_messy_hybrid(root: Path) -> None:
    project = root / "messy_hybrid"
    pipe = project / "builds" / "robot"
    write_text(pipe / "publish" / "modeling" / "robot_geo_v004.usdnc", "#usda")
    write_text(pipe / "publish" / "lookdev" / "robot_mat_v003.usdnc", "#usda")
    write_png(pipe / "preview" / "robot.png")

    library = project / "dropbox_from_vendor" / "robot_raw"
    write_text(library / "robot_raw.fbx", "fake fbx")
    write_text(library / "Textures" / "robot_raw_BaseColor.exr", "fake exr")

    representation = project / "cache" / "usd" / "robot"
    write_text(representation / "robot_payload.usdnc", "#usda")

    refs = project / "ref" / "mood"
    write_png(refs / "frame_0001.png")
    write_png(refs / "frame_0002.png")


def create_sandbox(out_dir: Path, *, clean: bool) -> None:
    resolved = out_dir.resolve()
    if clean and resolved.exists():
        if ROOT not in resolved.parents:
            raise RuntimeError(f"Refusing to delete outside repository: {resolved}")
        shutil.rmtree(resolved)
    out_dir.mkdir(parents=True, exist_ok=True)
    create_standard_pipeline(out_dir)
    create_pipeline_plus_library(out_dir)
    create_library_only(out_dir)
    create_mirrored_usd(out_dir)
    create_shots_only(out_dir)
    create_messy_hybrid(out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local fake projects for Asset Manager layout testing.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--clean", action="store_true", help="Delete the output folder before regenerating.")
    args = parser.parse_args()
    create_sandbox(args.out, clean=args.clean)
    print(args.out.resolve())


if __name__ == "__main__":
    main()
