"""
Renders an actual picture of the ocarina with the holes for a given note
marked, instead of an ASCII table. Saves one PNG per note into diagrams/
and can open it in the default image viewer.

Layout (12-hole Alto C, "Ocarina of Time replica" style):
  - Front view: two columns of 4 holes each.
      Left hand column (top->bottom nearest mouthpiece -> toward the bell):
        L1, L2, L3, L4
      Right hand column (same direction):
        R1, R2, R3, R4
  - Back view (small inset): two thumb holes, TL and TR.
"""
import os

from PIL import Image, ImageDraw, ImageFont

import fingering
from config import app_dir

FINGERING_12_HOLE_ALTO_C = {p: e["holes"] for p, e in fingering.PROFILES["12-hole Alto C"].items()}

OUT_DIR = os.path.join(app_dir(), "diagrams")
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 900, 700
COVERED_COLOR = (40, 40, 40)
OPEN_FILL = (255, 255, 255)
OUTLINE = (20, 20, 20)
BODY_FILL = (235, 220, 190)  # terracotta-ish
HOLE_R = 28


def _font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _draw_hole(draw, cx, cy, covered, label):
    fill = COVERED_COLOR if covered else OPEN_FILL
    draw.ellipse([cx - HOLE_R, cy - HOLE_R, cx + HOLE_R, cy + HOLE_R], fill=fill, outline=OUTLINE, width=3)
    text_color = (255, 255, 255) if covered else (20, 20, 20)
    f = _font(20)
    bbox = draw.textbbox((0, 0), label, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2, cy - th / 2 - bbox[1]), label, fill=text_color, font=f)


def render(note_name: str) -> str:
    covered = FINGERING_12_HOLE_ALTO_C.get(note_name, set())
    img = Image.new("RGB", (W, H), (250, 250, 248))
    draw = ImageDraw.Draw(img)

    title_font = _font(36)
    sub_font = _font(22)
    draw.text((30, 20), f"Ocarina fingering: {note_name}", fill=(10, 10, 10), font=title_font)

    # ---- FRONT VIEW ----
    front_cx = 280
    draw.text((front_cx - 90, 80), "FRONT (facing you)", fill=(90, 90, 90), font=sub_font)

    # body outline: a rounded blob behind the two hole columns
    body_box = [front_cx - 170, 130, front_cx + 170, 560]
    draw.rounded_rectangle(body_box, radius=130, fill=BODY_FILL, outline=OUTLINE, width=4)

    # mouthpiece nub at the top
    draw.ellipse([front_cx - 35, 90, front_cx + 35, 150], fill=(210, 195, 165), outline=OUTLINE, width=3)
    draw.text((front_cx - 55, 60), "mouthpiece", fill=(90, 90, 90), font=_font(16))

    col_left_x = front_cx - 70
    col_right_x = front_cx + 70
    row_ys = [220, 310, 400, 490]
    fingers = ["index", "middle", "ring", "pinky"]
    finger_font = _font(16)

    for i, hole in enumerate(["L1", "L2", "L3", "L4"]):
        _draw_hole(draw, col_left_x, row_ys[i], hole in covered, hole)
        draw.text((col_left_x - 95, row_ys[i] - 8), fingers[i], fill=(110, 110, 110), font=finger_font)
    for i, hole in enumerate(["R1", "R2", "R3", "R4"]):
        _draw_hole(draw, col_right_x, row_ys[i], hole in covered, hole)
        draw.text((col_right_x + 40, row_ys[i] - 8), fingers[i], fill=(110, 110, 110), font=finger_font)

    draw.text((col_left_x - 30, 170), "left hand", fill=(90, 90, 90), font=_font(18))
    draw.text((col_right_x - 35, 170), "right hand", fill=(90, 90, 90), font=_font(18))
    draw.text((front_cx - 60, 570), "(near mouth)", fill=(130, 130, 130), font=_font(16))
    draw.text((front_cx - 50, 500 + 55), "", fill=(0, 0, 0))

    # ---- BACK VIEW (thumb holes) ----
    back_cx = 700
    draw.text((back_cx - 70, 80), "BACK (thumbs)", fill=(90, 90, 90), font=sub_font)
    back_box = [back_cx - 140, 150, back_cx + 140, 420]
    draw.rounded_rectangle(back_box, radius=100, fill=BODY_FILL, outline=OUTLINE, width=4)
    _draw_hole(draw, back_cx - 55, 280, "TL" in covered, "TL")
    _draw_hole(draw, back_cx + 55, 280, "TR" in covered, "TR")
    draw.text((back_cx - 90, 440), "held behind the\ninstrument, thumbs", fill=(130, 130, 130), font=_font(16))

    # ---- LEGEND ----
    legend_y = 610
    _draw_hole(draw, 70, legend_y, True, "")
    draw.text((100, legend_y - 14), "= cover this hole", fill=(20, 20, 20), font=sub_font)
    _draw_hole(draw, 350, legend_y, False, "")
    draw.text((380, legend_y - 14), "= leave this hole open", fill=(20, 20, 20), font=sub_font)

    note_order_hint = {
        "D5": "A-button note (lowest, most holes covered)",
        "F5": "C-Down note",
        "A5": "C-Right note",
        "B5": "C-Left note",
        "D6": "C-Up note (highest, fewest holes covered)",
    }.get(note_name, "")
    draw.text((30, 660), note_order_hint, fill=(90, 90, 90), font=sub_font)

    path = os.path.join(OUT_DIR, f"{note_name}.png")
    img.save(path)
    return path


def open_image(path: str):
    try:
        os.startfile(path)  # Windows
    except Exception as e:
        print(f"  (couldn't auto-open image: {e}; open it yourself: {path})")


def render_and_open(note_name: str):
    # Don't re-render if it already exists -- the previous viewer window may
    # still have the file open, and re-saving on top of an open file fails
    # with "Invalid argument" (seen when calibrate.py retries a note).
    path = os.path.join(OUT_DIR, f"{note_name}.png")
    if not os.path.exists(path):
        path = render(note_name)
    open_image(path)
    return path


if __name__ == "__main__":
    for note in FINGERING_12_HOLE_ALTO_C:
        print("rendering", note, "->", render(note))
