"""High score in battery-backed cartridge RAM (docs/DESIGN.md "Save RAM"):
two 8-byte slots at 0xA000 and 0xA008, each 'P' 'J', version 2, a
sequence number, the score little-endian, checksum ~(sum of bytes 0-5)
and a 0. A save writes the slot that doesn't hold the newest good copy;
loading takes the good slot with the newest sequence number; a cartridge
without a good slot reads 0 and is not written until the next new best."""
import pytest

from gb import SLOT_SIZE, dark_text, find_text, hud_hi_row, save_ram, sram_slot

BLANK = bytes([0xFF]) * SLOT_SIZE


def slots(g):
    raw = bytes(g.sram(2 * SLOT_SIZE))
    return raw[:SLOT_SIZE], raw[SLOT_SIZE:]


def score_then_die(g, cfg, score):
    """Play invincible until `score`, then let the next obstacle kill the panda."""
    g.start_run(invincible=True)
    if score:
        g.run_until(lambda g: g.u16("score") >= score, 20000, what=f"score {score}")
    g.write8("debug_invincible", 0)
    g.run_until(lambda g: g.state() != cfg.STATE_PLAY, 5000, what="death")
    assert g.state() == cfg.STATE_DEAD
    assert g.u16("score") == score


def test_slot_format(cfg):
    """The helper matches the byte layout in docs/DESIGN.md."""
    assert sram_slot(3, seq=1) == b"PJ\x02\x01\x03\x00" + bytes([(~(0x50 + 0x4A + 2 + 1 + 3)) & 0xFF, 0])
    assert sram_slot(0x1234, seq=0xFE)[3:6] == bytes([0xFE, 0x34, 0x12])


def test_new_best_is_saved_in_contract_format(make_game, cfg):
    """A blank cartridge: the first new best goes to slot 0 with sequence 1."""
    g = make_game(ram=save_ram())
    score_then_die(g, cfg, 3)
    assert g.u16("high_score") == 3
    assert slots(g) == (sram_slot(3, seq=1), BLANK)
    scx = g.u8("world_scx")
    g.tick(1)
    assert g.win_row(0)[:20] == hud_hi_row(cfg, 3)
    assert find_text(g, 8, dark_text(cfg, "NEW BEST! 3"), scx) is not None


def test_high_score_survives_power_cycle(make_game, cfg):
    g = make_game(name="cart")
    score_then_die(g, cfg, 2)
    g.stop(save=True)
    assert g.ram_path.read_bytes()[:SLOT_SIZE] == sram_slot(2, seq=1)
    g2 = make_game(name="cart")          # same directory: same battery RAM
    assert g2.u16("high_score") == 2
    assert g2.win_row(0)[:20] == hud_hi_row(cfg, 2)
    # the next new best goes to the other slot; the first one stays
    old = slots(g2)[0]
    score_then_die(g2, cfg, 3)
    assert slots(g2) == (old, sram_slot(3, seq=2))
    g2.stop(save=True)
    g3 = make_game(name="cart")
    assert g3.u16("high_score") == 3


@pytest.mark.parametrize("final", [0, 4, 5])
def test_worse_or_equal_run_keeps_the_best(make_game, cfg, final):
    ram = save_ram(sram_slot(5, seq=9), sram_slot(4, seq=8))
    g = make_game(ram=ram)
    assert g.u16("high_score") == 5
    score_then_die(g, cfg, final)
    assert g.u16("high_score") == 5
    assert g.sram(0x2000) == list(ram), "a run that isn't a new best wrote to the save RAM"
    scx = g.u8("world_scx")
    g.tick(1)
    assert find_text(g, 8, dark_text(cfg, f"SCORE {final}"), scx) is not None
    assert g.win_row(0)[:20] == hud_hi_row(cfg, 5)


def test_save_ram_disabled_after_use(make_game, cfg):
    """docs/DESIGN.md: enable the RAM, use it, disable it after. With the
    MBC's RAM gate closed the CPU reads 0xFF at 0xA000, so a stray write
    can't touch the save."""
    g = make_game(ram=save_ram(sram_slot(1)))

    def cpu_view():
        return [g.pb.memory[0xA000 + i] for i in range(2 * SLOT_SIZE)]

    assert cpu_view() == [0xFF] * 2 * SLOT_SIZE, "save RAM left enabled after loading"
    g.start_run(invincible=True)
    for _ in range(30):
        g.tick(10)
        assert cpu_view() == [0xFF] * 2 * SLOT_SIZE
    g.run_until(lambda g: g.u16("score") >= 2, 5000)
    g.write8("debug_invincible", 0)
    g.run_until(lambda g: g.state() == cfg.STATE_DEAD, 5000)
    assert slots(g) == (sram_slot(1), sram_slot(2, seq=2))
    assert cpu_view() == [0xFF] * 2 * SLOT_SIZE, "save RAM left enabled after saving"


def test_saves_alternate_between_the_slots(make_game, cfg):
    """Each new best goes to the slot without the newest copy, so the
    previous best is never touched while a save is written."""
    g = make_game(ram=save_ram(sram_slot(1, seq=4)))
    score_then_die(g, cfg, 2)
    assert slots(g) == (sram_slot(1, seq=4), sram_slot(2, seq=5))
    g.tick(200)                           # until a restart is possible
    score_then_die(g, cfg, 3)
    assert slots(g) == (sram_slot(3, seq=6), sram_slot(2, seq=5))


