"""compose the bandersnatch gang sheet — 22in wide @300dpi (6600px),
shelf-packed rows, 0.5in spacing, transparent ground. outputs the
print file (no marks) + a labeled preview on dark for checking."""
from PIL import Image, ImageDraw

DPI = 300
W = 22 * DPI                      # 6600
GAP = int(0.5 * DPI)              # 150
OUT = "out/"

def load(name, width_in=None):
    im = Image.open(OUT + name).convert("RGBA")
    if width_in:
        w = int(width_in * DPI)
        im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
    return im

# the order: what one sheet yields (fronts, backs, chests, necks)
items = [
    ("wordmark bone 12in",  load("bandersnatch-wordmark-bone.png")),
    ("wordmark bone 12in",  load("bandersnatch-wordmark-bone.png")),
    ("wordmark ink 12in",   load("bandersnatch-wordmark-ink.png")),
    ("seal bone 10in",      load("bandersnatch-seal-bone.png")),
    ("seal silver 10in",    load("bandersnatch-seal-silver.png")),
    ("seal ink 10in",       load("bandersnatch-seal-ink.png")),
    ("cardinal 12in",       load("bandersnatch-cardinal-red.png", 12)),
    ("lc seal bone 3.5in",  load("bandersnatch-seal-bone.png", 3.5)),
    ("lc seal bone 3.5in",  load("bandersnatch-seal-bone.png", 3.5)),
    ("lc seal ink 3.5in",   load("bandersnatch-seal-ink.png", 3.5)),
    ("lc seal silver 3.5in",load("bandersnatch-seal-silver.png", 3.5)),
    ("lc cardinal 3.5in",   load("bandersnatch-cardinal-red.png", 3.5)),
    ("lc cardinal 3.5in",   load("bandersnatch-cardinal-red.png", 3.5)),
    ("tagline bone 12in",   load("bandersnatch-tagline-bone.png")),
    ("neck tag bone 4in",   load("bandersnatch-tagline-bone.png", 4)),
    ("neck tag bone 4in",   load("bandersnatch-tagline-bone.png", 4)),
    ("neck tag ink 4in",    load("bandersnatch-tagline-ink.png", 4)),
]

# shelf pack: tallest first, fill rows left to right
items.sort(key=lambda t: t[1].height, reverse=True)
placed, x, y, row_h = [], GAP, GAP, 0
for name, im in items:
    if x + im.width + GAP > W:
        x = GAP
        y += row_h + GAP
        row_h = 0
    placed.append((name, im, x, y))
    x += im.width + GAP
    row_h = max(row_h, im.height)
H = y + row_h + GAP

# snap to the vendor's 12in length increments
inc = 12 * DPI
H_snap = ((H + inc - 1) // inc) * inc

sheet = Image.new("RGBA", (W, H_snap), (0, 0, 0, 0))
for name, im, px, py in placed:
    sheet.alpha_composite(im, (px, py))
sheet.save("bandersnatch-gang-sheet-22x%d.png" % (H_snap // DPI), dpi=(DPI, DPI))

# labeled preview on the field dark, quarter scale
prev = Image.new("RGBA", (W, H_snap), (16, 14, 12, 255))
prev.alpha_composite(sheet)
d = ImageDraw.Draw(prev)
for name, im, px, py in placed:
    d.rectangle([px, py, px + im.width, py + im.height], outline=(142, 137, 127, 120), width=3)
    d.text((px + 12, py + 8), name, fill=(230, 224, 211, 255))
prev = prev.resize((W // 5, H_snap // 5))
prev.convert("RGB").save("gang-sheet-preview.png")

print("sheet: 22 x %d in  (%d x %d px)  used %.1f in of length" % (H_snap // DPI, W, H_snap, H / DPI))
for name, im, px, py in placed:
    print("  %-22s at %4.1f, %4.1f in  (%.1f x %.1f in)" % (name, px / DPI, py / DPI, im.width / DPI, im.height / DPI))
