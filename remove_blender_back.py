#!/usr/bin/env python3
"""
remove_blender_back.py

Background removal for mp4/mkv video files.

Features:
- Uses `rembg` (U-2-Net) for best results if installed, otherwise tries MediaPipe SelfieSegmentation
- Falls back to a naive background subtraction if nothing else is installed
- Writes the result as a video with alpha (WebM VP9 or MOV) or as an mp4 composited on a background image/color

Usage:
  python remove_blender_back.py --input in.mp4 --output out.webm --background none

Notes:
- Requires ffmpeg installed and on PATH for video encoding/decoding
- Install recommended packages with:
    pip install opencv-python pillow numpy rembg mediapipe tqdm

"""
import argparse
import os
import tempfile
import shutil
import subprocess
from pathlib import Path
import sys
import math

from PIL import Image
import numpy as np

# Try to import better segmentation libraries
try:
    from rembg import remove as rembg_remove
    HAS_REMBG = True
except Exception:
    HAS_REMBG = False

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except Exception:
    HAS_MEDIAPIPE = False

try:
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

from tqdm import tqdm


def ensure_ffmpeg_exists():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        print("Error: ffmpeg not found on PATH. Please install ffmpeg and ensure it's available.")
        sys.exit(1)


def get_video_properties(path):
    # Uses OpenCV if available; otherwise tries ffprobe
    if HAS_CV2:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open video {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        return int(width), int(height), float(fps), int(frame_count)
    # fallback using ffprobe
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=width,height,r_frame_rate,nb_frames", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffprobe error: " + proc.stderr)
    pieces = proc.stdout.strip().splitlines()
    if len(pieces) >= 4:
        width = int(pieces[0])
        height = int(pieces[1])
        # r_frame_rate like 30000/1001
        r = pieces[2]
        if "/" in r:
            a, b = r.split("/")
            fps = float(a) / float(b)
        else:
            fps = float(r)
        try:
            frame_count = int(pieces[3])
        except ValueError:
            frame_count = 0
        return width, height, fps, frame_count
    raise RuntimeError("Failed to read video properties")


def save_rgba_frame(img: np.ndarray, alpha: np.ndarray, out_path: Path):
    # img BGR if from opencv
    if img.shape[2] == 3:
        # use top-level cv2 imported earlier
        b, g, r = cv2.split(img)
        rgba = cv2.merge([r, g, b, alpha])
        pil = Image.fromarray(rgba)
    else:
        pil = Image.fromarray(img).convert('RGBA')
    pil.save(str(out_path), format='PNG')


def segment_with_rembg(frame):
    # Expects a PIL Image
    pil = frame.convert('RGBA')
    # returns PIL Image with alpha channel (transparent where background removed)
    out = rembg_remove(pil)
    return out


def segment_with_mediapipe_np(img):
    # img in BGR (cv2)
    mp_selfie_segmentation = mp.solutions.selfie_segmentation
    with mp_selfie_segmentation.SelfieSegmentation(model_selection=1) as segmenter:
        # convert to RGB
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = segmenter.process(rgb)
        mask = results.segmentation_mask
        # map to 0-255
        a = (mask * 255).astype('uint8')
        return a


def fallback_segment_median(bg_img, frame_bgr):
    # naive background subtraction with threshold; expects background image (bgr) or None
    if bg_img is None:
        # can't do meaningful subtraction: make fully opaque mask
        return np.full((frame_bgr.shape[0], frame_bgr.shape[1]), 255, dtype='uint8')
    # cv2.absdiff and grayscale
    diff = cv2.absdiff(bg_img, frame_bgr)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
    return mask


