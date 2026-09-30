#!/usr/bin/env python3
"""Hand-pixelled art for PandaJump GB: writes art/*.png from the text grids below.

Every image is drawn here as text, one character per pixel, so the art can be
reviewed and diffed like code. After editing a grid, run `make art` (or this
script), then `python3 tools/preview_art.py` to see the result with the
in-game shades and in a mock game screen.

Output format (docs/DESIGN.md): indexed PNGs with exactly 4 palette entries,
where the palette index is the Game Boy colour number. File names, sizes and
tile positions are fixed by the contract; the script checks them.

The grid characters name the shade you see on screen, so the same character
looks the same in every image:

  Background tiles and the title logo (BGP = 0xE4, index = shade):
    '.'  index 0, shade 0 (sky, lightest)
    '+'  index 1, shade 1
    'x'  index 2, shade 2
    '#'  index 3, shade 3 (darkest)

  Sprites (OBP0 = 0xD0):
    '.'  index 0, transparent
    'o'  index 1, shade 0 (white fur)
    '+'  index 2, shade 1 (grey shading)
    '#'  index 3, shade 3 (black fur and outline)
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art"

# RGB is only for viewing the PNGs; the game uses the index.
PALETTE = [(0xE0, 0xF8, 0xD0), (0x88, 0xC0, 0x70), (0x34, 0x68, 0x56), (0x08, 0x18, 0x20)]
BG_KEY = {".": 0, "+": 1, "x": 2, "#": 3}
SPRITE_KEY = {".": 0, "o": 1, "+": 2, "#": 3}


# --------------------------------------------------------------------------
# Helpers

def grid(text, width, height):
    """Split a triple-quoted grid into rows and check its size."""
    rows = [line.strip() for line in text.strip().splitlines()]
    assert len(rows) == height, f"expected {height} rows, got {len(rows)}:\n{text}"
    for row in rows:
        assert len(row) == width, f"expected {width} columns, got {len(row)}: {row!r}"
    return rows


def new_image(w, h):
    im = Image.new("P", (w, h), 0)
    im.putpalette([c for rgb in PALETTE for c in rgb])
    return im


def draw(im, x0, y0, rows, key):
    px = im.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            px[x0 + x, y0 + y] = key[ch]


def tile_xy(index):
    """Top-left pixel of a tile in the 16-tiles-wide bg_tiles.png."""
    return (index % 16) * 8, (index // 16) * 8


def save(im, name, size):
    assert im.size == size, (name, im.size)
    assert len(im.getpalette()) == 4 * 3, name  # exactly 4 entries
    im.save(ART / name)


def check_outlined(rows, what):
    """Sprites: every white or grey pixel must be closed in by black, so the
    panda never bleeds into the (white) sky."""
    h, w = len(rows), len(rows[0])
    for y in range(h):
        for x in range(w):
            if rows[y][x] in "o+":
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    edge = not (0 <= nx < w and 0 <= ny < h)
                    assert not edge and rows[ny][nx] != ".", f"{what}: open outline at x={x} y={y}"


# --------------------------------------------------------------------------
# art/panda.png: ten 16x16 frames, facing right. The metasprite is placed by
# its top-left corner; the feet rest on row 15 in the running frames, so the
# game draws the sprite at y = GROUND_Y - 16 when the panda is on the ground.
#
# The face, like the original's: two solid black eye patches that droop
# down and outward (the near one with a white glint at its upper inner
# side, the far one running into the head's outline) and a black nose
# below between them. The dead pose (frame 9) has X eyes instead.

PANDA = [
    # 0: run, contact. Legs spread, near arm swung back. Body down 1 px.
    """
    ................
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ..#############.
    .####oooooo+#...
    .##.#+oooo++#...
    ....#########...
    ...###...###....
    ..###.....###...
    """,
    # 1: run, passing. Front foot planted, back leg swinging through, arm down.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ....###########.
    ....#o##oooo#...
    ....#o###ooo#...
    ....#+oooo++#...
    ....#########...
    ....###.###.....
    ........###.....
    """,
    # 2: run, push-off. Back foot pushing, front knee up, arm forward.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ....###########.
    ....#ooooooo####
    ....#oooooo+##..
    ....#+oooo++#...
    ....#########...
    ...###..#####...
    ..###...........
    """,
    # 3: run, contact (other leg forward), arm forward. Body down 1 px.
    """
    ................
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ....###########.
    ....#ooooooo####
    ....#+ooooo+##..
    ....#########...
    ...###...###....
    ..###.....###...
    """,
    # 4: run, passing. Back foot planted, front leg swinging through, arm down.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ....###########.
    ....#o##oooo#...
    ....#o###ooo#...
    ....#+oooo++#...
    ....#########...
    ....###.###.....
    ....###.........
    """,
    # 5: run, push-off, arm swinging back.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ..#############.
    .####oooooo+#...
    .##.#ooooo++#...
    ....#+oooo++#...
    ....#########...
    ...###..#####...
    ..###...........
    """,
    # 6: jump (rising). Arm thrown up, legs trailing.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ##.##ooooooooo##
    ##.#ooooooooooo#
    ##.#ooooo##oo###
    .#.#ooo##o#oo###
    .#.#ooo##ooooo##
    .##.#+ooooo#oo#.
    ..#############.
    ....#ooooooo#...
    ....#oooooo+#...
    ....#+oooo++#...
    ....#########...
    ...#####........
    ..###.##........
    """,
    # 7: double jump (tucked). Knees pulled up to the chest, arm wrapped
    # round them (the white gap between arm and knees shows the hug).
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#ooooo##oo###
    ...#ooo##o#oo###
    ...#ooo##ooooo##
    ....#+ooooo#oo#.
    ...############.
    ..#oooooo####...
    ..#ooooo#oooo##.
    ..#+ooo########.
    ...#++o######...
    ....########....
    ................
    """,
    # 8: falling. Arm raised beside the head (a 2 px wide paw that stops
    # below the ears, so it doesn't read as a stick), legs dangling apart.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    .#.##ooooooooo##
    ##.#ooooooooooo#
    ##.#ooooo##oo###
    ##.#ooo##o#oo###
    ##.#ooo##ooooo##
    .##.#+ooooo#oo#.
    ..#############.
    ....#ooooooo#...
    ....#+oooo++#...
    ....#########...
    ....##....##....
    ....##....##....
    ....##....##....
    """,
    # 9: dead / hurt. X eyes, arms flung out, legs apart.
    """
    ....##......##..
    ...############.
    ...###oooooo###.
    ...##ooooooooo##
    ...#ooooooooooo#
    ...#oooo#o#oo#o#
    ...#ooooo#ooo###
    ...#oooo#o#oo#o#
    ....#+ooooo#oo#.
    ..#############.
    .##.#ooooooo####
    ....#oooooo+#...
    ....#+oooo++#...
    ....#########...
    ....###..###....
    ...###....###...
    """,
]


