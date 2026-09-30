"""Jump physics and input rules against src/config.h (docs/DESIGN.md
"Gameplay"): the ROM's panda, including the kept press (jump_buffer), must
follow the constants' integer simulation (tests/model.py) frame for frame.

A press held during one tick is acted on by the logic of the next tick, so
`press_then_record` holds A for one tick and then records from the frame
that acts on it (frame 1 of the model's trajectory has the press)."""
import pytest

from model import Panda, Physics


def state(g):
    return (g.s16("panda_y"), g.s16("panda_vy"), bool(g.u8("panda_on_ground")), g.u8("jumps_used"),
            g.u8("jump_buffer"))


def as_tuple(p: Panda):
    return (p.y, p.vy, p.on_ground, p.jumps, p.buffer)


def landing_frame(phys, presses, start=None):
    """The first frame (1-based) that ends on the ground after the last press."""
    traj = phys.trajectory(presses, 400, start)
    last = max(presses)
    return next(i + 1 for i, p in enumerate(traj) if i + 1 >= last and p.on_ground)


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
    assert got[land] == (floor, 0, True, 0, 0)


def test_jump_sets_minus_jump_vel(run, cfg):
    got = run_script(run, {2}, 2)
    # the frame that sees the press applies one frame of gravity
    assert got[1][1] == -cfg.JUMP_VEL + cfg.GRAVITY
    assert got[1][2] is False and got[1][3] == 1


@pytest.mark.parametrize("delay", [15, 16, 29, 30, 45, 53])
def test_double_jump_sets_minus_djump_vel(run, cfg, delay):
    """From 15 frames after take-off (when -DJUMP_VEL is a boost) until the
    panda is BUFFER_HEIGHT px from the ground, a second press sets
    vy = -DJUMP_VEL."""
    phys = Physics(cfg)
    presses = {2, 2 + delay}
    got = run_script(run, presses, 130)
    want = [as_tuple(p) for p in phys.trajectory(presses, 130)]
    assert got[1 + delay][1] == -cfg.DJUMP_VEL + cfg.GRAVITY
    assert got[1 + delay][3] == 2
    assert got == want


def test_double_jump_window_follows_the_rules(cfg):
    """Model only: which second presses double jump. 14 frames after
    take-off vy is exactly -DJUMP_VEL (no boost: not a double jump), one
    frame later it is; near the ground it is not again."""
    phys = Physics(cfg)
    single = phys.trajectory({1}, 80)
    land = landing_frame(phys, {1})
    for k in range(1, land):
        before = single[k - 1]          # the state the press at frame 1 + k sees
        want = before.vy > -cfg.DJUMP_VEL and before.y <= phys.floor - (cfg.BUFFER_HEIGHT << 8)
        p = before.copy()
        assert (phys.press(p) == 2) == want, f"second press {k} frames after take-off"
    assert single[13].vy == -cfg.DJUMP_VEL and single[14].vy > -cfg.DJUMP_VEL
    near = [k for k in range(15, land) if phys.floor - single[k - 1].y < cfg.BUFFER_HEIGHT << 8]
    assert near == list(range(land - 4, land)), "BUFFER_HEIGHT should cover the last 4 frames of a jump"


@pytest.mark.parametrize("delay", [2, 3, 5, 8, 12, 14])
def test_early_second_press_is_not_used_up(run, cfg, delay):
    """A second press while the panda still rises faster than DJUMP_VEL
    would only slow it down, so it isn't the double jump: the jump goes on
    unchanged, jumps_used stays 1 (no sound, no puff), and the double jump
    is still there later."""
    phys = Physics(cfg)
    single = [as_tuple(p) for p in phys.trajectory({2}, 40)]
    got = run_script(run, {2, 2 + delay}, 40)
    assert [s[:4] for s in got] == [s[:4] for s in single], "an early second press changed the jump"
    assert max(s[3] for s in got) == 1
    # kept for JUMP_BUFFER frames, counting its own (which ends one down)
    assert got[1 + delay][4] == cfg.JUMP_BUFFER - 1, "the press should be kept, then run out"
    assert got[delay + cfg.JUMP_BUFFER][4] == 0 < got[delay + cfg.JUMP_BUFFER - 1][4]
    # the same again, with a real double jump 20 frames later
    run_script(run, set(), 80)          # land
    presses = {2, 2 + delay, 2 + delay + 20}
    got = run_script(run, presses, 130)
    assert got == [as_tuple(p) for p in phys.trajectory(presses, 130)]
    assert got[1 + delay + 20][3] == 2 and got[1 + delay + 20][1] == -cfg.DJUMP_VEL + cfg.GRAVITY


