"""
calibrate.py - Camera-to-plotter calibration utility.

Place 4 ArUco markers at the corners of your plotter's drawing area,
then run this script to compute and save the perspective transform.

The markers define the plotter coordinate rectangle:
    Marker 0 → (0, 0)        top-left
    Marker 1 → (PAGE_W, 0)   top-right
    Marker 2 → (PAGE_W, PAGE_H)  bottom-right
    Marker 3 → (0, PAGE_H)   bottom-left

Usage:
    python calibrate.py [--camera 0] [--page-w 8] [--page-h 6]

Saves calibration.json with the transform matrix and page dimensions.
If ArUco markers are not available, falls back to manual corner selection
from a saved camera frame.
"""
import cv2
import numpy as np
import json
import argparse
import sys
import os


CALIB_FILE = 'calibration.json'


def find_aruco_corners(frame):
    """Detect ArUco markers and return the 4 corner points ordered by ID 0-3."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Try multiple ArUco dictionaries
    for dict_type in [
        cv2.aruco.DICT_4X4_50,
        cv2.aruco.DICT_5X5_50,
        cv2.aruco.DICT_6X6_50,
    ]:
        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_type)
        params = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(aruco_dict, params)
        corners_list, ids, _ = detector.detectMarkers(gray)

        if ids is not None and len(ids) >= 4:
            # We need markers with IDs 0, 1, 2, 3
            id_to_center = {}
            for i, marker_id in enumerate(ids.flatten()):
                if marker_id in [0, 1, 2, 3]:
                    # Center of the marker
                    c = corners_list[i][0].mean(axis=0)
                    id_to_center[int(marker_id)] = c

            if len(id_to_center) == 4:
                return np.array([
                    id_to_center[0],
                    id_to_center[1],
                    id_to_center[2],
                    id_to_center[3],
                ], dtype=np.float32)

    return None


def manual_corner_selection(frame):
    """
    Fallback: save frame to disk and ask user to provide corner coordinates.
    For headless environments where cv2.imshow is not available.
    """
    fname = 'calibration_frame.png'
    cv2.imwrite(fname, frame)
    print(f'\nSaved camera frame to: {fname}')
    print('Open this image and identify the 4 corners of the plotter drawing area.')
    print('Enter pixel coordinates for each corner.\n')

    corners = []
    labels = [
        'Top-left (plotter origin 0,0)',
        'Top-right (PAGE_W, 0)',
        'Bottom-right (PAGE_W, PAGE_H)',
        'Bottom-left (0, PAGE_H)',
    ]
    for label in labels:
        while True:
            try:
                raw = input(f'  {label} — enter x,y: ')
                x, y = map(float, raw.replace(' ', '').split(','))
                corners.append([x, y])
                break
            except (ValueError, KeyboardInterrupt):
                print('    Invalid format. Enter as: x,y (e.g. 150,80)')

    return np.array(corners, dtype=np.float32)


def compute_transform(camera_corners, page_w, page_h):
    """
    Compute perspective transform from camera pixels to plotter inches.
    Also compute the inverse (plotter inches → camera pixels).
    """
    # Destination points in plotter coordinates (inches)
    plotter_corners = np.array([
        [0, 0],
        [page_w, 0],
        [page_w, page_h],
        [0, page_h],
    ], dtype=np.float32)

    # Camera → plotter (for warping the captured image to plotter space)
    M_cam_to_plotter = cv2.getPerspectiveTransform(camera_corners, plotter_corners)

    # Plotter → camera (for overlaying)
    M_plotter_to_cam = cv2.getPerspectiveTransform(plotter_corners, camera_corners)

    return M_cam_to_plotter, M_plotter_to_cam


def save_calibration(camera_corners, page_w, page_h, camera_id):
    M_c2p, M_p2c = compute_transform(camera_corners, page_w, page_h)
    data = {
        'page_w': page_w,
        'page_h': page_h,
        'camera_id': camera_id,
        'camera_corners': camera_corners.tolist(),
        'cam_to_plotter': M_c2p.tolist(),
        'plotter_to_cam': M_p2c.tolist(),
    }
    with open(CALIB_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'\nCalibration saved to {CALIB_FILE}')
    print(f'  Page size: {page_w}" x {page_h}"')
    print(f'  Camera corners (px): {camera_corners.tolist()}')


def load_calibration(path=CALIB_FILE):
    """Load saved calibration data."""
    with open(path) as f:
        data = json.load(f)
    data['camera_corners'] = np.array(data['camera_corners'], dtype=np.float32)
    data['cam_to_plotter'] = np.array(data['cam_to_plotter'], dtype=np.float64)
    data['plotter_to_cam'] = np.array(data['plotter_to_cam'], dtype=np.float64)
    return data


def main():
    parser = argparse.ArgumentParser(description='Camera-to-plotter calibration')
    parser.add_argument('--camera', type=int, default=0, help='Camera device index')
    parser.add_argument('--page-w', type=float, default=8.0, help='Page width in inches')
    parser.add_argument('--page-h', type=float, default=6.0, help='Page height in inches')
    parser.add_argument('--manual', action='store_true', help='Force manual corner entry')
    args = parser.parse_args()

    print(f'Opening camera {args.camera}...')
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f'ERROR: Cannot open camera {args.camera}')
        sys.exit(1)

    # Grab a few frames to let auto-exposure settle
    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print('ERROR: Failed to capture frame')
        sys.exit(1)

    print(f'Captured frame: {frame.shape[1]}x{frame.shape[0]}')

    corners = None
    if not args.manual:
        print('Searching for ArUco markers (IDs 0-3)...')
        corners = find_aruco_corners(frame)
        if corners is not None:
            print('Found ArUco markers!')
            for i, c in enumerate(corners):
                print(f'  Marker {i}: ({c[0]:.1f}, {c[1]:.1f})')

    if corners is None:
        print('ArUco markers not found — using manual entry.')
        corners = manual_corner_selection(frame)

    save_calibration(corners, args.page_w, args.page_h, args.camera)


if __name__ == '__main__':
    main()
