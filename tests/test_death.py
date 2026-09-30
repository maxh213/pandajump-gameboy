"""Collision, death and restart (docs/DESIGN.md "Gameplay", "States and
controls")."""
import copy
import io

import pytest

from gb import dark_text, find_text, record_world, render_band, sprite_text
from model import AutoPlayer, Physics, WorldMap


def die_without_input(g, cap=2000):
    frames = g.run_until(lambda g: g.state() != 1, cap, what="death")
    return frames


def first_obstacle_start(cfg, start_x):
    """World tile of a run's first obstacle: the first column generated is
    (world_x >> 3) + 22, then FIRST_GAP empty ones."""
    return (start_x >> 3) + 22 + cfg.FIRST_GAP


def test_no_input_dies_at_first_obstacle(game, cfg):
    game.start_run()
    x0 = game.u16("world_x")
    hx1 = cfg.PANDA_X + cfg.HIT_X1
    last = None
    while True:
        game.tick()
        if game.state() != cfg.STATE_PLAY:
            break
        last = game.u16("world_x")
    assert game.state() == cfg.STATE_DEAD
    wx = game.u16("world_x")
    start = first_obstacle_start(cfg, x0)
    # the first frame the hitbox's right edge reaches the first box column
    assert last + hx1 < start * 8 <= wx + hx1
    assert game.col_height()[start & 31] == 16, "the first obstacle is always 1 box high"
    assert game.u16("score") == 0


def frames_to_sink(cfg, y):
    """Dead frames until the panda, dying at panda_y = y, has sunk out of
    sight (the death hop, then GRAVITY/MAX_FALL down to GROUND_Y << 8)."""
    vy, k = -cfg.DEAD_HOP_VEL, 0
    while y < cfg.GROUND_Y << 8:
        vy = min(vy + cfg.GRAVITY, cfg.MAX_FALL)
        y = max(y + vy, 0)
        k += 1
    return k


def panda_on_screen(g, cfg):
    return any(-8 < y < 144 for (y, x, t, a) in g.oam()[cfg.OAM_PANDA:cfg.OAM_PANDA + 4])


def air_death(g, cfg):
    """Run invincibly to a 2-box column, then jump into its side (take-off
    when it is 12 px from the hitbox), the death the panda's hop used to
    carry over the text. Returns once dead."""
    hx0, hx1 = cfg.PANDA_X + cfg.HIT_X0, cfg.PANDA_X + cfg.HIT_X1
    g.start_run(invincible=True)
    wmap, x = record_world(g, 0, WorldMap())
    while True:
        ahead = [o for o in wmap.obstacles(complete_only=False) if o.right_edge > x + hx0]
        if ahead and ahead[0].height == 32 and ahead[0].start * 8 - (x + hx1) in range(13, 16):
            break
        wmap, x = record_world(g, 1, wmap)
        assert x < 30000
    g.write8("debug_invincible", 0)
    g.tap("a")
    die_without_input(g)
    assert g.s16("panda_y") < (cfg.GROUND_Y - 16) << 8, "meant to die in the air"