def panda():
    im = new_image(160, 16)
    for f, text in enumerate(PANDA):
        rows = grid(text, 16, 16)
        check_outlined(rows, f"panda frame {f}")
        draw(im, f * 16, 0, rows, SPRITE_KEY)
    save(im, "panda.png", (160, 16))


# --------------------------------------------------------------------------
# art/fx.png: four 8x8 dust-puff frames, drawn under the panda's feet on the
# double jump and on landing: small, bigger, biggest, fading. Soft grey
# outlines (no black) so the puff reads as dust, not as an object.

FX = [
    # 0: small, just kicked up
    """
    ........
    ........
    ........
    ........
    ...++...
    ..+oo+..
    ..+oo+..
    ...++...
    """,
    # 1: bigger, two puffs
    """
    ........
    ........
    ........
    ..++....
    .+oo+++.
    +ooo+oo+
    +oooooo+
    .++++++.
    """,
    # 2: biggest, rising
    """
    ........
    .++..++.
    +oo++oo+
    +oooooo+
    +oooooo+
    .+oooo+.
    ..++++..
    ........
    """,
    # 3: fading into wisps
    """
    .++.....
    +oo+..+.
    .++..+o+
    ......+.
    ..+.....
    .+o+....
    ..+.....
    ........
    """,
]


def fx():
    im = new_image(32, 8)
    for f, text in enumerate(FX):
        rows = grid(text, 8, 8)
        draw(im, f * 8, 0, rows, SPRITE_KEY)
    save(im, "fx.png", (32, 8))


# --------------------------------------------------------------------------
# art/bg_tiles.png: 128x64, 16x8 tiles. Tile positions are fixed by the
# contract (docs/DESIGN.md, src/tiles.h).

