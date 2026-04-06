#!/usr/bin/env python3
"""Draw boundary using RAW EBB commands — bypasses entire axi library.
Uses the same step counts that the simulation confirmed are correct.
If this draws correctly, the problem is in the library's timing/planning.
If this also draws wrong, the problem is in the hardware/firmware."""
import sys, os, time
from serial import Serial
from serial.tools.list_ports import comports

VID_PID = '04D8:FD92'

def find_port():
    for port in comports():
        if VID_PID in port[2]:
            return port[0]
    return None

port = find_port()
if not port:
    print("ERROR: No EBB device found")
    sys.exit(1)

ser = Serial(port, timeout=5)

def cmd(line):
    ser.write((line + '\r').encode())
    r = ser.readline().decode().strip()
    return r

def wait():
    while True:
        r = cmd('QM')
        if '1' not in r:
            break
        time.sleep(0.01)

# Enable motors
cmd('EM,1,1')
cmd('CS')

print("*** Place pen at HOME (ID2, bottom-right) ***")
input("Press Enter when ready...")

# Draw boundary as 4 long moves using SM (step move) command
# SM,duration_ms,axis1_steps,axis2_steps
# Max duration for SM is 24000ms (24s), max steps ~24000

# Page: 12.91" x 4.7244" 
# Steps per inch: 2117
# X steps = 12.91 * 2117 = 27330
# Y steps = 4.7244 * 2117 = 10001

X_STEPS = 27330
Y_STEPS = 10001

# Calculate durations (at ~2 inches/sec = ~4234 steps/sec)
SPEED = 4000  # steps per second
x_dur = int(X_STEPS / SPEED * 1000)
y_dur = int(Y_STEPS / SPEED * 1000)

print(f"X: {X_STEPS} steps, duration {x_dur}ms")
print(f"Y: {Y_STEPS} steps, duration {y_dur}ms")

# Pen down
cmd('SP,1,500')
time.sleep(0.6)

# Segment 1: (0,0) -> (page_w, 0) = +X only (LEFT)
print("Drawing: right edge -> bottom-left (+X)...")
cmd(f'SM,{x_dur},{X_STEPS},0')
wait()
time.sleep(0.2)

# Segment 2: (page_w, 0) -> (page_w, page_h) = +Y only (UP)
print("Drawing: bottom-left -> top-left (+Y)...")
cmd(f'SM,{y_dur},0,{Y_STEPS}')
wait()
time.sleep(0.2)

# Segment 3: (page_w, page_h) -> (0, page_h) = -X only (RIGHT)
print("Drawing: top-left -> top-right (-X)...")
cmd(f'SM,{x_dur},{-X_STEPS},0')
wait()
time.sleep(0.2)

# Segment 4: (0, page_h) -> (0, 0) = -Y only (DOWN)
print("Drawing: top-right -> origin (-Y)...")
cmd(f'SM,{y_dur},0,{-Y_STEPS}')
wait()
time.sleep(0.2)

# Pen up
cmd('SP,0,500')
time.sleep(0.5)

# Disable motors
cmd('EM,0,0')
ser.close()

print(f"""
Done! This drew a rectangle using RAW EBB commands:
  Width:  {X_STEPS} steps = {X_STEPS/2117:.2f}" = {X_STEPS/2117*2.54:.1f}cm
  Height: {Y_STEPS} steps = {Y_STEPS/2117:.2f}" = {Y_STEPS/2117*2.54:.1f}cm

Expected: 32.8cm x 12.0cm
Measure the actual drawn rectangle and tell me the dimensions.
""")
