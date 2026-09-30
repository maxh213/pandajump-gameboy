"""Sprites (docs/DESIGN.md "Tiles and VRAM", art/panda.png and art/fx.png
frame tables): which panda frame is shown when, the dust puff, the
sprite tile range and the hardware limits."""
from gb import metasprites

RUN_FRAMES = range(0, 6)
JUMP, DOUBLE, FALL, DEAD = 6, 7, 8, 9


def panda_frame(g, cfg, frames):
    """Which art/panda.png frame OAM 0-3 shows, placed at (PANDA_X, panda_y)."""
    top = g.s16("panda_y") >> 8
    items = []
    for (y, x, t, a) in g.oam()[cfg.OAM_PANDA:cfg.OAM_PANDA + 4]:
        if -8 < y < 144:
            items.append((y - top, x - cfg.PANDA_X, t - cfg.S_PANDA_BASE))
    sig = tuple(sorted(items))
    hits = [f for f, s in frames.items() if s == sig]
    assert len(hits) == 1, f"OAM {sig} is not one panda frame"
    return hits[0]


def expected_pose(g):
    if not g.u8("panda_on_ground"):
        if g.s16("panda_vy") < 0:
            return DOUBLE if g.u8("jumps_used") == 2 else JUMP
        return FALL
    return None     # a run frame


def test_panda_frames_follow_the_state(make_game, cfg):
    frames = metasprites("panda")
    g = make_game()
    g.start_run(invincible=True)
    seen = []
    for n in range(260):
        if n in (20, 40, 120, 200):     # jump, double jump, jump, jump
            g.hold("a")
        else:
            g.release("a")
        g.tick()
        f = panda_frame(g, cfg, frames)
        want = expected_pose(g)
        if want is None:
            assert f in RUN_FRAMES, f"frame {n}: on the ground but showing panda frame {f}"
        else:
            assert f == want, f"frame {n}: showing panda frame {f}, expected {want}"
        seen.append(f)
    assert {JUMP, DOUBLE, FALL} <= set(seen)


def test_run_cycle_speed(make_game, cfg):
    """RUN_ANIM_STEP (8.8 px) of travel per run frame: all 6 run frames in
    order, the next one exactly when the travel added up at world_speed per
    frame passes another RUN_ANIM_STEP (from whatever remainder the title
    left)."""
    frames = metasprites("panda")
    g = make_game()
    g.start_run(invincible=True)
    speed = g.u16("world_speed")
    shown = []
    for _ in range(80):
        g.tick()
        shown.append(panda_frame(g, cfg, frames))
    assert g.u16("world_speed") == speed
    changes = [i for i in range(1, len(shown)) if shown[i] != shown[i - 1]]
    for i in changes:
        assert shown[i] == (shown[i - 1] + 1) % 6

    def predicted(acc):
        out = []
        for i in range(1, len(shown)):
            acc += speed
            if acc >= cfg.RUN_ANIM_STEP:
                acc -= cfg.RUN_ANIM_STEP
                out.append(i)
        return out

    assert any(predicted(a) == changes for a in range(cfg.RUN_ANIM_STEP)), f"run frames change at {changes}"
    assert len(changes) >= len(shown) * speed // cfg.RUN_ANIM_STEP - 1


def test_dead_pose_then_behind_ground(make_game, cfg):
    frames = metasprites("panda")
    g = make_game()
    g.start_run()
    g.run_until(lambda g: g.state() == cfg.STATE_DEAD, 400)
    floor = (cfg.GROUND_Y - 16) << 8
    behind = False
    for _ in range(60):
        g.tick()
        oam = g.oam()[cfg.OAM_PANDA:cfg.OAM_PANDA + 4]
        if all(not -8 < y < 144 for (y, x, t, a) in oam):
            break                               # fallen away and hidden
        assert panda_frame(g, cfg, frames) == DEAD
        if g.s16("panda_y") > floor:
            assert all(a & 0x80 for (y, x, t, a) in oam), "below the ground line but drawn in front of it"
            behind = True
    assert behind


def fx_sprite(g, cfg):
    y, x, t, a = g.oam()[cfg.OAM_FX]
    if -8 < y < 144 and -8 < x < 168:
        return y, x, t
    return None