SKY = "\n".join(["........"] * 8)
SOLID_BLACK = "\n".join(["########"] * 8)

# Box, 16x16 at tiles 2,3 / 18,19: a dark crate. Black outline, a shade 2
# plank frame with shade 1 nail heads, and a shade 3 panel crossed by a
# diagonal brace. The outline keeps boxes apart when they stand side by side.
BOX = """
################
#xxxxxxxxxxxxxx#
#x+xxxxxxxxxx+x#
#xx##########xx#
#xx#######xxxxx#
#xx######xx##xx#
#xx#####xx###xx#
#xx####xx####xx#
#xx###xx#####xx#
#xx##xx######xx#
#xx#xx#######xx#
#xxxxx#######xx#
#xx##########xx#
#x+xxxxxxxxxx+x#
#xxxxxxxxxxxxxx#
################
"""

# Box variant, 16x16 at tiles 4,5 / 20,21: the upper box of a 2-box column.
# The same crate with an X brace, so a stack reads as two separate crates.
BOX2 = """
################
#xxxxxxxxxxxxxx#
#x+xxxxxxxxxx+x#
#xxxx######xxxx#
#xx#xx####xx#xx#
#xx##xx##xx##xx#
#xx###xxxx###xx#
#xx####xx####xx#
#xx####xx####xx#
#xx###xxxx###xx#
#xx##xx##xx##xx#
#xx#xx####xx#xx#
#xxxx######xxxx#
#x+xxxxxxxxxx+x#
#xxxxxxxxxxxxxx#
################
"""

# Ground: one 16x16 block of cobbles, split into rows A (tiles 8,9, map row
# 15) and B (tiles 24,25, map row 16). The block wraps in both directions, so
# A over B, B over A and each row repeated sideways are all seamless. The
# stones are staggered so the joints never line up into stripes. Its last
# line is solid mortar (shade 3), which also frames the window HUD below.
ROCKS = """
xx###++xxx###++x
xxx#+xxxxxx#+xxx
xxx#xxxxxxx#xxxx
xx###xxxxxx#xxxx
########xx###xxx
#++xxx##########
+xxxxxx##++xxx##
xxxxxxx#+xxxxxx#
#xxxxx##xxxxxxx#
#########xxxxx##
###++xx#########
x#+xxxxxx###++xx
x#xxxxxxxx#+xxxx
x#xxxxxxxx#xxxxx
###xxxxxx###xxxx
################
"""

# Grass top, 16x8 at tiles 6,7 (map row 14). The walking surface GROUND_Y is
# the top edge of this row, so the grass starts on its very first line.
# Rounded tufts hang over a shadow line; the last line is solid mortar like
# the last line of the rock block, so grass over row A joins up the same way
# B over A does.
GRASS = """
++++++++++++++++
++++++++++++++++
++++x++++++++x++
+x+++++++x++++++
#++++##+++#++++#
##++####+###++##
x####xx###xx##xx
################
"""

# Cloud, 32x16 at tiles 10-13 / 26-29: sky-coloured puff with a shade 1
# outline and a little shade 1 shading underneath.
CLOUD = """
................................
.............+++++..............
...........++.....++............
..........+.........+.+++.......
.........+...........+...++.....
.....+++.+.................+....
....+...++..................+...
...+.........................+..
..+..........................+..
..+...........................+.
..+...........................+.
...+.....++.........++........+.
....++.....++++++++++....++..+..
......+++++++++++++++++++++++...
................................
................................
"""

# Window HUD background: solid shade 3, the same as the ground's mortar.
HUD_DARK = SOLID_BLACK

