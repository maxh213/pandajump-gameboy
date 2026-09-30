"""Parallax (docs/DESIGN.md "Screen layout"): lines 0-15 are a static HUD,
lines 16-47 the sky band scrolling at world speed >> CLOUD_SHIFT and
bobbing (SCY 0-4), lines 48-135 the world band scrolling with world_x,
136-143 the window. Checked on the rendered screen: how far each band's
picture moved between two frames."""
import numpy as np
import pytest

from gb import HUD, SKY, WINDOW, WORLD, render_band


def shifts(a, b, dxs, dys, x0=0):
    """All (dx, dy) with b[y, x] == a[y + dy, x + dx] on the overlap
    (content moved left by dx, up by dy). Columns left of x0 are ignored
    (sprites)."""
    h, w = a.shape
    out = []
    for dy in dys:
        for dx in dxs:
            ya, yb = max(0, dy), max(0, -dy)
            n = h - abs(dy)
            m = w - x0 - dx
            if n <= 0 or m <= 0:
                continue
            pa = a[ya:ya + n, x0 + dx:x0 + dx + m]
            pb = b[yb:yb + n, x0:x0 + m]
            if np.array_equal(pa, pb):
                out.append((dx, dy))
    return out


@pytest.fixture
def running(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    # boxes on screen and the start clouds still in view
    g.run_until(lambda g: any(g.col_height()[((g.u8("world_scx") >> 3) + c) & 31] for c in range(8, 18)),
                2000, what="boxes on screen")
    g.tick(2, render=True)
    return g


def test_world_band_follows_world_x(running, cfg):
    g = running
    a = g.shades()
    wx_a = g.u16("world_x")
    n = 12
    g.tick(n, render=True)
    b = g.shades()
    moved = g.u16("world_x") - wx_a
    assert moved == n * g.u16("world_speed") // 256
    found = shifts(a[WORLD], b[WORLD], range(0, 16), [0], x0=56)
    assert found == [(moved, 0)]


def test_sky_band_moves_slower(running, cfg):
    g = running
    a = g.shades()
    n = 12
    g.tick(n, render=True)
    b = g.shades()
    assert (a[SKY] == 1).any(), "no cloud outline in the sky band"
    found = shifts(a[SKY], b[SKY], range(0, 16), range(-4, 5))
    assert len({dx for dx, _ in found}) == 1, f"ambiguous sky shift {found}"
    dx = found[0][0]
    world = n * g.u16("world_speed") // 256
    assert dx < world
    assert dx == (n * (g.u16("world_speed") >> cfg.CLOUD_SHIFT)) // 256, \
        f"sky moved {dx} px while the world moved {world}"


def test_bands_frame_by_frame(running, cfg):
    """Every consecutive pair of frames: the world band moves by exactly the
    frame's world_step, the sky band by 0 or 1 px (a quarter of the world
    speed on average), the HUD band and window not at all."""
    g = running
    prev = g.shades()
    world_steps, sky_steps = [], []
    prev_x = g.u16("world_x")
    for _ in range(32):
        g.tick(1, render=True)
        cur = g.shades()
        # the screen shows the previous frame's scroll
        step = (g.u16("world_x") - prev_x) & 0xFFFF   # this frame's step
        prev_x = g.u16("world_x")
        found = shifts(prev[WORLD], cur[WORLD], range(0, 8), [0], x0=56)
        assert len(found) == 1, f"world band shift ambiguous or missing: {found}"
        world_steps.append(found[0][0])
        sky = shifts(prev[SKY], cur[SKY], range(0, 4), range(-4, 5))
        assert len({dx for dx, _ in sky}) == 1, f"sky band shift ambiguous or missing: {sky}"
        sky_steps.append(sky[0][0])
        assert np.array_equal(prev[HUD], cur[HUD])
        assert np.array_equal(prev[WINDOW], cur[WINDOW])
        prev = cur
        assert step == 1
    assert world_steps == [1] * 32
    assert set(sky_steps) <= {0, 1}
    assert sum(sky_steps) == 32 * (g.u16("world_speed") >> cfg.CLOUD_SHIFT) // 256


def test_sky_band_bobs_within_0_to_4(running, cfg):
    """Over a whole bob cycle the sky band's picture moves vertically by at
    most 4 lines, and does move."""
    g = running
    base = g.shades()[SKY]
    dys = set()
    for _ in range(16):
        g.tick(cfg.CLOUD_BOB_FRAMES, render=True)
        b = g.shades()[SKY]
        found = shifts(base, b, range(0, 60), range(-4, 5))
        assert found, "sky band content no longer matches a shifted copy of itself"
        dys |= {dy for _, dy in found}
    assert max(dys) - min(dys) >= 3, f"no visible bob: {sorted(dys)}"
    assert max(dys) - min(dys) <= 4


def test_hud_and_window_are_static(running):
    g = running
    a = g.shades()
    score = g.u16("score")
    g.tick(10, render=True)
    assert g.u16("score") == score
    b = g.shades()
    assert np.array_equal(a[HUD], b[HUD])
    assert np.array_equal(a[WINDOW], b[WINDOW])


def test_screen_matches_vram_render(make_game, cfg):
    """Each band on screen is exactly the BG map drawn with that band's
    scroll for the frame the RAM describes: HUD at 0, sky at the sky
    band's scroll (world speed >> CLOUD_SHIFT per frame since the run
    started, plus a 0-4 bob), world at world_scx, through the speed ramp.
    Sprite columns are left out. The screen after tick k+1 shows the logic
    of tick k."""
    from gb import bg_picture
    g = make_game()
    g.start_run(invincible=True)
    sky_pos, speed = 0, g.u16("world_speed")
    keep = np.ones(160, dtype=bool)
    keep[24:56] = False                      # panda and dust puff
    checked = 0
    for frame in range(1, 3000):
        sample = frame % 5 == 1 and frame > 5
        if sample:
            # what tick k+1 draws: frame k's scroll and the map as it stood
            # after frame k's VBlank writes (frame k+1's writes come later)
            wscx = g.u8("world_scx")
            sscx = (sky_pos >> 8) & 255
            pic = bg_picture(g)
        g.tick(1, render=frame % 5 in (0, 1))
        sky_pos = (sky_pos + (speed >> cfg.CLOUD_SHIFT)) & 0xFFFF
        speed = g.u16("world_speed")
        if not sample:
            continue
        sh = g.shades()
        hud = render_band(g, range(0, 16), 0, 0, pic)
        assert np.array_equal(sh[HUD][:, keep], hud[:, keep]), f"frame {frame}: HUD band"
        world = render_band(g, range(48, 136), wscx, 0, pic)
        assert np.array_equal(sh[WORLD][:, keep], world[:, keep]), f"frame {frame}: world band at scx {wscx}"
        ok = [bob for bob in range(5)
              if np.array_equal(sh[SKY][:, keep], render_band(g, range(16, 48), sscx, bob, pic)[:, keep])]
        assert ok, f"frame {frame}: sky band does not match scx {sscx} with any bob 0-4"
        checked += 1
    assert g.u16("world_speed") > cfg.SPEED_BASE, "the check should reach the speed ramp"
    assert checked > 500


def test_clouds_keep_coming(make_game, cfg):
    """New clouds are written into the sky band's map (rows 3-4 only,
    whole 4-tile clouds) as it scrolls, and rows 2 and 5 stay sky.

    A column written in a VBlank that runs long can still be half written
    when a tick ends (it is off-screen and done early in the next frame),
    so only columns that read the same on two consecutive frames are
    checked."""
    g = make_game()
    g.start_run(invincible=True)
    tops = {cfg.T_CLOUD_TOP + i for i in range(4)}
    seen = set()
    sky_pos = 0          # the sky band's 8.8 scroll, as world_clouds() advances it
    speed = g.u16("world_speed")
    prev_rows = None
    for frame in range(1, 3601):
        g.tick()
        sky_pos = (sky_pos + (speed >> cfg.CLOUD_SHIFT)) & 0xFFFF
        speed = g.u16("world_speed")
        if frame % 60 and (frame % 60 != 1 or prev_rows is None):
            continue
        rows = [g.bg_row(r) for r in (2, 3, 4, 5)]
        if frame % 60 == 0:
            prev_rows = rows
            continue
        r2, r3, r4, r5 = rows
        tile = (sky_pos >> 8) >> 3
        # columns from the left of the screen to the newest one written
        window = [(tile + k) & 31 for k in range(22)]
        stable = [c for c in window if all(prev_rows[i][c] == rows[i][c] for i in range(4))]
        for c in stable:
            assert r2[c] == cfg.T_SKY and r5[c] == cfg.T_SKY, f"sky band rows 2/5 not sky at column {c}"
            t, b = r3[c], r4[c]
            if t == cfg.T_SKY:
                assert b == cfg.T_SKY, f"cloud bottom without top at column {c}"
                continue
            assert t in tops, f"unexpected tile {t} in the cloud row"
            i = t - cfg.T_CLOUD_TOP
            assert b == cfg.T_CLOUD_BOT + i
            # inside the window cloud columns are in order: a cloud is only
            # cut at the window's ends (scrolled off, or still being written)
            k = window.index(c)
            if k > 0 and i > 0:
                assert r3[window[k - 1]] == t - 1, f"broken cloud at column {c}: {r3}"
            if k < 21 and i < 3 and window[k + 1] in stable:
                assert r3[window[k + 1]] == t + 1, f"broken cloud at column {c}: {r3}"
            if i == 0:
                seen.add(frame // 60 * 1000 + c)
    starts = {s % 1000 for s in seen}
    assert len(starts) >= 6, f"clouds seen at map columns {sorted(starts)} only"
