#!/usr/bin/env python3
"""Draw a center cross ONLY, with reduced jog speed.
Place pen at HOME (bottom-right corner), then run this."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

page_w, page_h = 15.35, 7.09
cx, cy = page_w / 2, page_h / 2
cross_size = 0.5

print(f"Page: {page_w}\" x {page_h}\"")
print(f"Center: ({cx:.3f}\", {cy:.3f}\")")
print(f"  = ({cx*2.54:.1f}cm from right, {cy*2.54:.1f}cm from bottom)")
print(f"JOG_MAX_VELOCITY is now 4 in/s (was 8)")
print()
print("  *** Place pen at HOME (bottom-right, marker ID 2) ***")
input("  Press Enter when ready...")

paths = [
    [(cx - cross_size, cy), (cx + cross_size, cy)],
    [(cx, cy - cross_size), (cx, cy + cross_size)],
]
drawing = axi.Drawing(paths)

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.5)
d.run_drawing(drawing)
d.wait()
d.disable_motors()
print("Done. Cross should be at page center:")
print(f"  {cx*2.54:.1f}cm from right, {cy*2.54:.1f}cm from bottom")
