# automation-tools

A collection of small, self-contained automation tools. Each tool lives in its
own folder with its own README, dependencies and usage instructions.

## Tools

### [jewelry-image-batch-processor](jewelry-image-batch-processor/)

Batch-processes jewelry product photos for web use. It auto-detects the item
against a plain background, crops to a centered 1:1 square (or lays out a
two-piece set such as earrings as a balanced pair), and exports compressed
WebP images. A convert-only mode skips the crop and just recompresses.
Originals are never modified; output goes to a `processed` subfolder.

- Stack: Python (Pillow, NumPy, SciPy)
- Platform: Windows, with drag-and-drop `.bat` launchers (`process_photos.bat`, `convert_only.bat`) or a command-line script (`jewelry_crop.py`)

## Adding a tool

Create a new top-level folder for the tool, include its own `README.md`, and
add a short entry to the list above.
