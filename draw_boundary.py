"""
draw_boundary.py — Draw the plotter area boundary using the AxiDraw plotter.

Uses the calibration data to draw a rectangle matching the page boundary,
plus an optional inch grid, so you can verify the calibration is correct.

Usage:
    python draw_boundary.py              # draw boundary only
    python draw_boundary.py --grid       # draw boundary + 1-inch grid
    python draw_boundary.py --grid 2     # draw boundary + 2-inch grid
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
    """Load page dimensions from calibration.json."""
    if not os.path.exists(CALIB_FILE):
        print(f'ERROR: {CALIB_FILE} not found. Run calibrate.py first.')
        sys.exit(1)
    with open(CALIB_FILE) as f:
        data = json.load(f)
    return data['page_w'], data['page_h']


def draw_boundary(page_w, page_h, grid_spacing=0):
    """Draw the page boundary and optional grid on the plotter.

    Uses axi.Drawing + Device.run_drawing() — the same approach
    that sample_test.py uses successfully.
    Draws boundary and center cross as a single Drawing to avoid accumulated error.
    """
    print()
    print('  *** IMPORTANT: Pen must be at HOME position (bottom-right corner) ***')
    print('  *** This is where ArUco marker ID 2 is placed.                    ***')
    print()
    input('  Press Enter when the pen is at home (bottom-right)...')

    cx, cy = page_w / 2, page_h / 2
    cross_size = 0.3

    # Build all paths as a single Drawing (no accumulated error)
    paths = [
        # Boundary rectangle
        [(0, 0), (page_w, 0), (page_w, page_h), (0, page_h), (0, 0)],
        # Center cross - horizontal
        [(cx - cross_size, cy), (cx + cross_size, cy)],
        # Center cross - vertical
        [(cx, cy - cross_size), (cx, cy + cross_size)],
    ]

    drawing = axi.Drawing(paths)
    print(f'Drawing boundary: {page_w}" x {page_h}"')
    print(f'  Center mark at ({cx:.2f}", {cy:.2f}")')

    d = axi.Device()
    d.enable_motors()
    d.zero_position()
    time.sleep(0.3)
    d.run_drawing(drawing)
    d.wait()
    print('  Boundary done.')

    # ── Grid lines ──
    if grid_spacing > 0:
        print(f'Drawing grid (every {grid_spacing}")...')
        cur_pos = (0, 0)
        # Horizontal lines
        y = grid_spacing
        while y < page_h:
            d.run_path([cur_pos, (0, y)], jog=True)
            d.wait()
            d.pen_down()
            time.sleep(0.1)
            d.run_path([(0, y), (page_w, y)])
            d.wait()
            d.pen_up()
            time.sleep(0.1)
            cur_pos = (page_w, y)
            y += grid_spacing
        # Vertical lines
        x = grid_spacing
        while x < page_w:
            d.run_path([cur_pos, (x, 0)], jog=True)
            d.wait()
            d.pen_down()
            time.sleep(0.1)
            d.run_path([(x, 0), (x, page_h)])
            d.wait()
            d.pen_up()
            time.sleep(0.1)
            cur_pos = (x, page_h)
            x += grid_spacing
        print('  Grid done.')
    else:
        cur_pos = (0, 0)

    # Return home
    d.run_path([cur_pos, (0, 0)], jog=True)
    d.wait()
    d.disable_motors()
    print('Complete.')


def main():
    parser = argparse.ArgumentParser(description='Draw plotter area boundary')
    parser.add_argument('--grid', nargs='?', const=1, type=float, default=0,
                        help='Draw grid lines (default spacing: 1 inch)')
    parser.add_argument('--page-w', type=float, default=None,
                        help='Override page width (inches)')
    parser.add_argument('--page-h', type=float, default=None,
                        help='Override page height (inches)')
    args = parser.parse_args()

    # Load from calibration or use overrides
    cal_w, cal_h = load_page_size()
    page_w = args.page_w if args.page_w else cal_w
    page_h = args.page_h if args.page_h else cal_h

    print(f'Page: {page_w}" x {page_h}"')
    draw_boundary(page_w, page_h, grid_spacing=args.grid)


if __name__ == '__main__':
    main()
