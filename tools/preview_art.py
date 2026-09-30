#!/usr/bin/env python3
"""Preview the art the way the Game Boy shows it.

Renders every PNG in art/ with the in-game shade mapping (background:
index = shade; sprites: 0 transparent, 1 -> shade 0, 2 -> shade 1,
3 -> shade 3) at 4x with labels, plus mock title, game and game-over
screens assembled from the tiles the way docs/DESIGN.md lays out the
screen. Tile numbers come from src/tiles.h, so the mocks use the same
names as the game code.

Output: sheet_<palette>.png (every art file) and scene_<palette>.png
(the three mock screens side by side).

Each image is written once per palette: grey DMG shades, the green
palette from the contract, and the darker "pea soup" green of an original
DMG screen (where shades 0 and 1 are hard to tell apart, a good stress test).

  tools/preview_art.py                 # writes build/preview/*.png
  tools/preview_art.py --out DIR --scale 3
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art"

PALETTES = {
    "grey": [(0xFF, 0xFF, 0xFF), (0xAA, 0xAA, 0xAA), (0x55, 0x55, 0x55), (0x00, 0x00, 0x00)],
    "green": [(0xE0, 0xF8, 0xD0), (0x88, 0xC0, 0x70), (0x34, 0x68, 0x56), (0x08, 0x18, 0x20)],
    "dmg": [(0x9B, 0xBC, 0x0F), (0x8B, 0xAC, 0x0F), (0x30, 0x62, 0x30), (0x0F, 0x38, 0x0F)],
}
BGP = [0, 1, 2, 3]            # BGP = 0xE4
OBP0 = [None, 0, 1, 3]        # OBP0 = 0xD0, colour 0 is transparent
LABEL_BG = (40, 40, 48)
LABEL_FG = (230, 230, 230)

# Screen layout from docs/DESIGN.md.
PANDA_X, GROUND_Y = 32, 112


def load_indices(name):
    im = Image.open(ART / name)
    assert im.mode == "P", f"{name} is not indexed"
    assert len(im.getpalette()) == 12, f"{name} must have exactly 4 palette entries"
    return im


def tile_names():
    """The #defines in src/tiles.h, e.g. {'T_SKY': 0, ...}."""
    text = (ROOT / "src" / "tiles.h").read_text()
    return {m[1]: int(m[2]) for m in re.finditer(r"#define\s+(\w+)\s+(\d+)", text)}


