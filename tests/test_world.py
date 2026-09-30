"""The world map (docs/DESIGN.md "Screen layout", "Tiles and VRAM"): boxes
are BG tiles mirrored by col_height, and the ground and sky rows never
change during a run."""
from gb import unwrap16
from model import WorldMap


def expected_column(cfg, height, right_half):
    """Rows 10-13 of a map column."""
    sky = cfg.T_SKY
    if height == 0:
        return [sky] * 4
    if right_half:
        low = [cfg.T_BOX_TR, cfg.T_BOX_BR]
        high = [cfg.T_BOX2_TR, cfg.T_BOX2_BR]
    else:
        low = [cfg.T_BOX_TL, cfg.T_BOX_BL]
        high = [cfg.T_BOX2_TL, cfg.T_BOX2_BL]
    return (high if height == 32 else [sky, sky]) + low


def test_map_mirrors_col_height(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    wmap = WorldMap()
    raw = x = g.u16("world_x")
    ground = [[cfg.T_GRASS_0, cfg.T_GRASS_1], [cfg.T_GROUND_A0, cfg.T_GROUND_A1],
              [cfg.T_GROUND_B0, cfg.T_GROUND_B1], [cfg.T_GROUND_B0, cfg.T_GROUND_B1]]
    checked = 0
    for frame in range(4000):
        g.tick()
        new = g.u16("world_x")
        x += unwrap16(raw, new)
        raw = new
        wmap.record(x, g.col_height())
        if frame < 4:
            continue                       # the run's first clears are still going
        newest = (x >> 3) + 21
        starts = {}
        for o in wmap.obstacles(complete_only=False):
            for k in range(o.width):
                starts[o.start + k] = k
        rows = [g.bg_row(r) for r in range(10, 14)]
        for tile in range(newest - 31, newest):    # the newest column may still be in flight
            c = tile & 31
            h = wmap.height(tile)
            assert g.col_height()[c] == h
            want = expected_column(cfg, h, starts.get(tile, 0) % 2 == 1)
            got = [rows[r][c] for r in range(4)]
            assert got == want, f"frame {frame}: map column {c} (tile {tile}, {h} px) is {got}"
            checked += 1
        for r, pair in zip(range(14, 18), ground):
            assert g.bg_row(r) == pair * 16, f"ground row {r} changed"
        for r in range(6, 10):
            assert g.bg_row(r) == [cfg.T_SKY] * 32, f"row {r} should stay sky during a run"
    assert g.u16("score") > cfg.DOUBLE_SCORE + 5
    assert any(o.width == 4 for o in wmap.obstacles())
    assert checked > 100000
