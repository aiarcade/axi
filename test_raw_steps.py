#!/usr/bin/env python3
"""Draw 4 separate lines of exactly 2000 steps each, in all 4 directions.
This bypasses ALL unit conversion and sends raw steps directly.
Measure each line to establish the true step-to-cm ratio per axis."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    return ser.readline().decode().strip()

def wait():
    while True:
        r = cmd('QM')
        if '1' not in r:
            break
        time.sleep(0.01)

# Enable motors
cmd('EM,1,1')
# Zero position
cmd('CS')

print("*** Place pen at HOME (ID2, bottom-right) ***")
input("Press Enter when ready...")

# Pen down
cmd('SP,1,500')
time.sleep(0.6)

STEPS = 5000
DURATION_MS = 5000  # 5 seconds for safety (slow)

print(f"\nTest 1: Motor1 only, +{STEPS} steps")
print(f"  Command: XM,{DURATION_MS},{STEPS},0")
cmd(f'XM,{DURATION_MS},{STEPS},0')
wait()
time.sleep(0.5)

# Pen up, return, pen down
cmd('SP,0,500')
time.sleep(0.6)
cmd(f'XM,{DURATION_MS},{-STEPS},0')
wait()
time.sleep(0.5)
cmd('SP,1,500')
time.sleep(0.6)

print(f"\nTest 2: Motor2 only, +{STEPS} steps")
print(f"  Command: XM,{DURATION_MS},0,{STEPS}")
cmd(f'XM,{DURATION_MS},0,{STEPS}')
wait()
time.sleep(0.5)

# Pen up, return
cmd('SP,0,500')
time.sleep(0.6)
cmd(f'XM,{DURATION_MS},0,{-STEPS}')
wait()
time.sleep(0.5)

# Now draw a box using raw steps
print(f"\nTest 3: Drawing a box of {STEPS}x{STEPS} raw steps")
cmd('SP,1,500')
time.sleep(0.6)

# Right (+Motor1)
cmd(f'XM,{DURATION_MS},{STEPS},0')
wait()
# Up (+Motor2)
cmd(f'XM,{DURATION_MS},0,{STEPS}')
wait()
# Left (-Motor1)
cmd(f'XM,{DURATION_MS},{-STEPS},0')
wait()
# Down (-Motor2)
cmd(f'XM,{DURATION_MS},0,{-STEPS}')
wait()

cmd('SP,0,500')
time.sleep(0.6)

# Disable motors
cmd('EM,0,0')
ser.close()

print(f"""
Done! You should see:
  1) A line from origin in the Motor1 direction
  2) A line from origin in the Motor2 direction  
  3) A square box drawn with {STEPS} steps per side

Please measure:
  - Line 1 direction (left/right/up/down?) and length in cm
  - Line 2 direction (left/right/up/down?) and length in cm
  - Box width and height in cm
  - Is the box a proper rectangle or a parallelogram/diamond?
""")