class Canvas:
    """A 160x144 screen of shade numbers."""

    def __init__(self, w=160, h=144):
        self.w, self.h = w, h
        self.px = [[0] * w for _ in range(h)]

    def tile(self, tiles, index, tx, ty, yoff=0):
        sx, sy = (index % 16) * 8, (index // 16) * 8
        for y in range(8):
            for x in range(8):
                py = ty * 8 + y + yoff
                if 0 <= py < self.h:
                    self.px[py][tx * 8 + x] = BGP[tiles[sx + x, sy + y]]

    def sprite_tile(self, tiles, index, x0, y0):
        """A BG tile drawn as an 8x8 sprite (OBP0, colour 0 transparent), as
        the game does for sprite text such as the title's PRESS START."""
        sx, sy = (index % 16) * 8, (index // 16) * 8
        for y in range(8):
            for x in range(8):
                shade = OBP0[tiles[sx + x, sy + y]]
                if shade is not None and 0 <= x0 + x < self.w and 0 <= y0 + y < self.h:
                    self.px[y0 + y][x0 + x] = shade

    def sprite(self, sheet, frame, fw, fh, x0, y0):
        for y in range(fh):
            for x in range(fw):
                shade = OBP0[sheet[frame * fw + x, y]]
                if shade is not None and 0 <= x0 + x < self.w and 0 <= y0 + y < self.h:
                    self.px[y0 + y][x0 + x] = shade

    def image(self, palette, scale):
        im = Image.new("RGB", (self.w, self.h))
        im.putdata([palette[s] for row in self.px for s in row])
        return im.resize((self.w * scale, self.h * scale), Image.NEAREST)


def text_tiles(t, s, light=False):
    """Tile numbers for a string in the dark or light font."""
    if light:
        base = {"digit": t["T_LFONT_DIGIT"], "alpha": t["T_LFONT_ALPHA"]}
        punct = {" ": t["T_LFONT_SPACE"], "!": t["T_LFONT_BANG"], "-": t["T_LFONT_DASH"],
                 ":": t["T_LFONT_COLON"]}
    else:
        base = {"digit": t["T_FONT_DIGIT"], "alpha": t["T_FONT_ALPHA"]}
        punct = {" ": t["T_SKY"], "!": t["T_FONT_BANG"], "-": t["T_FONT_DASH"],
                 ":": t["T_FONT_COLON"], ".": t["T_FONT_DOT"], "?": t["T_FONT_QUEST"],
                 "'": t["T_FONT_APOS"], "/": t["T_FONT_SLASH"], "x": t["T_FONT_TIMES"]}
    out = []
    for ch in s:
        if ch.isdigit():
            out.append(base["digit"] + int(ch))
        elif "A" <= ch <= "Z":
            out.append(base["alpha"] + ord(ch) - ord("A"))
        else:
            out.append(punct[ch])
    return out


def ground(c, tiles, t):
    for tx in range(20):
        odd = tx & 1
        c.tile(tiles, t["T_GRASS_1"] if odd else t["T_GRASS_0"], tx, 14)
        c.tile(tiles, t["T_GROUND_A1"] if odd else t["T_GROUND_A0"], tx, 15)
        c.tile(tiles, t["T_GROUND_B1"] if odd else t["T_GROUND_B0"], tx, 16)


def window_hud(c, tiles, t, text):
    """The window's bottom HUD row at lines 136-143."""
    row = text_tiles(t, " " + text, light=True)
    for tx in range(20):
        c.tile(tiles, row[tx] if tx < len(row) else t["T_HUD_DARK"], tx, 17)


def cloud(c, tiles, t, tx, ty, yoff=0, small=False):
    """The big 32x16 cloud, or the small 24x16 one."""
    top, bot, n = ((t["T_CLOUD2_TOP"], t["T_CLOUD2_BOT"], 3) if small
                   else (t["T_CLOUD_TOP"], t["T_CLOUD_BOT"], 4))
    for i in range(n):
        c.tile(tiles, top + i, tx + i, ty, yoff)
        c.tile(tiles, bot + i, tx + i, ty + 1, yoff)


def box(c, tiles, t, tx, ty, variant=False):
    tl = t["T_BOX2_TL"] if variant else t["T_BOX_TL"]
    c.tile(tiles, tl, tx, ty)
    c.tile(tiles, tl + 1, tx + 1, ty)
    c.tile(tiles, tl + 16, tx, ty + 1)
    c.tile(tiles, tl + 17, tx + 1, ty + 1)


def game_scene(tiles, panda, t, frame=1):
    """A mid-run screen: HUD score, a big and a small cloud, a 1-box column,
    a double 2-box column, grass, ground, the panda, and the window HUD."""
    c = Canvas()
    for tx, ch in enumerate(text_tiles(t, "12")):
        c.tile(tiles, ch, 1 + tx, 1)
    # Clouds sit on map rows 3-4; the bob (SCY 0-4) raises the sky band's
    # content, here by 2 px.
    cloud(c, tiles, t, 2, 3, yoff=-2)
    cloud(c, tiles, t, 12, 3, yoff=-2, small=True)
    box(c, tiles, t, 9, 12)
    for tx in (14, 16):                    # double column, 2 boxes high
        box(c, tiles, t, tx, 10, variant=True)
        box(c, tiles, t, tx, 12)
    ground(c, tiles, t)
    window_hud(c, tiles, t, "HI 0042")
    c.sprite(panda, frame, 16, 16, PANDA_X, GROUND_Y - 16)
    return c


def title_scene(tiles, logo, panda, t):
    """The title screen: logo in the sky band (map rows 2-5, columns 1-18),
    PRESS START in sprite text (centred, y = 64, as src/hud.c draws it),
    the panda running at PANDA_X and the high score."""
    c = Canvas()
    lw, lh = logo.size
    lpx = logo.load()
    for y in range(lh):
        for x in range(lw):
            c.px[16 + y][8 + x] = BGP[lpx[x, y]]
    prompt = "PRESS START"
    x = (160 - len(prompt) * 8) // 2
    for ch, tile in zip(prompt, text_tiles(t, prompt)):
        if ch != " ":
            c.sprite_tile(tiles, tile, x, 64)
        x += 8
    ground(c, tiles, t)
    window_hud(c, tiles, t, "HI 0042")
    c.sprite(panda, 0, 16, 16, PANDA_X, GROUND_Y - 16)
    return c


def game_over_scene(tiles, panda, fx, t):
    """The end of a run as src/main.c and src/hud.c draw it, once the dead
    panda has sunk out of sight: GAME OVER in sprite text at y = 40 (the sky
    band's plain bottom row, under the clouds), the score as BG text in map
    row 7 and PRESS START in sprite text at y = 72, each centred with a
    blank line between them, over the boxes the run ended at. (The panda
    and fx sheets are unused: nothing of the panda is left on screen.)"""
    c = Canvas()
    for tx, ch in enumerate(text_tiles(t, "17")):
        c.tile(tiles, ch, 1 + tx, 1)
    cloud(c, tiles, t, 5, 3, yoff=-1)
    cloud(c, tiles, t, 16, 3, yoff=-1, small=True)
    for text, y in (("GAME OVER", 40), ("PRESS START", 72)):
        x = (160 - len(text) * 8) // 2
        for ch, tile in zip(text, text_tiles(t, text)):
            if ch != " ":
                c.sprite_tile(tiles, tile, x, y)
            x += 8
    text = "NEW BEST! 17"
    for tx, ch in enumerate(text_tiles(t, text)):
        c.tile(tiles, ch, (84 - len(text) * 4) // 8 + tx, 7)
    box(c, tiles, t, 5, 10, variant=True)  # the 2-box column it ran into
    box(c, tiles, t, 5, 12)
    box(c, tiles, t, 18, 12)
    ground(c, tiles, t)
    window_hud(c, tiles, t, "HI 0017")
    return c


def label(im, text, pad=4):
    """Put a caption strip above an image."""
    font = ImageFont.load_default()
    h = 14
    out = Image.new("RGB", (im.width, im.height + h + pad), LABEL_BG)
    ImageDraw.Draw(out).text((pad, 2), text, fill=LABEL_FG, font=font)
    out.paste(im, (0, h + pad))
    return out


def stack(images, gap=8, horizontal=False):
    if horizontal:
        w = sum(i.width for i in images) + gap * (len(images) - 1)
        h = max(i.height for i in images)
    else:
        w = max(i.width for i in images)
        h = sum(i.height for i in images) + gap * (len(images) - 1)
    out = Image.new("RGB", (w, h), LABEL_BG)
    pos = 0
    for i in images:
        out.paste(i, (pos, 0) if horizontal else (0, pos))
        pos += (i.width if horizontal else i.height) + gap
    return out


def bg_sheet(tiles, palette, scale):
    """bg_tiles.png with tile-index rulers: column 0-15 on top, row base on the left."""
    w, h = tiles.size
    img = Image.new("RGB", (w, h))
    img.putdata([palette[BGP[tiles.getpixel((x, y))]] for y in range(h) for x in range(w)])
    big = img.resize((w * scale, h * scale), Image.NEAREST)
    margin = 28
    out = Image.new("RGB", (big.width + margin, big.height + margin), LABEL_BG)
    out.paste(big, (margin, margin))
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    cell = 8 * scale
    for col in range(16):
        d.text((margin + col * cell + 2, 8), f"+{col}", fill=LABEL_FG, font=font)
    for row in range(h // 8):
        d.text((2, margin + row * cell + 2), str(row * 16), fill=LABEL_FG, font=font)
    for i in range(17):   # faint tile grid
        d.line([(margin + i * cell, margin), (margin + i * cell, out.height)], fill=(255, 0, 255))
    for i in range(h // 8 + 1):
        d.line([(margin, margin + i * cell), (out.width, margin + i * cell)], fill=(255, 0, 255))
    return out


def sprite_sheet(sheet, fw, palette, scale, backdrops=(0, 2)):
    """Sprite frames over the sky and over a dark backdrop (to show which
    pixels are transparent), with frame numbers."""
    w, h = sheet.size
    rows = []
    for back in backdrops:
        img = Image.new("RGB", (w, h))
        data = []
        for y in range(h):
            for x in range(w):
                shade = OBP0[sheet.getpixel((x, y))]
                data.append(palette[back if shade is None else shade])
        img.putdata(data)
        rows.append(img.resize((w * scale, h * scale), Image.NEAREST))
    body = stack(rows, gap=2)
    out = Image.new("RGB", (body.width, body.height + 14), LABEL_BG)
    out.paste(body, (0, 14))
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    for f in range(w // fw):
        d.text((f * fw * scale + 2, 1), str(f), fill=LABEL_FG, font=font)
        if f:
            d.line([(f * fw * scale, 14), (f * fw * scale, out.height)], fill=(255, 0, 255))
    return out


def logo_sheet(logo, palette, scale):
    w, h = logo.size
    img = Image.new("RGB", (w, h))
    img.putdata([palette[BGP[logo.getpixel((x, y))]] for y in range(h) for x in range(w)])
    return img.resize((w * scale, h * scale), Image.NEAREST)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "build" / "preview"))
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--frame", type=int, default=1, help="panda frame in the mock game screen")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tiles = load_indices("bg_tiles.png")
    panda = load_indices("panda.png")
    fx = load_indices("fx.png")
    logo = load_indices("title_logo.png")
    t = tile_names()
    s = args.scale

    game = game_scene(tiles.load(), panda.load(), t, args.frame)
    title = title_scene(tiles.load(), logo, panda.load(), t)
    over = game_over_scene(tiles.load(), panda.load(), fx.load(), t)

    for name, pal in PALETTES.items():
        sheet = stack([
            label(bg_sheet(tiles, pal, s), f"art/bg_tiles.png ({name}) - tile index = row + column"),
            label(sprite_sheet(panda, 16, pal, s), "art/panda.png - frames 0-5 run, 6 jump, 7 double jump, 8 fall, 9 dead"),
            label(sprite_sheet(fx, 8, pal, s), "art/fx.png - dust puff frames 0-3"),
            label(logo_sheet(logo, pal, s), "art/title_logo.png"),
        ])
        sheet.save(out / f"sheet_{name}.png")
        scenes = stack([label(title.image(pal, s), f"mock title screen ({name})"),
                        label(game.image(pal, s), f"mock game screen ({name})"),
                        label(over.image(pal, s), f"mock game over ({name})")], horizontal=True)
        scenes.save(out / f"scene_{name}.png")
    print(f"wrote {out}/sheet_*.png and {out}/scene_*.png ({', '.join(PALETTES)})")


if __name__ == "__main__":
    main()