# Font: 7x7 glyphs in the top-left of each 8x8 tile (the right column and
# bottom row stay empty, which spaces the letters). Vertical strokes are
# 2 px wide so the text stays solid on a real DMG screen.
FONT = {
    "0": """
        .#####.
        ##...##
        ##...##
        ##...##
        ##...##
        ##...##
        .#####.
        """,
    "1": """
        ..##...
        .###...
        ..##...
        ..##...
        ..##...
        ..##...
        .####..
        """,
    "2": """
        .#####.
        ##...##
        .....##
        ..####.
        .##....
        ##.....
        #######
        """,
    "3": """
        .#####.
        ##...##
        .....##
        ...###.
        .....##
        ##...##
        .#####.
        """,
    "4": """
        ...###.
        ..####.
        .##.##.
        ##..##.
        #######
        ....##.
        ....##.
        """,
    "5": """
        #######
        ##.....
        ######.
        .....##
        .....##
        ##...##
        .#####.
        """,
    "6": """
        ..####.
        .##....
        ##.....
        ######.
        ##...##
        ##...##
        .#####.
        """,
    "7": """
        #######
        ##...##
        ....##.
        ...##..
        ..##...
        ..##...
        ..##...
        """,
    "8": """
        .#####.
        ##...##
        ##...##
        .#####.
        ##...##
        ##...##
        .#####.
        """,
    "9": """
        .#####.
        ##...##
        ##...##
        .######
        .....##
        ....##.
        .####..
        """,
    "A": """
        ..###..
        .##.##.
        ##...##
        ##...##
        #######
        ##...##
        ##...##
        """,
    "B": """
        ######.
        ##...##
        ##...##
        ######.
        ##...##
        ##...##
        ######.
        """,
    "C": """
        .#####.
        ##...##
        ##.....
        ##.....
        ##.....
        ##...##
        .#####.
        """,
    "D": """
        #####..
        ##..##.
        ##...##
        ##...##
        ##...##
        ##..##.
        #####..
        """,
    "E": """
        #######
        ##.....
        ##.....
        ######.
        ##.....
        ##.....
        #######
        """,
    "F": """
        #######
        ##.....
        ##.....
        ######.
        ##.....
        ##.....
        ##.....
        """,
    "G": """
        .#####.
        ##...##
        ##.....
        ##.####
        ##...##
        ##...##
        .#####.
        """,
    "H": """
        ##...##
        ##...##
        ##...##
        #######
        ##...##
        ##...##
        ##...##
        """,
    "I": """
        ######.
        ..##...
        ..##...
        ..##...
        ..##...
        ..##...
        ######.
        """,
    "J": """
        .....##
        .....##
        .....##
        .....##
        ##...##
        ##...##
        .#####.
        """,
    "K": """
        ##...##
        ##..##.
        ##.##..
        ####...
        ##.##..
        ##..##.
        ##...##
        """,
    "L": """
        ##.....
        ##.....
        ##.....
        ##.....
        ##.....
        ##.....
        #######
        """,
    "M": """
        ##...##
        ###.###
        #######
        ##.#.##
        ##...##
        ##...##
        ##...##
        """,
    "N": """
        ##...##
        ###..##
        ####.##
        ##.####
        ##..###
        ##...##
        ##...##
        """,
    "O": """
        .#####.
        ##...##
        ##...##
        ##...##
        ##...##
        ##...##
        .#####.
        """,
    "P": """
        ######.
        ##...##
        ##...##
        ######.
        ##.....
        ##.....
        ##.....
        """,
    "Q": """
        .#####.
        ##...##
        ##...##
        ##...##
        ##.#.##
        ##..##.
        .###.##
        """,
    "R": """
        ######.
        ##...##
        ##...##
        ######.
        ##.##..
        ##..##.
        ##...##
        """,
    "S": """
        .#####.
        ##...##
        ##.....
        .#####.
        .....##
        ##...##
        .#####.
        """,
    "T": """
        ######.
        ..##...
        ..##...
        ..##...
        ..##...
        ..##...
        ..##...
        """,
    "U": """
        ##...##
        ##...##
        ##...##
        ##...##
        ##...##
        ##...##
        .#####.
        """,
    "V": """
        ##...##
        ##...##
        ##...##
        ##...##
        .##.##.
        ..###..
        ...#...
        """,
    "W": """
        ##...##
        ##...##
        ##...##
        ##.#.##
        #######
        ###.###
        ##...##
        """,
    "X": """
        ##...##
        ##...##
        .##.##.
        ..###..
        .##.##.
        ##...##
        ##...##
        """,
    "Y": """
        ##..##.
        ##..##.
        ##..##.
        .####..
        ..##...
        ..##...
        ..##...
        """,
    "Z": """
        #######
        .....##
        ....##.
        ...##..
        ..##...
        .##....
        #######
        """,
    "!": """
        ..##...
        ..##...
        ..##...
        ..##...
        ..##...
        .......
        ..##...
        """,
    "-": """
        .......
        .......
        .......
        .#####.
        .......
        .......
        .......
        """,
    ":": """
        .......
        ..##...
        ..##...
        .......
        ..##...
        ..##...
        .......
        """,
    ".": """
        .......
        .......
        .......
        .......
        .......
        ..##...
        ..##...
        """,
    "?": """
        .#####.
        ##...##
        .....##
        ...###.
        ..##...
        .......
        ..##...
        """,
    "'": """
        ..##...
        ..##...
        .##....
        .......
        .......
        .......
        .......
        """,
    "/": """
        .......
        .....##
        ....##.
        ...##..
        ..##...
        .##....
        ##.....
        """,
    "x": """
        .......
        ##...##
        .##.##.
        ..###..
        .##.##.
        ##...##
        .......
        """,
}

