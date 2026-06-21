#!/usr/bin/env python3
"""
Batch-crops jewelry product photos to a centered 1:1 square and saves them
as compressed WebP images. Cropping can be disabled with --no-crop to just
convert/compress to WebP as-is.

Usage:
    python jewelry_crop.py "C:\\path\\to\\photos"
    python jewelry_crop.py "C:\\path\\to\\photos" --quality 90 --recursive
    python jewelry_crop.py "C:\\path\\to\\photos" --debug
    python jewelry_crop.py "C:\\path\\to\\photos" --no-crop

Originals are never modified or deleted. Output goes into a "processed"
subfolder created inside the input directory.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def estimate_background_color(rgb: np.ndarray, border_px: int = 10) -> np.ndarray:
    """Estimate the background color by sampling a border strip around the image.

    Product photos are typically shot on a plain backdrop, so the border of
    the frame is a reliable sample of the background color.
    """
    h, w, _ = rgb.shape
    border_px = max(1, min(border_px, h // 4, w // 4))
    top = rgb[:border_px, :, :].reshape(-1, 3)
    bottom = rgb[-border_px:, :, :].reshape(-1, 3)
    left = rgb[:, :border_px, :].reshape(-1, 3)
    right = rgb[:, -border_px:, :].reshape(-1, 3)
    samples = np.concatenate([top, bottom, left, right], axis=0)
    return np.median(samples, axis=0)


def find_item_bbox(rgb: np.ndarray, threshold: float):
    """Find the bounding box of the foreground item against the background.

    Returns (left, top, right, bottom) or None if no item could be detected.
    """
    bg_color = estimate_background_color(rgb)
    diff = np.linalg.norm(rgb.astype(np.float32) - bg_color.astype(np.float32), axis=2)
    mask = diff > threshold

    # Drop isolated noise pixels: keep only rows/cols with enough foreground
    # pixels, which prevents stray sensor noise or shadows from blowing up
    # the bounding box.
    col_counts = mask.sum(axis=0)
    row_counts = mask.sum(axis=1)
    min_run = 3
    cols = np.where(col_counts >= min_run)[0]
    rows = np.where(row_counts >= min_run)[0]

    if cols.size == 0 or rows.size == 0:
        return None

    left, right = int(cols.min()), int(cols.max())
    top, bottom = int(rows.min()), int(rows.max())
    return left, top, right, bottom


def compute_square_crop(image_size, bbox, padding_ratio: float):
    """Compute a square crop box centered on bbox, clamped to the image bounds."""
    img_w, img_h = image_size

    if bbox is None:
        # Fallback: simple center crop using the full image.
        side = min(img_w, img_h)
        center_x, center_y = img_w / 2, img_h / 2
    else:
        left, top, right, bottom = bbox
        item_w = right - left + 1
        item_h = bottom - top + 1
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        side = max(item_w, item_h) * (1 + padding_ratio)
        side = min(side, img_w, img_h)

    side = int(round(side))
    crop_left = int(round(center_x - side / 2))
    crop_top = int(round(center_y - side / 2))

    # Clamp so the crop box stays fully inside the image.
    crop_left = max(0, min(crop_left, img_w - side))
    crop_top = max(0, min(crop_top, img_h - side))

    return crop_left, crop_top, crop_left + side, crop_top + side


def process_image(
    src_path: Path,
    dst_path: Path,
    quality: int,
    threshold: float,
    padding_ratio: float,
    debug: bool,
    crop: bool,
) -> str:
    """Process a single image. Returns a short status string."""
    with Image.open(src_path) as img:
        img = img.convert("RGB")

        if not crop:
            img.save(dst_path, "WEBP", quality=quality)
            return "ok"

        rgb = np.array(img)

        bbox = find_item_bbox(rgb, threshold)
        crop_box = compute_square_crop(img.size, bbox, padding_ratio)

        status = "ok"
        if bbox is None:
            status = "fallback (no item detected, used full-image center crop)"

        cropped = img.crop(crop_box)
        cropped.save(dst_path, "WEBP", quality=quality)

        if debug:
            debug_img = img.copy()
            draw = ImageDraw.Draw(debug_img)
            draw.rectangle(crop_box, outline=(255, 0, 0), width=max(2, img.width // 300))
            if bbox:
                draw.rectangle(bbox, outline=(0, 255, 0), width=max(2, img.width // 300))
            debug_path = dst_path.with_name(dst_path.stem + ".debug.jpg")
            debug_img.save(debug_path, "JPEG", quality=90)

        return status


def collect_images(input_dir: Path, recursive: bool):
    pattern = "**/*" if recursive else "*"
    for path in sorted(input_dir.glob(pattern)):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def main():
    parser = argparse.ArgumentParser(
        description="Crop jewelry photos to a centered 1:1 square and save as WebP."
    )
    parser.add_argument("input_dir", help="Folder containing the photos to process")
    parser.add_argument(
        "--quality", type=int, default=85, help="WebP quality, 0-100 (default: 85)"
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.15,
        help="Extra margin around the detected item, as a fraction of its size (default: 0.15)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=30.0,
        help="Color-distance threshold used to separate the item from the background "
        "(default: 30). Lower it if the item isn't being detected; raise it if too much "
        "background is being included.",
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Also process images in subfolders"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Where to save results (default: a 'processed' subfolder inside input_dir)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Also save a copy with the detected item box (green) and crop box (red) drawn, "
        "so you can sanity-check detection before trusting it on the full batch",
    )
    parser.add_argument(
        "--no-crop",
        action="store_true",
        help="Skip item detection and cropping entirely; just convert/compress to WebP as-is",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.is_dir():
        print(f"Error: '{input_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else input_dir / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    images = list(collect_images(input_dir, args.recursive))
    if not images:
        print(f"No .jpg/.jpeg/.png files found in '{input_dir}'.")
        return

    print(f"Found {len(images)} image(s). Saving results to '{output_dir}'.\n")

    processed = 0
    skipped = 0
    warnings = 0

    for src_path in images:
        rel_path = src_path.relative_to(input_dir)
        dst_path = (output_dir / rel_path).with_suffix(".webp")
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if dst_path.exists():
            print(f"[skip]  {rel_path} -> already processed")
            skipped += 1
            continue

        try:
            status = process_image(
                src_path,
                dst_path,
                args.quality,
                args.threshold,
                args.padding,
                args.debug,
                crop=not args.no_crop,
            )
        except Exception as exc:  # noqa: BLE001 - report and keep going on batch jobs
            print(f"[error] {rel_path}: {exc}")
            continue

        if status == "ok":
            print(f"[done]  {rel_path} -> {dst_path.relative_to(output_dir)}")
            processed += 1
        else:
            print(f"[warn]  {rel_path} -> {dst_path.relative_to(output_dir)} ({status})")
            processed += 1
            warnings += 1

    print(f"\nDone. {processed} processed, {skipped} skipped, {warnings} flagged for review.")
    if warnings:
        print("Review the flagged files above (and rerun with --debug to visualize detection).")


if __name__ == "__main__":
    main()
