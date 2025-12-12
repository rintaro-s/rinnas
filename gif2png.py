#!/usr/bin/env python3
"""
gif2png.py

Convert animated GIF to per-frame PNGs (preserving transparency).

This implements a robust frame composition that handles GIFs which only update partial
regions of the frame.

Usage:
  python gif2png.py -i animation.gif -o frames_dir -p frame

Dependencies: pillow (PIL)
  pip install pillow
"""
from __future__ import annotations
import argparse
from pathlib import Path
from PIL import Image, ImageSequence
import os
import sys


def ensure_output_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def frames_from_gif(input_path: Path, output_dir: Path, prefix: str = 'frame', digits: int | None = None,
                    force_overwrite=False, verbose: bool = False):
    im = Image.open(input_path)
    if im.format != 'GIF':
        raise ValueError('Input is not a GIF file')

    w, h = im.size
    # Count frames first
    frames = getattr(im, 'n_frames', None)
    if frames is None:
        frames = sum(1 for _ in ImageSequence.Iterator(im))

    if digits is None:
        digits = max(3, len(str(frames)))

    ensure_output_dir(output_dir)
    output_paths = []

    # Keep a persistent RGBA frame representing the composed image
    base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    previous = base.copy()

    im.seek(0)
    frame_index = 0
    while True:
        try:
            im.seek(frame_index)
        except EOFError:
            break
        frame = im.copy()
        # Convert to RGBA for alpha
        if frame.mode != 'RGBA':
            frame_rgba = frame.convert('RGBA')
        else:
            frame_rgba = frame

        # Determine update region: Pillow gives it via tile
        box = None
        if hasattr(frame, 'tile') and frame.tile:
            tile = frame.tile[0]
            # tile[1] holds the bounding box (x0, y0, x1, y1)
            try:
                box = tile[1]
            except Exception:
                box = None

        # If we have an update box smaller than frame, we paste only that region
        if box and (box[2] - box[0] < w or box[3] - box[1] < h):
            # update region
            composed = previous.copy()
            composed.paste(frame_rgba, box[:2], frame_rgba)
        else:
            composed = frame_rgba if frame_rgba.size == (w, h) else previous.copy()

        # Save the composed image for this frame
        out_name = f"{prefix}_{frame_index:0{digits}d}.png"
        out_path = output_dir / out_name
        if out_path.exists() and not force_overwrite:
            print(f"Skipping existing: {out_path}")
        else:
            composed.save(out_path, 'PNG')
            output_paths.append(out_path)
            if verbose and frame_index == 0:
                alpha = composed.split()[-1]
                aarr = alpha.getdata()
                # min/max
                amin = min(aarr)
                amax = max(aarr)
                total = w * h
                num_transparent = sum(1 for v in aarr if v == 0)
                print(f"First frame alpha: min={amin}, max={amax}, transparent={num_transparent}/{total}")

        # Disposal handling: if disposal == 2 -> restore background color for updated region
        disposal = im.disposal_method if hasattr(im, 'disposal_method') else im.info.get('disposal', None)
        if disposal == 2 and box:
            # restore previous region to fully transparent quickly by pasting a transparent image
            x0, y0, x1, y1 = box
            transparent_block = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
            previous.paste(transparent_block, (x0, y0))
        else:
            previous = composed

        frame_index += 1

    return output_paths


def main():
    parser = argparse.ArgumentParser(description='Extract frames from GIF as PNGs (preserves transparency).')
    parser.add_argument('--input', '-i', required=True, help='Input GIF path')
    parser.add_argument('--output', '-o', default='frames', help='Output directory')
    parser.add_argument('--prefix', '-p', default='frame', help='Output filename prefix')
    parser.add_argument('--digits', '-d', type=int, default=None, help='Number of digits in frame index filenames')
    parser.add_argument('--force', action='store_true', help='Overwrite existing frames if present')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output (print alpha stats for first frame)')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print('Input file not found:', input_path)
        sys.exit(1)

    output_dir = Path(args.output)
    try:
        paths = frames_from_gif(input_path, output_dir, args.prefix, args.digits, args.force, args.verbose)
        print(f'Extracted {len(paths)} frames to', output_dir)
    except Exception as e:
        print('Error:', e)
        sys.exit(2)


if __name__ == '__main__':
    main()
