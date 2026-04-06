#!/usr/bin/env python3
"""Draw boundary using RAW XM commands (not SM).
XM confirmed to be Cartesian: Motor1=X(left), Motor2=Y(up)."""
import sys, time
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
    print("ERROR: No EBB device found"); sys.exit(1)

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

def xm_move(total_steps_a, total_steps_b, steps_per_chunk=200, chunk_ms=100):
    """Move using multiple XM commands (XM has limited step count per call).
    Break long moves into chunks."""
    remaining_a = total_steps_a
    remaining_b = total_steps_b
    
    while remaining_a != 0 or remaining_b != 0:
        # Calculate this chunk
        chunk_a = max(-steps_per_chunk, min(steps_per_chunk, remaining_a))
        chunk_b = max(-steps_per_chunk, min(steps_per_chunk, remaining_b))
        
        # Scale duration proportionally if one axis has fewer steps
        max_steps = max(abs(chunk_a), abs(chunk_b), 1)
        dur = int(chunk_ms * max_steps / steps_per_chunk)
        dur = max(dur, 10)
        
        cmd(f'XM,{dur},{chunk_a},{chunk_b}')
        
        remaining_a -= chunk_a
        remaining_b -= chunk_b
    
    wait()

cmd('EM,1,1')
cmd('CS')

print("*** Place pen at HOME (ID2, bottom-right) ***")
input("Press Enter when ready...")

# Page: 12.91" x 4.7244"
# 2117 steps/inch
X_STEPS = 27330
Y_STEPS = 10001

print(f"Drawing boundary: {X_STEPS} x {Y_STEPS} steps")
print(f"  = {X_STEPS/2117*2.54:.1f}cm x {Y_STEPS/2117*2.54:.1f}cm")

cmd('SP,1,500')
time.sleep(0.6)

# Segment 1: +X (left)
print("1/4: +X (left)...")
xm_move(X_STEPS, 0)
time.sleep(0.2)

# Segment 2: +Y (up)
print("2/4: +Y (up)...")
xm_move(0, Y_STEPS)
time.sleep(0.2)

# Segment 3: -X (right)
print("3/4: -X (right)...")
xm_move(-X_STEPS, 0)
time.sleep(0.2)

# Segment 4: -Y (down)
print("4/4: -Y (down)...")
xm_move(0, -Y_STEPS)
time.sleep(0.2)

cmd('SP,0,500')
time.sleep(0.5)
cmd('EM,0,0')
ser.close()

print(f"\nDone! Expected: 32.8cm x 12.0cm rectangle")
print("Measure and tell me the dimensions.")
