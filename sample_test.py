"""
Read a binary line-drawing PNG and draw it on the AxiDraw pen plotter.

Workflow:
    1. python create_image.py      # generate face_drawing.png
    2. python sample_test.py       # read PNG -> extract contours -> plot

Uses scikit-image find_contours on the binary image to trace outlines,
then simplifies and sorts paths for efficient plotting.
Drives the plotter with direct Device() calls.
"""
import numpy as np
from PIL import Image
from skimage.measure import find_contours
import axi
import time
import math

IMAGE_FILE = 'face_drawing.png'

# Plotter page (inches)
PAGE_W = 8.0
PAGE_H = 6.0
MARGIN = 0.5


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
        if line_len < 1e-12:
            d = np.linalg.norm(np.array(pts[i]) - p0)
        else:
            d = abs(np.cross(line, p0 - np.array(pts[i]))) / line_len
        if d > dmax:
            dmax = d
            idx = i
    if dmax > eps:
        left = rdp_simplify(pts[:idx+1], eps)
        right = rdp_simplify(pts[idx:], eps)
        return left[:-1] + right
    else:
        return [pts[0], pts[-1]]


def nearest_path_start(pos, paths, used):
    """Find the nearest unused path start/end point."""
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
    """Sort paths with a greedy nearest-neighbor approach."""
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


def image_to_paths(filename):
    """Read a binary PNG and extract vector paths via contour tracing."""
    im = Image.open(filename).convert('L')
    pixels = np.array(im, dtype=float) / 255.0  # 0=black, 1=white

    # find_contours finds iso-lines at the given level
    # For a binary image, 0.5 traces the boundary of black regions
    contours = find_contours(pixels, 0.5)

    # Convert (row, col) -> (x, y)
    paths = []
    for c in contours:
        path = [(float(col), float(row)) for row, col in c]
        paths.append(path)

    return paths, im.size


def scale_paths(paths, img_w, img_h, page_w, page_h, margin):
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    scale = min(usable_w / img_w, usable_h / img_h)
    offset_x = margin + (usable_w - img_w * scale) / 2
    offset_y = margin + (usable_h - img_h * scale) / 2
    scaled = []
    for path in paths:
        sp = [(x * scale + offset_x, y * scale + offset_y) for x, y in path]
        scaled.append(sp)
    return scaled


def main():
    print(f'Reading {IMAGE_FILE}...')
    paths, (img_w, img_h) = image_to_paths(IMAGE_FILE)
    print(f'  image size    : {img_w} x {img_h}')
    print(f'  raw contours  : {len(paths)}')

    # Scale to plotter page
    paths = scale_paths(paths, img_w, img_h, PAGE_W, PAGE_H, MARGIN)

    # Simplify and filter
    paths = [rdp_simplify(p, 0.008) for p in paths]
    paths = [p for p in paths if len(p) >= 2 and path_length(p) > 0.02]
    print(f'  after filter  : {len(paths)}')

    # Sort paths to minimise pen-up travel
    paths = sort_paths_greedy(paths)

    total_pts = sum(len(p) for p in paths)
    total_draw = sum(path_length(p) for p in paths)
    print(f'  total points  : {total_pts}')
    print(f'  draw length   : {total_draw:.1f} inches')

    if not paths:
        print('No paths found!')
        return

    # --- Draw on plotter ---
    d = axi.Device()
    print('Connected to AxiDraw')
    d.enable_motors()
    d.pen_up()
    time.sleep(0.5)

    total = len(paths)
    for i, path in enumerate(paths):
        # Jog to start (pen up)
        d.goto(path[0][0], path[0][1])
        time.sleep(0.05)

        # Pen down
        d.pen_down()
        time.sleep(0.2)

        # Draw segments
        for j in range(1, len(path)):
            x1, y1 = path[j - 1]
            x2, y2 = path[j]
            d.move(x2 - x1, y2 - y1)

        # Pen up
        d.pen_up()
        time.sleep(0.1)

        if (i + 1) % 20 == 0 or i == total - 1:
            print(f'  path {i + 1}/{total}')

    # Home
    d.goto(0, 0)
    d.disable_motors()
    print('Done!')


if __name__ == '__main__':
    main()