def test_dust_puff_on_double_jump_and_landing(make_game, cfg):
    fx_tiles = {cfg.S_FX_BASE + i for i in range(4)}
    g = make_game()
    g.start_run(invincible=True)
    g.tick(10)
    g.tap("a")
    g.tick(20)
    assert fx_sprite(g, cfg) is None
    g.hold("a")
    g.tick()
    g.release("a")
    g.tick()                          # the double jump happens in this frame
    assert g.u8("jumps_used") == 2
    y0 = g.s16("panda_y") >> 8
    puffs = []
    for _ in range(4 * cfg.FX_FRAME_TIME + 2):
        puffs.append(fx_sprite(g, cfg))
        g.tick()
    shown = [p for p in puffs if p]
    assert shown, "no dust puff on the double jump"
    assert all(t in fx_tiles for (_, _, t) in shown)
    assert y0 + 8 <= shown[0][0] <= y0 + 16, "the puff starts under the panda"
    assert cfg.PANDA_X <= shown[0][1] <= cfg.PANDA_X + 8
    assert puffs[-1] is None, "the puff should be gone after its 4 frames"
    # landing: the puff starts at the heel, where it isn't behind the legs
    g.run_until(lambda g: g.u8("panda_on_ground"), 200, render=True)
    landing = fx_sprite(g, cfg)
    assert landing is not None and landing[2] in fx_tiles, "no dust puff on landing"
    assert landing[0] == cfg.GROUND_Y - 8
    # made at PANDA_X - 4, and already moved with the ground that frame
    assert landing[1] == cfg.PANDA_X - 4 - g.u8("world_step")
    g.tick(1, render=True)                # the landing frame on screen
    y = cfg.GROUND_Y - 8
    assert (g.shades()[y:y + 8, cfg.PANDA_X - 4:cfg.PANDA_X] != 0).sum() >= 3, \
        "the landing puff's first frame is not visible left of the panda"
    xs = []
    for _ in range(8):
        g.tick()
        p = fx_sprite(g, cfg)
        if p:
            xs.append(p[1])
    assert xs == sorted(xs, reverse=True) and xs[0] > xs[-1], "the puff should drift left with the ground"


def visible(g):
    return [(y, x, t) for (y, x, t, a) in g.oam() if -8 < y < 144 and -8 < x < 160]


def test_sprite_tiles_and_limits(make_game, cfg):
    g = make_game()
    seen = set()

    def check(n, text_allowed):
        for _ in range(n):
            g.tick()
            sprites = visible(g)
            for (y, x, t) in sprites:
                assert t < 128, f"sprite tile {t} would read BG tiles 128+ (the title logo)"
                seen.add(t)
            for line in range(144):
                on = sum(1 for (y, x, t) in sprites if y <= line < y + 8)
                assert on <= 10, f"{on} sprites on line {line}"
            for i, (y, x, t, a) in enumerate(g.oam()):
                used = -8 < y < 144 and -8 < x < 160
                if i >= cfg.OAM_USED:
                    assert not used, f"OAM {i} is in use"
                if cfg.OAM_TEXT <= i < cfg.OAM_OVER_END and not text_allowed:
                    assert not used, f"text sprite {i} left on screen"

    check(80, True)                   # title with PRESS START
    g.start_run(invincible=True)
    check(20, False)
    g.tap("a")
    check(20, False)
    g.tap("a")                        # double jump: dust puff
    check(80, False)                  # landing: dust puff
    g.write8("debug_invincible", 0)
    g.run_until(lambda g: g.state() == cfg.STATE_DEAD, 2000)
    check(180, True)                  # death pose and fall, GAME OVER, PRESS START
    assert any(cfg.S_FX_BASE <= t < cfg.S_TEXT_BASE for t in seen), "the dust puff never showed"
    assert any(t >= cfg.S_TEXT_BASE for t in seen), "PRESS START never showed"
    g.tick(cfg.BLINK_PERIOD)
    g.tap("start")
    check(20, False)                  # the new run: no text sprites left


def test_panda_sprite_at_panda_x_and_panda_y(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    for n in range(120):
        if n in (10, 40):
            g.hold("a")
        else:
            g.release("a")
        g.tick()
        panda = [(y, x) for (y, x, t, a) in g.oam()[cfg.OAM_PANDA:cfg.OAM_PANDA + 4]]
        assert min(x for _, x in panda) == cfg.PANDA_X
        assert min(y for y, _ in panda) == g.s16("panda_y") >> 8
