#!/usr/bin/env python3
"""
art_completer.py — AI-assisted art completion for pen plotter.

Workflow:
    1. Capture current paper state via camera
    2. Warp to plotter coordinate space using calibration
    3. Extract existing sketch
    4. Send to SDXL (Stability AI API) for completion
    5. Diff original vs completed to find new lines
    6. Convert new lines to plotter paths (in inches)
    7. Draw only the new parts

Coordinate system (same as draw_marker_boundary.py):
    (0,0) = home = marker ID2 (bottom-right)
    +X = leftward toward ID3
    +Y = upward toward ID1

Usage:
    python art_completer.py
    python art_completer.py --prompt "complete this sketch" --strength 0.6
    python art_completer.py --skip-capture photo.png --no-plot
"""
import cv2
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize as _skimage_skeletonize
import axi
import time
import math
import json
import sys
import os
import argparse
import base64
import io

try:
    import requests
except ImportError:
    requests = None

try:
    import torch
    from diffusers import AutoPipelineForImage2Image
    HAS_DIFFUSERS = True
except ImportError:
    HAS_DIFFUSERS = False

# ── Config ──────────────────────────────────────────────────────────────────

CALIB_FILE = 'calibration.json'

DEFAULT_PROMPT = (
    'Complete this unfinished pencil sketch by adding new lines and details '
    'to make it a finished drawing. Draw new elements that naturally extend '
    'the existing lines. Thin black ink outlines on white paper. '
    'No shading, no hatching, no color, no fill. Clean single-weight pen strokes.'
)

STABILITY_API_URL = (
    'https://api.stability.ai/v1/generation/'
    'stable-diffusion-xl-1024-v1-0/image-to-image'
)

# Resolution of the warped image (pixels per inch)
WARP_PPI = 100


# ── Calibration ─────────────────────────────────────────────────────────────

def load_calibration():
    if not os.path.exists(CALIB_FILE):
        print(f'ERROR: {CALIB_FILE} not found.  Run calibrate.py first.')
        sys.exit(1)
    with open(CALIB_FILE) as f:
        data = json.load(f)
    data['cam_to_plotter'] = np.array(data['cam_to_plotter'], dtype=np.float64)
    data['plotter_to_cam'] = np.array(data['plotter_to_cam'], dtype=np.float64)
    return data


# ── Camera ──────────────────────────────────────────────────────────────────

def _find_working_camera(preferred_id):
    """Try preferred camera first; USB cameras need warmup."""
    candidates = [preferred_id] + [i for i in range(6) if i != preferred_id]
    for cam_id in candidates:
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            continue
        time.sleep(2.0)
        good = False
        for _ in range(60):
            ret, frame = cap.read()
            if ret and frame is not None and frame.mean() > 5:
                good = True
                break
        cap.release()
        if good:
            if cam_id != preferred_id:
                print(f'  Camera {preferred_id} unavailable, using {cam_id}')
            return cam_id
    raise RuntimeError(f'No working camera found (tried {candidates})')


def capture_frame(camera_id, warmup_frames=60, warmup_secs=4):
    camera_id = _find_working_camera(camera_id)
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open camera {camera_id}')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    time.sleep(warmup_secs)
    for _ in range(warmup_frames):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None or frame.mean() < 5:
        raise RuntimeError('Failed to capture (black or empty)')
    return frame


# ── Warp camera → plotter-aligned image ─────────────────────────────────────