DARK_FONT = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ!-:.?'/x"   # tiles 32-75
LIGHT_FONT = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"          # tiles 80-115
LIGHT_FONT_PUNCT = "!-:"                                    # tiles 117-119


def glyph_tile(ch, ink, paper):
    """An 8x8 font tile: the 7x7 glyph at the top left on a paper colour."""
    rows = grid(FONT[ch], 7, 7)
    colour = {"#": ink, ".": paper}
    return ["".join(colour[c] for c in row) + paper for row in rows] + [paper * 8]


def put_tiles(im, index, text, width, height):
    """Draw a grid made of whole tiles with its top-left tile at `index`."""
    rows = grid(text, width, height)
    x0, y0 = tile_xy(index)
    assert x0 + width <= 128, f"tile {index} would wrap"
    draw(im, x0, y0, rows, BG_KEY)


def bg_tiles():
    # Seams: the grass and the rock block end on the same solid mortar line,
    # which is also the colour of the window HUD below the ground.
    rocks = grid(ROCKS, 16, 16)
    assert grid(GRASS, 16, 8)[-1] == rocks[-1] == "#" * 16
    assert set(HUD_DARK) <= {"#", "\n"}

    im = new_image(128, 64)   # every tile starts as sky (index 0); spares stay sky
    put_tiles(im, 0, SKY, 8, 8)
    put_tiles(im, 1, SOLID_BLACK, 8, 8)
    put_tiles(im, 2, BOX, 16, 16)
    put_tiles(im, 4, BOX2, 16, 16)
    put_tiles(im, 6, GRASS, 16, 8)
    put_tiles(im, 8, "\n".join(rocks[:8]), 16, 8)    # ground row A
    put_tiles(im, 24, "\n".join(rocks[8:]), 16, 8)   # ground row B
    put_tiles(im, 10, CLOUD, 32, 16)
    put_tiles(im, 14, HUD_DARK, 8, 8)
    for i, ch in enumerate(DARK_FONT):
        put_tiles(im, 32 + i, "\n".join(glyph_tile(ch, "#", ".")), 8, 8)
    for i, ch in enumerate(LIGHT_FONT):
        put_tiles(im, 80 + i, "\n".join(glyph_tile(ch, ".", "#")), 8, 8)
    put_tiles(im, 116, HUD_DARK, 8, 8)
    for i, ch in enumerate(LIGHT_FONT_PUNCT):
        put_tiles(im, 117 + i, "\n".join(glyph_tile(ch, ".", "#")), 8, 8)
    save(im, "bg_tiles.png", (128, 64))


# --------------------------------------------------------------------------
# art/title_logo.png: 144x32, drawn over the shade-0 sky on the title screen.
#
# The letters are drawn below as solid masks ('#' = letter). title_logo()
# then gives every letter the same finish: a white face whose bottom rows
# are shade 1, a 1 px black outline, and a shade 2 block extrusion below,
# so the logo stands off the sky. The panda face between the words is drawn
# in full (background legend) and gets the same outline and extrusion.

