#!/usr/bin/env python3
"""Draw boundary using XM commands at SLOW speed (1000 steps/sec).
Previous raw test at 1000 steps/sec was accurate.
Boundary XM test at 2000 steps/sec lost ~40% of Y steps."""
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

def xm_move_slow(total_a, total_b, speed=1000):
    """Move using XM commands at specified steps/sec.
    Uses larger chunks with proportionally longer durations."""
    CHUNK = 500  # steps per chunk
    remaining_a = total_a
    remaining_b = total_b
    
    while remaining_a != 0 or remaining_b != 0:
        chunk_a = max(-CHUNK, min(CHUNK, remaining_a))
        chunk_b = max(-CHUNK, min(CHUNK, remaining_b))
        
        max_steps = max(abs(chunk_a), abs(chunk_b), 1)
        dur = int(max_steps * 1000 / speed)  # ms = steps / (steps/sec) * 1000
        dur = max(dur, 10)
        
        cmd(f'XM,{dur},{chunk_a},{chunk_b}')
        
        remaining_a -= chunk_a
        remaining_b -= chunk_b
    
    wait()

cmd('EM,1,1')
cmd('CS')

print("*** Place pen at HOME (ID2, bottom-right) ***")
input("Press Enter when ready...")

X_STEPS = 27330
Y_STEPS = 10001
SPEED = 1000  # steps/sec (same as successful raw test)

print(f"Drawing boundary: {X_STEPS} x {Y_STEPS} steps at {SPEED} steps/sec")
print(f"  = {X_STEPS/2117*2.54:.1f}cm x {Y_STEPS/2117*2.54:.1f}cm")
print(f"  Estimated time: {(2*X_STEPS + 2*Y_STEPS)/SPEED:.0f}s")

cmd('SP,1,500')
time.sleep(0.6)

print("1/4: +X (left)...")
xm_move_slow(X_STEPS, 0, SPEED)
time.sleep(0.3)

print("2/4: +Y (up)...")
xm_move_slow(0, Y_STEPS, SPEED)
time.sleep(0.3)

print("3/4: -X (right)...")
xm_move_slow(-X_STEPS, 0, SPEED)
time.sleep(0.3)

print("4/4: -Y (down)...")
xm_move_slow(0, -Y_STEPS, SPEED)
time.sleep(0.3)

cmd('SP,0,500')
time.sleep(0.5)
cmd('EM,0,0')
ser.close()

print(f"\nDone! Expected: {X_STEPS/2117*2.54:.1f}cm x {Y_STEPS/2117*2.54:.1f}cm")
print("Measure and tell me the dimensions.")
