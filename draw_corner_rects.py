#!/usr/bin/env python3
"""Draw small rectangles at all 4 corners of the calibration boundary.
Helps verify plotter positioning matches the calibration area."""
import json, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

CALIB_FILE = 'calibration.json'

with open(CALIB_FILE) as f:
    cal = json.load(f)

page_w = cal['page_w']
page_h = cal['page_h']

# Small rectangle size (inches)
SIZE = 0.4

print(f'Page: {page_w:.2f}" x {page_h:.2f}" ({page_w*2.54:.1f}cm x {page_h*2.54:.1f}cm)')
print(f'Drawing {SIZE}" rectangles at all 4 corners')
print()
print('  *** Place pen at HOME (ID2, bottom-right) ***')
input('  Press Enter when ready...')

# Build corner rectangles as paths
# Each corner gets a small rectangle centered on the corner point
s = SIZE / 2
corners = [
    (0, 0),             # ID2 - origin/home (bottom-right)
    (page_w, 0),        # ID3 - bottom-left
    (page_w, page_h),   # ID0 - top-left
    (0, page_h),        # ID1 - top-right
]

paths = []
for cx, cy in corners:
    # Clamp rectangle to stay within page bounds
    x1 = max(0, cx - s)
    y1 = max(0, cy - s)
    x2 = min(page_w, cx + s)
    y2 = min(page_h, cy + s)
    paths.append([
        (x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)
    ])

drawing = axi.Drawing(paths)

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.3)
d.run_drawing(drawing)
d.wait()
d.disable_motors()
print('Done. Check if rectangles align with marker positions.')
