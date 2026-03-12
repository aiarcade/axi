"""
calibrate.py - Camera-to-plotter calibration utility.

This script calibrates the camera-to-plotter coordinate mapping using one of
three methods (tried in order):

1. **Plotter-drawn marks** (default, most reliable):
   The plotter draws small '+' marks at 4 known positions on a blank piece of
   paper, the camera captures the paper, and the marks are detected
   automatically via contour analysis.

2. **ArUco marker detection**:
   If --aruco is specified, uses printed ArUco markers (DICT_4X4_50, IDs 0-3).

3. **Manual corner entry**:
   Pass --corners "x0,y0 x1,y1 x2,y2 x3,y3" to provide pixel coordinates
   directly, or use --manual to be prompted interactively.

Usage:
    python calibrate.py --camera 3
    python calibrate.py --camera 3 --page-w 8 --page-h 6
    python calibrate.py --camera 3 --corners "100,50 580,50 580,420 100,420"
    python calibrate.py --camera 3 --aruco

Saves calibration.json with the transform matrix and page dimensions.
"""
import cv2
import numpy as np
import json
import argparse
import sys
import os
import time


CALIB_FILE = 'calibration.json'

# Plotter mark positions — inset from page edges (inches)
MARK_INSET = 0.5
MARK_SIZE = 0.15  # half-size of the '+' mark in inches


def capture_frame(camera_id, width=1280, height=720, warmup_frames=60, warmup_secs=4):
    """Capture a single frame from camera with proper warm-up."""
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f'ERROR: Cannot open camera {camera_id}')
        return None, None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    time.sleep(warmup_secs)
    for _ in range(warmup_frames):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print('ERROR: Failed to capture frame')
        return None, None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.max() == 0:
        print('WARNING: Frame is all black — camera may need more warm-up')
    return frame, gray