@pytest.mark.parametrize("where", ["ground", "air"])
def test_messages_wait_until_the_panda_has_sunk(make_game, cfg, where):
    """GAME OVER (sprites at OVER_TEXT_Y) and the score (BG row
    OVER_SCORE_ROW) appear on the frame the dead panda has sunk out of
    sight, never while it is still on screen, centred, with sky between them."""
    g = make_game()
    if where == "ground":
        g.start_run()
        die_without_input(g)
    else:
        air_death(g, cfg)
    k = frames_to_sink(cfg, g.s16("panda_y"))
    scx = g.u8("world_scx")
    score = g.u16("score")                # a fresh cartridge: any points are a new best
    score_text = dark_text(cfg, f"NEW BEST! {score}" if score else "SCORE 0")
    for n in range(1, k):
        g.tick()
        assert panda_on_screen(g, cfg) or n == k
        assert sprite_text(g, cfg.OAM_OVER, cfg.OAM_OVER_END) is None, f"GAME OVER {n} frames after dying"
        assert find_text(g, cfg.OVER_SCORE_ROW, score_text, scx) is None, f"score {n} frames after dying"
    g.tick()
    assert not panda_on_screen(g, cfg)
    text, x, y = sprite_text(g, cfg.OAM_OVER, cfg.OAM_OVER_END)
    assert (text, y) == ("GAME OVER", cfg.OVER_TEXT_Y)
    assert x + 4 * len(text) == 80, "GAME OVER is not centred"
    x = find_text(g, cfg.OVER_SCORE_ROW, score_text, scx)
    assert x is not None, "the score should be in the same frame's VBlank writes"
    assert abs(x + 4 * len(score_text) - 80) <= 4, "the score is not centred"
    # The glyphs are 7 px tall (the font's bottom row is empty). Between the
    # lines, and between PRESS START and the top of a 2-box column (y 80,
    # and the column the panda ran into is always under the text), there
    # must be clear sky; the clouds (map rows 3-4) end above y 40.
    ink = 7
    score_y = cfg.OVER_SCORE_ROW * 8
    assert score_y - (cfg.OVER_TEXT_Y + ink) >= 4, "GAME OVER crowds the score"
    assert cfg.OVER_PROMPT_Y - (score_y + ink) >= 4, "the score crowds PRESS START"
    assert 80 - (cfg.OVER_PROMPT_Y + ink) >= 4, "PRESS START sits on a 2-box column"
    assert cfg.OVER_TEXT_Y >= 40, "GAME OVER over the clouds"


def test_press_start_comes_prompt_delay_frames_later_and_blinks(game, cfg):
    game.start_run()
    die_without_input(game)
    game.run_until(lambda g: sprite_text(g, cfg.OAM_OVER, cfg.OAM_OVER_END), 100, what="GAME OVER")
    for n in range(1, cfg.PROMPT_DELAY):
        game.tick()
        assert sprite_text(game, cfg.OAM_TEXT, cfg.OAM_TEXT_END) is None, f"PRESS START {n} frames early"
    shown = []
    for _ in range(3 * cfg.BLINK_PERIOD):
        game.tick()
        p = sprite_text(game, cfg.OAM_TEXT, cfg.OAM_TEXT_END)
        if p:
            assert p == ("PRESS START", 36, cfg.OVER_PROMPT_Y)
        shown.append(p is not None)
    on, off = cfg.BLINK_ON, cfg.BLINK_PERIOD - cfg.BLINK_ON
    assert shown == ([True] * on + [False] * off) * 3, "PRESS START should blink from when it appears"
    assert sprite_text(game, cfg.OAM_OVER, cfg.OAM_OVER_END)[0] == "GAME OVER"


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


def prompt_frame(g, cfg):
    """Frames after the death frame until the one that shows PRESS START."""
    return frames_to_sink(cfg, g.s16("panda_y")) + cfg.PROMPT_DELAY


@pytest.mark.parametrize("button", ["start", "a"])
def test_input_ignored_until_press_start_shows(game, cfg, button):
    game.start_run()
    die_without_input(game)
    last = prompt_frame(game, cfg) - 1
    # presses seen by frames 2, 4, ... up to the frame before the prompt
    n = 0
    while n + 2 <= last:
        register_press_at(game, button, 2)
        n += 2
        assert game.state() == cfg.STATE_DEAD, f"a press {n} frames after dying restarted"
    if n < last:
        register_press_at(game, button, last - n)
        assert game.state() == cfg.STATE_DEAD, "a press the frame before PRESS START restarted"
    assert sprite_text(game, cfg.OAM_TEXT, cfg.OAM_TEXT_END) is None


@pytest.mark.parametrize("button", ["start", "a"])
def test_press_on_the_prompt_frame_restarts(game, cfg, button):
    """Input counts from the very frame PRESS START appears."""
    game.start_run()
    die_without_input(game)
    register_press_at(game, button, prompt_frame(game, cfg))
    assert game.state() == cfg.STATE_PLAY


