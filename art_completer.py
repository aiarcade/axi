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
from skimage.measure import find_contours
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
    print('ERROR: requests not installed. Run: pip install requests')
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CALIB_FILE = 'calibration.json'

# Default SDXL prompt for sketch completion
DEFAULT_PROMPT = (
    'Complete this pencil line drawing sketch. '
    'Add missing details to make it a finished pencil sketch. '
    'Clean black lines on white paper. Pencil drawing style. '
    'Do not add shading or color, only clean outlines.'
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

def capture_frame(camera_id, warmup=10):
    """Capture a single frame from the USB camera."""
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open camera {camera_id}')
    # Let auto-exposure settle
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError('Failed to capture frame')
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


def call_sdxl_img2img(sketch_binary, prompt, api_key, strength=0.55,
                       negative_prompt='color, shading, gradient, photograph, realistic, 3d'):
    """
    Send the current sketch to SDXL img2img via Stability AI API.
    Returns the completed sketch as a PIL Image.
    """
    # Convert binary sketch to PIL, resize to 1024x1024 for SDXL
    pil_sketch = Image.fromarray(sketch_binary).convert('RGB')
    pil_sketch_resized = pil_sketch.resize((1024, 1024), Image.LANCZOS)

    png_bytes = pil_to_png_bytes(pil_sketch_resized)

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
    completed = Image.open(io.BytesIO(img_bytes)).convert('L')

    # Resize back to original sketch dimensions
    orig_h, orig_w = sketch_binary.shape
    completed = completed.resize((orig_w, orig_h), Image.LANCZOS)

    return completed


def call_sdxl_local_fallback(sketch_binary, prompt):
    """
    Fallback if no API key: just return the sketch as-is (no AI completion).
    This lets the rest of the pipeline be tested without an API key.
    """
    print('  WARNING: No SDXL API key. Returning original sketch (no AI completion).')
    print('  Set STABILITY_API_KEY env var or pass --api-key to enable AI completion.')
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

    # Threshold completed to binary
    _, completed_bin = cv2.threshold(completed, 128, 255, cv2.THRESH_BINARY)

    # Original: 0=black(drawn), 255=white
    # Completed: 0=black(drawn), 255=white
    # New lines = black in completed AND white in original
    original_drawn = (original_binary == 0)       # True where artist drew
    completed_drawn = (completed_bin == 0)         # True where AI wants lines

    new_lines = completed_drawn & ~original_drawn  # Only new stuff

    # Dilate the original slightly before diffing to avoid edge artifacts
    kernel = np.ones((5, 5), np.uint8)
    original_dilated = cv2.dilate((original_drawn * 255).astype(np.uint8), kernel)
    original_dilated_mask = original_dilated > 0

    new_lines = completed_drawn & ~original_dilated_mask

    # Clean up
    new_img = np.full_like(original_binary, 255)
    new_img[new_lines] = 0

    # Remove tiny noise
    kernel_sm = np.ones((2, 2), np.uint8)
    new_img = cv2.morphologyEx(new_img, cv2.MORPH_OPEN, kernel_sm)

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


def extract_paths_from_binary(binary_img, dpi):
    """
    Extract plotter paths (in inches) from a binary image.
    binary_img: 255=white, 0=black (lines to draw).
    dpi: pixels per inch in the image.
    """
    pixels = binary_img.astype(float) / 255.0
    contours = find_contours(pixels, 0.5)

    paths = []
    for c in contours:
        # find_contours returns (row, col) = (y, x) in pixels
        # Convert to (x_inches, y_inches)
        path = [(float(col) / dpi, float(row) / dpi) for row, col in c]
        paths.append(path)

    # Simplify
    tolerance = 0.5 / dpi  # half-pixel tolerance in inches
    paths = [rdp_simplify(p, tolerance) for p in paths]

    # Filter tiny paths
    min_len = 2.0 / dpi  # at least 2 pixels long
    paths = [p for p in paths if len(p) >= 2 and path_length(p) > min_len]

    # Sort for efficient plotting
    paths = sort_paths_greedy(paths)

    return paths


# ---------------------------------------------------------------------------
# Plotter drawing
# ---------------------------------------------------------------------------

def draw_paths(paths):
    """Draw paths on the AxiDraw using direct Device() calls."""
    if not paths:
        print('  No paths to draw!')
        return

    d = axi.Device()
    print(f'  Connected to AxiDraw')
    d.enable_motors()
    d.pen_up()
    time.sleep(0.5)

    total = len(paths)
    for i, path in enumerate(paths):
        d.goto(path[0][0], path[0][1])
        time.sleep(0.05)

        d.pen_down()
        time.sleep(0.2)

        for j in range(1, len(path)):
            x1, y1 = path[j - 1]
            x2, y2 = path[j]
            d.move(x2 - x1, y2 - y1)

        d.pen_up()
        time.sleep(0.1)

        if (i + 1) % 20 == 0 or i == total - 1:
            print(f'    path {i + 1}/{total}')

    d.goto(0, 0)
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
    parser.add_argument('--strength', type=float, default=0.55,
                        help='Generation strength 0-1 (higher = more AI changes)')
    parser.add_argument('--api-key', type=str, default=None,
                        help='Stability AI API key')
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

    # --- SDXL completion ---
    print('\nStep 5: AI completion via SDXL...')
    api_key = get_api_key(args.api_key)
    if api_key:
        completed_pil = call_sdxl_img2img(
            sketch_binary, args.prompt, api_key, args.strength)
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
