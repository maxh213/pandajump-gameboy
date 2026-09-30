"""Art contract (docs/DESIGN.md "Tiles and VRAM", "Palette") and the tile
budgets of what png2asset generated into build/res/."""
import re
import struct

import numpy as np
import pytest
from PIL import Image

from gb import BUILD, ROOT, generated_array, metasprites

ART = ROOT / "art"
RES = BUILD / "res"

pytestmark = pytest.mark.usefixtures("rom")    # build/res comes from the build

SIZES = {
    "bg_tiles.png": (128, 64),
    "panda.png": (160, 16),
    "fx.png": (32, 8),
    "title_logo.png": (144, 32),
}
PALETTE = [(0xE0, 0xF8, 0xD0), (0x88, 0xC0, 0x70), (0x34, 0x68, 0x56), (0x08, 0x18, 0x20)]


def png_chunks(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    i, out = 8, {}
    while i < len(data):
        (n,) = struct.unpack(">I", data[i:i + 4])
        kind = data[i + 4:i + 8].decode("latin-1")
        out.setdefault(kind, data[i + 8:i + 8 + n])
        i += 12 + n
    return out


def res_defines(name):
    text = (RES / f"{name}.h").read_text()
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"#define\s+(\w+)\s+(\d+)\b", text)}


def test_every_contract_png_exists():
    assert sorted(p.name for p in ART.glob("*.png")) == sorted(SIZES)


@pytest.mark.parametrize("name", sorted(SIZES))
def test_png_is_indexed_with_exactly_4_entries(name):
    chunks = png_chunks(ART / name)
    ihdr = chunks["IHDR"]
    w, h, depth, color_type = struct.unpack(">IIBB", ihdr[:10])
    assert color_type == 3, "not an indexed (palette) PNG"
    assert len(chunks["PLTE"]) == 4 * 3, "palette must have exactly 4 entries"
    assert (w, h) == SIZES[name]
    img = Image.open(ART / name)
    assert img.mode == "P"
    px = np.array(img)
    assert px.max() <= 3


@pytest.mark.parametrize("name", sorted(SIZES))
def test_png_palette_is_the_contract_palette(name):
    plte = png_chunks(ART / name)["PLTE"]
    got = [tuple(plte[i:i + 3]) for i in range(0, 12, 3)]
    assert got == PALETTE


def _tiles(name):
    a = np.array(Image.open(ART / name))
    h, w = a.shape
    return [a[r:r + 8, c:c + 8] for r in range(0, h, 8) for c in range(0, w, 8)]


def test_bg_tiles_fixed_tiles(cfg):
    t = _tiles("bg_tiles.png")
    assert (t[cfg.T_SKY] == 0).all(), "T_SKY must be solid shade 0"
    assert (t[cfg.T_BLACK] == 3).all(), "T_BLACK must be solid shade 3"
    assert (t[cfg.T_LFONT_SPACE] == t[cfg.T_HUD_DARK]).all(), "light font space = T_HUD_DARK"


def test_fonts_use_their_two_shades(cfg):
    t = _tiles("bg_tiles.png")
    for i in range(cfg.T_FONT_DIGIT, cfg.T_FONT_TIMES + 1):
        assert set(np.unique(t[i])) <= {0, 3}, f"dark font tile {i} is not shade 3 on shade 0"
        assert (t[i] == 3).any(), f"dark font tile {i} is blank"
    hud = t[cfg.T_HUD_DARK]
    for i in range(cfg.T_LFONT_DIGIT, cfg.T_LFONT_COLON + 1):
        if i == cfg.T_LFONT_SPACE:
            continue
        assert ((t[i] == 0) | (t[i] == hud)).all(), f"light font tile {i} is not shade 0 on T_HUD_DARK"
        assert (t[i] == 0).any(), f"light font tile {i} is blank"


def test_digit_glyphs_are_distinct(cfg):
    t = _tiles("bg_tiles.png")
    for base in (cfg.T_FONT_DIGIT, cfg.T_LFONT_DIGIT):
        glyphs = {t[base + d].tobytes() for d in range(10)}
        assert len(glyphs) == 10


def test_generated_tile_counts_within_budget(cfg):
    bg = res_defines("bg_tiles")
    panda = res_defines("panda")
    logo = res_defines("title_logo")
    fx = res_defines("fx")
    assert bg["bg_tiles_TILE_COUNT"] == 128, "bg_tiles is converted with -keep_duplicate_tiles: 16x8 tiles"
    assert panda["panda_TILE_COUNT"] < 64, "panda tiles must stay below S_FX_BASE (64)"
    assert cfg.S_PANDA_BASE + panda["panda_TILE_COUNT"] <= cfg.S_FX_BASE
    assert cfg.S_FX_BASE + fx["fx_TILE_COUNT"] <= cfg.S_TEXT_BASE
    assert cfg.S_TEXT_BASE + 26 <= 128, "sprite tiles must stay below 128"
    assert logo["title_logo_TILE_COUNT"] <= 128
    assert logo["title_logo_TILE_ORIGIN"] == 128
    assert (logo["title_logo_WIDTH"], logo["title_logo_HEIGHT"]) == (144, 32)


def test_panda_has_10_frames_of_at_most_4_sprites():
    text = (RES / "panda.c").read_text()
    frames = re.findall(r"const metasprite_t panda_metasprite(\d+)\[\] = \{(.*?)\};", text, re.S)
    assert len(frames) == 10
    for idx, body in frames:
        assert body.count("METASPR_ITEM") <= 4, f"panda frame {idx} needs more than 4 hardware sprites"


def test_fx_has_4_frames():
    text = (RES / "fx.h").read_text()
    assert re.search(r"fx_metasprites\[4\]", text)


def _decode(data, i):
    b = data[16 * i:16 * i + 16]
    return np.array([[((b[2 * y] >> (7 - x)) & 1) | (((b[2 * y + 1] >> (7 - x)) & 1) << 1)
                      for x in range(8)] for y in range(8)])


@pytest.mark.parametrize("name,size", [("panda", 16), ("fx", 8)])
def test_metasprites_rebuild_the_art(name, size):
    """Each generated metasprite, drawn from its tiles, is the art frame."""
    data = generated_array(name, f"{name}_tiles")
    art = np.array(Image.open(ART / f"{name}.png"))
    frames = metasprites(name)
    assert len(frames) == art.shape[1] // size
    for f, items in frames.items():
        img = np.zeros((size, size), dtype=int)
        for (y, x, t) in items:
            img[y:y + 8, x:x + 8] = _decode(data, t)
        assert np.array_equal(img, art[:, f * size:(f + 1) * size]), f"{name} frame {f}"
