# Jewelry Image Batch Processor

Crops jewelry photos to a centered 1:1 square and saves them as WebP (85% quality).
Originals are never touched; results go to a `processed` subfolder.

## Setup (once, Windows)

1. Install [Python](https://python.org) (tick "Add python.exe to PATH").
2. In this folder, run:
   ```
   py -m pip install -r requirements.txt
   ```

## Usage

**Drag and drop**

| Drag your photo folder onto... | Result |
|---|---|
| `process_photos.bat` | crop to 1:1 + convert to WebP |
| `convert_only.bat` | convert to WebP only, no crop |

**Command line**
```
py jewelry_crop.py "C:\Photos\NewArrivals"              # crop + convert
py jewelry_crop.py "C:\Photos\NewArrivals" --no-crop    # convert only
```

Input: `.jpg`, `.jpeg`, `.png`. Output: `C:\Photos\NewArrivals\processed\*.webp`.
Re-running skips files that are already processed.

## Options

```
--quality 90            WebP quality, 0-100 (default 85)
--recursive             include subfolders
--output-dir "D:\out"   save somewhere other than <folder>\processed
--debug                 also save a *.debug.jpg showing what was detected
--threshold 20          lower it if a pale item isn't detected (default 30)
--padding 0.2           margin around the item (default 0.15)
--no-crop               skip cropping, only convert
```

## Pairs (e.g. earrings)

If two similar-sized items are found, they are spread apart, the right one is
placed higher, and the pair is centered. Neither piece is resized.

```
--pair-mode off             never use the pair layout
--pair-mode on              force it whenever 2+ items are found
--pair-gap 0.8              gap between pieces (default 0.6 x avg width)
--pair-vertical-offset 0.2  right piece height offset (default 0.15 x avg height)
```

## Tips

- Works best on plain, solid backgrounds.
- Try `--debug` on a few photos first to check the detection.
- If no item is found, the photo is center-cropped and flagged in the console.
- Phone photos are auto-rotated upright, transparent PNGs go onto white, and the
  photo's color profile is kept in the WebP so gold/stone tones don't shift.
