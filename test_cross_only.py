#!/usr/bin/env python3
"""Minimal test: draw ONLY a center cross mark, no boundary.
Helps isolate whether the cross positioning issue is caused by
interaction with the boundary or is a standalone problem."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

page_w, page_h = 15.35, 7.09
cx, cy = page_w / 2, page_h / 2
cross_size = 0.5  # half-inch arms for visibility

print(f"Page: {page_w}\" x {page_h}\"")
print(f"Center: ({cx:.3f}\", {cy:.3f}\")")
print(f"Cross arms: {cross_size}\" each side")
print()
print("  *** Pen must be at HOME (bottom-right, marker ID 2) ***")
input("  Press Enter to start...")

d = axi.Device()
d.enable_motors()
d.zero_position()
time.sleep(0.5)

# Method: single run_path for each segment with explicit waits

# 1) Jog to horizontal cross start
print(f"  Jogging to ({cx-cross_size:.3f}, {cy:.3f})...")
d.pen_up()
time.sleep(0.3)
d.run_path([(0, 0), (cx - cross_size, cy)], jog=True)
d.wait()
time.sleep(0.2)

# 2) Draw horizontal cross line
print(f"  Drawing horizontal line...")
d.pen_down()
time.sleep(0.2)
d.run_path([(cx - cross_size, cy), (cx + cross_size, cy)])
d.wait()
d.pen_up()
time.sleep(0.2)

# 3) Jog to vertical cross start
print(f"  Jogging to ({cx:.3f}, {cy-cross_size:.3f})...")
d.run_path([(cx + cross_size, cy), (cx, cy - cross_size)], jog=True)
d.wait()
time.sleep(0.2)

# 4) Draw vertical cross line
print(f"  Drawing vertical line...")
d.pen_down()
time.sleep(0.2)
d.run_path([(cx, cy - cross_size), (cx, cy + cross_size)])
d.wait()
d.pen_up()
time.sleep(0.2)

# 5) Return home
print("  Returning home...")
d.run_path([(cx, cy + cross_size), (0, 0)], jog=True)
d.wait()

d.disable_motors()
print("Done. Measure where the cross was drawn:")
print(f"  Expected: center of page, ~{cx*2.54:.1f}cm from right, ~{cy*2.54:.1f}cm from bottom")
