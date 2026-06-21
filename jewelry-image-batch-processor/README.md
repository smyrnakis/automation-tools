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

### Option A: drag and drop
Drag the folder containing your photos onto `process_photos.bat`.

### Option B: command line
```
py jewelry_crop.py "C:\Users\you\Pictures\NewArrivals"
```

This creates `C:\Users\you\Pictures\NewArrivals\processed\` containing one
`.webp` file per source `.jpg`/`.jpeg`/`.png` photo.

### Useful options
```
py jewelry_crop.py "C:\path\to\photos" --quality 90        # change compression quality (0-100, default 85)
py jewelry_crop.py "C:\path\to\photos" --recursive         # also process photos in subfolders
py jewelry_crop.py "C:\path\to\photos" --debug              # also save a copy showing the detected crop box, so you can sanity-check it
py jewelry_crop.py "C:\path\to\photos" --threshold 20      # lower this if a faint/light item isn't being detected
```

Already-processed files are skipped on rerun, so it's safe to drop new
photos into the same folder and run it again.

## How "centering" works

The script samples the border of each photo to estimate the background
color (works best with a plain/solid backdrop, which is typical for jewelry
product shots), finds the bounding box of whatever differs from that
background, and centers the square crop on that bounding box with a 15%
margin. If no item can be confidently detected, it falls back to a plain
center crop of the full image and flags that file in the console output so
you can check it manually.

Run with `--debug` first on a sample folder to confirm detection looks
right before processing your full catalog — it saves a `*.debug.jpg` next
to each output with the detected item (green box) and final crop (red box)
drawn on it.
