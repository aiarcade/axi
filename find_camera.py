#!/usr/bin/env python3
"""Find external USB cameras connected to the system."""

import cv2
import subprocess
import os
import time


def find_cameras():
    """Scan all /dev/video* devices and identify working cameras."""
    video_devs = sorted(
        [f for f in os.listdir('/dev') if f.startswith('video')],
        key=lambda x: int(x.replace('video', ''))
    )

    if not video_devs:
        print('No /dev/video* devices found.')
        return []

    print(f'Found devices: {", ".join("/dev/" + d for d in video_devs)}\n')

    # Get v4l2 info for each device
    for dev in video_devs:
        path = f'/dev/{dev}'
        idx = int(dev.replace('video', ''))
        print(f'--- {path} ---')

        # v4l2-ctl info
        try:
            info = subprocess.run(
                ['v4l2-ctl', '-d', path, '--info'],
                capture_output=True, text=True, timeout=5
            )
            if info.returncode == 0:
                for line in info.stdout.strip().split('\n'):
                    line = line.strip()
                    if any(k in line.lower() for k in ['driver', 'card', 'bus', 'capabilities']):
                        print(f'  {line}')
            else:
                print(f'  v4l2-ctl failed')
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f'  v4l2-ctl not available')

        # Try opening with OpenCV
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            print(f'  OpenCV: cannot open')
            print()
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Warmup
        time.sleep(1)
        for _ in range(10):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            mean = frame.mean()
            status = 'WORKING' if mean > 5 else 'BLACK FRAME'
            print(f'  OpenCV: {status} ({w}x{h}, brightness={mean:.0f})')
        else:
            print(f'  OpenCV: opened but no frame')
        print()

    # Summary: find best external camera
    print('=' * 50)
    print('Auto-detecting best external camera...\n')

    best = None
    for dev in video_devs:
        path = f'/dev/{dev}'
        idx = int(dev.replace('video', ''))

        # Check if it's a "capture" device (not metadata)
        try:
            info = subprocess.run(
                ['v4l2-ctl', '-d', path, '--info'],
                capture_output=True, text=True, timeout=5
            )
            output = info.stdout.lower()
            # Skip metadata devices (they often have even indices)
            if 'metadata' in output:
                continue
        except Exception:
            pass

        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        time.sleep(1)
        for _ in range(10):
            cap.read()
        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None and frame.mean() > 5:
            if best is None:
                best = idx

    if best is not None:
        print(f'  Best camera: /dev/video{best} (index {best})')
        print(f'\n  Use with: python art_completer.py --camera {best}')
        print(f'            python calibrate.py --aruco --camera {best}')
    else:
        print('  No working camera found!')
        print('  Try: reconnect USB camera, then run again.')

    return best


if __name__ == '__main__':
    find_cameras()
