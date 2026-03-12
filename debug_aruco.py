"""Comprehensive ArUco detection - try everything."""
import cv2
import numpy as np
import time

# Capture fresh frame
print("Finding camera...")
cap = None
cam_idx = -1
for i in [3, 2, 4, 1, 0, 5]:
    c = cv2.VideoCapture(i)
    if c.isOpened():
        time.sleep(1)
        for _ in range(10):
            c.read()
        ret, test = c.read()
        if ret and test is not None:
            g = cv2.cvtColor(test, cv2.COLOR_BGR2GRAY)
            if g.max() > 10:
                cap = c
                cam_idx = i
                print(f"Using camera {i}")
                break
        c.release()

if cap is None:
    print("No working camera found!")
    exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
time.sleep(3)
for _ in range(60):
    cap.read()
time.sleep(1)

ret, frame = cap.read()
cap.release()

if not ret or frame is None:
    print("ERROR: Failed to capture frame")
    exit(1)

gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
h, w = gray.shape
print(f"Frame: {w}x{h}")
print(f"Gray: min={gray.min()}, max={gray.max()}, mean={gray.mean():.1f}, std={gray.std():.1f}")

if gray.max() < 10:
    print("ERROR: Frame is too dark/black. Camera issue.")
    exit(1)

cv2.imwrite('calibration_frame.png', frame)

# All ArUco dictionaries
DICTS = [
    ("4X4_50", cv2.aruco.DICT_4X4_50),
    ("4X4_100", cv2.aruco.DICT_4X4_100),
    ("4X4_250", cv2.aruco.DICT_4X4_250),
    ("4X4_1000", cv2.aruco.DICT_4X4_1000),
    ("5X5_50", cv2.aruco.DICT_5X5_50),
    ("5X5_100", cv2.aruco.DICT_5X5_100),
    ("6X6_50", cv2.aruco.DICT_6X6_50),
    ("6X6_100", cv2.aruco.DICT_6X6_100),
    ("7X7_50", cv2.aruco.DICT_7X7_50),
    ("ORIGINAL", cv2.aruco.DICT_ARUCO_ORIGINAL),
    ("APT_16h5", cv2.aruco.DICT_APRILTAG_16h5),
    ("APT_25h9", cv2.aruco.DICT_APRILTAG_25h9),
    ("APT_36h10", cv2.aruco.DICT_APRILTAG_36h10),
    ("APT_36h11", cv2.aruco.DICT_APRILTAG_36h11),
]

# Preprocessing
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)
kernel_sharp = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
sharp = cv2.filter2D(gray, -1, kernel_sharp)
scaled2x = cv2.resize(gray, (w*2, h*2), interpolation=cv2.INTER_CUBIC)

IMAGES = [
    ("gray", gray),
    ("clahe", enhanced),
    ("sharp", sharp),
    ("2x", scaled2x),
    ("rot90", cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)),
    ("rot180", cv2.rotate(gray, cv2.ROTATE_180)),
    ("rot270", cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)),
]

print(f"\nTesting {len(DICTS)} dicts x {len(IMAGES)} images = {len(DICTS)*len(IMAGES)} combos\n")

found_any = False
for dict_name, dict_id in DICTS:
    d = cv2.aruco.getPredefinedDictionary(dict_id)
    p = cv2.aruco.DetectorParameters()
    det = cv2.aruco.ArucoDetector(d, p)

    for img_name, img in IMAGES:
        corners, ids, _ = det.detectMarkers(img)
        n = len(ids) if ids is not None else 0
        if n > 0:
            found_any = True
            print(f"*** {dict_name} + {img_name}: {n} markers ***")
            for i, mid in enumerate(ids.flatten()):
                ctr = corners[i][0].mean(axis=0)
                print(f"    ID {mid}: ({ctr[0]:.1f}, {ctr[1]:.1f})")

if not found_any:
    print("No markers with standard params.\nTrying relaxed params on key combos...")
    for dict_name, dict_id in DICTS:
        d = cv2.aruco.getPredefinedDictionary(dict_id)
        p = cv2.aruco.DetectorParameters()
        p.adaptiveThreshWinSizeMin = 3
        p.adaptiveThreshWinSizeMax = 53
        p.adaptiveThreshWinSizeStep = 4
        p.adaptiveThreshConstant = 7
        p.minMarkerPerimeterRate = 0.005
        p.maxMarkerPerimeterRate = 4.0
        p.polygonalApproxAccuracyRate = 0.08
        p.errorCorrectionRate = 0.8
        det = cv2.aruco.ArucoDetector(d, p)

        for img_name, img in IMAGES[:4]:
            corners, ids, _ = det.detectMarkers(img)
            n = len(ids) if ids is not None else 0
            if 1 <= n <= 8:
                found_any = True
                print(f"  Relaxed {dict_name}+{img_name}: {n} markers")
                for i, mid in enumerate(ids.flatten()):
                    ctr = corners[i][0].mean(axis=0)
                    print(f"    ID {mid}: ({ctr[0]:.1f}, {ctr[1]:.1f})")

if not found_any:
    print("\n=== NO MARKERS DETECTED ===")
    print("Possible issues:")
    print("  1. Markers too small relative to camera resolution")
    print("  2. Camera out of focus")
    print("  3. Markers not fully visible in frame")
    print("  4. Poor lighting / glare on paper")
    print("\nPlease check calibration_frame.png")

# Save annotated
annotated = frame.copy()
for x in range(0, w, 100):
    cv2.line(annotated, (x, 0), (x, h), (200, 200, 200), 1)
    cv2.putText(annotated, str(x), (x+2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
for y in range(0, h, 100):
    cv2.line(annotated, (0, y), (w, y), (200, 200, 200), 1)
    cv2.putText(annotated, str(y), (2, y+15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
cv2.imwrite('calibration_frame_annotated.png', annotated)
print("\nImages saved: calibration_frame.png, calibration_frame_annotated.png")