def draw_calibration_marks(page_w, page_h):
    """
    Use the AxiDraw plotter to draw small '+' marks at 4 corner positions.
    Uses direct move commands to avoid serial read issues with goto().
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from axi import Device

    marks = [
        (MARK_INSET, MARK_INSET),                           # top-left
        (page_w - MARK_INSET, MARK_INSET),                  # top-right
        (page_w - MARK_INSET, page_h - MARK_INSET),         # bottom-right
        (MARK_INSET, page_h - MARK_INSET),                  # bottom-left
    ]

    print('Drawing calibration marks on plotter...')
    print(f'  Mark positions (inches): {marks}')

    d = Device()
    d.enable_motors()
    d.pen_up()
    time.sleep(0.5)

    # Track position manually to avoid reading serial (which can fail)
    cur_x, cur_y = 0.0, 0.0

    def move_to(x, y):
        nonlocal cur_x, cur_y
        dx = x - cur_x
        dy = y - cur_y
        if abs(dx) > 0.001 or abs(dy) > 0.001:
            d.move(dx, dy)
            d.wait()
            cur_x, cur_y = x, y
            time.sleep(0.1)

    for i, (mx, my) in enumerate(marks):
        # Draw horizontal stroke of '+'
        move_to(mx - MARK_SIZE, my)
        d.pen_down()
        time.sleep(0.15)
        move_to(mx + MARK_SIZE, my)
        d.pen_up()
        time.sleep(0.15)

        # Draw vertical stroke of '+'
        move_to(mx, my - MARK_SIZE)
        d.pen_down()
        time.sleep(0.15)
        move_to(mx, my + MARK_SIZE)
        d.pen_up()
        time.sleep(0.15)
        print(f'  Mark {i} drawn at ({mx}, {my})')

    # Return to home
    move_to(0, 0)
    d.disable_motors()
    print('Calibration marks complete.')
    return marks


def detect_marks(frame, gray, expected_count=4):
    """
    Detect '+' shaped marks in the camera frame.
    Returns list of (x, y) centroids for detected marks, sorted
    top-left, top-right, bottom-right, bottom-left.
    """
    # Enhance contrast
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Adaptive threshold to find dark marks on light paper
    binary = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 21, 10
    )

    # Morphological operations to clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter contours by area and aspect ratio to find mark-sized blobs
    h, w = gray.shape
    min_area = (w * h) * 0.00005   # at least 0.005% of frame
    max_area = (w * h) * 0.01      # at most 1% of frame

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        M = cv2.moments(cnt)
        if M['m00'] == 0:
            continue
        cx = M['m10'] / M['m00']
        cy = M['m01'] / M['m00']
        # Check that contour is roughly compact (not elongated)
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / (min(bw, bh) + 1)
        if aspect < 5:  # '+' marks should be roughly square in bounding box
            candidates.append((cx, cy, area))

    print(f'  Found {len(candidates)} mark candidates (area {min_area:.0f}-{max_area:.0f})')

    if len(candidates) < expected_count:
        # Try a simpler approach — look for small dark blobs
        _, bin2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours2, _ = cv2.findContours(bin2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for cnt in contours2:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue
            M = cv2.moments(cnt)
            if M['m00'] == 0:
                continue
            cx = M['m10'] / M['m00']
            cy = M['m01'] / M['m00']
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = max(bw, bh) / (min(bw, bh) + 1)
            if aspect < 5:
                candidates.append((cx, cy, area))
        print(f'  Otsu fallback: {len(candidates)} candidates')

    if len(candidates) < expected_count:
        return None

    # If more candidates than expected, pick the 4 closest to the image corners
    if len(candidates) > expected_count:
        img_corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        selected = []
        used = set()
        for ic in img_corners:
            best_dist = float('inf')
            best_idx = -1
            for j, (cx, cy, _) in enumerate(candidates):
                if j in used:
                    continue
                dist = np.hypot(cx - ic[0], cy - ic[1])
                if dist < best_dist:
                    best_dist = dist
                    best_idx = j
            if best_idx >= 0:
                used.add(best_idx)
                selected.append(candidates[best_idx])
        candidates = selected

    # Sort: top-left, top-right, bottom-right, bottom-left
    points = np.array([(c[0], c[1]) for c in candidates], dtype=np.float32)
    return sort_corners(points)


def sort_corners(points):
    """Sort 4 points into order: top-left, top-right, bottom-right, bottom-left."""
    # Sum x+y: smallest = top-left, largest = bottom-right
    # Diff x-y: smallest = bottom-left, largest = top-right
    s = points.sum(axis=1)
    d = np.diff(points, axis=1).flatten()

    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = points[np.argmin(s)]   # top-left
    ordered[2] = points[np.argmax(s)]   # bottom-right
    ordered[1] = points[np.argmax(d)]   # top-right
    ordered[3] = points[np.argmin(d)]   # bottom-left

    return ordered


def find_aruco_corners(frame):
    """Detect ArUco markers and return the 4 corner points ordered by ID 0-3."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    for dict_type in [cv2.aruco.DICT_4X4_50, cv2.aruco.DICT_5X5_50, cv2.aruco.DICT_6X6_50]:
        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_type)
        params = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(aruco_dict, params)
        corners_list, ids, _ = detector.detectMarkers(gray)

        if ids is not None and len(ids) >= 2:
            id_to_center = {}
            for i, marker_id in enumerate(ids.flatten()):
                if marker_id in [0, 1, 2, 3]:
                    c = corners_list[i][0].mean(axis=0)
                    id_to_center[int(marker_id)] = c

            if len(id_to_center) == 4:
                return np.array([
                    id_to_center[0], id_to_center[1],
                    id_to_center[2], id_to_center[3],
                ], dtype=np.float32), id_to_center

            # If 3 markers found, infer the 4th from geometry
            if len(id_to_center) == 3:
                missing = [k for k in [0, 1, 2, 3] if k not in id_to_center][0]
                infer_map = {
                    0: (3, 1, 2),  # TL = BL + TR - BR
                    1: (0, 2, 3),  # TR = TL + BR - BL
                    2: (1, 3, 0),  # BR = TR + BL - TL
                    3: (2, 0, 1),  # BL = BR + TL - TR
                }
                a, b, c = infer_map[missing]
                inferred = id_to_center[a] + id_to_center[b] - id_to_center[c]
                id_to_center[missing] = inferred
                print(f'  Inferred marker {missing} at ({inferred[0]:.1f}, {inferred[1]:.1f})')
                return np.array([
                    id_to_center[0], id_to_center[1],
                    id_to_center[2], id_to_center[3],
                ], dtype=np.float32), id_to_center

            # If 2 markers found, infer from known page aspect ratio
            if len(id_to_center) == 2:
                found = sorted(id_to_center.keys())
                print(f'  Found 2 markers: IDs {found}. Inferring remaining...')
                # Use the two known markers + page geometry to estimate all 4
                # Marker positions in plotter space:
                plotter_pos = {0: np.array([0, 0]), 1: np.array([1, 0]),
                               2: np.array([1, 1]), 3: np.array([0, 1])}
                k0, k1 = found
                cam0, cam1 = id_to_center[k0], id_to_center[k1]
                pp0, pp1 = plotter_pos[k0], plotter_pos[k1]

                # Build affine from the two points + orthogonality assumption
                dp = pp1 - pp0
                dc = cam1 - cam0
                # Scale
                scale_p = np.linalg.norm(dp)
                scale_c = np.linalg.norm(dc)
                s = scale_c / scale_p if scale_p > 0 else 1
                # Rotation angle
                angle_c = np.arctan2(dc[1], dc[0])
                angle_p = np.arctan2(dp[1], dp[0])
                theta = angle_c - angle_p
                R = np.array([[np.cos(theta), -np.sin(theta)],
                              [np.sin(theta), np.cos(theta)]])
                for mk in [0, 1, 2, 3]:
                    if mk not in id_to_center:
                        rel = plotter_pos[mk] - pp0
                        cam_pt = cam0 + s * R @ rel
                        id_to_center[mk] = cam_pt
                        print(f'  Inferred marker {mk} at ({cam_pt[0]:.1f}, {cam_pt[1]:.1f})')
                return np.array([
                    id_to_center[0], id_to_center[1],
                    id_to_center[2], id_to_center[3],
                ], dtype=np.float32), id_to_center

    return None, None


