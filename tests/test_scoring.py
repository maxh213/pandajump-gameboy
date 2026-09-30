"""Scoring (docs/DESIGN.md "Gameplay"): +1 when an obstacle's right edge
passes the left edge of the panda's hitbox, a double column counting once.

The expected score is counted independently: the columns are recorded from
col_height as they are generated, grouped into obstacles (runs of box
columns), and an obstacle counts once its right edge is at or left of the
hitbox's left edge (PANDA_X + HIT_X0 on screen)."""
import bisect

from gb import score_row, unwrap16
from model import WorldMap


def test_score_once_per_obstacle(make_game, cfg):
    g = make_game()
    g.start_run(invincible=True)
    hx0 = cfg.PANDA_X + cfg.HIT_X0
    wmap = WorldMap()
    raw, x = 0, 0
    samples = []           # (world_x, score, score row tiles) after each frame
    target = 45            # past DOUBLE_SCORE, so double columns are in
    while not samples or samples[-1][1] < target:
        g.tick()
        new = g.u16("world_x")
        x += unwrap16(raw, new)
        raw = new
        wmap.record(x, g.col_height())
        samples.append((x, g.u16("score"), g.bg_row(1)[1:6]))
        assert len(samples) < 20000, "score stopped going up"
    obstacles = wmap.obstacles(complete_only=False)
    edges = [o.right_edge for o in obstacles]
    assert edges == sorted(edges)
    for i, (wx, score, _) in enumerate(samples):
        expected = bisect.bisect_right(edges, wx + hx0)
        assert score == expected, f"frame {i + 1}: world_x {wx}, score {score}, obstacles passed {expected}"
    passed = obstacles[:target]
    assert any(o.width == 4 for o in passed), "no double column was passed: the test needs one"
    # the HUD follows: the digits of the score, at most one frame late
    for i in range(1, len(samples)):
        row = samples[i][2]
        assert row in (score_row(cfg, samples[i][1]), score_row(cfg, samples[i - 1][1])), \
            f"frame {i + 1}: score row {row} for score {samples[i][1]}"
        if i + 1 < len(samples):
            assert samples[i + 1][2] == score_row(cfg, samples[i][1]) or samples[i + 1][1] != samples[i][1]
