#!/usr/bin/env python3
"""Draw ONLY the bottom edge: ID2 → ID3 (page_w inches in X direction).
Measure the drawn line length to verify step rate."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

with open('calibration.json') as f:
    cal = json.load(f)

W = cal['page_w']
print(f'Drawing bottom edge: {W}" = {W*2.54:.1f}cm')
print('*** Place pen at marker ID2 (bottom-right, home) ***')
input('Press Enter when ready...')

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.3)

# Pen down, draw +X (leftward) by page_w inches
d.pen_down()
time.sleep(0.3)
d.run_path([(0, 0), (W, 0)])
d.wait()
d.pen_up()
time.sleep(0.3)

print(f'\nDone. Expected line length: {W}" = {W*2.54:.1f}cm')
print('Measure the actual drawn length and report.')

# Return home
d.run_path([(W, 0), (0, 0)], jog=True)
d.wait()
d.disable_motors()