def warp_to_plotter_space(frame, calib):
    """
    Warp camera frame to a top-down view aligned with plotter coordinates,
    then flip 180° to natural human orientation for AI processing.

    Returns a colour image where 1 inch = WARP_PPI pixels.

    The raw warped image has plotter (0,0) = marker ID2 (bottom-right)
    at the top-left pixel, making it appear rotated 180° from a human
    perspective.  The final flip corrects this so the AI sees a natural
    top-down view.  Path extraction undoes the flip when converting
    pixel coords back to plotter inches.
    """
    page_w = calib['page_w']
    page_h = calib['page_h']
    M = calib['cam_to_plotter']

    out_w = int(page_w * WARP_PPI)
    out_h = int(page_h * WARP_PPI)

    # Scale homography so output is in pixels
    S = np.diag([WARP_PPI, WARP_PPI, 1.0])
    M_px = S @ M

    warped = cv2.warpPerspective(
        frame, M_px, (out_w, out_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )

    # White-out a thin border to mask ArUco tape / edge artefacts
    margin = int(WARP_PPI * 0.15)
    if margin > 0:
        warped[:margin, :] = 255
        warped[-margin:, :] = 255
        warped[:, :margin] = 255
        warped[:, -margin:] = 255

    # Flip 180° so the image looks like a natural top-down view of the paper.
    # The warped image is in plotter coords where (0,0)=bottom-right, +X=left,
    # +Y=up, which appears rotated 180° from a human perspective.
    # Flipping here gives the AI a natural orientation for better completions.
    # Path coordinates are transformed back to plotter space after extraction.
    warped = cv2.flip(warped, -1)  # flip both axes = 180° rotation

    return warped


# ── Sketch extraction ───────────────────────────────────────────────────────

def extract_sketch(warped_bgr):
    """Extract clean sketch from warped camera image.

    Returns (sketch_for_ai, binary):
        sketch_for_ai — clean grayscale suitable for AI input
                        (derived from binary so white=paper, dark=lines;
                         slightly softened edges for natural look)
        binary        — adaptive-threshold binary for diff (0=line, 255=white)
    """
    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold handles the poor camera contrast well
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=15,
    )
    k = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)

    # Build a clean grayscale for AI input from the binary.
    # Slight Gaussian blur softens the hard binary edges so the AI
    # sees natural-looking pencil strokes instead of jagged pixels.
    sketch_for_ai = cv2.GaussianBlur(binary, (5, 5), 1.2)

    return sketch_for_ai, binary


# ── Stability AI img2img ────────────────────────────────────────────────────

