"""Tile data in VRAM (docs/DESIGN.md "Tiles and VRAM"): BG tiles 0-127 are
art/bg_tiles.png in order (LCDC bit 4 = 0, so they live at 0x9000), the
title logo at BG 128+ (0x8800), sprite tiles at 0x8000: the panda at
S_PANDA_BASE, the dust puff at S_FX_BASE and the dark font's A-Z at
S_TEXT_BASE."""
import numpy as np
from PIL import Image

from gb import ROOT, generated_array


def encode_2bpp(px):
    """An 8x8 tile of colour indices as the Game Boy's 16 bytes."""
    out = []
    for row in px:
        lo = hi = 0
        for x, v in enumerate(row):
            lo |= (int(v) & 1) << (7 - x)
            hi |= ((int(v) >> 1) & 1) << (7 - x)
        out += [lo, hi]
    return out


def art_tiles(name):
    a = np.array(Image.open(ROOT / "art" / name))
    h, w = a.shape
    return [encode_2bpp(a[r:r + 8, c:c + 8]) for r in range(0, h, 8) for c in range(0, w, 8)]


def vram(g, addr, n):
    return [g.pb.memory[addr + i] for i in range(n)]


def bg_tile_addr(i):
    """LCDC bit 4 = 0: tiles 0-127 at 0x9000, 128-255 at 0x8800."""
    return 0x9000 + 16 * i if i < 128 else 0x8800 + 16 * (i - 128)


def test_bg_tiles_are_the_art_in_order(game):
    tiles = art_tiles("bg_tiles.png")
    for i, want in enumerate(tiles):
        assert vram(game, bg_tile_addr(i), 16) == want, f"BG tile {i} differs from art/bg_tiles.png"


def test_logo_tiles_and_map(game, cfg):
    data = generated_array("title_logo", "title_logo_tiles")
    assert vram(game, bg_tile_addr(cfg.T_LOGO_BASE), len(data)) == data
    logo_map = generated_array("title_logo", "title_logo_map")
    rows = [game.bg_row(r)[1:19] for r in range(2, 6)]
    assert sum(rows, []) == logo_map


def test_sprite_tiles(game, cfg):
    panda = generated_array("panda", "panda_tiles")
    assert vram(game, 0x8000 + 16 * cfg.S_PANDA_BASE, len(panda)) == panda
    fx = generated_array("fx", "fx_tiles")
    assert vram(game, 0x8000 + 16 * cfg.S_FX_BASE, len(fx)) == fx
    font = art_tiles("bg_tiles.png")
    for j in range(26):
        assert vram(game, 0x8000 + 16 * (cfg.S_TEXT_BASE + j), 16) == font[cfg.T_FONT_ALPHA + j], \
            f"sprite letter {chr(65 + j)}"


def test_run_keeps_tile_data(make_game, cfg):
    """Nothing overwrites tile data during play (only the maps change)."""
    g = make_game()
    before = vram(g, 0x8000, 0x1800)
    g.start_run(invincible=True)
    g.tick(3000)
    g.write8("debug_invincible", 0)
    g.run_until(lambda g: g.state() == cfg.STATE_DEAD, 3000)
    g.tick(100)
    assert vram(g, 0x8000, 0x1800) == before
