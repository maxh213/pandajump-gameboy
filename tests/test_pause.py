"""Pause (docs/DESIGN.md "States and controls"): Start pauses a run
(STATE_PAUSED, "PAUSED" shown), nothing moves, Start resumes where it
left off."""
import numpy as np
import pytest

from gb import SKY, bg_picture, dark_text, find_text, render_band
from model import Physics, Scroll


def snapshot(g):
    return (g.u16("world_x"), g.s16("panda_y"), g.s16("panda_vy"), g.u8("panda_on_ground"),
            g.u8("jumps_used"), g.u16("score"), tuple(g.col_height()), g.u16("world_speed"))


def paused_mid_jump(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    g.tick(20)
    g.tap("a")             # jump; RAM shows it now
    g.tick(8)              # rising
    assert not g.u8("panda_on_ground")
    g.tap("start")
    assert g.state() == cfg.STATE_PAUSED
    return g


def test_start_pauses(make_game, cfg):
    g = paused_mid_jump(make_game, cfg)
    scx = g.u8("world_scx")
    g.tick(1)
    x = find_text(g, 8, dark_text(cfg, "PAUSED"), scx)
    assert x is not None, "PAUSED not shown"
    assert abs(x + 4 * len("PAUSED") - 80) <= 4


def test_nothing_moves_while_paused(make_game, cfg):
    g = paused_mid_jump(make_game, cfg)
    g.tick(2, render=True)
    ram0 = snapshot(g)
    screen0 = g.shades()
    oam0 = g.oam()
    fc = g.u8("frame_count")
    for i in range(60):
        g.tick(1, render=True)
        assert snapshot(g) == ram0, f"RAM changed {i + 1} frames into the pause"
        assert np.array_equal(g.shades(), screen0), f"screen changed {i + 1} frames into the pause"
        assert g.oam() == oam0
        assert g.state() == cfg.STATE_PAUSED
    # the main loop keeps running: one frame_count per frame
    assert g.u8("frame_count") == (fc + 60) & 0xFF


def test_a_does_nothing_while_paused(make_game, cfg):
    g = paused_mid_jump(make_game, cfg)
    before = snapshot(g)
    for _ in range(5):
        g.tap("a")
    assert snapshot(g) == before
    assert g.state() == cfg.STATE_PAUSED


def test_start_resumes_where_it_left_off(make_game, cfg):
    """The jump continues frame for frame as if the pause never happened."""
    g = make_game()
    g.start_run(invincible=True)
    g.tick(20)
    phys = Physics(cfg)
    ys = []
    g.hold("a")
    g.tick()
    g.release("a")
    for _ in range(9):
        g.tick()
        ys.append((g.s16("panda_y"), g.s16("panda_vy")))
    g.hold("start")
    g.tick()                             # a normal frame; Start is read at its end
    ys.append((g.s16("panda_y"), g.s16("panda_vy")))
    scroll = g.scroll()
    before = snapshot(g)
    g.release("start")
    g.tick()                             # the pause frame changes nothing but the state
    assert g.state() == cfg.STATE_PAUSED
    assert snapshot(g) == before
    g.tick(30)
    g.hold("start")
    g.tick()
    g.release("start")
    g.tick()                             # the resume frame: state only
    assert g.state() == cfg.STATE_PLAY
    assert snapshot(g) == before
    for _ in range(60):
        g.tick()
        ys.append((g.s16("panda_y"), g.s16("panda_vy")))
    want = [(p.y, p.vy) for p in phys.trajectory({1}, 70)]
    assert ys == want
    g.tick(1)
    assert g.bg_row(8) == [cfg.T_SKY] * 32, "PAUSED not cleared"
    for _ in range(61):                  # the frames played since `before`
        scroll.step()
    assert (g.u16("world_x"), g.u8("world_sub")) == (scroll.x & 0xFFFF, scroll.sub)


def test_pause_holds_the_music_and_resume_continues_it(make_game, cfg):
    """Pausing silences the music without losing its place (music_pause),
    and resuming carries on from there (music_resume) instead of starting
    the song again from the top (music_play)."""
    NR51, CH2, CH3 = 0xFF25, 0x22, 0x44
    g = make_game(sound=True)
    g.start_run(invincible=True)
    g.tick(30)
    calls = []
    for name in ("music_play", "music_stop", "music_pause", "music_resume"):
        _bank, addr = g.pb.symbol_lookup("_" + name)
        g.pb.hook_register(0, addr, calls.append, name)

    def levels(n):
        out = []
        for _ in range(n):
            g.tick()
            a = np.asarray(g.pb.sound.ndarray).astype(np.int32)
            out.append(int(a.max() - a.min()) if a.size else 0)
        return out

    g.pb.memory[NR51] = CH2 | CH3                 # only the music channels
    assert max(levels(60)) > 0, "no music before the pause"
    g.tap("start")
    assert g.state() == cfg.STATE_PAUSED
    g.tick(10)                                    # the last note fades out
    assert max(levels(60)) == 0, "music still audible while paused"
    g.tap("start")
    assert g.state() == cfg.STATE_PLAY
    assert max(levels(60)) > 0, "the music did not come back after the pause"
    assert calls == ["music_pause", "music_resume"]


@pytest.mark.parametrize("delay", [1, 2, 3])
def test_pause_during_the_logo_wipe(make_game, cfg, delay):
    """Start `delay` frames after A has started a run from the title, while
    the logo is still being replaced: the sky band keeps hiding the wipe
    behind plain sky (and shows no second PAUSED from the world band's
    message rows), the wipe finishes during the pause, and PAUSED is shown
    once, in the world band."""
    g = make_game()
    g.tick(2, render=True)
    title = g.shades()[SKY].copy()
    g.hold("a")                          # starts the run
    seen = []
    for i in range(12):
        if i == delay:
            g.hold("start")              # pauses it
        g.tick(1, render=True)
        g.release("a")
        g.release("start")
        sky = g.shades()[SKY]
        if np.array_equal(sky, title):
            seen.append("logo")
        elif (sky == 0).all():
            seen.append("sky")
        else:
            pic = bg_picture(g)          # fails while logo tiles are left in the map
            ok = any(np.array_equal(sky, render_band(g, range(16, 48), scx, bob, pic))
                     for scx in range(4) for bob in range(5))
            assert ok, f"sky band {i} frames after A is neither the logo, plain sky nor the new sky"
            seen.append("run")
    assert g.state() == cfg.STATE_PAUSED
    assert seen == ["logo"] * 2 + ["sky"] * 4 + ["run"] * 6, seen
    scx = g.u8("world_scx")
    x = find_text(g, 8, dark_text(cfg, "PAUSED"), scx)
    assert x is not None, "PAUSED not shown"
    assert (g.shades()[64:72, x:x + 48] == 3).any(), "PAUSED not on the screen"