@pytest.mark.parametrize("button", ["a", "start"])
def test_button_held_from_the_run_does_not_restart(game, cfg, button):
    """Holding the button through the death screen never restarts (only a
    new press does): mashing or holding A to jump when the panda died can't
    skip the score."""
    game.start_run()
    die_without_input(game)
    game.hold(button)
    game.tick(prompt_frame(game, cfg) + cfg.BLINK_PERIOD + 10)
    assert sprite_text(game, cfg.OAM_TEXT, cfg.OAM_TEXT_END), "PRESS START should be up"
    assert game.state() == cfg.STATE_DEAD
    game.release(button)
    game.tick()
    assert game.state() == cfg.STATE_DEAD
    game.tap(button)
    assert game.state() == cfg.STATE_PLAY


def test_restart_is_a_fresh_run(game, cfg):
    game.start_run()
    die_without_input(game)
    old_x = game.u16("world_x")
    game.tick(prompt_frame(game, cfg) + 5)
    assert game.u16("world_x") == old_x, "the world should stand still while dead"
    game.tap("start")
    assert game.state() == cfg.STATE_PLAY
    assert game.u16("score") == 0
    assert game.col_height() == [0] * 32
    x0 = game.u16("world_x")
    assert x0 == old_x & 15, "the new run should keep the ground's 16 px phase"
    assert (game.u8("world_sub"), game.u16("world_speed")) == (0, cfg.SPEED_BASE)
    assert (game.s16("panda_y"), game.s16("panda_vy"), game.u8("panda_on_ground"),
            game.u8("jumps_used")) == ((cfg.GROUND_Y - 16) << 8, 0, 1, 0)
    game.tick(2)
    # Old boxes are gone from the 22 map columns the new run shows before
    # the generator reaches them; the other 10 are rewritten before they
    # scroll into view (checked below). Messages are gone too.
    first = x0 >> 3
    for row in range(10, 14):
        r = game.bg_row(row)
        assert [r[(first + c) & 31] for c in range(22)] == [cfg.T_SKY] * 22, f"row {row} not cleared"
    for row in range(6, 10):
        assert game.bg_row(row) == [cfg.T_SKY] * 32, f"message row {row} not cleared"
    assert game.bg_row(1)[1:6] == [cfg.T_FONT_DIGIT] + [cfg.T_SKY] * 4
    # and it plays the same way: the first obstacle is FIRST_GAP tiles in,
    # with no old box ever in view
    hx1 = cfg.PANDA_X + cfg.HIT_X1
    last = x0
    while True:
        game.tick()
        if game.state() != cfg.STATE_PLAY:
            break
        last = game.u16("world_x")
        ch, left = game.col_height(), (game.u8("world_scx") >> 3)
        rows = [game.bg_row(row) for row in range(10, 14)]
        for c in range(left, left + 21):
            if not ch[c & 31]:
                assert all(r[c & 31] == cfg.T_SKY for r in rows), f"an old box at map column {c & 31}"
    assert last + hx1 < first_obstacle_start(cfg, x0) * 8 <= game.u16("world_x") + hx1


