#!/usr/bin/env python3
"""PLACEHOLDER art generator: blocky stand-ins so the build works end to end.

The real, hand-pixelled art replaces this file. It must keep the same file
names, sizes and tile layout (docs/DESIGN.md).
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art"
PALETTE = [(0xE0, 0xF8, 0xD0), (0x88, 0xC0, 0x70), (0x34, 0x68, 0x56), (0x08, 0x18, 0x20)]

FONT3x5 = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", ".#.", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#.#", "###", "###", "#.#", "#.#"], "N": ["##.", "#.#", "#.#", "#.#", "#.#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."], "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#.#", "#.#", "###", "###", "#.#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"],
    "!": [".#.", ".#.", ".#.", "...", ".#."], "-": ["...", "...", "###", "...", "..."],
    ":": ["...", ".#.", "...", ".#.", "..."], ".": ["...", "...", "...", "...", ".#."],
    "?": ["##.", "..#", ".#.", "...", ".#."], "'": [".#.", ".#.", "...", "...", "..."],
    "/": ["..#", "..#", ".#.", "#..", "#.."], "x": ["...", "#.#", ".#.", "#.#", "..."],
}


def new_image(w, h):
    im = Image.new("P", (w, h), 0)
    im.putpalette([c for rgb in PALETTE for c in rgb])
    return im


def fill(px, x0, y0, w, h, c):
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            px[x, y] = c


def tile_xy(index):
    return (index % 16) * 8, (index // 16) * 8


def glyph(px, index, ch, fg, bg):
    x0, y0 = tile_xy(index)
    fill(px, x0, y0, 8, 8, bg)
    for y, row in enumerate(FONT3x5[ch]):
        for x, c in enumerate(row):
            if c == "#":
                fill(px, x0 + 1 + x * 2, y0 + 1 + y, 2, 1, fg)


def bg_tiles():
    im = new_image(128, 64)
    px = im.load()
    fill(px, *tile_xy(1), 8, 8, 3)
    for tl, variant in ((2, 3), (4, 2)):  # box and box variant, 16x16
        x0, y0 = tile_xy(tl)
        fill(px, x0, y0, 16, 16, 3)
        fill(px, x0 + 2, y0 + 2, 12, 12, variant)
    for i in (6, 7):
        x0, y0 = tile_xy(i)
        fill(px, x0, y0, 8, 8, 2)
        fill(px, x0, y0, 8, 3, 1)
    for i in (8, 9, 24, 25):
        x0, y0 = tile_xy(i)
        fill(px, x0, y0, 8, 8, 2)
        fill(px, x0 + (i % 2) * 4, y0 + 3, 3, 2, 3)
    cx, cy = tile_xy(10)
    fill(px, cx + 2, cy + 3, 28, 11, 1)
    fill(px, cx + 3, cy + 4, 26, 9, 0)
    fill(px, *tile_xy(14), 8, 8, 3)
    for i, ch in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ!-:.?'/x"):
        glyph(px, 32 + i, ch, 3, 0)
    for i, ch in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        glyph(px, 80 + i, ch, 0, 3)
    fill(px, *tile_xy(116), 8, 8, 3)
    for i, ch in enumerate("!-:"):
        glyph(px, 117 + i, ch, 0, 3)
    im.save(ART / "bg_tiles.png")


def panda():
    im = new_image(160, 16)
    px = im.load()
    for f in range(10):
        x0 = f * 16
        fill(px, x0 + 2, 1, 12, 14, 3)
        fill(px, x0 + 3, 2, 10, 12, 1)
        fill(px, x0 + 8, 5, 2, 2, 3)
        leg = f % 2
        fill(px, x0 + 4 + leg * 4, 12, 3, 4, 3)
    im.save(ART / "panda.png")


def fx():
    im = new_image(32, 8)
    px = im.load()
    for f in range(4):
        r = 1 + f
        fill(px, f * 8 + 4 - r, 4 - r // 2, r * 2, max(1, r), 2)
    im.save(ART / "fx.png")


def title_logo():
    im = new_image(144, 32)
    px = im.load()
    for i, ch in enumerate("PANDAJUMP"):
        for y, row in enumerate(FONT3x5[ch]):
            for x, c in enumerate(row):
                if c == "#":
                    fill(px, 8 + i * 14 + x * 4, 6 + y * 4, 4, 4, 3)
    im.save(ART / "title_logo.png")


if __name__ == "__main__":
    ART.mkdir(exist_ok=True)
    bg_tiles()
    panda()
    title_logo()
    fx()
