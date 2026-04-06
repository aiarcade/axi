#!/usr/bin/env python3
"""Draw calibration lines of known plotter-unit length.
Draws a horizontal and vertical line, each 4 inches (10.16cm) long,
centered in the page. Measure the actual physical length to determine
the real steps-per-inch ratio."""
import json, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

CALIB_FILE = 'calibration.json'

with open(CALIB_FILE) as f:
    cal = json.load(f)

page_w = cal['page_w']
page_h = cal['page_h']

# Draw lines that are exactly 4 inches in plotter coordinates (~10.16 cm)
LINE_LEN = 4.0  # inches in plotter units

cx, cy = page_w / 2, page_h / 2

print(f'Page: {page_w:.2f}" x {page_h:.2f}"')
print(f'Center: ({cx:.2f}", {cy:.2f}")')
print(f'Drawing two lines, each {LINE_LEN}" in plotter units ({LINE_LEN*2.54:.1f}cm expected)')
print(f'  Horizontal: ({cx-LINE_LEN/2:.2f}", {cy:.2f}") to ({cx+LINE_LEN/2:.2f}", {cy:.2f}")')
print(f'  Vertical:   ({cx:.2f}", {cy-LINE_LEN/2:.2f}") to ({cx:.2f}", {cy+LINE_LEN/2:.2f}")')
print()
print('  *** Place pen at HOME (ID2, bottom-right) ***')
input('  Press Enter when ready...')

paths = [
    # Horizontal line (4" in X)
    [(cx - LINE_LEN/2, cy), (cx + LINE_LEN/2, cy)],
    # Vertical line (4" in Y)
    [(cx, cy - LINE_LEN/2), (cx, cy + LINE_LEN/2)],
]

drawing = axi.Drawing(paths)

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.3)
d.run_drawing(drawing)
d.wait()
d.disable_motors()

print()
print('Done! Now measure the actual physical length of each line:')
print(f'  Horizontal line: expected {LINE_LEN*2.54:.1f} cm ({LINE_LEN}" in plotter units)')
print(f'  Vertical line:   expected {LINE_LEN*2.54:.1f} cm ({LINE_LEN}" in plotter units)')
print()
print('Tell me the measured lengths and I will compute the correct steps-per-inch.')