def compute_transform(camera_corners, page_w, page_h):
    """Compute perspective transform from camera pixels to plotter inches.

    Plotter coordinate system:
        (0,0) = home = bottom-right corner (marker ID 2)
        +X = leftward along bottom edge (toward marker ID 3)
        +Y = upward toward top edge (toward marker ID 1)

    Camera corners order: [ID0/TL, ID1/TR, ID2/BR, ID3/BL]
    Plotter mapping:
        ID0 (TL) -> (page_w, page_h)  (far corner)
        ID1 (TR) -> (0, page_h)       (top, home-X side)
        ID2 (BR) -> (0, 0)            (home / origin)
        ID3 (BL) -> (page_w, 0)       (bottom, far-X side)
    """
    plotter_corners = np.array([
        [page_w, page_h],  # ID0 TL -> far corner
        [0, page_h],       # ID1 TR -> top, near home
        [0, 0],            # ID2 BR -> home (origin)
        [page_w, 0],       # ID3 BL -> bottom, far X
    ], dtype=np.float32)

    M_cam_to_plotter = cv2.getPerspectiveTransform(camera_corners, plotter_corners)
    M_plotter_to_cam = cv2.getPerspectiveTransform(plotter_corners, camera_corners)

    return M_cam_to_plotter, M_plotter_to_cam


def save_calibration(camera_corners, page_w, page_h, camera_id,
                     mark_positions=None):
    """Save calibration data to JSON."""
    M_c2p, M_p2c = compute_transform(camera_corners, page_w, page_h)
    data = {
        'page_w': page_w,
        'page_h': page_h,
        'camera_id': camera_id,
        'camera_corners': camera_corners.tolist(),
        'cam_to_plotter': M_c2p.tolist(),
        'plotter_to_cam': M_p2c.tolist(),
    }
    if mark_positions:
        data['mark_positions'] = mark_positions
    with open(CALIB_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'\nCalibration saved to {CALIB_FILE}')
    print(f'  Page size: {page_w}" x {page_h}"')
    print(f'  Camera corners (px): {camera_corners.tolist()}')


