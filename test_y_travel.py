#!/usr/bin/env python3
"""Test Y-axis maximum travel distance.
Moves Y in 2cm increments, pausing each time."""
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

cmd('EM,1,1')
cmd('CS')

print("*** Place pen at HOME (ID2, bottom-right) ***")
print("*** Keep pen DOWN so you can see the travel ***")
input("Press Enter when ready...")

cmd('SP,1,500')
time.sleep(0.6)

# 2cm = ~1667 steps (at 5000 steps/6cm = 833 steps/cm)
STEPS_PER_CM = 5000 / 6.0  # = 833.3
CHUNK_CM = 2.0
CHUNK_STEPS = int(STEPS_PER_CM * CHUNK_CM)
CHUNK_MS = 2000  # 2 seconds per chunk (slow)

total_cm = 0
total_steps = 0

for i in range(8):  # 8 x 2cm = 16cm max
    print(f"  Moving +{CHUNK_CM}cm (Y only)... chunk {i+1}/8")
    
    # Move in small XM commands
    remaining = CHUNK_STEPS
    while remaining > 0:
        chunk = min(200, remaining)
        dur = max(10, int(CHUNK_MS * chunk / CHUNK_STEPS))
        cmd(f'XM,{dur},0,{chunk}')
        remaining -= chunk
    wait()
    
    total_steps += CHUNK_STEPS
    total_cm += CHUNK_CM
    print(f"    Total Y travel so far: {total_cm:.0f}cm ({total_steps} steps)")
    
    resp = input(f"    Did the pen actually move? How far total from start? (or 'stop' if stuck): ")
    if resp.lower().startswith('stop'):
        print(f"  Y axis maxed out at ~{total_cm}cm")
        break

# Return home
print("Returning to origin...")
cmd('SP,0,500')
time.sleep(0.5)

remaining = total_steps
while remaining > 0:
    chunk = min(200, remaining)
    dur = max(10, int(2000 * chunk / CHUNK_STEPS))
    cmd(f'XM,{dur},0,{-chunk}')
    remaining -= chunk
wait()

cmd('EM,0,0')
ser.close()
print("Done.")
