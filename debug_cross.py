#!/usr/bin/env python3
"""Debug script to trace exactly what steps would be sent for the cross drawing."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from math import modf
from axi.planner import Planner, Point

TIMESLICE_MS = 10
STEPS_PER_INCH_X = 2464
STEPS_PER_INCH_Y = 2700

page_w, page_h = 15.35, 7.09
cx, cy = page_w / 2, page_h / 2
cross_size = 0.3

def simulate_run_plan(plan, steps_x, steps_y, error=(0,0)):
    """Simulate run_plan and return total steps moved + final error."""
    step_ms = TIMESLICE_MS
    step_s = step_ms / 1000.0
    t = 0
    total_sx = 0
    total_sy = 0
    ex, ey = error
    n_slices = 0
    while t < plan.t:
        i1 = plan.instant(t)
        i2 = plan.instant(t + step_s)
        d = i2.p.sub(i1.p)
        ex, sx = modf(d.x * steps_x + ex)
        ey, sy = modf(d.y * steps_y + ey)
        total_sx += int(sx)
        total_sy += int(sy)
        t += step_s
        n_slices += 1
    return total_sx, total_sy, (ex, ey), n_slices

# Simulate what run_drawing does
print(f"Page: {page_w}\" x {page_h}\"")
print(f"Center: ({cx:.3f}\", {cy:.3f}\")")
print(f"Steps/inch: X={STEPS_PER_INCH_X}, Y={STEPS_PER_INCH_Y}")
print()

# Create planners
draw_planner = Planner(acceleration=16, max_velocity=4, corner_factor=0.001)
jog_planner = Planner(acceleration=16, max_velocity=8, corner_factor=0.001)

error = (0, 0)

# Path 1: Boundary rectangle
boundary = [(0,0), (page_w,0), (page_w,page_h), (0,page_h), (0,0)]

# Jog from (0,0) to (0,0) — no-op
jog_path = [(0,0), (0,0)]
plan = jog_planner.plan(jog_path)
print(f"Jog to boundary start: plan.t={plan.t:.4f}s, blocks={len(plan.blocks)}")
if plan.t > 0:
    sx, sy, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
    print(f"  Steps: ({sx}, {sy}), error: ({error[0]:.4f}, {error[1]:.4f}), slices: {n}")

# Draw boundary
plan = draw_planner.plan(boundary)
print(f"\nBoundary draw: plan.t={plan.t:.4f}s, blocks={len(plan.blocks)}")
sx, sy, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
print(f"  Steps: ({sx}, {sy}), error: ({error[0]:.4f}, {error[1]:.4f}), slices: {n}")
expected_x = 0  # closed rectangle
expected_y = 0
print(f"  Expected net steps: ({expected_x}, {expected_y})")
print(f"  Difference: ({sx - expected_x}, {sy - expected_y})")

# pen_up, position = (0,0)

# Path 2: Horizontal cross line
cross_h = [(cx - cross_size, cy), (cx + cross_size, cy)]
jog_path = [(0,0), cross_h[0]]
plan = jog_planner.plan(jog_path)
print(f"\nJog to cross-H start ({cross_h[0][0]:.3f}, {cross_h[0][1]:.3f}):")
print(f"  plan.t={plan.t:.4f}s, blocks={len(plan.blocks)}")
sx, sy, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
expected_x = round(cross_h[0][0] * STEPS_PER_INCH_X)
expected_y = round(cross_h[0][1] * STEPS_PER_INCH_Y)
print(f"  Steps: ({sx}, {sy}), error: ({error[0]:.4f}, {error[1]:.4f}), slices: {n}")
print(f"  Expected: ~({expected_x}, {expected_y})")
print(f"  Difference: ({sx - expected_x}, {sy - expected_y})")
print(f"  Physical position: ({sx/STEPS_PER_INCH_X:.4f}\", {sy/STEPS_PER_INCH_Y:.4f}\")")

# Draw cross-H
plan = draw_planner.plan(cross_h)
print(f"\nDraw cross-H:")
print(f"  plan.t={plan.t:.4f}s, blocks={len(plan.blocks)}")
sx2, sy2, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
print(f"  Steps: ({sx2}, {sy2}), error: ({error[0]:.4f}, {error[1]:.4f}), slices: {n}")
expected_x2 = round(0.6 * STEPS_PER_INCH_X)  # cross_size*2 in X
expected_y2 = 0
print(f"  Expected: ~({expected_x2}, {expected_y2})")

# Cumulative from origin to end of cross-H
cum_x = sx + sx2
cum_y = sy + sy2
print(f"\nCumulative from origin to end of cross-H: ({cum_x}, {cum_y})")
print(f"  = ({cum_x/STEPS_PER_INCH_X:.4f}\", {cum_y/STEPS_PER_INCH_Y:.4f}\")")
print(f"  Expected end: ({cx+cross_size:.3f}\", {cy:.3f}\")")

# Path 3: Vertical cross line  
cross_v = [(cx, cy - cross_size), (cx, cy + cross_size)]
jog_from = (cx + cross_size, cy)
jog_path = [jog_from, cross_v[0]]
plan = jog_planner.plan(jog_path)
print(f"\nJog to cross-V start ({cross_v[0][0]:.3f}, {cross_v[0][1]:.3f}):")
print(f"  plan.t={plan.t:.4f}s, blocks={len(plan.blocks)}")
sx3, sy3, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
print(f"  Steps: ({sx3}, {sy3})")

# Draw cross-V 
plan = draw_planner.plan(cross_v)
print(f"\nDraw cross-V:")
sx4, sy4, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
print(f"  Steps: ({sx4}, {sy4})")

# Total from origin
total_x = sx + sx2 + sx3 + sx4
total_y = sy + sy2 + sy3 + sy4
print(f"\nTotal from origin after all cross drawing: ({total_x}, {total_y})")
print(f"  = ({total_x/STEPS_PER_INCH_X:.4f}\", {total_y/STEPS_PER_INCH_Y:.4f}\")")

# Return home jog
jog_home = [(cx, cy + cross_size), (0, 0)]
plan = jog_planner.plan(jog_home)
sx5, sy5, error, n = simulate_run_plan(plan, STEPS_PER_INCH_X, STEPS_PER_INCH_Y, error)
grand_x = total_x + sx5
grand_y = total_y + sy5
print(f"\nJog home steps: ({sx5}, {sy5})")
print(f"Grand total steps from origin: ({grand_x}, {grand_y})")
print(f"  Position error: ({grand_x/STEPS_PER_INCH_X:.4f}\", {grand_y/STEPS_PER_INCH_Y:.4f}\")")
