"""Collision, death and restart (docs/DESIGN.md "Gameplay", "States and
controls")."""
import io

import pytest

from gb import dark_text, find_text, record_world, render_band
from model import AutoPlayer, Physics, WorldMap


def die_without_input(g, cap=2000):
    frames = g.run_until(lambda g: g.state() != 1, cap, what="death")
    return frames


def first_obstacle_start(cfg):
    return 21 + 1 + cfg.FIRST_GAP


def test_no_input_dies_at_first_obstacle(game, cfg):
    game.start_run()
    hx1 = cfg.PANDA_X + cfg.HIT_X1
    last = None
    while True:
        game.tick()
        if game.state() != cfg.STATE_PLAY:
            break
        last = game.u16("world_x")
    assert game.state() == cfg.STATE_DEAD
    wx = game.u16("world_x")
    start = first_obstacle_start(cfg)
    # the first frame the hitbox's right edge reaches the first box column
    assert wx == start * 8 - hx1
    assert last == wx - 1
    assert game.col_height()[start & 31] in (16, 32)
    assert game.u16("score") == 0


def test_dead_state_shows_game_over_and_score(game, cfg):
    game.start_run()
    die_without_input(game)
    scx = game.u8("world_scx")
    game.tick(1)   # BG text appears one frame after the state change
    for row, text in ((7, "GAME OVER"), (8, "SCORE 0")):
        x = find_text(game, row, dark_text(cfg, text), scx)
        assert x is not None, f"{text!r} not in BG row {row}"
        centre = x + 4 * len(text)
        assert abs(centre - 80) <= 4, f"{text!r} is not centred (starts at x={x})"


def test_press_start_appears_after_the_delay(game, cfg):
    game.start_run()
    die_without_input(game)
    scx = game.u8("world_scx")
    want = dark_text(cfg, "PRESS START")
    for _ in range(cfg.DEAD_DELAY):
        game.tick()
        assert find_text(game, 9, want, scx) is None
    seen = False
    for _ in range(2 * cfg.BLINK_FRAMES + 2):
        game.tick()
        seen |= find_text(game, 9, want, scx) is not None
    assert seen


def test_death_pose_falls_off_screen(game, cfg):
    game.start_run()
    die_without_input(game)
    hidden = False
    for _ in range(200):
        game.tick()
        ys = [y for (y, x, t, a) in game.oam()[cfg.OAM_PANDA:cfg.OAM_PANDA + 4]]
        if all(y < -8 or y >= 144 for y in ys):
            hidden = True
            break
    assert hidden, "the dead panda should fall away and be hidden"


def register_press_at(g, button, n):
    """Press so that the logic of the n-th frame from now (n >= 2) sees it."""
    g.tick(n - 2)
    g.hold(button)
    g.tick()
    g.release(button)
    g.tick()


@pytest.mark.parametrize("button", ["start", "a"])
def test_input_ignored_for_dead_delay(game, cfg, button):
    game.start_run()
    die_without_input(game)
    # presses seen by frames 2, 4, ... DEAD_DELAY after the death frame
    n = 0
    while n + 2 <= cfg.DEAD_DELAY:
        register_press_at(game, button, 2)
        n += 2
        assert game.state() == cfg.STATE_DEAD, f"a press {n} frames after dying restarted"
    assert n == cfg.DEAD_DELAY


@pytest.mark.parametrize("button", ["start", "a"])
def test_first_press_after_dead_delay_restarts(game, cfg, button):
    game.start_run()
    die_without_input(game)
    register_press_at(game, button, cfg.DEAD_DELAY + 1)
    assert game.state() == cfg.STATE_PLAY


def test_restart_is_a_fresh_run(game, cfg):
    game.start_run()
    die_without_input(game)
    game.tick(cfg.DEAD_DELAY + 5)
    game.tap("start")
    assert game.state() == cfg.STATE_PLAY
    assert game.u16("score") == 0
    assert game.col_height() == [0] * 32
    assert game.u16("world_x") == 0
    assert game.u16("world_speed") == cfg.SPEED_BASE
    assert (game.s16("panda_y"), game.s16("panda_vy"), game.u8("panda_on_ground"),
            game.u8("jumps_used")) == ((cfg.GROUND_Y - 16) << 8, 0, 1, 0)
    game.tick(2)
    # old boxes and messages are gone from the map
    for row in range(10, 14):
        assert game.bg_row(row) == [cfg.T_SKY] * 32, f"row {row} not cleared"
    for row in range(6, 10):
        assert game.bg_row(row) == [cfg.T_SKY] * 32, f"message row {row} not cleared"
    assert game.bg_row(1)[1:6] == [cfg.T_FONT_DIGIT] + [cfg.T_SKY] * 4
    # and it plays the same way: the first obstacle is FIRST_GAP tiles in
    last = 0
    while True:
        game.tick()
        if game.state() != cfg.STATE_PLAY:
            break
        last = game.u16("world_x")
    assert game.u16("world_x") == first_obstacle_start(cfg) * 8 - (cfg.PANDA_X + cfg.HIT_X1)


