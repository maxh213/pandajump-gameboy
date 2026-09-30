"""High score in battery-backed cartridge RAM (docs/DESIGN.md "Save RAM"):
'P' 'J', version 1, score little-endian, checksum ~(sum of bytes 0-4)."""
import pytest

from gb import sram_block
from test_boot import light_digits
from test_death import row_text_on_screen, text_tiles


def ram_with(block: bytes, fill: int = 0) -> bytes:
    return block + bytes([fill]) * (0x2000 - len(block))


def score_then_die(g, cfg, score):
    """Play invincible until `score`, then let the next obstacle kill the panda."""
    g.start_run(invincible=True)
    if score:
        g.run_until(lambda g: g.u16("score") >= score, 20000, what=f"score {score}")
    g.write8("debug_invincible", 0)
    g.run_until(lambda g: g.state() != cfg.STATE_PLAY, 5000, what="death")
    assert g.state() == cfg.STATE_DEAD
    assert g.u16("score") == score


def hud_hi(cfg, value):
    """Window row 0: " HI 0042" in the light font, the rest T_HUD_DARK."""
    row = light_digits(cfg, f" HI {value:04d}")
    return row + [cfg.T_HUD_DARK] * (20 - len(row))


def test_new_best_is_saved_in_contract_format(make_game, cfg):
    g = make_game()
    score_then_die(g, cfg, 3)
    assert g.u16("high_score") == 3
    assert bytes(g.sram(6)) == sram_block(3) == b"PJ\x01\x03\x00" + bytes([(~(0x50 + 0x4A + 1 + 3)) & 0xFF])
    scx = g.u8("world_scx")
    g.tick(1)
    assert g.win_row(0)[:20] == hud_hi(cfg, 3)
    assert row_text_on_screen(g, 8, text_tiles(cfg, "NEW BEST! 3"), scx) is not None


def test_high_score_survives_power_cycle(make_game, cfg):
    g = make_game(name="cart")
    score_then_die(g, cfg, 2)
    g.stop(save=True)
    assert g.ram_path.read_bytes()[:6] == sram_block(2)
    g2 = make_game(name="cart")          # same directory: same battery RAM
    assert g2.u16("high_score") == 2
    assert bytes(g2.sram(6)) == sram_block(2)
    assert g2.win_row(0)[:20] == hud_hi(cfg, 2)


@pytest.mark.parametrize("final", [0, 4, 5])
def test_worse_or_equal_run_keeps_the_best(make_game, cfg, final):
    g = make_game(ram=ram_with(sram_block(5)))
    assert g.u16("high_score") == 5
    score_then_die(g, cfg, final)
    assert g.u16("high_score") == 5
    assert bytes(g.sram(6)) == sram_block(5)
    scx = g.u8("world_scx")
    g.tick(1)
    assert row_text_on_screen(g, 8, text_tiles(cfg, f"SCORE {final}"), scx) is not None
    assert g.win_row(0)[:20] == hud_hi(cfg, 5)


def test_save_ram_disabled_after_use(make_game, cfg):
    """docs/DESIGN.md: enable the RAM, use it, disable it after. With the
    MBC's RAM gate closed the CPU reads 0xFF at 0xA000, so a stray write
    can't touch the save."""
    g = make_game(ram=ram_with(sram_block(1)))

    def cpu_view():
        return [g.pb.memory[0xA000 + i] for i in range(6)]

    assert cpu_view() == [0xFF] * 6, "save RAM left enabled after loading"
    g.start_run(invincible=True)
    for _ in range(30):
        g.tick(10)
        assert cpu_view() == [0xFF] * 6
    g.run_until(lambda g: g.u16("score") >= 2, 5000)
    g.write8("debug_invincible", 0)
    g.run_until(lambda g: g.state() == cfg.STATE_DEAD, 5000)
    assert bytes(g.sram(6)) == sram_block(2)
    assert cpu_view() == [0xFF] * 6, "save RAM left enabled after saving"


def test_better_run_overwrites(make_game, cfg):
    g = make_game(ram=ram_with(sram_block(1)))
    score_then_die(g, cfg, 2)
    assert bytes(g.sram(6)) == sram_block(2)


def good(v=7):
    return sram_block(v)


BAD = {
    "magic": b"PX" + good()[2:5] + bytes([(~sum(b"PX" + good()[2:5])) & 0xFF]),
    "magic_order": b"JP" + good()[2:5] + bytes([(~sum(b"JP" + good()[2:5])) & 0xFF]),
    "version0": sram_block(7, version=0),
    "version2": sram_block(7, version=2),
    "checksum": good()[:5] + bytes([(good()[5] + 1) & 0xFF]),
    "checksum_not_inverted": good()[:5] + bytes([sum(good()[:5]) & 0xFF]),
    "score_bit_flip": good()[:3] + bytes([good()[3] ^ 0x10]) + good()[4:],
}


@pytest.mark.parametrize("image", [
    pytest.param(ram_with(b"", 0xFF), id="blank_ff"),
    pytest.param(ram_with(b"", 0x00), id="blank_00"),
] + [pytest.param(ram_with(v, 0xFF), id=k) for k, v in BAD.items()])
def test_bad_save_reads_as_zero_and_is_rewritten(make_game, cfg, image):
    g = make_game(ram=image)
    assert g.u16("high_score") == 0
    assert bytes(g.sram(6)) == sram_block(0)
    assert g.win_row(0)[:20] == hud_hi(cfg, 0)
    g.stop(save=True)
    assert g.ram_path.read_bytes()[:6] == sram_block(0)


@pytest.mark.parametrize("value", [1, 42, 999, 1234, 9999, 12345, 65535])
def test_valid_save_loads(make_game, cfg, value):
    g = make_game(ram=ram_with(sram_block(value), 0xFF))
    assert g.u16("high_score") == value
    assert bytes(g.sram(6)) == sram_block(value)
    assert g.win_row(0)[:20] == hud_hi(cfg, value)