def draw_overlay(frame, camera_corners, page_w, page_h, plotter_to_cam, output_path='calibration_overlay.png'):
    """Draw the plotter area boundary and inch grid on the camera frame."""
    overlay = frame.copy()
    h, w = overlay.shape[:2]
    pts = camera_corners.astype(int)

    # Green boundary
    for i in range(4):
        p1 = tuple(pts[i])
        p2 = tuple(pts[(i + 1) % 4])
        cv2.line(overlay, p1, p2, (0, 255, 0), 3)

    # Label corners
    labels = ['TL (0,0)', f'TR ({page_w},0)',
              f'BR ({page_w},{page_h})', f'BL (0,{page_h})']
    offsets = [(-80, -15), (10, -15), (10, 25), (-80, 25)]
    for i, (label, pt) in enumerate(zip(labels, pts)):
        cv2.circle(overlay, tuple(pt), 8, (0, 0, 255), -1)
        tx = pt[0] + offsets[i][0]
        ty = pt[1] + offsets[i][1]
        cv2.putText(overlay, label, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # Inch grid
    M_p2c = np.array(plotter_to_cam, dtype=np.float64)
    for y_inch in range(int(page_h) + 1):
        line_pts = []
        for xf in np.linspace(0, page_w, 50):
            pt = np.array([[[xf, float(y_inch)]]], dtype=np.float32)
            px = cv2.perspectiveTransform(pt, M_p2c)[0][0].astype(int)
            line_pts.append(px)
        for j in range(len(line_pts) - 1):
            cv2.line(overlay, tuple(line_pts[j]), tuple(line_pts[j + 1]),
                     (255, 200, 0), 1)
    for x_inch in range(int(page_w) + 1):
        line_pts = []
        for yf in np.linspace(0, page_h, 50):
            pt = np.array([[[float(x_inch), yf]]], dtype=np.float32)
            px = cv2.perspectiveTransform(pt, M_p2c)[0][0].astype(int)
            line_pts.append(px)
        for j in range(len(line_pts) - 1):
            cv2.line(overlay, tuple(line_pts[j]), tuple(line_pts[j + 1]),
                     (255, 200, 0), 1)

    cv2.putText(overlay, f'Plotter Area ({page_w}x{page_h} inches)',
                (w // 2 - 180, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (255, 255, 255), 2)

    cv2.imwrite(output_path, overlay)
    print(f'  Overlay image: {output_path}')


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
    parser.add_argument('--page-w', type=float, default=15.35, help='Page width in inches')
    parser.add_argument('--page-h', type=float, default=7.09, help='Page height in inches')
    parser.add_argument('--aruco', action='store_true',
                        help='Use ArUco markers instead of plotter-drawn marks')
    parser.add_argument('--manual', action='store_true', help='Force manual corner entry')
    parser.add_argument('--skip-draw', action='store_true',
                        help='Skip drawing marks (assume they are already on paper)')
    parser.add_argument('--corners', type=str, default=None,
                        help='Provide corners directly: "x0,y0 x1,y1 x2,y2 x3,y3" '
                             '(top-left top-right bottom-right bottom-left in pixels)')
    args = parser.parse_args()

    # ── Method 1: Direct corner coordinates ──
    if args.corners:
        try:
            parts = args.corners.strip().split()
            assert len(parts) == 4, 'Need exactly 4 corner points'
            corners = []
            for p in parts:
                x, y = map(float, p.split(','))
                corners.append([x, y])
            corners = np.array(corners, dtype=np.float32)
        except Exception as e:
            print(f'ERROR parsing --corners: {e}')
            sys.exit(1)

        # Capture reference frame
        frame, _ = capture_frame(args.camera)
        if frame is not None:
            cv2.imwrite('calibration_frame.png', frame)

        for i, c in enumerate(corners):
            print(f'  Corner {i}: ({c[0]:.1f}, {c[1]:.1f})')
        save_calibration(corners, args.page_w, args.page_h, args.camera)
        return

    # ── Method 2: ArUco markers ──
    if args.aruco:
        print(f'Capturing frame from camera {args.camera}...')
        frame, gray = capture_frame(args.camera)
        if frame is None:
            sys.exit(1)
        cv2.imwrite('calibration_frame.png', frame)
        print(f'Frame: {frame.shape[1]}x{frame.shape[0]}')

        print('Searching for ArUco markers (IDs 0-3)...')
        corners, id_map = find_aruco_corners(frame)
        if corners is not None:
            print('Found ArUco markers!')
            for i, c in enumerate(corners):
                print(f'  Marker {i}: ({c[0]:.1f}, {c[1]:.1f})')
            save_calibration(corners, args.page_w, args.page_h, args.camera)
            # Draw overlay
            _, M_p2c = compute_transform(corners, args.page_w, args.page_h)
            draw_overlay(frame, corners, args.page_w, args.page_h,
                         M_p2c, 'calibration_overlay.png')
        else:
            print('ERROR: ArUco markers not found.')
            print('  Make sure markers IDs 0-3 (DICT_4X4_50) are visible to camera.')
            sys.exit(1)
        return

    # ── Method 3: Plotter-drawn marks (default, most reliable) ──
    print('=== Plotter-Drawn Marks Calibration ===')
    print(f'Page: {args.page_w}" x {args.page_h}"')
    print(f'Camera: index {args.camera}')
    print()

    # Step 1: Draw marks (unless --skip-draw)
    mark_positions = [
        (MARK_INSET, MARK_INSET),
        (args.page_w - MARK_INSET, MARK_INSET),
        (args.page_w - MARK_INSET, args.page_h - MARK_INSET),
        (MARK_INSET, args.page_h - MARK_INSET),
    ]

    if not args.skip_draw:
        print('Step 1: Place a blank sheet of paper on the plotter.')
        print('        The plotter will draw 4 small + marks at the corners.')
        print('        Make sure a pen is loaded.\n')
        draw_calibration_marks(args.page_w, args.page_h)
        print()
        # Give user a moment to check
        time.sleep(1)

    # Step 2: Capture frame
    print('Step 2: Capturing camera frame...')
    frame, gray = capture_frame(args.camera)
    if frame is None:
        sys.exit(1)
    cv2.imwrite('calibration_frame.png', frame)
    print(f'  Frame: {frame.shape[1]}x{frame.shape[0]}')
    print(f'  Saved: calibration_frame.png')

    # Step 3: Detect marks
    print('\nStep 3: Detecting calibration marks...')
    corners = detect_marks(frame, gray)

    if corners is not None:
        print('Marks detected successfully!')
        for i, c in enumerate(corners):
            print(f'  Mark {i}: pixel ({c[0]:.1f}, {c[1]:.1f}) '
                  f'→ plotter ({mark_positions[i][0]}", {mark_positions[i][1]}")')

        # For plotter-drawn marks, the camera corners map to mark positions
        # (not page edges), so we compute the transform from marks
        plotter_pts = np.array(mark_positions, dtype=np.float32)
        M_c2p = cv2.getPerspectiveTransform(corners, plotter_pts)
        M_p2c = cv2.getPerspectiveTransform(plotter_pts, corners)

        # Compute what the page corners would be in camera space
        page_corners_plotter = np.array([
            [0, 0], [args.page_w, 0],
            [args.page_w, args.page_h], [0, args.page_h]
        ], dtype=np.float32).reshape(-1, 1, 2)
        page_corners_cam = cv2.perspectiveTransform(page_corners_plotter, M_p2c)
        page_corners_cam = page_corners_cam.reshape(-1, 2)

        # Save using page corner coordinates for consistency
        save_calibration(
            page_corners_cam, args.page_w, args.page_h, args.camera,
            mark_positions=[(m[0], m[1]) for m in mark_positions]
        )

        # Save debug image with detected marks
        debug = frame.copy()
        for i, c in enumerate(corners):
            cv2.circle(debug, (int(c[0]), int(c[1])), 10, (0, 255, 0), 2)
            cv2.putText(debug, f'{i}', (int(c[0]) + 15, int(c[1]) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        # Draw page boundary
        for i in range(4):
            p1 = tuple(page_corners_cam[i].astype(int))
            p2 = tuple(page_corners_cam[(i + 1) % 4].astype(int))
            cv2.line(debug, p1, p2, (255, 0, 0), 2)
        cv2.imwrite('debug_calibration.png', debug)
        print('  Debug image: debug_calibration.png')

        # Draw overlay with grid
        draw_overlay(frame, page_corners_cam, args.page_w, args.page_h,
                     M_p2c.tolist(), 'calibration_overlay.png')
    else:
        print('\nAutomatic mark detection failed.')
        print('Possible causes:')
        print('  - Marks not visible to camera (check camera position)')
        print('  - Lighting too bright/dark')
        print('  - Paper not in frame')
        print('\nFallback: Open calibration_frame.png and identify the 4 mark')
        print('positions, then re-run with:')
        print(f'  python calibrate.py --camera {args.camera} '
              f'--corners "x0,y0 x1,y1 x2,y2 x3,y3"')
        sys.exit(1)


if __name__ == '__main__':
    main()