LOGO_LETTERS = {
    "P": """
        #########..
        ##########.
        ###########
        ####...####
        ####...####
        ####...####
        ####...####
        ###########
        ##########.
        #########..
        ####.......
        ####.......
        ####.......
        ####.......
        ####.......
        ####.......
        ####.......
        ####.......
        ####.......
        ####.......
        """,
    "A": """
        ..########..
        .##########.
        ############
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ############
        ############
        ############
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        """,
    "N": """
        ####....####
        #####...####
        #####...####
        ######..####
        ######..####
        #######.####
        #######.####
        ############
        ############
        ############
        ############
        ####.#######
        ####.#######
        ####..######
        ####..######
        ####...#####
        ####...#####
        ####....####
        ####....####
        ####....####
        """,
    "D": """
        #########...
        ##########..
        ###########.
        ####...#####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####...#####
        ###########.
        ##########..
        #########...
        """,
    "J": """
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        .......####
        ####...####
        ####...####
        ####...####
        ###########
        ###########
        .#########.
        ..#######..
        """,
    "U": """
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ####....####
        ############
        ############
        .##########.
        ..########..
        """,
    "M": """
        ####......####
        #####....#####
        ######..######
        ##############
        ##############
        ####.####.####
        ####..##..####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        ####......####
        """,
}

# A front-facing panda head, 16x16, background legend. Its shaded chin lines
# up with the shaded bottom rows of the letters.
LOGO_FACE = """
..###......###..
.#####....#####.
.##############.
.###........###.
.#............#.
#..............#
#..##......##..#
#.#.##....#.##.#
#.####....####.#
#..###....###..#
#......##......#
.#+...#..#...+#.
.#++........++#.
..##++++++++##..
....########....
................
"""

# Top-left corner of each piece: "PANDA", the face, then "JUMP" hopping up
# and down a pixel per letter.
LOGO_LAYOUT = [
    ("P", 4, 4), ("A", 16, 4), ("N", 29, 4), ("D", 42, 4), ("A", 55, 4),
    ("face", 70, 7),
    ("J", 89, 5), ("U", 101, 3), ("M", 114, 5), ("P", 129, 3),
]
LOGO_DEPTH = 3         # rows of shade 2 extrusion under each letter
LOGO_SHADE_ROWS = 6    # bottom rows of each letter face drawn in shade 1


def inside(rows):
    """Pixels of a drawing that are not open sky: flood the '.' pixels
    reachable from the edges; everything else is part of the drawing."""
    h, w = len(rows), len(rows[0])
    outside = set()
    todo = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    while todo:
        x, y = todo.pop()
        if 0 <= x < w and 0 <= y < h and (x, y) not in outside and rows[y][x] == ".":
            outside.add((x, y))
            todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return [(x, y) for y in range(h) for x in range(w) if (x, y) not in outside]


def title_logo():
    w, h = 144, 32
    letters = {}   # (x, y) -> grid character of a letter's face
    face = {}      # (x, y) -> grid character of the panda face (already outlined)
    for name, x0, y0 in LOGO_LAYOUT:
        if name == "face":
            rows = grid(LOGO_FACE, 16, 16)
            for x, y in inside(rows):
                face[x0 + x, y0 + y] = rows[y][x]
        else:
            rows = grid(LOGO_LETTERS[name], len(LOGO_LETTERS[name].split()[0]), 20)
            for y, row in enumerate(rows):
                for x, ch in enumerate(row):
                    if ch == "#":
                        letters[x0 + x, y0 + y] = "+" if y >= 20 - LOGO_SHADE_ROWS else "."
    solid = {**letters, **face}
    depth = set()
    for x, y in solid:
        for k in range(1, LOGO_DEPTH + 1):
            if (x, y + k) not in solid:
                depth.add((x, y + k))
    out = []
    for y in range(h):
        row = ""
        for x in range(w):
            if (x, y) in solid:
                row += solid[x, y]
            elif (x, y) in depth:
                row += "#" if (x, y - 1) in letters else "x"  # a letter's bottom edge
            elif any((x + dx, y + dy) in letters or (x + dx, y + dy) in depth
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                row += "#"                                    # outline
            else:
                row += "."
        out.append(row)
    assert all(0 < x < w - 1 and 0 < y < h - 1 for x, y in set(solid) | depth), "logo does not fit"
    im = new_image(w, h)
    draw(im, 0, 0, out, BG_KEY)
    save(im, "title_logo.png", (w, h))


if __name__ == "__main__":
    ART.mkdir(exist_ok=True)
    bg_tiles()
    panda()
    fx()
    title_logo()
    print("wrote art/bg_tiles.png art/panda.png art/fx.png art/title_logo.png")
