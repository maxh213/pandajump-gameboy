"""Sound (docs/DESIGN.md "Sound API"): sound_init turns the APU on; effects
play on channels 1 and 4, music on 2 and 3.

PyBoy mixes all channels into one buffer, so a test isolates channels by
routing only them to the outputs (NR51, which the game sets once in
sound_init) and measures the peak-to-peak level of each frame's samples."""
import numpy as np
import pytest

NR51 = 0xFF25
NR52 = 0xFF26
CH1, CH2, CH3, CH4 = 0x11, 0x22, 0x44, 0x88


def levels(g, n):
    out = []
    for _ in range(n):
        g.tick()
        a = np.asarray(g.pb.sound.ndarray).astype(np.int32)
        out.append(int(a.max() - a.min()) if a.size else 0)
    return out


@pytest.fixture
def sgame(make_game):
    return make_game(sound=True)


def test_apu_on_after_boot(sgame):
    assert sgame.io(NR52) & 0x80, "APU off (NR52 bit 7)"
    assert sgame.io(0xFF24) & 0x77, "master volume is zero"


def quiet_run(g):
    """A run past the start jingle, before the first obstacle scores."""
    g.start_run(invincible=True)
    g.tick(40)


def test_jump_sounds_on_effect_channel(sgame):
    g = sgame
    quiet_run(g)
    g.pb.memory[NR51] = CH1
    assert max(levels(g, 10)) == 0, "channel 1 is not silent before the jump"
    g.hold("a")
    g.tick()
    g.release("a")
    lv = levels(g, 12)
    assert g.u8("jumps_used") == 1
    # sound_update() runs at the end of the jump's frame (VBlank), so the
    # sound can only be heard from the last few lines of that frame on
    assert max(lv[:2]) > 0, f"the jump sound should start with the jump: {lv}"
    assert sum(1 for v in lv if v > 0) >= 8, f"jump sound too short: {lv}"


def test_double_jump_sounds_on_effect_channel(sgame):
    g = sgame
    quiet_run(g)
    g.pb.memory[NR51] = CH1
    g.tap("a")
    levels(g, 25)                     # let the jump sound end
    assert max(levels(g, 3)) == 0
    g.hold("a")
    g.tick()
    g.release("a")
    assert g.u8("jumps_used") == 1   # the logic sees it next frame
    lv = levels(g, 10)
    assert g.u8("jumps_used") == 2
    assert max(lv) > 0


def test_death_sounds_on_channels_1_and_4(sgame, cfg):
    g = sgame
    g.start_run()
    g.run_until(lambda g: g.state() == cfg.STATE_PLAY and g.u16("world_x") > 120, 400)
    g.pb.memory[NR51] = CH4
    assert max(levels(g, 5)) == 0
    g.run_until(lambda g: g.state() == cfg.STATE_DEAD, 400)
    assert max(levels(g, 8)) > 0, "no noise (channel 4) in the death sound"
    g.pb.memory[NR51] = CH1
    assert max(levels(g, 8)) > 0, "no tone (channel 1) in the death sound"


def test_music_stays_off_the_effect_channels(sgame):
    g = sgame
    quiet_run(g)
    g.pb.memory[NR51] = CH1 | CH4
    assert max(levels(g, 90)) == 0, "sound on channels 1/4 with no effect playing"
    g.pb.memory[NR51] = CH2 | CH3
    assert max(levels(g, 90)) > 0, "no music on channels 2/3 during a run"
