#!/usr/bin/env python3
"""
draw_marker_boundary.py — Draw a rectangle connecting the 4 ArUco markers.

Pen starts at marker ID2 (origin = bottom-right, plotter home).
Plotter coords: (0,0)=ID2, +X=left toward ID3, +Y=up toward ID1.

Marker layout (as seen from above):
    ID0 (page_w, page_h) ---- ID1 (0, page_h)
         |                          |
         |                          |
    ID3 (page_w, 0)     ---- ID2 (0, 0)  <-- HOME

The boundary is: ID2 → ID3 → ID0 → ID1 → ID2
"""
import json, sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

CALIB_FILE = 'calibration.json'

with open(CALIB_FILE) as f:
    cal = json.load(f)

W = cal['page_w']
H = cal['page_h']

print(f'Page: {W}" x {H}"')
print(f'Markers:')
print(f'  ID2 (home/origin) = (0, 0)')
print(f'  ID3 (bottom-left) = ({W}, 0)')
print(f'  ID0 (top-left)    = ({W}, {H})')
print(f'  ID1 (top-right)   = (0, {H})')
print()
print('*** Place pen at HOME = marker ID2 (bottom-right) ***')
input('Press Enter when ready...')

# Single closed rectangle: ID2 → ID3 → ID0 → ID1 → ID2
boundary = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]

drawing = axi.Drawing([boundary])

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.3)
d.run_drawing(drawing)
d.wait()
d.disable_motors()
print('Done.')
