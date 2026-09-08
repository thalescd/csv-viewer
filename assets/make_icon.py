"""Generates assets/icon.ico (the app/executable icon).

Kept as a script so the icon can be regenerated or tweaked reproducibly.
Run it only when you want to change the icon:

    pip install pillow
    python assets/make_icon.py

The generated icon.ico is committed, so building the app does not need Pillow.
"""
import os

from PIL import Image, ImageDraw

ACCENT = (47, 111, 237)        # same blue as the app's cell highlight
HEADER = (28, 71, 158)         # darker blue for the table's header row
PAPER = (255, 255, 255)
GRID = (176, 196, 222)

SIZE = 256
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw_icon(size=SIZE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256  # scale factor so all measurements below are in 256-px units

    def px(v):
        return round(v * s)

    # rounded blue background
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=px(52), fill=ACCENT)

    # the "spreadsheet": a white sheet with a dark header row and grid lines
    left, top, right, bottom = px(40), px(48), px(216), px(208)
    d.rectangle([left, top, right, bottom], fill=PAPER)

    header_bottom = top + px(38)
    d.rectangle([left, top, right, header_bottom], fill=HEADER)

    # column dividers
    for frac in (1 / 3, 2 / 3):
        x = left + round((right - left) * frac)
        d.line([x, top, x, bottom], fill=GRID, width=px(6))

    # row dividers (below the header)
    rows = 3
    for i in range(1, rows):
        y = header_bottom + round((bottom - header_bottom) * i / rows)
        d.line([left, y, right, y], fill=GRID, width=px(6))

    return img


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    base = draw_icon(SIZE)

    ico_path = os.path.join(out_dir, "icon.ico")
    base.save(ico_path, format="ICO", sizes=ICON_SIZES)
    print("wrote", ico_path)

    # a PNG preview, handy for the README or just eyeballing the result
    png_path = os.path.join(out_dir, "icon.png")
    base.save(png_path, format="PNG")
    print("wrote", png_path)


if __name__ == "__main__":
    main()