def _pil_to_png(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _pad_square(img, fill=255):
    w, h = img.size
    s = max(w, h)
    mode_fill = fill if img.mode == 'L' else (fill, fill, fill)
    out = Image.new(img.mode, (s, s), color=mode_fill)
    pl, pt = (s - w) // 2, (s - h) // 2
    out.paste(img, (pl, pt))
    return out, (pl, pt, w, h)


def _unpad_square(img, info):
    pl, pt, ow, oh = info
    s = img.size[0]
    scale = s / max(ow + 2 * pl, oh + 2 * pt)
    l = int(pl * scale)
    t = int(pt * scale)
    return img.crop((l, t, l + int(ow * scale), t + int(oh * scale)))


def call_sdxl_api(sketch_gray, prompt, api_key, strength=0.65,
                   neg='color, shading, hatching, gradient, photograph, realistic, '
                       '3d, blurry, grey fill, watercolor, painted, thick lines'):
    """Send sketch to SDXL img2img.

    sketch_gray: grayscale image (uint8).
    strength:    how much the AI can change (0.5-0.8 for completion).
                 Stability API image_strength = 1 - strength, so
                 strength 0.65 → image_strength 0.35 → 65% creative freedom.
    """
    oh, ow = sketch_gray.shape[:2]
    pil = Image.fromarray(sketch_gray).convert('RGB')
    padded, pad_info = _pad_square(pil)
    resized = padded.resize((1024, 1024), Image.LANCZOS)

    # Stability API: image_strength = how much to KEEP the original.
    # Lower image_strength = more creative freedom.
    image_strength = max(0.15, min(0.85, 1.0 - strength))

    headers = {'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}
    files = {'init_image': ('sketch.png', _pil_to_png(resized), 'image/png')}
    data = {
        'text_prompts[0][text]': prompt,
        'text_prompts[0][weight]': '1.0',
        'text_prompts[1][text]': neg,
        'text_prompts[1][weight]': '-1.0',
        'init_image_mode': 'IMAGE_STRENGTH',
        'image_strength': str(image_strength),
        'cfg_scale': '10',
        'samples': '1',
        'steps': '40',
    }

    print(f'  Calling Stability AI API (strength={strength}, image_strength={image_strength:.2f})...')
    resp = requests.post(STABILITY_API_URL, headers=headers,
                         files=files, data=data, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f'API error {resp.status_code}: {resp.text[:500]}')

    b64 = resp.json()['artifacts'][0]['base64']
    completed = Image.open(io.BytesIO(base64.b64decode(b64))).convert('L')
    completed = _unpad_square(completed, pad_info)
    return completed.resize((ow, oh), Image.LANCZOS)


# ── Local SD Turbo fallback ─────────────────────────────────────────────────

_local_pipe = None

def _load_local():
    global _local_pipe
    if _local_pipe is not None:
        return _local_pipe
    if not HAS_DIFFUSERS:
        raise RuntimeError('diffusers not installed')
    print('  Loading SD Turbo (first run downloads ~2 GB)...')
    _local_pipe = AutoPipelineForImage2Image.from_pretrained(
        'stabilityai/sd-turbo', torch_dtype=torch.bfloat16,
        variant='fp16', low_cpu_mem_usage=True)
    _local_pipe.to('cpu')
    return _local_pipe


def call_local_img2img(sketch_bin, prompt, strength=0.55, steps=4,
                       neg='color, shading, gradient, photograph, realistic, 3d'):
    pipe = _load_local()
    oh, ow = sketch_bin.shape
    pil = Image.fromarray(sketch_bin).convert('RGB').resize((256, 256), Image.LANCZOS)
    print(f'  Running local img2img (steps={steps}, strength={strength})...')
    t0 = time.time()
    with torch.no_grad():
        result = pipe(prompt=prompt, negative_prompt=neg, image=pil,
                      num_inference_steps=steps, strength=strength,
                      guidance_scale=0.0, height=256, width=256)
    print(f'  Done in {time.time()-t0:.0f}s')
    return result.images[0].convert('L').resize((ow, oh), Image.LANCZOS)


# ── Diff: find new lines ────────────────────────────────────────────────────

def diff_sketches(original_bin, completed_pil):
    """Return binary image of NEW lines only (0=line, 255=bg)."""
    completed = np.array(completed_pil)
    _, comp_bin = cv2.threshold(completed, 180, 255, cv2.THRESH_BINARY)

    orig_drawn = original_bin < 128
    comp_drawn = comp_bin == 0

    # Dilate original slightly to avoid redrawing existing lines
    k = np.ones((3, 3), np.uint8)
    orig_mask = cv2.dilate((orig_drawn * 255).astype(np.uint8), k) > 0

    new_lines = comp_drawn & ~orig_mask

    out = np.full_like(original_bin, 255)
    out[new_lines] = 0

    # Clean small noise
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        255 - out, connectivity=8)
    for i in range(1, n_labels):
        if stats[i, cv2.CC_STAT_AREA] < 10:
            out[labels == i] = 255
    return out


# ── Path extraction (pixels → plotter inches) ──────────────────────────────

def _skeletonize(binary):
    fg = binary == 0
    skel = _skimage_skeletonize(fg)
    out = np.full_like(binary, 255)
    out[skel] = 0
    return out


def _trace_paths(skel_bin):
    fg = 255 - skel_bin
    contours, _ = cv2.findContours(fg, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    paths = []
    for cnt in contours:
        if len(cnt) < 2:
            continue
        pts = cnt.squeeze(axis=1)
        if pts.ndim < 2:
            continue
        paths.append([(float(x), float(y)) for x, y in pts])
    return paths


def _path_length(p):
    return sum(math.hypot(p[i][0]-p[i-1][0], p[i][1]-p[i-1][1])
               for i in range(1, len(p)))


def _sort_paths(paths):
    if not paths:
        return paths
    out, used, pos = [], set(), (0, 0)
    for _ in range(len(paths)):
        best_i, best_d, best_rev = -1, float('inf'), False
        for i, p in enumerate(paths):
            if i in used:
                continue
            d0 = math.hypot(p[0][0]-pos[0], p[0][1]-pos[1])
            d1 = math.hypot(p[-1][0]-pos[0], p[-1][1]-pos[1])
            if d0 < best_d:
                best_d, best_i, best_rev = d0, i, False
            if d1 < best_d:
                best_d, best_i, best_rev = d1, i, True
        if best_i < 0:
            break
        used.add(best_i)
        p = list(reversed(paths[best_i])) if best_rev else paths[best_i]
        out.append(p)
        pos = p[-1]
    return out


def extract_paths(binary, page_w, page_h):
    """
    From a binary image (in natural/flipped view), extract paths in plotter inches.

    The image was flipped 180° for AI processing, so pixel coords are in
    natural (human) orientation.  To get plotter coords we reverse the flip:
        plotter_x = page_w - pixel_col / WARP_PPI
        plotter_y = page_h - pixel_row / WARP_PPI
    """
    skel = _skeletonize(binary)
    cv2.imwrite('debug_05b_skeleton.png', skel)

    pixel_paths = _trace_paths(skel)

    # Simplify curves
    eps = 0.2  # pixels
    simplified = []
    for p in pixel_paths:
        pts = np.array(p, dtype=np.float32).reshape(-1, 1, 2)
        approx = cv2.approxPolyDP(pts, eps, closed=False)
        sp = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
        if len(sp) >= 2:
            simplified.append(sp)
    pixel_paths = simplified

    # Convert pixel coords → plotter inches
    # Undo the 180° flip: x_plotter = page_w - col/PPI, y_plotter = page_h - row/PPI
    plotter_paths = []
    for pp in pixel_paths:
        path = [(page_w - x / WARP_PPI, page_h - y / WARP_PPI) for x, y in pp]
        if _path_length(path) > 3.0 / WARP_PPI:
            plotter_paths.append(path)

    return _sort_paths(plotter_paths)


# ── Plotter drawing ─────────────────────────────────────────────────────────

def draw_paths(paths):
    """Draw paths on the plotter using direct run_path() + wait() calls.

    Avoids run_drawing() which lacks proper synchronisation between paths
    and causes accumulated position drift.
    """
    if not paths:
        print('  No paths to draw!')
        return

    total_len = sum(_path_length(p) for p in paths)
    print(f'  Paths: {len(paths)}')
    print(f'  Draw length: {total_len:.1f}"')
    print()
    print('  *** Ensure pen is at HOME (marker ID2, bottom-right) ***')
    input('  Press Enter to start drawing (Ctrl-C to cancel)...')

    d = axi.Device()
    d.enable_motors()
    d.zero_position()
    time.sleep(0.3)

    pos = (0.0, 0.0)
    total = len(paths)
    for i, path in enumerate(paths):
        # Jog to start of path (pen up)
        d.run_path([pos, path[0]], jog=True)
        d.wait()
        # Draw path
        d.pen_down()
        time.sleep(0.1)
        d.run_path(path)
        d.wait()
        d.pen_up()
        time.sleep(0.1)
        pos = path[-1]
        if (i + 1) % 20 == 0 or i == total - 1:
            print(f'    path {i + 1}/{total}')

    # Return home
    d.run_path([pos, (0, 0)], jog=True)
    d.wait()
    d.disable_motors()
    print('  Done!')


# ── API key helper ──────────────────────────────────────────────────────────

def get_api_key(arg_key):
    if arg_key:
        return arg_key
    key = os.environ.get('STABILITY_API_KEY')
    if key:
        return key
    env_f = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_f):
        for line in open(env_f):
            line = line.strip()
            if line.startswith('STABILITY_API_KEY='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return None


# ── Main pipeline ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='AI art completion for pen plotter')
    ap.add_argument('--camera', type=int, default=None)
    ap.add_argument('--prompt', type=str, default=DEFAULT_PROMPT)
    ap.add_argument('--subject', type=str, default=None,
                        help='REQUIRED: What the drawing depicts (e.g. "a cat", "a house")')
    ap.add_argument('--strength', type=float, default=0.65,
                        help='AI freedom 0-1 (default 0.65; higher=more new content)')
    ap.add_argument('--api-key', type=str, default=None)
    ap.add_argument('--local', action='store_true')
    ap.add_argument('--steps', type=int, default=4)
    ap.add_argument('--no-plot', action='store_true')
    ap.add_argument('--skip-capture', type=str, default=None)
    args = ap.parse_args()

    # 1) Calibration
    print('Step 1: Loading calibration...')
    cal = load_calibration()
    cam_id = args.camera if args.camera is not None else cal.get('camera_id', 0)
    page_w, page_h = cal['page_w'], cal['page_h']
    print(f'  Page: {page_w}" x {page_h}"  Camera: {cam_id}')

    # 2) Capture
    print('\nStep 2: Capturing artwork...')
    if args.skip_capture:
        frame = cv2.imread(args.skip_capture)
        if frame is None:
            print(f'ERROR: cannot read {args.skip_capture}'); sys.exit(1)
        print(f'  Loaded {args.skip_capture}')
    else:
        input('  Place artwork under camera, press Enter...')
        frame = capture_frame(cam_id)
    print(f'  Frame: {frame.shape[1]}x{frame.shape[0]}')
    cv2.imwrite('debug_01_capture.png', frame)

    # 3) Warp to plotter space (flipped 180° for natural view)
    print('\nStep 3: Warping to plotter space...')
    warped = warp_to_plotter_space(frame, cal)
    print(f'  Warped: {warped.shape[1]}x{warped.shape[0]} ({WARP_PPI} PPI)')
    cv2.imwrite('debug_02_warped.png', warped)

    # 4) Extract existing sketch
    print('\nStep 4: Extracting sketch...')
    sketch_gray, sketch_bin = extract_sketch(warped)
    cv2.imwrite('debug_03_sketch.png', sketch_bin)
    cv2.imwrite('debug_03b_sketch_gray.png', sketch_gray)
    black_pct = 100 * np.sum(sketch_bin == 0) / sketch_bin.size
    print(f'  Black: {black_pct:.1f}%')

    # 5) AI completion
    print('\nStep 5: AI completion...')
    # Build prompt — prepend subject for much better results
    prompt = args.prompt
    if args.subject:
        prompt = (f'Complete this pencil sketch of {args.subject}. ' + prompt)
        print(f'  Subject: {args.subject}')
    else:
        print('  WARNING: No --subject given. AI results will be much better')
        print('           if you describe the drawing, e.g. --subject "a cat"')
    print(f'  Strength: {args.strength}')
    print(f'  Prompt: {prompt[:120]}...')

    api_key = get_api_key(args.api_key)
    if api_key and not args.local:
        # Send grayscale (not binary) — preserves pencil texture for the AI
        completed = call_sdxl_api(sketch_gray, prompt, api_key, args.strength)
    elif HAS_DIFFUSERS:
        completed = call_local_img2img(sketch_bin, prompt, args.strength,
                                        steps=args.steps)
    else:
        print('  WARNING: No API key and no diffusers.  Returning sketch as-is.')
        completed = Image.fromarray(sketch_bin).convert('L')
    completed.save('debug_04_completed.png')

    # 6) Diff (uses binary for clean line detection)
    print('\nStep 6: Finding new lines...')
    new_lines = diff_sketches(sketch_bin, completed)
    cv2.imwrite('debug_05_new_lines.png', new_lines)
    new_pct = 100 * np.sum(new_lines == 0) / new_lines.size
    print(f'  New line pixels: {new_pct:.2f}%')
    if new_pct < 0.01:
        print('  Almost no new lines.  Nothing to draw.')
        return
    if new_pct > 20:
        print(f'  WARNING: {new_pct:.1f}% new pixels — AI completion looks wrong.')
        print('  The completed image may be mostly black / garbage.')
        print('  Check debug_04_completed.png.  Try --strength 0.3 or --subject.')
        resp = input('  Continue anyway? [y/N] ').strip().lower()
        if resp != 'y':
            print('  Aborted.')
            return

    # 7) Extract plotter paths
    print('\nStep 7: Extracting plotter paths...')
    paths = extract_paths(new_lines, page_w, page_h)
    total_len = sum(_path_length(p) for p in paths)
    print(f'  Paths: {len(paths)}')
    print(f'  Draw length: {total_len:.1f}"')

    if not paths:
        print('  No valid paths.')
        return

    # Bounds check
    xs = [x for p in paths for x, y in p]
    ys = [y for p in paths for x, y in p]
    print(f'  Plotter bounds: x=[{min(xs):.2f}, {max(xs):.2f}]  '
          f'y=[{min(ys):.2f}, {max(ys):.2f}]')
    if max(xs) > page_w + 0.1 or max(ys) > page_h + 0.1:
        print('  WARNING: paths exceed page bounds!')
    if min(xs) < -0.1 or min(ys) < -0.1:
        print('  WARNING: paths go below origin!')

    # 8) Draw
    if args.no_plot:
        print('\nStep 8: --no-plot, skipping plotter.')
    else:
        print('\nStep 8: Drawing...')
        draw_paths(paths)

    print('\nAll done!  Debug images: debug_*.png')


if __name__ == '__main__':
    main()
