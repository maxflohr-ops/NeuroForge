"""compose the bandersnatch gang sheet — 22 x 60 in @300dpi, explicit
layout: the notice poster leads, left-chest columns ride beside it,
bonus pieces fill every paid-for gap. outputs the print file (no
marks) + a labeled preview on dark."""
from PIL import Image, ImageDraw

DPI = 300
W_IN, H_IN = 22, 60
OUT = "out/"

def load(name, width_in=None):
    im = Image.open(OUT + name).convert("RGBA")
    if width_in:
        w = int(width_in * DPI)
        im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
    return im

notice     = load("bandersnatch-notice-bone.png")          # 12 x 16
seal_b     = load("bandersnatch-seal-bone.png")            # 10 x 10
seal_s     = load("bandersnatch-seal-silver.png")
seal_i     = load("bandersnatch-seal-ink.png")
card12     = load("bandersnatch-cardinal-red.png", 12)     # 12 x 9.4
lc_b       = load("bandersnatch-seal-bone.png", 3.5)
lc_i       = load("bandersnatch-seal-ink.png", 3.5)
lc_s       = load("bandersnatch-seal-silver.png", 3.5)
lc_c       = load("bandersnatch-cardinal-red.png", 3.5)    # 3.5 x 2.8
wm_b       = load("bandersnatch-wordmark-bone.png")        # 12.2 x 2.6
wm_i       = load("bandersnatch-wordmark-ink.png")
tag_b      = load("bandersnatch-tagline-bone.png")         # 12.3 x 1.4
neck_b     = load("bandersnatch-tagline-bone.png", 4)      # 4 x 0.4
neck_i     = load("bandersnatch-tagline-ink.png", 4)

# (name, image, x_in, y_in) — inches from top-left
P = [
    # row 1 · the notice leads; left-chest columns beside it
    ("THE NOTICE 12x16",     notice, 0.5,  0.5),
    ("lc seal bone",         lc_b,  13.0,  0.5),
    ("lc seal bone",         lc_b,  13.0,  4.5),
    ("lc seal ink",          lc_i,  13.0,  8.5),
    ("lc seal silver",       lc_s,  13.0, 12.5),
    ("lc cardinal",          lc_c,  17.0,  0.5),
    ("lc cardinal",          lc_c,  17.0,  3.8),
    ("lc cardinal +",        lc_c,  17.0,  7.1),
    ("lc cardinal +",        lc_c,  17.0, 10.4),
    # row 2 · full-back seals
    ("seal bone 10in",       seal_b, 0.5, 17.0),
    ("seal silver 10in",     seal_s, 11.0, 17.0),
    # row 3 · ink seal + a bonus bone seal in the free width
    ("seal ink 10in",        seal_i, 0.5, 27.5),
    ("seal bone 10in +",     seal_b, 11.0, 27.5),
    # row 4 · the cardinal back print + bonus chest pieces
    ("cardinal 12in",        card12, 0.5, 38.0),
    ("lc seal bone +",       lc_b,  13.0, 38.0),
    ("lc seal ink +",        lc_i,  13.0, 42.0),
    ("lc cardinal +",        lc_c,  17.0, 38.0),
    ("lc cardinal +",        lc_c,  17.0, 41.3),
    # rows 5-7 · wordmarks with neck tags in the margins
    ("wordmark bone",        wm_b,   0.5, 48.0),
    ("neck tag bone",        neck_b, 13.2, 48.0),
    ("neck tag ink",         neck_i, 17.7, 48.0),
    ("wordmark bone",        wm_b,   0.5, 51.1),
    ("neck tag bone",        neck_b, 13.2, 51.1),
    ("neck tag ink",         neck_i, 17.7, 51.1),
    ("wordmark ink",         wm_i,   0.5, 54.2),
    ("neck tag bone",        neck_b, 13.2, 54.2),
    ("neck tag bone",        neck_b, 17.7, 54.2),
    # row 8 · across-shoulders tagline
    ("tagline bone 12in",    tag_b,  0.5, 57.3),
    ("neck tag ink",         neck_i, 13.3, 57.3),
    ("neck tag bone",        neck_b, 17.8, 57.3),
]

W, H = W_IN * DPI, H_IN * DPI
sheet = Image.new("RGBA", (W, H), (0, 0, 0, 0))
for name, im, x, y in P:
    px, py = int(x * DPI), int(y * DPI)
    assert px + im.width <= W and py + im.height <= H, (name, x, y)
    sheet.alpha_composite(im, (px, py))
sheet.save("bandersnatch-gang-sheet-22x60.png", dpi=(DPI, DPI))

prev = Image.new("RGBA", (W, H), (16, 14, 12, 255))
prev.alpha_composite(sheet)
d = ImageDraw.Draw(prev)
for name, im, x, y in P:
    px, py = int(x * DPI), int(y * DPI)
    d.rectangle([px, py, px + im.width, py + im.height], outline=(142, 137, 127, 110), width=3)
    d.text((px + 12, py + 8), name, fill=(230, 224, 211, 255))
prev = prev.resize((W // 6, H // 6))
prev.convert("RGB").save("gang-sheet-preview.png")

bottom = max(y * DPI + im.height for _, im, x, y in P) / DPI
print("sheet 22 x 60 in · %d pieces · content ends at %.1f in" % (len(P), bottom))
