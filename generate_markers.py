"""
generate_markers.py — Generate printable ArUco calibration markers on A4 paper.

Produces a single A4-sized PNG (300 DPI) with 4 markers placed at the corners
and labels + cut-line instructions. Print at 100% scale on A4 paper, cut out
the markers, and place them at the 4 corners of your plotter's drawing area.

    Marker 0 → top-left      (plotter origin)
    Marker 1 → top-right
    Marker 2 → bottom-right
    Marker 3 → bottom-left

Usage:
    python generate_markers.py
"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def main():
    # --- A4 at 300 DPI ---
    DPI = 300
    A4_W_MM, A4_H_MM = 210, 297
    A4_W = int(A4_W_MM / 25.4 * DPI)   # 2480 px
    A4_H = int(A4_H_MM / 25.4 * DPI)   # 3508 px

    # Marker size: ~30mm (about 1.2 inches) — easily detectable
    MARKER_MM = 30
    MARKER_PX = int(MARKER_MM / 25.4 * DPI)  # ~354 px

    # Generate ArUco markers
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    markers = []
    for marker_id in range(4):
        img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, MARKER_PX)
        markers.append(img)

    # Create A4 canvas (white)
    page = Image.new('L', (A4_W, A4_H), 255)
    draw = ImageDraw.Draw(page)

    # Margin from page edge
    PAGE_MARGIN = int(15 / 25.4 * DPI)  # 15mm from edges

    # Marker positions (x, y of top-left corner of each marker)
    positions = [
        (PAGE_MARGIN, PAGE_MARGIN),                                  # 0: top-left
        (A4_W - PAGE_MARGIN - MARKER_PX, PAGE_MARGIN),              # 1: top-right
        (A4_W - PAGE_MARGIN - MARKER_PX, A4_H - PAGE_MARGIN - MARKER_PX),  # 2: bottom-right
        (PAGE_MARGIN, A4_H - PAGE_MARGIN - MARKER_PX),              # 3: bottom-left
    ]

    labels = [
        'Marker 0: TOP-LEFT (plotter origin)',
        'Marker 1: TOP-RIGHT',
        'Marker 2: BOTTOM-RIGHT',
        'Marker 3: BOTTOM-LEFT',
    ]

    label_offsets = [
        (0, MARKER_PX + 15),    # below marker
        (0, MARKER_PX + 15),    # below marker
        (0, -25),               # above marker
        (0, -25),               # above marker
    ]

    for i, (mx, my) in enumerate(positions):
        # Paste marker
        marker_pil = Image.fromarray(markers[i])
        page.paste(marker_pil, (mx, my))

        # Draw dashed cut-line border around marker (5mm padding)
        pad = int(5 / 25.4 * DPI)
        bx1, by1 = mx - pad, my - pad
        bx2, by2 = mx + MARKER_PX + pad, my + MARKER_PX + pad
        # Draw dashed rectangle
        dash_len = 15
        for edge_start, edge_end, horizontal in [
            ((bx1, by1), (bx2, by1), True),
            ((bx2, by1), (bx2, by2), False),
            ((bx2, by2), (bx1, by2), True),
            ((bx1, by2), (bx1, by1), False),
        ]:
            sx, sy = edge_start
            ex, ey = edge_end
            length = abs(ex - sx) if horizontal else abs(ey - sy)
            step_dir = 1 if (ex - sx + ey - sy) > 0 else -1
            pos = 0
            while pos < length:
                seg = min(dash_len, length - pos)
                if horizontal:
                    x1d = sx + step_dir * pos
                    x2d = sx + step_dir * (pos + seg)
                    draw.line([(x1d, sy), (x2d, sy)], fill=160, width=2)
                else:
                    y1d = sy + step_dir * pos
                    y2d = sy + step_dir * (pos + seg)
                    draw.line([(sx, y1d), (sx, y2d)], fill=160, width=2)
                pos += dash_len * 2

        # Label
        lx = mx + label_offsets[i][0]
        ly = my + label_offsets[i][1]
        draw.text((lx, ly), labels[i], fill=0)

    # Title in the center
    title_y = A4_H // 2 - 80
    draw.text((A4_W // 2 - 200, title_y),
              'AxiDraw Calibration Markers', fill=0)
    draw.text((A4_W // 2 - 280, title_y + 30),
              'Print at 100% scale on A4. Cut along dashed lines.', fill=0)
    draw.text((A4_W // 2 - 300, title_y + 55),
              'Place each marker at the corresponding corner of the', fill=0)
    draw.text((A4_W // 2 - 280, title_y + 80),
              'plotter drawing area, black side facing the camera.', fill=0)

    # Scissors icon hint
    draw.text((A4_W // 2 - 100, title_y + 120),
              '--- cut here ---', fill=120)

    # Save
    page.save('calibration_markers_a4.png', dpi=(DPI, DPI))
    print(f'Saved calibration_markers_a4.png')
    print(f'  A4 size: {A4_W}x{A4_H} px at {DPI} DPI')
    print(f'  Marker size: {MARKER_MM}mm ({MARKER_PX}px)')
    print(f'\nPrint this file at 100% scale on A4 paper.')
    print('Cut out the 4 markers and place them at the corners of your drawing area.')

    # Also save individual markers
    for i in range(4):
        fname = f'marker_{i}.png'
        cv2.imwrite(fname, markers[i])
    print('Also saved individual marker_0.png through marker_3.png')


if __name__ == '__main__':
    main()
