#!/usr/bin/env python3
"""Test: Draw an L-shape to determine which axis is X and which is Y.
Draws from origin:
  1) A line along X-only (should go left from home toward ID3)
  2) A line along Y-only (should go up from home toward ID1)
The L-shape will show which physical direction each axis actually moves."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

print("This draws an L-shape from origin (home/ID2):")
print("  1) Line along X-axis only: (0,0) -> (3,0) — should go LEFT toward ID3")
print("  2) Line along Y-axis only: (0,0) -> (0,3) — should go UP toward ID1")
print("  3) Returns to origin")
print()
print("  *** Place pen at HOME (ID2, bottom-right) ***")
input("  Press Enter when ready...")

d = axi.Device()
d.enable_motors()
d.zero_position()
d.pen_up()
time.sleep(0.5)

# Draw X-axis line: (0,0) -> (3,0)
print("Drawing X-axis line (3 inches)...")
d.pen_down()
time.sleep(0.2)
d.run_path([(0, 0), (3, 0)])
d.wait()
d.pen_up()
time.sleep(0.2)

# Return to origin
print("Returning to origin...")
d.run_path([(3, 0), (0, 0)], jog=True)
d.wait()
time.sleep(0.2)

# Draw Y-axis line: (0,0) -> (0,3)
print("Drawing Y-axis line (3 inches)...")
d.pen_down()
time.sleep(0.2)
d.run_path([(0, 0), (0, 3)])
d.wait()
d.pen_up()
time.sleep(0.2)

# Return to origin
print("Returning to origin...")
d.run_path([(0, 3), (0, 0)], jog=True)
d.wait()

d.disable_motors()
print()
print("Done! You should see an L-shape:")
print("  - One arm goes LEFT (toward ID3) = X-axis")
print("  - One arm goes UP (toward ID1) = Y-axis")
print("  If the directions are swapped, X and Y motors are swapped.")
print()
print("Measure each arm and tell me:")
print("  1) Which direction did the FIRST line go? (left or up?)")
print("  2) Length of first line (X-axis)?")
print("  3) Length of second line (Y-axis)?")
