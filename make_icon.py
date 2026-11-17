"""Draws the app icon (an ocarina) -> icon.ico (multi-size) and icon.png.

Run once after changing the design: python make_icon.py
"""
from PIL import Image, ImageDraw

SIZE = 1024                      # draw big, scale down for smooth edges
BODY = (64, 112, 196)            # deep blue
BODY_HI = (118, 164, 232)
OUTLINE = (24, 44, 92)
HOLE = (16, 26, 54)
SHINE = (255, 255, 255, 90)


def draw(size=SIZE):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size / 1024
    # mouthpiece: a short rounded stub on the upper left
    d.rounded_rectangle([110 * s, 330 * s, 400 * s, 470 * s], radius=60 * s,
                        fill=BODY, outline=OUTLINE, width=int(26 * s))
    # body: a big rounded "sweet potato" egg, tilted by drawing it as an ellipse
    body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.ellipse([250 * s, 230 * s, 950 * s, 800 * s], fill=BODY, outline=OUTLINE, width=int(30 * s))
    bd.ellipse([330 * s, 280 * s, 760 * s, 520 * s], fill=BODY_HI)          # top highlight
    bd.ellipse([250 * s + 30 * s, 230 * s + 30 * s, 950 * s - 30 * s, 800 * s - 30 * s],
               outline=OUTLINE, width=0)
    body = body.rotate(-18, resample=Image.BICUBIC, center=(600 * s, 515 * s))
    im.alpha_composite(body)
    d = ImageDraw.Draw(im)
    # cover the joint so the stub looks attached
    d.rounded_rectangle([300 * s, 352 * s, 420 * s, 448 * s], radius=40 * s, fill=BODY)
    # finger holes: two rows
    r = 46 * s
    for cx, cy in [(520, 470), (650, 510), (780, 560), (560, 640), (690, 680)]:
        d.ellipse([cx * s - r, cy * s - r, cx * s + r, cy * s + r], fill=HOLE)
    # windway slot on the mouthpiece
    d.rounded_rectangle([140 * s, 385 * s, 250 * s, 415 * s], radius=14 * s, fill=HOLE)
    # small shine
    shine = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shine).ellipse([430 * s, 320 * s, 560 * s, 380 * s], fill=SHINE)
    im.alpha_composite(shine)
    return im


if __name__ == "__main__":
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save("icon.png")
    big.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote icon.ico and icon.png")
