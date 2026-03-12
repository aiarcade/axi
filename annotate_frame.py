"""Annotate calibration_frame.png with a coordinate grid to help identify marker positions."""
import cv2
import numpy as np

frame = cv2.imread('calibration_frame.png')
if frame is None:
    print("ERROR: calibration_frame.png not found")
    exit(1)

h, w = frame.shape[:2]
annotated = frame.copy()

# Draw grid every 100px
for x in range(0, w, 100):
    cv2.line(annotated, (x, 0), (x, h), (200, 200, 200), 1)
    cv2.putText(annotated, str(x), (x+2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
for y in range(0, h, 100):
    cv2.line(annotated, (0, y), (w, y), (200, 200, 200), 1)
    cv2.putText(annotated, str(y), (2, y+15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

# Also mark the rejected ArUco candidates (potential marker positions)
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
p = cv2.aruco.DetectorParameters()
det = cv2.aruco.ArucoDetector(d, p)
_, _, rejected = det.detectMarkers(gray)

for i, r in enumerate(rejected):
    pts = r.reshape(-1, 2).astype(int)
    cx, cy = pts.mean(axis=0)
    perim = cv2.arcLength(r, True)
    side = perim / 4
    # Draw red boxes around rejected candidates
    cv2.polylines(annotated, [pts], True, (0, 0, 255), 2)
    cv2.putText(annotated, f"R{i}:({int(cx)},{int(cy)})", (int(cx)+5, int(cy)-8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

cv2.imwrite('calibration_frame_annotated.png', annotated)
print(f"Saved calibration_frame_annotated.png ({w}x{h})")
print(f"Red boxes show {len(rejected)} rejected ArUco candidates")
print("Open this image to identify the 4 marker/corner positions")
