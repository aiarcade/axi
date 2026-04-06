"""
art_completer.py — AI-assisted art completion for AxiDraw pen plotter.

Workflow:
    1. Calibrate camera → plotter alignment  (run calibrate.py first)
    2. Artist draws something on paper by hand
    3. This program captures the current state via camera
    4. Extracts the existing sketch
    5. Sends to SDXL (Stability AI API) for completion
    6. Diffs original vs completed to find new lines
    7. Converts new lines to plotter paths
    8. Draws only the new parts on the plotter

Usage:
    # First time: calibrate
    python calibrate.py --camera 0

    # Then run the completer
    python art_completer.py

    # Or with options
    python art_completer.py --camera 0 --prompt "complete this pencil sketch of a face" \\
                            --strength 0.6 --api-key YOUR_KEY

Environment variable:
    STABILITY_API_KEY — your Stability AI API key
                        (or pass --api-key, or put it in .env file)
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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CALIB_FILE = 'calibration.json'

# Default SDXL prompt for sketch completion
DEFAULT_PROMPT = (
    'Add new elements to complete this pencil line drawing sketch. '
    'Keep all existing lines exactly as they are. '
    'Only add new lines in the empty white areas to complete the drawing. '
    'Clean thin black outlines on white paper. No shading, no color, no fill.'
)

# Stability AI API endpoint (img2img)
STABILITY_API_URL = 'https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/image-to-image'

# Plotter drawing parameters
DPI_FOR_WARP = 100  # pixels per inch in the warped image


# ---------------------------------------------------------------------------
# Calibration loading
# ---------------------------------------------------------------------------

def load_calibration():
    """Load camera-to-plotter calibration."""
    if not os.path.exists(CALIB_FILE):
        print(f'ERROR: {CALIB_FILE} not found. Run calibrate.py first.')
        sys.exit(1)
    with open(CALIB_FILE) as f:
        data = json.load(f)
    data['cam_to_plotter'] = np.array(data['cam_to_plotter'], dtype=np.float64)
    data['plotter_to_cam'] = np.array(data['plotter_to_cam'], dtype=np.float64)
    return data


# ---------------------------------------------------------------------------
# Camera capture
# ---------------------------------------------------------------------------

def _find_working_camera(preferred_id):
    """Try the preferred camera first, then scan others.
    USB cameras (like Logitech C270) need a warmup period before they
    produce non-black frames, so we read several frames before deciding."""
    candidates = [preferred_id] + [i for i in range(6) if i != preferred_id]
    for cam_id in candidates:
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            continue
        # Give the camera time to initialise (auto-exposure, USB settle)
        time.sleep(2.0)
        # Read up to 60 frames to let the sensor warm up
        good = False
        for _ in range(60):
            ret, frame = cap.read()
            if ret and frame is not None and frame.mean() > 5:
                good = True
                break
        cap.release()
        if good:
            if cam_id != preferred_id:
                print(f'  Camera {preferred_id} unavailable, using camera {cam_id}')
            return cam_id
    raise RuntimeError(f'No working camera found (tried {candidates})')


def capture_frame(camera_id, warmup_frames=60, warmup_secs=4):
    """Capture a single frame from the USB camera."""
    camera_id = _find_working_camera(camera_id)
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open camera {camera_id}')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # Let USB camera and auto-exposure settle
    time.sleep(warmup_secs)
    for _ in range(warmup_frames):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None or frame.mean() < 5:
        raise RuntimeError('Failed to capture frame (black or empty)')
    return frame


def warp_to_plotter_space(frame, calib):
    """
    Warp camera frame to a flat top-down view aligned with plotter coordinates.
    Returns a grayscale image where 1 inch = DPI_FOR_WARP pixels.
    """
    page_w = calib['page_w']
    page_h = calib['page_h']
    M = calib['cam_to_plotter']

    out_w = int(page_w * DPI_FOR_WARP)
    out_h = int(page_h * DPI_FOR_WARP)

    # Scale the transform so output is in pixels (DPI_FOR_WARP px/inch)
    S = np.array([
        [DPI_FOR_WARP, 0, 0],
        [0, DPI_FOR_WARP, 0],
        [0, 0, 1],
    ], dtype=np.float64)
    M_scaled = S @ M

    warped = cv2.warpPerspective(frame, M_scaled, (out_w, out_h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=(255, 255, 255))

    # Crop a small margin from the edges to remove ArUco markers, tape,
    # and any camera-captured content that bleeds in from outside the
    # calibrated drawing area.
    margin = int(DPI_FOR_WARP * 0.15)  # ~0.15" inset (15px at 100 DPI)
    if margin > 0:
        # Set border pixels to white so they don't appear as sketch lines
        warped[:margin, :] = 255          # top
        warped[-margin:, :] = 255         # bottom
        warped[:, :margin] = 255          # left
        warped[:, -margin:] = 255         # right

    # Flip 180° so the image looks like a natural top-down view of the paper.
    # The warped image is in plotter coords where (0,0)=bottom-right, +X=left,
    # +Y=up, which appears rotated 180° from a human perspective.
    # Flipping here gives the AI a natural orientation for better completions.
    # Path coordinates are transformed back to plotter space after extraction.
    warped = cv2.flip(warped, -1)  # flip both axes = 180° rotation

    return warped


# ---------------------------------------------------------------------------
# Sketch extraction
# ---------------------------------------------------------------------------

def extract_sketch(warped_color):
    """
    Convert warped camera image to a clean binary sketch.
    Black lines on white background.
    """
    gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold to handle uneven lighting
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15
    )

    # Clean up noise
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    return binary  # 255=white, 0=black


# ---------------------------------------------------------------------------
# SDXL API call (Stability AI)
# ---------------------------------------------------------------------------

def pil_to_png_bytes(pil_img):
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    return buf.getvalue()


def _pad_to_square(pil_img, fill=255):
    """Pad a PIL image to a square with white, preserving aspect ratio.
    Returns (padded_image, (pad_left, pad_top, orig_w, orig_h))."""
    w, h = pil_img.size
    size = max(w, h)
    padded = Image.new(pil_img.mode, (size, size), color=fill if pil_img.mode == 'L' else (fill, fill, fill))
    pad_left = (size - w) // 2
    pad_top = (size - h) // 2
    padded.paste(pil_img, (pad_left, pad_top))
    return padded, (pad_left, pad_top, w, h)


def _unpad_from_square(pil_img, pad_info):
    """Crop back to original aspect ratio after padding."""
    pad_left, pad_top, orig_w, orig_h = pad_info
    # Scale pad_info to current image size
    cur_size = pil_img.size[0]  # square
    scale = cur_size / max(orig_w + 2 * pad_left, orig_h + 2 * pad_top)
    left = int(pad_left * scale)
    top = int(pad_top * scale)
    right = left + int(orig_w * scale)
    bottom = top + int(orig_h * scale)
    return pil_img.crop((left, top, right, bottom))


def call_sdxl_img2img(sketch_binary, prompt, api_key, strength=0.55,
                       negative_prompt='color, shading, gradient, photograph, realistic, 3d'):
    """
    Send the current sketch to SDXL img2img via Stability AI API.
    Returns the completed sketch as a PIL Image.
    """
    orig_h, orig_w = sketch_binary.shape
    pil_sketch = Image.fromarray(sketch_binary).convert('RGB')

    # Pad to square (preserve aspect ratio) then resize to 1024x1024
    pil_padded, pad_info = _pad_to_square(pil_sketch, fill=255)
    pil_resized = pil_padded.resize((1024, 1024), Image.LANCZOS)

    png_bytes = pil_to_png_bytes(pil_resized)

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json',
    }

    # Build multipart form
    files = {
        'init_image': ('sketch.png', png_bytes, 'image/png'),
    }
    data = {
        'text_prompts[0][text]': prompt,
        'text_prompts[0][weight]': '1.0',
        'text_prompts[1][text]': negative_prompt,
        'text_prompts[1][weight]': '-1.0',
        'init_image_mode': 'IMAGE_STRENGTH',
        'image_strength': str(1.0 - strength),  # API uses 1-strength
        'cfg_scale': '12',
        'samples': '1',
        'steps': '35',
        'style_preset': 'line-art',
    }

    print(f'  Calling Stability AI API (strength={strength})...')
    resp = requests.post(STABILITY_API_URL, headers=headers,
                         files=files, data=data, timeout=120)

    if resp.status_code != 200:
        print(f'  API error {resp.status_code}: {resp.text[:500]}')
        raise RuntimeError(f'SDXL API returned {resp.status_code}')

    result = resp.json()
    img_b64 = result['artifacts'][0]['base64']
    img_bytes = base64.b64decode(img_b64)
    completed_square = Image.open(io.BytesIO(img_bytes)).convert('L')

    # Unpad from square back to original aspect ratio, then resize to exact dims
    completed_cropped = _unpad_from_square(completed_square, pad_info)
    completed = completed_cropped.resize((orig_w, orig_h), Image.LANCZOS)

    return completed


# ---------------------------------------------------------------------------
# Local SD Turbo (CPU) — no API key needed
# ---------------------------------------------------------------------------

_local_pipe = None  # cache the loaded pipeline


def load_local_pipeline():
    """Load SD Turbo pipeline once, cached globally."""
    global _local_pipe
    if _local_pipe is not None:
        return _local_pipe
    if not HAS_DIFFUSERS:
        raise RuntimeError(
            'diffusers not installed. Run: pip install diffusers transformers accelerate torch')
    print('  Loading SD Turbo model (first run downloads ~2GB)...')
    _local_pipe = AutoPipelineForImage2Image.from_pretrained(
        'stabilityai/sd-turbo',
        torch_dtype=torch.bfloat16,
        variant='fp16',
        low_cpu_mem_usage=True,
    )
    _local_pipe.to('cpu')
    # Reduce memory usage
    _local_pipe.set_progress_bar_config(disable=False)
    print('  Model loaded.')
    return _local_pipe


def call_local_img2img(sketch_binary, prompt, strength=0.55,
                       negative_prompt='color, shading, gradient, photograph, realistic, 3d',
                       num_steps=4):
    """
    Run img2img locally on CPU using SD Turbo.
    SD Turbo is designed for 1-4 steps, making it feasible on CPU.
    Uses 256x256 to keep CPU inference under ~2 minutes.
    """
    pipe = load_local_pipeline()

    # Prepare input image — resize to 256x256 for CPU speed
    pil_sketch = Image.fromarray(sketch_binary).convert('RGB')
    orig_h, orig_w = sketch_binary.shape
    pil_sketch_resized = pil_sketch.resize((256, 256), Image.LANCZOS)

    print(f'  Running img2img locally (steps={num_steps}, strength={strength}, 256x256)...')
    print('  This may take a few minutes on CPU...')
    t0 = time.time()

    with torch.no_grad():
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=pil_sketch_resized,
            num_inference_steps=num_steps,
            strength=strength,
            guidance_scale=0.0,  # SD Turbo works best with guidance_scale=0
            height=256,
            width=256,
        )

    elapsed = time.time() - t0
    print(f'  Generation complete in {elapsed:.0f}s')

    completed = result.images[0].convert('L')
    completed = completed.resize((orig_w, orig_h), Image.LANCZOS)
    return completed


def call_sdxl_local_fallback(sketch_binary, prompt):
    """
    Fallback if no API key and no diffusers: return sketch as-is.
    """
    print('  WARNING: No API key and diffusers not installed.')
    print('  Returning original sketch (no AI completion).')
    print('  Install local model: pip install diffusers transformers accelerate torch')
    return Image.fromarray(sketch_binary).convert('L')


# ---------------------------------------------------------------------------
# Diff: find new lines to draw
# ---------------------------------------------------------------------------

def diff_sketches(original_binary, completed_pil):
    """
    Find pixels that are in the completed sketch but NOT in the original.
    Returns a binary image of only the new lines.
    """
    completed = np.array(completed_pil)

    # Threshold completed to binary — use a higher threshold to catch
    # gray AI lines that aren't fully black
    _, completed_bin = cv2.threshold(completed, 180, 255, cv2.THRESH_BINARY)

    # Original: 0=black(drawn), 255=white
    # Completed: 0=black(drawn), 255=white
    # New lines = black in completed AND white in original
    original_drawn = (original_binary < 128)      # True where artist drew
    completed_drawn = (completed_bin == 0)         # True where AI wants lines

    new_lines = completed_drawn & ~original_drawn  # Only new stuff

    # Dilate the original to exclude lines very close to existing artwork.
    # Use a smaller kernel to avoid masking genuinely new nearby lines.
    kernel = np.ones((3, 3), np.uint8)
    original_dilated = cv2.dilate((original_drawn * 255).astype(np.uint8), kernel)
    original_dilated_mask = original_dilated > 0

    new_lines = completed_drawn & ~original_dilated_mask

    # Clean up — remove small noise blobs
    new_img = np.full_like(original_binary, 255)
    new_img[new_lines] = 0

    # Morphological open to remove tiny isolated dots
    kernel_sm = np.ones((2, 2), np.uint8)
    new_img = cv2.morphologyEx(new_img, cv2.MORPH_OPEN, kernel_sm)

    # Remove small connected components (< 10 pixels)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        255 - new_img, connectivity=8)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] < 10:
            new_img[labels == i] = 255

    return new_img


# ---------------------------------------------------------------------------
# Path extraction (from sample_test.py approach)
# ---------------------------------------------------------------------------

def path_length(path):
    d = 0
    for i in range(1, len(path)):
        dx = path[i][0] - path[i-1][0]
        dy = path[i][1] - path[i-1][1]
        d += math.hypot(dx, dy)
    return d


def rdp_simplify(pts, eps):
    """Ramer-Douglas-Peucker line simplification."""
    if len(pts) < 3:
        return pts
    p0 = np.array(pts[0])
    p1 = np.array(pts[-1])
    line = p1 - p0
    line_len = np.linalg.norm(line)
    dmax = 0.0
    idx = 0
    for i in range(1, len(pts) - 1):
        pt = np.array(pts[i])
        if line_len < 1e-12:
            d = np.linalg.norm(pt - p0)
        else:
            d = abs((line[0] * (p0[1] - pt[1]) - line[1] * (p0[0] - pt[0]))) / line_len
        if d > dmax:
            dmax = d
            idx = i
    if dmax > eps:
        left = rdp_simplify(pts[:idx + 1], eps)
        right = rdp_simplify(pts[idx:], eps)
        return left[:-1] + right
    else:
        return [pts[0], pts[-1]]


def nearest_path_start(pos, paths, used):
    best_d = float('inf')
    best_i = -1
    best_rev = False
    for i, p in enumerate(paths):
        if i in used:
            continue
        d0 = math.hypot(p[0][0] - pos[0], p[0][1] - pos[1])
        d1 = math.hypot(p[-1][0] - pos[0], p[-1][1] - pos[1])
        if d0 < best_d:
            best_d = d0
            best_i = i
            best_rev = False
        if d1 < best_d:
            best_d = d1
            best_i = i
            best_rev = True
    return best_i, best_rev


def sort_paths_greedy(paths):
    if not paths:
        return paths
    sorted_paths = []
    used = set()
    pos = (0, 0)
    for _ in range(len(paths)):
        i, rev = nearest_path_start(pos, paths, used)
        if i < 0:
            break
        used.add(i)
        p = list(reversed(paths[i])) if rev else paths[i]
        sorted_paths.append(p)
        pos = p[-1]
    return sorted_paths


def _skeletonize(binary_img):
    """Thin black lines to 1-pixel skeleton using skimage."""
    # skimage.skeletonize expects True=foreground
    foreground = binary_img == 0  # black lines are foreground
    skel = _skimage_skeletonize(foreground)
    # Return as binary: 0=black lines, 255=white bg
    result = np.full_like(binary_img, 255)
    result[skel] = 0
    return result


def _trace_skeleton_paths(skeleton_binary):
    """
    Trace connected skeleton pixels into ordered path sequences.
    Uses cv2.findContours for robust curve following.
    skeleton_binary: 0=lines, 255=background.
    Returns list of pixel-coordinate paths [(col, row), ...].
    """
    # findContours needs white foreground on black bg
    fg = 255 - skeleton_binary
    contours, _ = cv2.findContours(fg, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    paths = []
    for cnt in contours:
        if len(cnt) < 2:
            continue
        # cnt shape is (N,1,2) with (x,y) = (col, row)
        pts = cnt.squeeze(axis=1)  # (N, 2)
        if pts.ndim < 2:
            continue
        path = [(float(x), float(y)) for x, y in pts]
        paths.append(path)
    return paths


def extract_paths_from_binary(binary_img, dpi):
    """
    Extract plotter paths (in inches) from a binary image.
    binary_img: 255=white, 0=black (lines to draw).
    dpi: pixels per inch in the image.
    """
    # Skeletonize to get center-line paths (avoids doubled outlines)
    skeleton = _skeletonize(binary_img)
    cv2.imwrite('debug_05b_skeleton.png', skeleton)

    # Trace connected skeleton paths
    pixel_paths = _trace_skeleton_paths(skeleton)

    # Convert pixel coords to inches
    paths = []
    for pp in pixel_paths:
        path = [(x / dpi, y / dpi) for x, y in pp]
        paths.append(path)

    # Simplify with cv2.approxPolyDP for smooth curves
    epsilon = 0.2 / dpi  # tight tolerance to preserve curves (0.2 px in inches)
    simplified = []
    for p in paths:
        pts = np.array(p, dtype=np.float32).reshape(-1, 1, 2)
        approx = cv2.approxPolyDP(pts, epsilon, closed=False)
        sp = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
        if len(sp) >= 2:
            simplified.append(sp)
    paths = simplified

    # Filter tiny paths
    min_len = 3.0 / dpi  # at least 3 pixels long
    paths = [p for p in paths if path_length(p) > min_len]

    # Sort for efficient plotting
    paths = sort_paths_greedy(paths)

    return paths


# ---------------------------------------------------------------------------
# Plotter drawing
# ---------------------------------------------------------------------------

def draw_paths(paths):
    """Draw paths on the plotter using axi.Drawing + run_drawing()."""
    if not paths:
        print('  No paths to draw!')
        return

    drawing = axi.Drawing(paths)
    print(f'  Paths: {len(drawing.paths)}')
    print(f'  Draw length: {drawing.down_length:.1f}"')
    print(f'  Travel length: {drawing.up_length:.1f}"')

    print()
    print('  *** Ensure pen is at HOME (bottom-right / marker ID 2) ***')

    d = axi.Device()
    print(f'  Connected to plotter')
    d.enable_motors()
    d.zero_position()
    time.sleep(0.3)
    d.run_drawing(drawing)
    d.run_path([drawing.paths[-1][-1], (0, 0)], jog=True)
    d.wait()
    d.disable_motors()
    print('  Plotter done!')


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def get_api_key(args_key):
    """Get API key from args, env var, or .env file."""
    if args_key:
        return args_key
    key = os.environ.get('STABILITY_API_KEY')
    if key:
        return key
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith('STABILITY_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return None


def main():
    parser = argparse.ArgumentParser(
        description='AI-assisted art completion for AxiDraw pen plotter')
    parser.add_argument('--camera', type=int, default=None,
                        help='Camera device index (default: from calibration)')
    parser.add_argument('--prompt', type=str, default=DEFAULT_PROMPT,
                        help='SDXL prompt for completion')
    parser.add_argument('--strength', type=float, default=0.6,
                        help='Generation strength 0-1 (higher = more AI changes)')
    parser.add_argument('--api-key', type=str, default=None,
                        help='Stability AI API key (if omitted, uses local SD Turbo)')
    parser.add_argument('--local', action='store_true', default=False,
                        help='Force local SD Turbo model on CPU instead of API')
    parser.add_argument('--steps', type=int, default=4,
                        help='Number of inference steps for local model (1-4)')
    parser.add_argument('--no-plot', action='store_true',
                        help='Skip actual plotter drawing (preview only)')
    parser.add_argument('--skip-capture', type=str, default=None,
                        help='Skip camera, use this image file instead')
    args = parser.parse_args()

    # --- Load calibration ---
    print('Step 1: Loading calibration...')
    calib = load_calibration()
    camera_id = args.camera if args.camera is not None else calib.get('camera_id', 0)
    page_w = calib['page_w']
    page_h = calib['page_h']
    print(f'  Page: {page_w}" x {page_h}", Camera: {camera_id}')

    # --- Capture ---
    print('\nStep 2: Capturing current artwork...')
    if args.skip_capture:
        print(f'  Using file: {args.skip_capture}')
        frame = cv2.imread(args.skip_capture)
        if frame is None:
            print(f'ERROR: Cannot read {args.skip_capture}')
            sys.exit(1)
    else:
        input('  Place your artwork under the camera and press Enter...')
        frame = capture_frame(camera_id)
    print(f'  Captured: {frame.shape[1]}x{frame.shape[0]}')
    cv2.imwrite('debug_01_raw_capture.png', frame)

    # --- Warp to plotter space ---
    print('\nStep 3: Warping to plotter coordinate space...')
    warped = warp_to_plotter_space(frame, calib)
    print(f'  Warped: {warped.shape[1]}x{warped.shape[0]} '
          f'({DPI_FOR_WARP} DPI)')
    cv2.imwrite('debug_02_warped.png', warped)

    # --- Extract existing sketch ---
    print('\nStep 4: Extracting existing sketch...')
    sketch_binary = extract_sketch(warped)
    cv2.imwrite('debug_03_sketch_original.png', sketch_binary)
    black_pct = 100 * np.sum(sketch_binary == 0) / sketch_binary.size
    print(f'  Black pixels: {black_pct:.1f}%')

    # --- AI completion ---
    print('\nStep 5: AI completion...')
    api_key = get_api_key(args.api_key)
    if api_key and not args.local:
        print('  Using Stability AI API...')
        completed_pil = call_sdxl_img2img(
            sketch_binary, args.prompt, api_key, args.strength)
    elif HAS_DIFFUSERS:
        print('  Using local SD Turbo on CPU...')
        completed_pil = call_local_img2img(
            sketch_binary, args.prompt, args.strength,
            num_steps=args.steps)
    else:
        completed_pil = call_sdxl_local_fallback(sketch_binary, args.prompt)
    completed_pil.save('debug_04_ai_completed.png')
    print('  Saved AI completed image')

    # --- Diff ---
    print('\nStep 6: Finding new lines to draw...')
    new_lines = diff_sketches(sketch_binary, completed_pil)
    cv2.imwrite('debug_05_new_lines.png', new_lines)
    new_black_pct = 100 * np.sum(new_lines == 0) / new_lines.size
    print(f'  New line pixels: {new_black_pct:.1f}%')

    if new_black_pct < 0.01:
        print('  Almost no new lines detected. Nothing to draw.')
        return

    # --- Extract paths ---
    print('\nStep 7: Extracting plotter paths...')
    paths = extract_paths_from_binary(new_lines, DPI_FOR_WARP)
    total_pts = sum(len(p) for p in paths)
    total_len = sum(path_length(p) for p in paths)
    print(f'  Paths: {len(paths)}')
    print(f'  Points: {total_pts}')
    print(f'  Draw length: {total_len:.1f} inches')

    if not paths:
        print('  No valid paths extracted.')
        return

    # --- Bounds check ---
    all_x = [x for p in paths for x, y in p]
    all_y = [y for p in paths for x, y in p]
    print(f'  Bounds: x=[{min(all_x):.2f}, {max(all_x):.2f}] '
          f'y=[{min(all_y):.2f}, {max(all_y):.2f}]')

    if max(all_x) > page_w + 0.1 or max(all_y) > page_h + 0.1:
        print('  WARNING: Some paths exceed page bounds!')

    # --- Transform paths from natural image coords back to plotter coords ---
    # The warped image was flipped 180° for natural AI viewing.
    # Plotter coords: (0,0)=bottom-right, +X=left, +Y=up
    # Natural image:  (0,0)=top-left of paper
    # Transform: x_plotter = page_w - x_image, y_plotter = page_h - y_image
    paths = [[(page_w - x, page_h - y) for x, y in path] for path in paths]
    print(f'  Plotter bounds: x=[{min(x for p in paths for x,y in p):.2f}, '
          f'{max(x for p in paths for x,y in p):.2f}] '
          f'y=[{min(y for p in paths for x,y in p):.2f}, '
          f'{max(y for p in paths for x,y in p):.2f}]')

    # --- Draw ---
    if args.no_plot:
        print('\nStep 8: --no-plot specified, skipping plotter.')
    else:
        print('\nStep 8: Drawing on plotter...')
        input('  Ready to draw? Press Enter to start (Ctrl+C to cancel)...')
        draw_paths(paths)

    print('\nAll done! Debug images saved as debug_*.png')


if __name__ == '__main__':
    main()