def outcomes(cfg, panda, scroll, score, wmap, frames=160):
    """For every take-off frame f, the model's first frame of contact (or
    None when the jump clears the first obstacle and lands)."""
    ap = AutoPlayer(cfg)
    xs, hs = ap.future_world(scroll, score, wmap, frames)
    phys = Physics(cfg)
    res = {}
    for f in range(2, min(120, frames)):
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
    """Jump at every frame around an obstacle: the ROM dies exactly when
    and only when the model's hitbox (HIT_X0..HIT_X1, feet at HIT_Y1)
    touches a box, including the last frame that is too early and the
    first that is too late.

    The run goes on invincibly (no jumps) until an obstacle of this height
    is 88-95 px ahead. The world for the next 200 frames is then read by
    running on from a save state (it doesn't depend on the panda), and each
    jump is tried from that save state with collisions on, up to the frame
    the hitbox could first reach the obstacle after it."""
    hx0, hx1 = cfg.PANDA_X + cfg.HIT_X0, cfg.PANDA_X + cfg.HIT_X1
    g = make_game()
    g.start_run(invincible=True)
    wmap, x = record_world(g, 0, WorldMap())
    while True:
        ahead = [o for o in wmap.obstacles(complete_only=False) if o.right_edge > x + hx0]
        if ahead and ahead[0].height == height and 88 <= ahead[0].start * 8 - (x + hx1) < 96:
            break
        wmap, x = record_world(g, 1, wmap)
        assert x < 30000, f"no {height} px obstacle came"
    scroll, score, panda = g.scroll(), g.u16("score"), g.panda()
    snap = io.BytesIO()
    g.pb.save_state(snap)
    known, _ = record_world(g, 200, copy.deepcopy(wmap))
    ahead = [o for o in known.obstacles() if o.right_edge > x + hx0]
    first, second = ahead[0], ahead[1]
    assert first.height == height
    ap = AutoPlayer(cfg)
    xs, _ = ap.future_world(scroll, score, known, 400)
    horizon = next(i for i, wx in enumerate(xs) if wx + hx1 >= second.start * 8)
    res = outcomes(cfg, panda, scroll, score, known, frames=horizon)
    ok = [f for f, h in res.items() if h is None]
    assert ok, "the model finds no jump that clears the obstacle"
    lo, hi = min(ok), max(ok)
    assert ok == list(range(lo, hi + 1))
    for f in (lo - 1, lo, (lo + hi) // 2, hi, hi + 1):
        snap.seek(0)
        g.pb.load_state(snap)
        g.write8("debug_invincible", 0)
        want = res[f]
        died = None
        for n in range(1, horizon + 1):
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
    """Restarting clears the old boxes and messages in the VBlank after the
    press. With a busy map (6+ box columns) the first frames of the new run
    must already show exactly the new map at the new scroll (no stale boxes
    or text), HUD band included, and that VBlank's tile work must be done
    early in the frame (the message row is at line 56, the boxes from line
    80): hooks on world_vram (entered when the text is done) and
    sound_update (entered when the boxes are done) read LY."""
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
    g.tick(prompt_frame(g, cfg) + 5, render=True)
    ground = g.shades()[112:136].copy()
    calls = []
    for name in ("world_start_run", "world_vram", "sound_update"):
        _bank, addr = g.pb.symbol_lookup("_" + name)
        g.pb.hook_register(0, addr, lambda n: calls.append((n, g.pb.memory[0xFF44])), name)
    g.hold("start")
    g.tick(1, render=True)
    g.release("start")
    g.tick(1, render=True)
    assert g.state() == cfg.STATE_PLAY
    # the panda is back on its feet in the new run's first frame
    floor = cfg.GROUND_Y - 16
    panda = [(y, x) for (y, x, t, a) in g.oam()[cfg.OAM_PANDA:cfg.OAM_PANDA + 4]]
    assert min(y for y, _ in panda) == floor and min(x for _, x in panda) == cfg.PANDA_X, panda
    keep = np.ones(160, dtype=bool)
    keep[24:56] = False                    # the panda
    for i in range(4):
        wscx = g.u8("world_scx")
        g.tick(1, render=True)
        sh = g.shades()
        if i == 0:
            assert np.array_equal(sh[112:136], ground), "the ground moved when the run restarted"
            sky = render_band(g, range(floor, floor + 16), wscx, 0)[:, 32:48]
            assert (sh[floor:floor + 16, 32:48] != sky).any(), "no panda on the new run's first frame"
        # The clearing runs on past VBlank into this frame, so compare with
        # the map as it is after the frame: it must have been finished
        # before the beam reached the rows it touches.
        pic = bg_picture(g)
        world = render_band(g, range(48, 136), wscx, 0, pic)
        assert np.array_equal(sh[WORLD][:, keep], world[:, keep]), f"frame {i + 1} of the new run"
        assert np.array_equal(sh[HUD], render_band(g, range(0, 16), 0, 0, pic))
        assert (sh[48:112][:, keep] == 0).all(), "rows 6-13 should be empty sky right after a restart"
    start = [name for name, _ in calls].index("world_start_run")
    job = dict(calls[start + 1:start + 3])   # the next VBlank's, in order
    assert set(job) == {"world_vram", "sound_update"}, calls
    for name, ly in job.items():
        assert ly >= 144 or ly < 40, f"the restart VBlank's tile work still running at line {ly} ({name})"
