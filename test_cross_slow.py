#!/usr/bin/env python3
"""Test cross with SLOW jog speed (same as draw speed).
Theory: JOG_MAX_VELOCITY=8 exceeds EasyDraw's max step rate,
causing lost steps. This test uses max_velocity=4 instead."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

page_w, page_h = 15.35, 7.09
cx, cy = page_w / 2, page_h / 2
cross_size = 0.5

print(f"Page: {page_w}\" x {page_h}\"")
print(f"Center: ({cx:.3f}\", {cy:.3f}\")")
print(f"  = ({cx*2.54:.1f}cm, {cy*2.54:.1f}cm) from origin")
print(f"Using MAX_VELOCITY=4 for jogs (instead of 8)")
print()
print("  *** Pen must be at HOME (bottom-right, marker ID 2) ***")
input("  Press Enter to start...")

d = axi.Device()
# Override jog velocity to match draw velocity
d.jog_max_velocity = 4
d.enable_motors()
d.zero_position()
time.sleep(0.5)

# Draw cross using Drawing (same approach as draw_boundary.py)
paths = [
    [(cx - cross_size, cy), (cx + cross_size, cy)],  # horizontal
    [(cx, cy - cross_size), (cx, cy + cross_size)],   # vertical
]
drawing = axi.Drawing(paths)
print("Drawing cross...")
d.run_drawing(drawing)
d.wait()
d.disable_motors()
print("Done.")
print(f"Cross should be at center of page:")
print(f"  {cx*2.54:.1f}cm from right edge, {cy*2.54:.1f}cm from bottom edge")
