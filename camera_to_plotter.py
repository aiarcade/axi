"""
draw_boundary.py — Draw calibrated plotter boundary (with scale correction)

Usage:
    python draw_boundary.py
    python draw_boundary.py --grid
    python draw_boundary.py --scale 0.985
    python draw_boundary.py --scale-x 0.98 --scale-y 0.99
"""

import json
import time
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

CALIB_FILE = 'calibration.json'


def load_page_size():
    if not os.path.exists(CALIB_FILE):
        print(f'ERROR: {CALIB_FILE} not found. Run calibrate.py first.')
        sys.exit(1)

    with open(CALIB_FILE) as f:
        data = json.load(f)

    return data['page_w'], data['page_h']


def draw_boundary(page_w, page_h, grid_spacing=0):
    print()
    print('*** IMPORTANT: Pen must be at HOME (bottom-right) ***')
    input('Press Enter when ready...')

    cx, cy = page_w / 2, page_h / 2
    cross_size = 0.3

    paths = [
        # Boundary
        [(0, 0), (page_w, 0), (page_w, page_h), (0, page_h), (0, 0)],
        # Center cross
        [(cx - cross_size, cy), (cx + cross_size, cy)],
        [(cx, cy - cross_size), (cx, cy + cross_size)],
    ]

    drawing = axi.Drawing(paths)

    print(f'Drawing boundary: {page_w:.3f}" x {page_h:.3f}"')

    d = axi.Device()
    d.enable_motors()
    d.zero_position()
    time.sleep(0.3)

    d.run_drawing(drawing)
    d.wait()

    print('Boundary done.')

    # ── Grid ──
    if grid_spacing > 0:
        print(f'Drawing grid ({grid_spacing}" spacing)...')
        cur_pos = (0, 0)

        # Horizontal lines
        y = grid_spacing
        while y < page_h:
            d.run_path([cur_pos, (0, y)], jog=True)
            d.wait()
            d.pen_down()
            d.run_path([(0, y), (page_w, y)])
            d.wait()
            d.pen_up()
            cur_pos = (page_w, y)
            y += grid_spacing

        # Vertical lines
        x = grid_spacing
        while x < page_w:
            d.run_path([cur_pos, (x, 0)], jog=True)
            d.wait()
            d.pen_down()
            d.run_path([(x, 0), (x, page_h)])
            d.wait()
            d.pen_up()
            cur_pos = (x, page_h)
            x += grid_spacing

        print('Grid done.')

    # Return home
    d.run_path([cur_pos, (0, 0)], jog=True)
    d.wait()
    d.disable_motors()
    print('Complete.')


def main():
    parser = argparse.ArgumentParser(description='Draw plotter boundary with scale correction')

    parser.add_argument('--grid', nargs='?', const=1, type=float, default=0,
                        help='Draw grid (default 1 inch)')

    parser.add_argument('--scale', type=float, default=1.0,
                        help='Uniform scale correction (e.g., 0.985)')

    parser.add_argument('--scale-x', type=float, default=None,
                        help='X-axis scale correction')

    parser.add_argument('--scale-y', type=float, default=None,
                        help='Y-axis scale correction')

    parser.add_argument('--page-w', type=float, default=None)
    parser.add_argument('--page-h', type=float, default=None)

    args = parser.parse_args()

    cal_w, cal_h = load_page_size()

    page_w = args.page_w if args.page_w else cal_w
    page_h = args.page_h if args.page_h else cal_h

    # Apply scaling
    scale_x = args.scale_x if args.scale_x else args.scale
    scale_y = args.scale_y if args.scale_y else args.scale

    corrected_w = page_w * scale_x
    corrected_h = page_h * scale_y

    print(f'Original: {page_w}" x {page_h}"')
    print(f'Scaled:   {corrected_w:.3f}" x {corrected_h:.3f}"')
    print(f'Scale X: {scale_x}, Scale Y: {scale_y}')

    draw_boundary(corrected_w, corrected_h, grid_spacing=args.grid)


if __name__ == '__main__':
    main()