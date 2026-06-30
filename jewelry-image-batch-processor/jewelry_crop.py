#!/usr/bin/env python3
"""
Batch-crops jewelry product photos to a centered 1:1 square and saves them
as compressed WebP images. Cropping can be disabled with --no-crop to just
convert/compress to WebP as-is.

When a photo contains two separate pieces (e.g. a pair of earrings), the
pair layout (on by default, see --pair-mode) repositions the two pieces -
spacing them apart and offsetting the right piece higher than the left one
- without resizing/zooming either piece, then centers the pair as a whole
in the square frame.

Usage:
    python jewelry_crop.py "C:\\path\\to\\photos"
    python jewelry_crop.py "C:\\path\\to\\photos" --quality 90 --recursive
    python jewelry_crop.py "C:\\path\\to\\photos" --debug
    python jewelry_crop.py "C:\\path\\to\\photos" --no-crop
    python jewelry_crop.py "C:\\path\\to\\photos" --pair-mode off

Originals are never modified or deleted. Output goes into a "processed"
subfolder created inside the input directory.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

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


def find_components(rgb: np.ndarray, bg_color: np.ndarray, threshold: float, min_area_ratio: float = 0.0015):
    """Find connected foreground blobs (items) against the background.

    Returns a list of {"bbox": (left, top, right, bottom), "size": pixel_count}
    dicts, largest first. Tiny noise blobs below min_area_ratio of the image
    area are dropped.
    """
    diff = np.linalg.norm(rgb.astype(np.float32) - bg_color.astype(np.float32), axis=2)
    mask = diff > threshold

    labeled, num = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if num == 0:
        return []

    img_area = mask.shape[0] * mask.shape[1]
    min_area = img_area * min_area_ratio
    sizes = ndimage.sum(mask, labeled, index=np.arange(1, num + 1))
    slices = ndimage.find_objects(labeled)

    components = []
    for i, sl in enumerate(slices):
        size = sizes[i]
        if sl is None or size < min_area:
            continue
        y0, y1 = sl[0].start, sl[0].stop - 1
        x0, x1 = sl[1].start, sl[1].stop - 1
        components.append({"bbox": (x0, y0, x1, y1), "size": int(size)})

    components.sort(key=lambda c: -c["size"])
    return components


def detect_pair(components, size_ratio: float):
    """Decide whether the two largest components look like a genuine pair.

    Returns (component_a, component_b) or None.
    """
    if len(components) < 2:
        return None
    largest, second = components[0], components[1]
    if len(components) > 2 and components[2]["size"] > second["size"] * 0.6:
        # A third comparably-sized blob means this isn't a clean two-item photo.
        return None
    if second["size"] < largest["size"] * size_ratio:
        return None
    return largest, second


def union_bbox(components):
    """Bounding box covering every detected component (used outside pair mode)."""
    if not components:
        return None
    lefts, tops, rights, bottoms = zip(*(c["bbox"] for c in components))
    return min(lefts), min(tops), max(rights), max(bottoms)


def order_left_right(comp_a, comp_b):
    cx_a = (comp_a["bbox"][0] + comp_a["bbox"][2]) / 2
    cx_b = (comp_b["bbox"][0] + comp_b["bbox"][2]) / 2
    return (comp_a, comp_b) if cx_a <= cx_b else (comp_b, comp_a)


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


def _item_crop_box(bbox, other_bbox, img_w, img_h):
    """A tight crop box around one item, padded a little but never reaching the other item."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    margin = max(2, int(round(0.04 * max(w, h))))

    if other_bbox[0] >= x1:
        gap_to_other = other_bbox[0] - x1
    else:
        gap_to_other = x0 - other_bbox[2]
    margin = min(margin, max(0, gap_to_other // 2))

    return (
        max(0, x0 - margin),
        max(0, y0 - margin),
        min(img_w, x1 + margin + 1),
        min(img_h, y1 + margin + 1),
    )


def build_pair_canvas(img, bg_color, left_comp, right_comp, gap_ratio, vertical_offset_ratio, padding_ratio):
    """Build a new square canvas with the left/right items spread apart and
    centered as a whole, without resizing either item.

    Returns (canvas, [left_final_box, right_final_box]) for optional debug drawing.
    """
    img_w, img_h = img.size
    left_crop_box = _item_crop_box(left_comp["bbox"], right_comp["bbox"], img_w, img_h)
    right_crop_box = _item_crop_box(right_comp["bbox"], left_comp["bbox"], img_w, img_h)

    left_img = img.crop(left_crop_box)
    right_img = img.crop(right_crop_box)
    lw, lh = left_img.size
    rw, rh = right_img.size

    gap = max(1, int(round(((lw + rw) / 2) * gap_ratio)))
    vertical_offset = int(round(((lh + rh) / 2) * vertical_offset_ratio))

    # Right piece sits `vertical_offset` px higher than the left piece.
    left_top = vertical_offset
    right_top = 0
    left_pos = (0, left_top)
    right_pos = (lw + gap, right_top)

    union_w = max(left_pos[0] + lw, right_pos[0] + rw)
    union_h = max(left_pos[1] + lh, right_pos[1] + rh)

    side = int(round(max(union_w, union_h) * (1 + padding_ratio)))
    bg_rgb = tuple(int(round(c)) for c in bg_color)
    canvas = Image.new("RGB", (side, side), bg_rgb)

    offset_x = (side - union_w) // 2
    offset_y = (side - union_h) // 2

    left_final = (offset_x + left_pos[0], offset_y + left_pos[1])
    right_final = (offset_x + right_pos[0], offset_y + right_pos[1])
    canvas.paste(left_img, left_final)
    canvas.paste(right_img, right_final)

    left_box = (left_final[0], left_final[1], left_final[0] + lw, left_final[1] + lh)
    right_box = (right_final[0], right_final[1], right_final[0] + rw, right_final[1] + rh)
    return canvas, [left_box, right_box]


def process_image(
    src_path: Path,
    dst_path: Path,
    quality: int,
    threshold: float,
    padding_ratio: float,
    debug: bool,
    crop: bool,
    pair_mode: str,
    pair_gap_ratio: float,
    pair_vertical_offset_ratio: float,
    pair_size_ratio: float,
) -> str:
    """Process a single image. Returns a short status string."""
    with Image.open(src_path) as img:
        img = img.convert("RGB")

        if not crop:
            img.save(dst_path, "WEBP", quality=quality)
            return "ok"

        rgb = np.array(img)
        bg_color = estimate_background_color(rgb)
        components = find_components(rgb, bg_color, threshold)

        pair = None
        if pair_mode != "off" and len(components) >= 2:
            pair = detect_pair(components, pair_size_ratio)
            if pair is None and pair_mode == "on":
                pair = (components[0], components[1])

        if pair is not None:
            left_comp, right_comp = order_left_right(*pair)
            canvas, debug_boxes = build_pair_canvas(
                img, bg_color, left_comp, right_comp, pair_gap_ratio, pair_vertical_offset_ratio, padding_ratio
            )
            canvas.save(dst_path, "WEBP", quality=quality)

            if debug:
                debug_img = canvas.copy()
                draw = ImageDraw.Draw(debug_img)
                for box in debug_boxes:
                    draw.rectangle(box, outline=(0, 255, 0), width=max(2, canvas.width // 300))
                debug_path = dst_path.with_name(dst_path.stem + ".debug.jpg")
                debug_img.save(debug_path, "JPEG", quality=90)

            return "ok (pair layout)"

        bbox = union_bbox(components)
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
        help="Extra margin around the detected item (or item pair), as a fraction of its size "
        "(default: 0.15)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=30.0,
        help="Color-distance threshold used to separate items from the background "
        "(default: 30). Lower it if an item isn't being detected; raise it if too much "
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
        help="Also save a copy with the detected item box(es) (green) and crop box (red, "
        "single-item only) drawn, so you can sanity-check detection before trusting it on "
        "the full batch",
    )
    parser.add_argument(
        "--no-crop",
        action="store_true",
        help="Skip item detection, cropping and pair layout entirely; just convert/compress "
        "to WebP as-is",
    )
    parser.add_argument(
        "--pair-mode",
        choices=["auto", "on", "off"],
        default="auto",
        help="Control the two-piece (e.g. earrings) layout: spread the pieces apart, put the "
        "right one higher, and center the pair as a whole - without resizing either piece. "
        "'auto' (default) only applies it when two similarly-sized items are detected; 'on' "
        "forces it whenever at least two items are detected; 'off' always uses a plain single "
        "bounding-box crop",
    )
    parser.add_argument(
        "--pair-gap",
        type=float,
        default=0.6,
        help="Horizontal gap between paired items, as a fraction of their average width "
        "(default: 0.6)",
    )
    parser.add_argument(
        "--pair-vertical-offset",
        type=float,
        default=0.15,
        help="How much higher the right item sits versus the left item in pair layout, as a "
        "fraction of their average height (default: 0.15)",
    )
    parser.add_argument(
        "--pair-size-ratio",
        type=float,
        default=0.25,
        help="In 'auto' pair-mode, the minimum size of the second item relative to the "
        "largest for them to be treated as a pair (default: 0.25)",
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
                pair_mode=args.pair_mode,
                pair_gap_ratio=args.pair_gap,
                pair_vertical_offset_ratio=args.pair_vertical_offset,
                pair_size_ratio=args.pair_size_ratio,
            )
        except Exception as exc:  # noqa: BLE001 - report and keep going on batch jobs
            print(f"[error] {rel_path}: {exc}")
            continue

        if status in ("ok", "ok (pair layout)"):
            note = " (pair layout)" if status == "ok (pair layout)" else ""
            print(f"[done]  {rel_path} -> {dst_path.relative_to(output_dir)}{note}")
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