def test_sequence_number_wraps(make_game, cfg):
    g = make_game(ram=save_ram(BLANK, sram_slot(7, seq=255)))
    assert g.u16("high_score") == 7
    score_then_die(g, cfg, 8)
    assert slots(g) == (sram_slot(8, seq=0), sram_slot(7, seq=255))
    g.stop(save=True)
    g2 = make_game(name="gb")            # power cycle: 0 is newer than 255
    assert g2.u16("high_score") == 8


@pytest.mark.parametrize("seq0,val0,seq1,val1,want", [
    (1, 10, 2, 20, 20),
    (2, 20, 1, 10, 20),
    (6, 40, 5, 50, 40),        # the newest copy wins, not the biggest number
    (255, 10, 0, 12, 12),      # sequence numbers wrap
    (0, 12, 255, 10, 12),
    (100, 3, 101, 4, 4),
])
def test_newest_good_slot_is_loaded(make_game, cfg, seq0, val0, seq1, val1, want):
    ram = save_ram(sram_slot(val0, seq=seq0), sram_slot(val1, seq=seq1))
    g = make_game(ram=ram)
    assert g.u16("high_score") == want
    assert g.win_row(0)[:20] == hud_hi_row(cfg, want)
    assert g.sram(0x2000) == list(ram), "loading wrote to the save RAM"


def good(v=7, seq=3):
    return sram_slot(v, seq=seq)


def with_checksum(body: bytes) -> bytes:
    return body + bytes([(~sum(body)) & 0xFF, 0])


BAD = {
    "magic": with_checksum(b"PX" + good()[2:6]),
    "magic_order": with_checksum(b"JP" + good()[2:6]),
    "version1": sram_slot(7, seq=3, version=1),
    "version3": sram_slot(7, seq=3, version=3),
    "checksum": good()[:6] + bytes([(good()[6] + 1) & 0xFF, 0]),
    "checksum_not_inverted": good()[:6] + bytes([sum(good()[:6]) & 0xFF, 0]),
    "score_bit_flip": good()[:4] + bytes([good()[4] ^ 0x10]) + good()[5:],
    "seq_bit_flip": good()[:3] + bytes([good()[3] ^ 0x01]) + good()[4:],
    # the single 6-byte block of the old format 1 is not read
    "old_format": b"PJ\x01\x07\x00" + bytes([(~(0x50 + 0x4A + 1 + 7)) & 0xFF]) + b"\xff\xff",
}


@pytest.mark.parametrize("image", [
    pytest.param(save_ram(fill=0xFF), id="blank_ff"),
    pytest.param(save_ram(fill=0x00), id="blank_00"),
] + [pytest.param(save_ram(v, fill=0xFF), id=k) for k, v in BAD.items()]
  + [pytest.param(save_ram(BAD["checksum"], BAD["magic"], fill=0x00), id="both_bad")])
def test_bad_save_reads_as_zero_and_is_not_written(make_game, cfg, image):
    g = make_game(ram=image)
    assert g.u16("high_score") == 0
    assert g.win_row(0)[:20] == hud_hi_row(cfg, 0)
    g.tick(60)
    g.stop(save=True)
    assert g.ram_path.read_bytes() == image


@pytest.mark.parametrize("bad", list(BAD))
@pytest.mark.parametrize("where", [0, 1])
def test_a_bad_slot_leaves_the_good_one(make_game, cfg, bad, where):
    pair = [good(42, seq=9), good(42, seq=9)]
    pair[where] = BAD[bad]
    g = make_game(ram=save_ram(*pair))
    assert g.u16("high_score") == 42


def torn_states(old: bytes, new: bytes):
    """What a slot holds if the power goes during a save that turns `old`
    into `new`, after each write of the order in docs/DESIGN.md: byte 0
    cleared first, then bytes 1-7, then byte 0 last."""
    cur = bytearray(old)
    cur[0] = 0
    yield "cleared", bytes(cur)
    for i in range(1, SLOT_SIZE):
        cur[i] = new[i]
        yield f"byte{i}", bytes(cur)


@pytest.mark.parametrize("older", ["good", "blank"])
def test_power_cut_during_a_save_keeps_the_old_best(make_game, cfg, older):
    """A save of 301 over the older slot is cut off after each of its
    writes: the cartridge still loads the old best (300), writes nothing
    at boot, and the next new best repairs the torn slot."""
    newest = sram_slot(300, seq=5)
    old = sram_slot(200, seq=4) if older == "good" else BLANK
    new = sram_slot(301, seq=6)
    for name, torn in torn_states(old, new):
        ram = save_ram(newest, torn)
        g = make_game(ram=ram, name=name)
        assert g.u16("high_score") == 300, f"torn at {name}: {torn.hex()}"
        assert g.sram(0x2000) == list(ram), f"torn at {name}: boot wrote to the save RAM"
        g.stop()
    # the next save goes over the torn slot
    g = make_game(ram=save_ram(newest, torn), name="next")
    g.write16("high_score", 0)            # let a short run be a new best
    score_then_die(g, cfg, 1)
    assert slots(g) == (newest, sram_slot(1, seq=6))


@pytest.mark.parametrize("value", [1, 42, 999, 1234, 9999, 12345, 65535])
@pytest.mark.parametrize("where", [0, 1])
def test_valid_save_loads(make_game, cfg, value, where):
    pair = [None, None]
    pair[where] = sram_slot(value, seq=77)
    ram = save_ram(*pair)
    g = make_game(ram=ram)
    assert g.u16("high_score") == value
    assert g.sram(0x2000) == list(ram)
    assert g.win_row(0)[:20] == hud_hi_row(cfg, value)
