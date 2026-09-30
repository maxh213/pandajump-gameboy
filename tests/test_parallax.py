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


class Tracked:
    """A run whose screen can be matched with the frame it shows: the
    screen after tick k shows frame k-1, so this remembers world_x and the
    number of frames played for the frame on screen. The sky band scrolls
    by (world_speed >> CLOUD_SHIFT) per frame from 0 when a run starts from
    the title, and the speed doesn't change before the first ramp step."""

    def __init__(self, g, cfg):
        self.g, self.cfg = g, cfg
        self.speed = g.u16("world_speed")
        self.played = 0                 # frames of play in RAM
        self.shown_x = self.shown_played = None

    def tick(self, n=1):
        """n frames, the last two rendered."""
        for i in range(n):
            x, played = self.g.u16("world_x"), self.played
            self.g.tick(1, render=i >= n - 2)
            self.played += 1
        self.shown_x, self.shown_played = x, played
        assert self.g.u16("world_speed") == self.speed

    def sky_scx(self, played=None):
        played = self.shown_played if played is None else played
        return (played * (self.speed >> self.cfg.CLOUD_SHIFT)) >> 8


@pytest.fixture
def running(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    t = Tracked(g, cfg)
    # boxes on screen and the start clouds still in view
    while not any(g.col_height()[((g.u8("world_scx") >> 3) + c) & 31] for c in range(8, 18)):
        t.tick()
        assert t.played < 2000, "no boxes on screen"
    t.tick(2)
    return t


def test_world_band_follows_world_x(running, cfg):
    t = running
    g = t.g
    a, xa = g.shades(), t.shown_x
    t.tick(12)
    b = g.shades()
    moved = t.shown_x - xa
    assert moved in (12 * t.speed // 256, 12 * t.speed // 256 + 1)
    found = shifts(a[WORLD], b[WORLD], range(0, 20), [0], x0=56)
    assert found == [(moved, 0)]


def test_sky_band_moves_slower(running, cfg):
    t = running
    g = t.g
    a, xa, sa = g.shades(), t.shown_x, t.sky_scx()
    t.tick(12)
    b = g.shades()
    assert (a[SKY] == 1).any(), "no cloud outline in the sky band"
    found = shifts(a[SKY], b[SKY], range(0, 16), range(-4, 5))
    assert len({dx for dx, _ in found}) == 1, f"ambiguous sky shift {found}"
    dx = found[0][0]
    world = t.shown_x - xa
    assert dx < world
    assert dx == t.sky_scx() - sa, f"sky moved {dx} px while the world moved {world}"


def test_bands_frame_by_frame(running, cfg):
    """Every consecutive pair of frames: the world band moves by exactly the
    shown frame's step of world_x, the sky band by exactly its step of the
    sky scroll (0 or 1 px, a quarter of the world speed), the HUD band and
    window not at all."""
    t = running
    g = t.g
    prev = g.shades()
    world_steps, want_world, sky_steps, want_sky = [], [], [], []
    for _ in range(32):
        x, sky = t.shown_x, t.sky_scx()
        t.tick(1)
        cur = g.shades()
        want_world.append((t.shown_x - x) & 0xFFFF)
        want_sky.append(t.sky_scx() - sky)
        found = shifts(prev[WORLD], cur[WORLD], range(0, 8), [0], x0=56)
        assert len(found) == 1, f"world band shift ambiguous or missing: {found}"
        world_steps.append(found[0][0])
        found = shifts(prev[SKY], cur[SKY], range(0, 4), range(-4, 5))
        assert len({dx for dx, _ in found}) == 1, f"sky band shift ambiguous or missing: {found}"
        sky_steps.append(found[0][0])
        assert np.array_equal(prev[HUD], cur[HUD])
        assert np.array_equal(prev[WINDOW], cur[WINDOW])
        prev = cur
    assert world_steps == want_world
    assert set(want_world) == {t.speed >> 8, (t.speed >> 8) + 1}, "the fraction should carry"
    assert sky_steps == want_sky
    assert set(sky_steps) == {0, 1}


def test_sky_band_bobs_within_0_to_4(running, cfg):
    """Over a whole bob cycle the sky band's picture moves vertically by at
    most 4 lines, and does move."""
    g = running.g
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
    g = running.g
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
    """New clouds are written into the sky band's map (rows 3-4 only, whole
    clouds: the big 4-tile one or the small 3-tile one) as it scrolls, both
    shapes turn up, and rows 2 and 5 stay sky.

    A column written in a VBlank that runs long can still be half written
    when a tick ends (it is off-screen and done early in the next frame),
    so only columns that read the same on two consecutive frames are
    checked."""
    g = make_game()
    g.start_run(invincible=True)
    shapes = {}                        # top tile -> (shape, index, bottom tile, width)
    for i in range(4):
        shapes[cfg.T_CLOUD_TOP + i] = ("big", i, cfg.T_CLOUD_BOT + i, 4)
    for i in range(3):
        shapes[cfg.T_CLOUD2_TOP + i] = ("small", i, cfg.T_CLOUD2_BOT + i, 3)
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
            assert t in shapes, f"unexpected tile {t} in the cloud row"
            shape, i, bottom, width = shapes[t]
            assert b == bottom, f"{shape} cloud column {i} has the wrong bottom tile"
            # inside the window cloud columns are in order: a cloud is only
            # cut at the window's ends (scrolled off, or still being written)
            k = window.index(c)
            if k > 0 and i > 0:
                assert r3[window[k - 1]] == t - 1, f"broken cloud at column {c}: {r3}"
            if k > 0 and i == 0:
                assert r3[window[k - 1]] == cfg.T_SKY, f"clouds run together at column {c}: {r3}"
            if k < 21 and window[k + 1] in stable:
                want = t + 1 if i < width - 1 else cfg.T_SKY
                assert r3[window[k + 1]] == want, f"broken cloud at column {c}: {r3}"
            if i == 0:
                seen.add((shape, frame // 60 * 1000 + c))
    starts = {(shape, s % 1000) for shape, s in seen}
    assert len(starts) >= 6, f"clouds seen at map columns {sorted(starts)} only"
    assert {shape for shape, _ in starts} == {"big", "small"}, "only one cloud shape"