def process_video(args):
    input_path = Path(args.input)
    output_path = Path(args.output)

    ensure_ffmpeg_exists()

    width, height, fps, frame_count = get_video_properties(input_path)
    print(f"Video properties: {width}x{height} fps={fps} frames={frame_count}")

    tmpdir = Path(tempfile.mkdtemp(prefix="rmbg_"))
    frames_dir = tmpdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    print(f"Tmp frames dir: {frames_dir}")

    # open video
    if not HAS_CV2:
        raise RuntimeError("opencv-python is required for reading frames (pip install opencv-python)")
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError("Unable to open video")

    # optional background image
    bg_image_cv = None
    if args.background and args.background.lower() not in ("none", "transparent"):
        bg_path = Path(args.background)
        if bg_path.exists():
            bg_pil = Image.open(bg_path).convert('RGBA')
            bg_image_cv = cv2.cvtColor(np.array(bg_pil), cv2.COLOR_RGBA2BGR)
            bg_image_cv = cv2.resize(bg_image_cv, (width, height))
        else:
            # assume background is a color 'R,G,B'
            if "," in args.background:
                comps = [int(x) for x in args.background.split(",")]
                bg_color = np.zeros((height, width, 3), dtype='uint8')
                bg_image_cv = np.full_like(bg_color, [comps[2], comps[1], comps[0]])
            else:
                raise RuntimeError("Background path or color not found")

    # select segmenter
    segmenter = None
    if HAS_REMBG:
        print("Using rembg for segmentation")
        segmenter = 'rembg'
    elif HAS_MEDIAPIPE:
        print("Using MediaPipe SelfieSegmentation")
        segmenter = 'mediapipe'
    else:
        print("Using fallback median-based segmentation (fast but may be poor)")
        segmenter = 'fallback'

    # If fallback is selected and background is 'none' (transparent), abort unless forced
    if segmenter == 'fallback' and (args.background is None or args.background.lower() in ("none", "transparent")):
        msg = (
            "Fallback segmentation requires a background image or color to compute differences,\n"
            "but none was provided and rembg/mediapipe aren't available.\n"
            "Install 'rembg' (preferred) with 'pip install rembg' or 'mediapipe' with 'pip install mediapipe',\n"
            "or pass '--background <path_or_color>' to let fallback compute the mask."
        )
        if args.force_fallback:
            print("Warning: " + msg)
        else:
            print(msg)
            shutil.rmtree(tmpdir)
            sys.exit(2)

    # Iterate frames
    i = 0
    pbar = tqdm(total=(frame_count if frame_count > 0 else None), desc='Processing frames')
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # frame is BGR
        if segmenter == 'rembg':
            pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            out_pil = segment_with_rembg(pil)
            # out_pil is RGBA
            out_pil.save(str(frames_dir / f"{i:06d}.png"), format='PNG')
            if i == 0:
                alpha = np.array(out_pil.getchannel('A'))
                total = alpha.size
                num_transparent = int((alpha == 0).sum())
                num_semi = int(((alpha > 0) & (alpha < 255)).sum())
                print(f"First frame alpha: transparent={num_transparent}/{total}, semi={num_semi}/{total}")
        elif segmenter == 'mediapipe':
            # segmentation mask
            a = segment_with_mediapipe_np(frame)
            save_rgba_frame(frame, a, frames_dir / f"{i:06d}.png")
            if i == 0:
                print(f"First frame mask: min={int(a.min())}, max={int(a.max())}")
        else:
            # fallback
            mask = fallback_segment_median(bg_image_cv, frame)
            # optional dilation/blur
            if True:
                mask = cv2.medianBlur(mask, 5)
            save_rgba_frame(frame, mask, frames_dir / f"{i:06d}.png")
            if i == 0:
                print(f"Fallback first frame mask: min={int(mask.min())}, max={int(mask.max())}")
        i += 1
        pbar.update(1)
    pbar.close()
    cap.release()

    # Compose or encode
    # If desired output supports alpha, create webm/mov with alpha
    out_ext = output_path.suffix.lower()
    if out_ext in ('.webm', '.mov'):
        if out_ext == '.webm':
            # WEBM with VP9 alpha supports yuva420p
            cmd = [
                'ffmpeg', '-y', '-framerate', str(fps), '-i', str(frames_dir / '%06d.png'),
                '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0', str(output_path)
            ]
        else:
            # MOV with qtrle
            cmd = ['ffmpeg', '-y', '-framerate', str(fps), '-i', str(frames_dir / '%06d.png'), '-c:v', 'qtrle', '-pix_fmt', 'rgba', str(output_path)]
    else:
        # If user wants mp4, composite onto background or plain white
        if args.background and args.background.lower() in ('none', 'transparent'):
            # mp4 cannot store transparency; default to black
            bg_for_comp = 'black'
        elif args.background:
            bg_for_comp = str(args.background)
        else:
            bg_for_comp = 'black'
        # We can ask ffmpeg to assemble pngs and flatten over a background color or image
        if bg_for_comp == 'black':
            cmd = ['ffmpeg', '-y', '-framerate', str(fps), '-i', str(frames_dir / '%06d.png'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output_path)]
        elif Path(bg_for_comp).exists():
            cmd = [
                'ffmpeg', '-y', '-framerate', str(fps), '-i', str(frames_dir / '%06d.png'), '-loop', '1', '-i', str(bg_for_comp),
                '-filter_complex', f"[1:v]scale={width}:{height}[bg];[bg][0:v]overlay=format=auto",
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output_path)
            ]
        else:
            # color like '255,255,255'
            comps = [int(x) for x in bg_for_comp.split(',')]
            col = f"color=c=rgb({comps[0]},{comps[1]},{comps[2]}):s={width}x{height}:r={fps}"
            cmd = ['ffmpeg', '-y', '-framerate', str(fps), '-i', str(frames_dir / '%06d.png'),
                   '-f', 'lavfi', '-i', col,
                   '-filter_complex', '[1:v][0:v]overlay=format=auto', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output_path)]

    print("Running ffmpeg to encode output: ", ' '.join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print("ffmpeg failed:")
        print(proc.stderr)
        # Clean up frames even if failure
        shutil.rmtree(tmpdir)
        raise RuntimeError("ffmpeg encoding failed")

    # cleanup
    shutil.rmtree(tmpdir)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Remove background from mp4/mkv videos.")
    parser.add_argument('--input', '-i', required=True, help='Input video (.mp4, .mkv, ... )')
    parser.add_argument('--output', '-o', required=True, help='Output video: .webm/.mov (alpha) or .mp4')
    parser.add_argument('--background', '-b', default='none', help='Background image path or color R,G,B or "none" for transparent')
    parser.add_argument('--force-fallback', action='store_true', help='Force using fallback segmentation when no rembg/mediapipe is available')
    args = parser.parse_args()
    process_video(args)


if __name__ == '__main__':
    main()
