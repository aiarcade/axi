#!/usr/bin/env python3
"""Draw three circles using direct Device.run_path — no Drawing class.
Tests if the issue is in Drawing or in the coordinate system."""
import json, sys, os, time, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

with open('calibration.json') as f:
    cal = json.load(f)

W = cal['page_w']  # 12.0"
H = cal['page_h']  # 9.0"
cx, cy = W / 2, H / 2  # center = (6.0, 4.5)

def circle_path(cx, cy, r, n=120):
    return [(cx + r * math.cos(2*math.pi*i/n),
             cy + r * math.sin(2*math.pi*i/n)) for i in range(n+1)]

diameters_cm = [5, 10, 15]
circles = [circle_path(cx, cy, (d/2)/2.54) for d in diameters_cm]

print(f'Page: {W}" x {H}"')
print(f'Center: ({cx}", {cy}")')
for d in diameters_cm:
    r = (d/2)/2.54
    print(f'  {d}cm circle: x=[{cx-r:.2f}, {cx+r:.2f}]  y=[{cy-r:.2f}, {cy+r:.2f}]')

# Sanity: where should the first move go?
first_pt = circles[0][0]
print(f'\nFirst circle starts at: ({first_pt[0]:.2f}", {first_pt[1]:.2f}")')
print(f'Jog from (0,0) to there = ({first_pt[0]:.2f}", {first_pt[1]:.2f}") inches')

print()
print('*** Place pen at HOME = marker ID2 (bottom-right) ***')
input('Press Enter when ready...')

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.3)

pos = (0.0, 0.0)
for i, circ in enumerate(circles):
    # Jog to start of circle
    print(f'Circle {i+1}: jog to ({circ[0][0]:.2f}", {circ[0][1]:.2f}")')
    d.run_path([pos, circ[0]], jog=True)
    d.wait()
    # Draw circle
    d.pen_down()
    time.sleep(0.1)
    d.run_path(circ)
    d.wait()
    d.pen_up()
    time.sleep(0.1)
    pos = circ[-1]

# Return home
print('Returning home...')
d.run_path([pos, (0, 0)], jog=True)
d.wait()
d.disable_motors()
print('Done.')
