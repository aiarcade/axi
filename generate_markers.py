"""
generate_markers.py — Generate printable ArUco calibration markers.

Print these and place them at the 4 corners of your plotter's drawing area:
    Marker 0 → top-left      (plotter origin)
    Marker 1 → top-right
    Marker 2 → bottom-right
    Marker 3 → bottom-left

Usage:
    python generate_markers.py
    # Prints 4 marker PNGs + a combined sheet
"""
import cv2
import numpy as np
from PIL import Image


def main():
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_size = 200  # pixels per marker

    markers = []
    for marker_id in range(4):
        img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)
        fname = f'marker_{marker_id}.png'
        cv2.imwrite(fname, img)
        markers.append(img)
        print(f'Saved {fname}')

    # Create a combined sheet with labels
    margin = 40
    label_h = 30
    cell = marker_size + 2 * margin + label_h
    sheet = np.full((cell * 2, cell * 2), 255, dtype=np.uint8)

    positions = [
        (0, 0, '0: Top-Left (origin)'),
        (0, 1, '1: Top-Right'),
        (1, 1, '2: Bottom-Right'),
        (1, 0, '3: Bottom-Left'),
    ]

    for row, col, label in positions:
        y = row * cell + margin
        x = col * cell + margin
        sheet[y:y + marker_size, x:x + marker_size] = markers[int(label[0])]
        # Add label text using cv2
        cv2.putText(sheet, label,
                    (x, y + marker_size + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)

    cv2.imwrite('calibration_markers.png', sheet)
    print('\nSaved calibration_markers.png (print this sheet)')
    print('Cut out markers and tape them to the 4 corners of your drawing area.')


if __name__ == '__main__':
    main()
