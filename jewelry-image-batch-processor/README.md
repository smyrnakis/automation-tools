# Jewelry Image Batch Processor

Batch-crops jewelry product photos to a centered 1:1 square (auto-detecting
the item against its background) and saves them as compressed WebP images
at 85% quality.

**Originals are never modified or deleted.** Output is written to a
`processed` subfolder created inside the folder you point it at.

## Setup (one-time, Windows)

1. Install Python from https://python.org if you don't already have it.
   During install, check "Add python.exe to PATH".
2. Download/copy this `jewelry-image-batch-processor` folder onto your laptop.
3. Open a terminal (PowerShell or Command Prompt) in that folder and run:
   ```
   py -m pip install -r requirements.txt
   ```

## Usage

There are two modes:
- **Crop + convert** — crops to a centered 1:1 square, then saves as WebP.
- **Convert only** — skips cropping entirely, just re-saves as WebP at the
  given quality (keeps the original aspect ratio).

### Option A: drag and drop
- Crop + convert: drag the folder containing your photos onto `process_photos.bat`.
- Convert only (no crop): drag the folder onto `convert_only.bat`.

### Option B: command line
```
py jewelry_crop.py "C:\Users\you\Pictures\NewArrivals"             REM crop + convert
py jewelry_crop.py "C:\Users\you\Pictures\NewArrivals" --no-crop   REM convert only, no crop
```

This creates `C:\Users\you\Pictures\NewArrivals\processed\` containing one
`.webp` file per source `.jpg`/`.jpeg`/`.png` photo.

### Useful options
```
py jewelry_crop.py "C:\path\to\photos" --quality 90               # change compression quality (0-100, default 85)
py jewelry_crop.py "C:\path\to\photos" --recursive                # also process photos in subfolders
py jewelry_crop.py "C:\path\to\photos" --debug                     # also save a copy showing the detected box(es), so you can sanity-check it
py jewelry_crop.py "C:\path\to\photos" --threshold 20             # lower this if a faint/light item isn't being detected
py jewelry_crop.py "C:\path\to\photos" --no-crop                   # skip cropping, just convert/compress to WebP as-is
py jewelry_crop.py "C:\path\to\photos" --pair-mode off            # always use a single bounding-box crop, never the two-piece layout
```

Already-processed files are skipped on rerun, so it's safe to drop new
photos into the same folder and run it again.

## How "centering" works

The script samples the border of each photo to estimate the background
color (works best with a plain/solid backdrop, which is typical for jewelry
product shots) and finds connected blobs that differ from that background.

- **One item detected:** centers the square crop on its bounding box with a
  15% margin (`--padding` to change it).
- **Two similarly-sized items detected** (e.g. a pair of earrings):
  automatically switches to a **pair layout** — it cuts out each piece
  (without resizing either one), spaces them apart, places the right piece
  higher than the left, and centers the pair as a whole. The output square
  is sized to match the original photo's own scale (`min(width, height)`),
  so the pieces only move within the frame — they're never zoomed in or
  enlarged relative to the canvas. (`--padding` has no effect in this mode,
  since there's no tight crop to pad.) Tune the layout with `--pair-gap`
  (space between pieces, default 0.6x their average width) and
  `--pair-vertical-offset` (how much higher the right piece sits, default
  0.15x their average height). Use `--pair-mode off` to disable this and
  always use a single box around everything detected, or `--pair-mode on`
  to force the pair layout whenever 2+ items are found.
- **No item detected:** falls back to a plain center crop of the full image
  and flags that file in the console output so you can check it manually.

The pair layout reuses the original photo's own background (erasing the
items' old spots and re-pasting them at their new positions), so it works
best on plain/solid backdrops — a subtle gradient or shadow in the original
background won't perfectly follow the moved pieces.

Run with `--debug` first on a sample folder to confirm detection looks
right before processing your full catalog — it saves a `*.debug.jpg` next
to each output with the detected item box(es) in green (and, for single-item
crops, the final crop box in red).
