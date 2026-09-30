"""Jump physics against src/config.h (docs/DESIGN.md "Gameplay"): the ROM's
panda must follow the constants' integer simulation (tests/model.py)
frame for frame.

A press held during one tick is acted on by the logic of the next tick, so
`press_then_record` holds A for one tick and then records from the frame
that acts on it (frame 1 of the model's trajectory has the press)."""
import pytest

from model import Panda, Physics


def state(g):
    return (g.s16("panda_y"), g.s16("panda_vy"), bool(g.u8("panda_on_ground")), g.u8("jumps_used"))


def as_tuple(p: Panda):
    return (p.y, p.vy, p.on_ground, p.jumps)


def run_script(g, presses: set[int], frames: int):
    """Tick `frames` frames; A is pressed (held one tick earlier) so that the
    logic of frame n (1-based, counted from now) sees it for n in presses.
    Returns the RAM panda state after each frame."""
    out = []
    for n in range(1, frames + 1):
        if (n + 1) in presses:
            g.hold("a")
        else:
            g.release("a")
        g.tick()
        out.append(state(g))
    g.release("a")
    return out


@pytest.fixture
def run(make_game):
    g = make_game()
    g.start_run(invincible=True)
    g.tick(5)
    return g


def test_jump_matches_integer_model(run, cfg):
    phys = Physics(cfg)
    got = run_script(run, {2}, 70)
    want = [as_tuple(p) for p in phys.trajectory({2}, 70)]
    assert got == want


def test_jump_apex_and_airtime(run, cfg):
    """Apex and airtime from the constants alone (no ROM): the ROM's jump
    must reach exactly that apex and stay up exactly that long."""
    floor = (cfg.GROUND_Y - 16) << 8
    y, vy, air, top = floor, -cfg.JUMP_VEL, 0, floor
    while True:
        vy = min(vy + cfg.GRAVITY, cfg.MAX_FALL)
        y += vy
        air += 1
        if y >= floor:
            break
        top = min(top, y)
    got = run_script(run, {2}, air + 10)
    ys = [s[0] for s in got]
    assert min(ys) == top
    # airborne frames: the take-off frame up to the frame before landing
    first = next(i for i, s in enumerate(got) if not s[2])
    land = next(i for i, s in enumerate(got) if i > first and s[2])
    assert land - first == air - 1
    assert got[land] == (floor, 0, True, 0)


def test_jump_sets_minus_jump_vel(run, cfg):
    got = run_script(run, {2}, 2)
    # the frame that sees the press applies one frame of gravity
    assert got[1][1] == -cfg.JUMP_VEL + cfg.GRAVITY
    assert got[1][2] is False and got[1][3] == 1


@pytest.mark.parametrize("delay", [2, 5, 15, 29, 30, 45, 57])
def test_double_jump_sets_minus_djump_vel(run, cfg, delay):
    phys = Physics(cfg)
    presses = {2, 2 + delay}
    got = run_script(run, presses, 130)
    want = [as_tuple(p) for p in phys.trajectory(presses, 130)]
    assert got[1 + delay][1] == -cfg.DJUMP_VEL + cfg.GRAVITY
    assert got[1 + delay][3] == 2
    assert got == want


def test_every_double_jump_timing_matches_model(run, cfg):
    """Double jump at every frame of the first jump's flight, landing each
    time: the whole trajectory matches the model (this also exercises the
    MAX_FALL cap on the long falls after a late double jump)."""
    phys = Physics(cfg)
    single = phys.trajectory({1}, 80)
    airtime = next(i for i, p in enumerate(single) if p.on_ground)
    for delay in range(2, airtime + 1):
        presses = {2, 2 + delay}
        got = run_script(run, presses, 150)
        want = [as_tuple(p) for p in phys.trajectory(presses, 150)]
        assert got == want, f"double jump {delay} frames after take-off"
        assert got[-1] == ((cfg.GROUND_Y - 16) << 8, 0, True, 0)
    assert any(p.vy == cfg.MAX_FALL for d in range(2, airtime + 1)
               for p in phys.trajectory({2, 2 + d}, 150)), \
        "some double jump (from near the apex) should reach MAX_FALL"


def test_third_press_does_nothing(run, cfg):
    phys = Physics(cfg)
    base = {2, 12}
    got = run_script(run, base | {22, 30}, 120)
    want = [as_tuple(p) for p in phys.trajectory(base, 120)]
    assert got == want
    assert max(s[3] for s in got) == 2


def test_holding_a_jumps_only_once(run, cfg):
    phys = Physics(cfg)
    got = []
    run.hold("a")
    for _ in range(50):
        run.tick()
        got.append(state(run))
    run.release("a")
    want = [as_tuple(p) for p in phys.trajectory({2}, 50)]
    assert got == want


def test_landing_resets_jumps_and_ground(run, cfg):
    got = run_script(run, {2, 20}, 120)
    land = next(i for i, s in enumerate(got) if i > 2 and s[2])
    assert got[land] == ((cfg.GROUND_Y - 16) << 8, 0, True, 0)
    assert all(s == got[land] for s in got[land:])
    # and the double jump is available again after landing
    phys = Physics(cfg)
    got2 = run_script(run, {2, 10}, 100)
    assert got2 == [as_tuple(p) for p in phys.trajectory({2, 10}, 100)]


def test_press_mid_air_after_landing_is_a_new_jump(run, cfg):
    phys = Physics(cfg)
    single = phys.trajectory({2}, 80)
    land = next(i for i, p in enumerate(single) if i > 2 and p.on_ground) + 1
    presses = {2, land + 2}
    got = run_script(run, presses, 150)
    assert got == [as_tuple(p) for p in phys.trajectory(presses, 150)]
    assert got[land + 1][1] == -cfg.JUMP_VEL + cfg.GRAVITY


def test_panda_never_above_top_of_screen(run, cfg):
    """Force the panda to the top edge mid-flight (unreachable in normal play:
    a double jump at the apex tops out at y=42): it clamps at y=0 with the
    upward speed killed, then falls back and lands."""
    run_script(run, {2}, 3)
    run.write16("panda_y", 0x0100)
    start = Panda(0x0100, run.s16("panda_vy"), False, 1)
    got = run_script(run, set(), 100)
    phys = Physics(cfg)
    want = [as_tuple(p) for p in phys.trajectory(set(), 100, start)]
    assert got == want
    assert got[0][0] == 0 and got[0][1] == 0
    assert all(s[0] >= 0 for s in got)
    assert got[-1][2]


def test_highest_double_jump_stays_on_screen(cfg):
    phys = Physics(cfg)
    tops = [min(p.y for p in phys.trajectory({1, 1 + d}, 200)) for d in range(2, 60)]
    assert min(tops) > 0
