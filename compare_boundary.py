#!/usr/bin/env python3
"""
compare_boundary.py — Compare the drawn boundary vs expected boundary.

Place ArUco markers at the 4 corners of the DRAWN rectangle, then run this.
It detects the markers, maps them through the calibration transform to plotter
coordinates, and compares with the expected page dimensions.

Usage:
    python compare_boundary.py --camera 1
    python compare_boundary.py --image photo.png
"""
import cv2
import numpy as np
import sys
import os
import time
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CALIB_FILE = 'calibration.json'


def capture_frame(camera_id, warmup_frames=60, warmup_secs=4):
    """Capture a single frame from the USB camera."""
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open camera {camera_id}')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    time.sleep(warmup_secs)
    for _ in range(warmup_frames):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None or frame.mean() < 5:
        raise RuntimeError('Failed to capture frame')
    return frame


def find_aruco_corners(frame):
    """Detect ArUco markers, return 4 corners ordered by ID 0-3."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners_list, ids, _ = detector.detectMarkers(gray)

    if ids is None:
        return None, {}

    id_to_center = {}
    for i, marker_id in enumerate(ids.flatten()):
        if marker_id in [0, 1, 2, 3]:
            c = corners_list[i][0].mean(axis=0)
            id_to_center[int(marker_id)] = c

    found = sorted(id_to_center.keys())
    print(f'  Found markers: {found}')

    if len(id_to_center) == 3:
        missing = [k for k in [0, 1, 2, 3] if k not in id_to_center][0]
        infer_map = {
            0: (3, 1, 2),
            1: (0, 2, 3),
            2: (1, 3, 0),
            3: (2, 0, 1),
        }
        a, b, c = infer_map[missing]
        inferred = id_to_center[a] + id_to_center[b] - id_to_center[c]
        id_to_center[missing] = inferred
        print(f'  Inferred marker {missing} at ({inferred[0]:.1f}, {inferred[1]:.1f})')
    elif len(id_to_center) < 3:
        return None, id_to_center

    corners = np.array([
        id_to_center[0], id_to_center[1],
        id_to_center[2], id_to_center[3],
    ], dtype=np.float32)
    return corners, id_to_center


def cam_to_plotter(cam_pt, M):
    """Map a camera pixel point to plotter inches using the calibration transform."""
    pt = np.array([cam_pt[0], cam_pt[1], 1.0])
    result = M @ pt
    result /= result[2]
    return result[0], result[1]


def dist(p1, p2):
    return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


def main():
    parser = argparse.ArgumentParser(description='Compare drawn boundary vs expected')
    parser.add_argument('--camera', type=int, default=None,
                        help='Camera index (default: from calibration)')
    parser.add_argument('--image', type=str, default=None,
                        help='Use existing image file instead of camera')
    args = parser.parse_args()

    # Load calibration
    if not os.path.exists(CALIB_FILE):
        print(f'ERROR: {CALIB_FILE} not found. Run calibrate.py first.')
        sys.exit(1)
    with open(CALIB_FILE) as f:
        cal = json.load(f)
    M = np.array(cal['cam_to_plotter'], dtype=np.float64)
    page_w = cal['page_w']
    page_h = cal['page_h']
    orig_cam_corners = np.array(cal['camera_corners'], dtype=np.float32)

    camera_id = args.camera if args.camera is not None else cal.get('camera_id', 0)

    # Capture or load
    if args.image:
        print(f'Loading: {args.image}')
        frame = cv2.imread(args.image)
        if frame is None:
            print(f'ERROR: Cannot read {args.image}')
            sys.exit(1)
    else:
        print(f'Capturing from camera {camera_id}...')
        print('  Place markers at the 4 corners of the DRAWN rectangle.')
        input('  Press Enter when ready...')
        frame = capture_frame(camera_id)

    print(f'  Image: {frame.shape[1]}x{frame.shape[0]}')
    cv2.imwrite('compare_capture.png', frame)

    # Detect markers at drawn boundary corners
    print('\n1. Detecting ArUco markers at drawn boundary corners...')
    drawn_cam, id_map = find_aruco_corners(frame)
    if drawn_cam is None:
        print('  ERROR: Need at least 3 markers!')
        sys.exit(1)

    # Map drawn boundary markers to plotter coordinates
    print('\n2. Mapping to plotter coordinates...')
    drawn_plotter = []
    labels = ['ID0', 'ID1', 'ID2', 'ID3']
    for i in range(4):
        px, py = cam_to_plotter(drawn_cam[i], M)
        drawn_plotter.append((px, py))
        print(f'  {labels[i]}: camera ({drawn_cam[i][0]:.1f}, {drawn_cam[i][1]:.1f})'
              f' -> plotter ({px:.2f}", {py:.2f}")')

    # Also show where original calibration corners map (should be exact)
    print('\n   Original calibration corners (for reference):')
    for i in range(4):
        px, py = cam_to_plotter(orig_cam_corners[i], M)
        print(f'  {labels[i]}: camera ({orig_cam_corners[i][0]:.1f}, {orig_cam_corners[i][1]:.1f})'
              f' -> plotter ({px:.2f}", {py:.2f}")')

    # Expected plotter coords (from calibrate.py compute_transform mapping):
    # ID0 -> (page_w, page_h), ID1 -> (0, page_h), ID2 -> (0, 0), ID3 -> (page_w, 0)
    expected = {
        0: (page_w, page_h),
        1: (0, page_h),
        2: (0, 0),
        3: (page_w, 0),
    }

    # Compare
    print(f'\n3. Comparison (expected page: {page_w}" x {page_h}"):')
    print('=' * 60)

    for i in range(4):
        ex = expected[i]
        ac = drawn_plotter[i]
        dx = ac[0] - ex[0]
        dy = ac[1] - ex[1]
        d = np.sqrt(dx**2 + dy**2)
        print(f'  {labels[i]}: expected ({ex[0]:.2f}", {ex[1]:.2f}")'
              f' actual ({ac[0]:.2f}", {ac[1]:.2f}")'
              f'  error: dx={dx:+.2f}" dy={dy:+.2f}" dist={d:.2f}"')

    # Drawn rectangle dimensions in plotter space
    drawn_w_bot = dist(drawn_plotter[3], drawn_plotter[2])
    drawn_h_right = dist(drawn_plotter[2], drawn_plotter[1])
    drawn_w_top = dist(drawn_plotter[0], drawn_plotter[1])
    drawn_h_left = dist(drawn_plotter[0], drawn_plotter[3])

    print(f'\n  Expected size: {page_w:.2f}" x {page_h:.2f}"')
    print(f'  Drawn size:')
    print(f'    Bottom edge (ID2-ID3): {drawn_w_bot:.2f}" ({drawn_w_bot/page_w*100:.1f}%)')
    print(f'    Top edge    (ID1-ID0): {drawn_w_top:.2f}" ({drawn_w_top/page_w*100:.1f}%)')
    print(f'    Right edge  (ID2-ID1): {drawn_h_right:.2f}" ({drawn_h_right/page_h*100:.1f}%)')
    print(f'    Left edge   (ID3-ID0): {drawn_h_left:.2f}" ({drawn_h_left/page_h*100:.1f}%)')

    # Center
    drawn_cx = np.mean([p[0] for p in drawn_plotter])
    drawn_cy = np.mean([p[1] for p in drawn_plotter])
    exp_cx = page_w / 2
    exp_cy = page_h / 2
    print(f'\n  Expected center: ({exp_cx:.2f}", {exp_cy:.2f}")')
    print(f'  Drawn center:    ({drawn_cx:.2f}", {drawn_cy:.2f}")')
    print(f'  Center offset:   dx={drawn_cx-exp_cx:+.2f}", dy={drawn_cy-exp_cy:+.2f}"')

    # Diagnosis
    avg_w = (drawn_w_bot + drawn_w_top) / 2
    avg_h = (drawn_h_right + drawn_h_left) / 2
    w_pct = avg_w / page_w * 100
    h_pct = avg_h / page_h * 100

    print(f'\n4. Diagnosis:')
    if abs(w_pct - 100) < 3 and abs(h_pct - 100) < 3:
        print(f'  Size is within 3% — GOOD!')
    else:
        print(f'  Width:  {w_pct:.1f}% of expected ({avg_w:.2f}" vs {page_w:.2f}")')
        print(f'  Height: {h_pct:.1f}% of expected ({avg_h:.2f}" vs {page_h:.2f}")')
        if abs(w_pct - h_pct) < 3:
            scale = (w_pct + h_pct) / 200
            current_steps = 2065
            needed = int(current_steps / scale)
            print(f'  Uniform scale error. Suggested STEPS_PER_INCH: {needed} (current: {current_steps})')
        else:
            print(f'  Non-uniform scale — X and Y axes have different step rates.')
            current_steps = 2065
            needed_x = int(current_steps / (w_pct / 100))
            needed_y = int(current_steps / (h_pct / 100))
            print(f'  Suggested X steps: {needed_x}, Y steps: {needed_y}')

    center_err = np.sqrt((drawn_cx-exp_cx)**2 + (drawn_cy-exp_cy)**2)
    if center_err > 0.3:
        print(f'  Center offset: {center_err:.2f}" — pen start position was misaligned.')

    # Visualization
    vis = frame.copy()
    # Original calibration boundary in green
    for i in range(4):
        p1 = tuple(orig_cam_corners[i].astype(int))
        p2 = tuple(orig_cam_corners[(i+1) % 4].astype(int))
        cv2.line(vis, p1, p2, (0, 255, 0), 2)
        cv2.putText(vis, f'cal-{labels[i]}', (p1[0]+5, p1[1]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    # Drawn boundary markers in red
    for i in range(4):
        p1 = tuple(drawn_cam[i].astype(int))
        p2 = tuple(drawn_cam[(i+1) % 4].astype(int))
        cv2.line(vis, p1, p2, (0, 0, 255), 2)
        cv2.circle(vis, tuple(drawn_cam[i].astype(int)), 8, (0, 0, 255), -1)
        cv2.putText(vis, f'drawn-{labels[i]}', (p1[0]+5, p1[1]+15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    cv2.putText(vis, 'GREEN = calibration (expected)', (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(vis, 'RED = drawn boundary (actual)', (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imwrite('compare_result.png', vis)
    print(f'\n  Saved: compare_result.png (green=expected, red=drawn)')


if __name__ == '__main__':
    main()