def test_early_second_press_makes_no_sound_or_puff(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    g.tick(5)
    calls = []
    for name in ("sfx_jump", "sfx_double_jump"):
        _bank, addr = g.pb.symbol_lookup("_" + name)
        g.pb.hook_register(0, addr, calls.append, name)
    run_script(g, {2, 7}, 20)
    assert calls == ["sfx_jump"]
    y, x, t, a = g.oam()[cfg.OAM_FX]
    assert not (-8 < y < 144), "a dust puff for a double jump that didn't happen"


@pytest.mark.parametrize("before", [0, 1, 2, 3])
def test_press_just_before_landing_jumps_on_landing(run, cfg, before):
    """After a single jump, a press in the last 4 frames of the fall
    (under BUFFER_HEIGHT) is not a short double jump: the panda lands and
    takes off again at once, exactly as if A had been pressed on its first
    frame on the ground (the landing frame shows it still at the floor)."""
    phys = Physics(cfg)
    land = landing_frame(phys, {2})
    presses = {2, land - before}
    got = run_script(run, presses, 130)
    assert got == [as_tuple(p) for p in phys.trajectory(presses, 130)]
    assert max(s[3] for s in got) == 1, "it double jumped"
    floor = (cfg.GROUND_Y - 16) << 8
    assert got[land - 1] == (floor, -cfg.JUMP_VEL, False, 1, 0)
    # identical to a jump pressed on the first frame on the ground
    fresh = [as_tuple(p) for p in phys.trajectory({2, land + 1}, 130)]
    assert got[land:] == fresh[land:]


@pytest.mark.parametrize("before", [0, 1, 3, 5, 6, 7])
def test_press_after_the_double_jump_is_kept_for_landing(run, cfg, before):
    """With the double jump used, a press in the last JUMP_BUFFER frames of
    the flight (the landing frame included) jumps on landing; an earlier one
    is lost."""
    phys = Physics(cfg)
    land = landing_frame(phys, {2, 27})
    presses = {2, 27, land - before}
    got = run_script(run, presses, 170)
    assert got == [as_tuple(p) for p in phys.trajectory(presses, 170)]
    kept = before < cfg.JUMP_BUFFER
    assert got[land - 1][2] is (not kept), f"press {before} frames before landing"
    if kept:
        assert got[land - 1][:4] == ((cfg.GROUND_Y - 16) << 8, -cfg.JUMP_VEL, False, 1)
    else:
        assert all(s[2] for s in got[land - 1:]), "a lost press should not jump"


def test_kept_press_plays_the_jump_sound_on_landing(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    g.tick(5)
    phys = Physics(cfg)
    land = landing_frame(phys, {2})
    calls = []
    _bank, addr = g.pb.symbol_lookup("_sfx_jump")
    g.pb.hook_register(0, addr, lambda _: calls.append(g.frames + 1), None)   # during tick n
    start = g.frames
    run_script(g, {2, land - 2}, land + 5)
    assert [f - start for f in calls] == [2, land], "jump sounds on take-off and on the kept jump"


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
        assert got[-1] == ((cfg.GROUND_Y - 16) << 8, 0, True, 0, 0)
    assert any(p.vy == cfg.MAX_FALL for d in range(2, airtime + 1)
               for p in phys.trajectory({2, 2 + d}, 150)), \
        "some double jump (from near the apex) should reach MAX_FALL"


def test_third_press_does_nothing(run, cfg):
    """Well before landing, a press after the double jump is kept for
    JUMP_BUFFER frames and runs out: the flight is unchanged."""
    phys = Physics(cfg)
    base = {2, 22}
    got = run_script(run, base | {32, 40}, 120)
    want = [as_tuple(p) for p in phys.trajectory(base, 120)]
    assert [s[:4] for s in got] == [s[:4] for s in want]
    assert got == [as_tuple(p) for p in phys.trajectory(base | {32, 40}, 120)]
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
    assert got[land] == ((cfg.GROUND_Y - 16) << 8, 0, True, 0, 0)
    assert all(s == got[land] for s in got[land:])
    # and the double jump is available again after landing
    phys = Physics(cfg)
    got2 = run_script(run, {2, 25}, 100)
    assert got2 == [as_tuple(p) for p in phys.trajectory({2, 25}, 100)]
    assert max(s[3] for s in got2) == 2


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