def outcomes(cfg, panda, scroll, score, wmap, frames=160):
    """For every take-off frame f, the model's first frame of contact (or
    None when the jump clears the first obstacle and lands)."""
    ap = AutoPlayer(cfg)
    xs, hs = ap.future_world(scroll, score, wmap, frames)
    phys = Physics(cfg)
    res = {}
    for f in range(2, 120):
        p = panda.copy()
        hit = None
        for i in range(frames):
            phys.step(p, i + 1 == f)
            if ap.hit(p.y, hs[i]):
                hit = i + 1
                break
        res[f] = hit
    return res


@pytest.mark.parametrize("height", [16, 32])
def test_collision_edges_match_the_hitbox(make_game, cfg, height):
    """Jump at every frame around the first obstacle: the ROM dies exactly
    when and only when the model's hitbox (HIT_X0..HIT_X1, feet at HIT_Y1)
    touches a box, including the last frame that is too early and the
    first that is too late."""
    from model import Scroll
    for wait in range(16):   # find a start frame whose first obstacle has this height
        g = make_game(name=f"w{wait}")
        g.tick(wait)
        g.start_run()
        g.tick(40)
        wmap, x = record_world(g, 0, WorldMap())
        first = wmap.obstacles()[0]
        if first.height == height:
            break
        g.stop()
    else:
        pytest.fail(f"no {height} px first obstacle in 16 start frames")
    assert first.start == first_obstacle_start(cfg)
    scroll = Scroll(x, 0, g.u16("world_speed"))   # speed 1.0: no fraction yet
    res = outcomes(cfg, g.panda(), scroll, 0, wmap)
    ok = [f for f, h in res.items() if h is None]
    assert ok, "the model finds no jump that clears the first obstacle"
    lo, hi = min(ok), max(ok)
    assert ok == list(range(lo, hi + 1))
    snap = io.BytesIO()
    g.pb.save_state(snap)
    for f in (lo - 1, lo, (lo + hi) // 2, hi, hi + 1):
        snap.seek(0)
        g.pb.load_state(snap)
        want = res[f]
        died = None
        for n in range(1, 160):
            g.hold("a") if n + 1 == f else g.release("a")
            g.tick()
            if g.state() == cfg.STATE_DEAD:
                died = n
                break
        g.release("a")
        assert died == want, (f"take-off at frame {f} (clear window {lo}..{hi}, "
                              f"height {first.height}): died at {died}, model says {want}")


def test_death_hop_and_fall_follow_the_physics(game, cfg):
    """The death pose hops (vy = -DEAD_HOP_VEL) and falls with GRAVITY and
    MAX_FALL through the ground, stopping once fully below it."""
    game.start_run()
    die_without_input(game)
    y, vy = game.s16("panda_y"), game.s16("panda_vy")
    assert vy == -cfg.DEAD_HOP_VEL
    assert y == (cfg.GROUND_Y - 16) << 8
    sunk = cfg.GROUND_Y << 8
    for n in range(200):
        game.tick()
        if y < sunk:
            vy = min(vy + cfg.GRAVITY, cfg.MAX_FALL)
            y = max(y + vy, 0)
        assert (game.s16("panda_y"), game.s16("panda_vy")) == (y, vy), f"dead frame {n + 1}"
    assert y >= sunk


def test_restart_frames_render_clean(make_game, cfg):
    """Restarting clears the old boxes and messages in the VBlank(s) after
    the press. With a busy map (6+ box columns) the first frames of the new
    run must already show exactly the new map at the new scroll (no stale
    boxes or text), HUD band included."""
    import numpy as np
    from gb import HUD, WORLD, bg_picture
    hx0, hx1 = cfg.PANDA_X + cfg.HIT_X0, cfg.PANDA_X + cfg.HIT_X1
    g = make_game()
    g.start_run(invincible=True)
    g.run_until(lambda g: g.u16("score") >= 12, 5000)

    def busy_and_touching(g):
        ch, scx = g.col_height(), g.u8("world_scx")
        return sum(1 for h in ch if h) >= 6 and (ch[((scx + hx0) & 255) >> 3] or ch[((scx + hx1) & 255) >> 3])

    g.run_until(busy_and_touching, 5000)
    g.write8("debug_invincible", 0)
    g.tick()
    assert g.state() == cfg.STATE_DEAD
    g.tick(cfg.DEAD_DELAY + 5)
    g.hold("start")
    g.tick(1, render=True)
    g.release("start")
    g.tick(1, render=True)
    assert g.state() == cfg.STATE_PLAY
    keep = np.ones(160, dtype=bool)
    keep[24:56] = False                    # the panda
    for i in range(4):
        wscx = g.u8("world_scx")
        g.tick(1, render=True)
        sh = g.shades()
        # The clearing runs on past VBlank into this frame, so compare with
        # the map as it is after the frame: it must have been finished
        # before the beam reached the rows it touches.
        pic = bg_picture(g)
        world = render_band(g, range(48, 136), wscx, 0, pic)
        assert np.array_equal(sh[WORLD][:, keep], world[:, keep]), f"frame {i + 1} of the new run"
        assert np.array_equal(sh[HUD], render_band(g, range(0, 16), 0, 0, pic))
        assert (sh[48:112][:, keep] == 0).all(), "rows 6-13 should be empty sky right after a restart"
