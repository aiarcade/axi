#!/usr/bin/env python3
"""Draw three circles (5cm, 10cm, 15cm diameter) centered on the page.
Uses the same coordinate system as draw_marker_boundary.py:
    (0,0) = ID2 (home, bottom-right)
    +X = left, +Y = up
"""
import json, sys, os, time, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

with open('calibration.json') as f:
    cal = json.load(f)

W = cal['page_w']  # inches
H = cal['page_h']  # inches

cx = W / 2  # center X in inches
cy = H / 2  # center Y in inches

def circle_path(cx, cy, radius_inches, n_pts=120):
    """Generate a closed circle as a list of (x, y) points."""
    pts = []
    for i in range(n_pts + 1):
        angle = 2 * math.pi * i / n_pts
        x = cx + radius_inches * math.cos(angle)
        y = cy + radius_inches * math.sin(angle)
        pts.append((x, y))
    return pts

# Diameters in cm → radii in inches
diameters_cm = [5, 10, 15]
paths = []
for d_cm in diameters_cm:
    r_inch = (d_cm / 2) / 2.54
    paths.append(circle_path(cx, cy, r_inch))

print(f'Page: {W}" x {H}" = {W*2.54:.1f}cm x {H*2.54:.1f}cm')
print(f'Center: ({cx:.1f}", {cy:.1f}") = ({cx*2.54:.1f}cm, {cy*2.54:.1f}cm)')
for d in diameters_cm:
    print(f'  Circle: {d}cm diameter = {d/2.54:.2f}" diameter')
print()
print('*** Place pen at HOME = marker ID2 (bottom-right) ***')
input('Press Enter when ready...')

drawing = axi.Drawing(paths)
d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.3)
d.run_drawing(drawing)
d.wait()
d.disable_motors()
print('Done.')
