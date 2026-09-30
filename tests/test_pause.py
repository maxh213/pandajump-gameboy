"""Pause (docs/DESIGN.md "States and controls"): Start pauses a run
(STATE_PAUSED, "PAUSED" shown), nothing moves, Start resumes where it
left off."""
import numpy as np

from gb import dark_text, find_text
from model import Physics


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
    wx = g.u16("world_x")
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
    assert g.u16("world_x") == wx + 61
