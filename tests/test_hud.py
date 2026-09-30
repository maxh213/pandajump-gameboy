"""HUD (docs/DESIGN.md "Screen layout", "Tiles and VRAM"): the score in
BG map row 1 (0x9800) with the dark font, the high score in the window
(0x9C00, WY=136, WX=7) with the light font, and the pixels on screen are
exactly those tiles."""
import numpy as np
from PIL import Image

from gb import ROOT
from test_boot import light_digits
from test_scoring import digits_row

TILES = np.array(Image.open(ROOT / "art" / "bg_tiles.png"))


def tile_px(i):
    r, c = divmod(i, 16)
    return TILES[r * 8:r * 8 + 8, c * 8:c * 8 + 8]


def row_px(tiles):
    return np.hstack([tile_px(t) for t in tiles])


def test_lcd_setup(game, cfg):
    lcdc = game.io(0xFF40)
    assert lcdc & 0x80, "LCD on"
    assert lcdc & 0x01, "BG on"
    assert lcdc & 0x02, "sprites on"
    assert not lcdc & 0x04, "8x8 sprites"
    assert not lcdc & 0x08, "BG map at 0x9800"
    assert not lcdc & 0x10, "BG/window tiles at 0x8800 (LCDC bit 4 = 0)"
    assert lcdc & 0x20, "window on"
    assert lcdc & 0x40, "window map at 0x9C00"
    assert (game.io(0xFF4A), game.io(0xFF4B)) == (cfg.WIN_Y, cfg.WIN_X)
    assert game.io(0xFF47) == 0xE4
    assert game.io(0xFF48) == 0xD0


def test_score_row_uses_dark_font(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    g.run_until(lambda g: g.u16("score") == 12, 5000)
    g.tick(2, render=True)
    assert g.bg_row(1)[1:6] == digits_row(cfg, 12)
    assert g.bg_row(1)[0] == cfg.T_SKY and g.bg_row(1)[6:20] == [cfg.T_SKY] * 14
    sh = g.shades()
    want = row_px([cfg.T_SKY] + digits_row(cfg, 12) + [cfg.T_SKY] * 14)
    assert np.array_equal(sh[8:16, :], want), "score row pixels differ from the dark font"
    assert (sh[0:8, :] == 0).all(), "map row 0 should be plain sky"


def test_window_shows_hi_with_light_font(make_game, cfg):
    from test_save import ram_with
    from gb import sram_block
    g = make_game(ram=ram_with(sram_block(907)))
    g.tick(2, render=True)
    tiles = light_digits(cfg, " HI 0907")
    tiles += [cfg.T_HUD_DARK] * (20 - len(tiles))
    assert g.win_row(0)[:20] == tiles
    sh = g.shades()
    assert np.array_equal(sh[136:144, :], row_px(tiles)), "window pixels differ from the light font"


def test_hud_band_does_not_scroll(make_game, cfg):
    """Lines 0-15 use SCX=0 while the world scrolls under them."""
    g = make_game()
    g.start_run(invincible=True)
    g.tick(30, render=True)
    a = g.shades()[0:16].copy()
    wx = g.u16("world_x")
    g.tick(7, render=True)
    assert g.u16("world_x") != wx
    assert g.u16("score") == 0
    assert np.array_equal(g.shades()[0:16], a)
