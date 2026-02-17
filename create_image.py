"""
Generate a binary line drawing of a woman's face (black lines on white).
Saves as face_drawing.png.
"""
from PIL import Image, ImageDraw
import math


def arc_pts(cx, cy, rx, ry, start_deg, end_deg, steps=60):
    pts = []
    for i in range(steps + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts


def bezier2(p0, p1, p2, steps=40):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = (1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t**2*p2[0]
        y = (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t**2*p2[1]
        pts.append((x, y))
    return pts


def draw_polyline(draw, pts, width=2):
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i+1]], fill=0, width=width)


def main():
    W, H = 500, 600
    im = Image.new('L', (W, H), 255)
    d = ImageDraw.Draw(im)
    cx, cy = W // 2, H // 2 - 20

    # --- Face outline (oval) ---
    draw_polyline(d, arc_pts(cx, cy, 155, 195, 0, 360, 80), 3)

    # --- Hair - outer ---
    draw_polyline(d, bezier2((cx-80, cy-185), (cx-220, cy-40), (cx-180, cy+130)), 3)
    draw_polyline(d, bezier2((cx+80, cy-185), (cx+220, cy-40), (cx+180, cy+130)), 3)
    draw_polyline(d, bezier2((cx-80, cy-185), (cx, cy-220), (cx+80, cy-185)), 3)
    # Hair - inner strands
    draw_polyline(d, bezier2((cx-60, cy-180), (cx-190, cy-20), (cx-165, cy+110)), 2)
    draw_polyline(d, bezier2((cx+60, cy-180), (cx+190, cy-20), (cx+165, cy+110)), 2)
    draw_polyline(d, bezier2((cx-40, cy-175), (cx, cy-200), (cx+40, cy-175)), 2)
    # Extra hair strands
    draw_polyline(d, bezier2((cx-100, cy-160), (cx-200, cy-80), (cx-175, cy+50)), 2)
    draw_polyline(d, bezier2((cx+100, cy-160), (cx+200, cy-80), (cx+175, cy+50)), 2)

    # --- Left eye ---
    draw_polyline(d, arc_pts(cx-55, cy-25, 32, 15, 0, 360, 40), 2)
    # Left iris
    draw_polyline(d, arc_pts(cx-55, cy-25, 10, 10, 0, 360, 24), 2)
    # Left pupil
    draw_polyline(d, arc_pts(cx-55, cy-25, 4, 4, 0, 360, 16), 2)

    # --- Right eye ---
    draw_polyline(d, arc_pts(cx+55, cy-25, 32, 15, 0, 360, 40), 2)
    # Right iris
    draw_polyline(d, arc_pts(cx+55, cy-25, 10, 10, 0, 360, 24), 2)
    # Right pupil
    draw_polyline(d, arc_pts(cx+55, cy-25, 4, 4, 0, 360, 16), 2)

    # --- Left eyebrow ---
    draw_polyline(d, bezier2((cx-90, cy-50), (cx-55, cy-75), (cx-20, cy-50)), 2)
    # --- Right eyebrow ---
    draw_polyline(d, bezier2((cx+20, cy-50), (cx+55, cy-75), (cx+90, cy-50)), 2)

    # --- Left eyelashes ---
    for xx in [-85, -70, -55, -40, -25]:
        d.line([(cx+xx, cy-40), (cx+xx-2, cy-48)], fill=0, width=2)
    # --- Right eyelashes ---
    for xx in [25, 40, 55, 70, 85]:
        d.line([(cx+xx, cy-40), (cx+xx+2, cy-48)], fill=0, width=2)

    # --- Nose ---
    draw_polyline(d, bezier2((cx, cy-15), (cx+4, cy+30), (cx, cy+45)), 2)
    draw_polyline(d, bezier2((cx-18, cy+40), (cx, cy+55), (cx+18, cy+40)), 2)

    # --- Lips ---
    # Upper lip
    draw_polyline(d, bezier2((cx-45, cy+80), (cx-15, cy+65), (cx, cy+75)), 2)
    draw_polyline(d, bezier2((cx, cy+75), (cx+15, cy+65), (cx+45, cy+80)), 2)
    # Lower lip
    draw_polyline(d, bezier2((cx-45, cy+80), (cx, cy+100), (cx+45, cy+80)), 2)
    # Lip line
    draw_polyline(d, bezier2((cx-35, cy+80), (cx, cy+84), (cx+35, cy+80)), 1)

    # --- Neck ---
    d.line([(cx-28, cy+195), (cx-32, cy+250)], fill=0, width=2)
    d.line([(cx+28, cy+195), (cx+32, cy+250)], fill=0, width=2)

    # --- Neckline / collar hint ---
    draw_polyline(d, bezier2((cx-32, cy+250), (cx, cy+235), (cx+32, cy+250)), 2)

    # --- Small beauty mark ---
    d.ellipse([(cx+35, cy+60), (cx+39, cy+64)], fill=0)

    im.save('face_drawing.png')
    print(f'Saved face_drawing.png ({W}x{H})')


if __name__ == '__main__':
    main()
