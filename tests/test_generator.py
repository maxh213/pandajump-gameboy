"""The obstacle generator over long invincible runs on several seeds
(docs/DESIGN.md "Gameplay", src/config.h's spacing derivation).

Everything is checked from what the ROM put in col_height, recorded as the
columns are generated. The score when an obstacle starting at world tile S
was generated is derived from positions: the column is made when
world_x >> 3 reaches S - 21, before that frame's scoring, so every obstacle
whose right edge is at or before world x 8 * (S - 17) had been passed."""
import bisect
from collections import Counter

import pytest

from gb import record_world
from model import WorldMap, documented_min_spacing, spacing_for_score, speed_for_score

SEEDS = (0, 7, 50)          # frames on the title before pressing Start
OBSTACLES_PER_SEED = 1000


class Run:
    def __init__(self, obstacles, samples, end_x):
        self.obstacles = obstacles
        self.samples = samples           # (world_x, score, world_speed)
        self.end_x = end_x
        edges = [o.right_edge for o in obstacles]
        self.gen_score = [bisect.bisect_right(edges, 8 * (o.start - 17)) for o in obstacles]


@pytest.fixture(scope="module")
def runs(rom, tmp_path_factory):
    from gb import GB
    out = {}
    for seed in SEEDS:
        g = GB(tmp_path_factory.mktemp(f"gen{seed}"), rom=rom)
        try:
            g.boot()
            g.tick(seed)
            g.start_run(invincible=True)
            samples = []
            wmap = WorldMap()

            def sample(g, x):
                samples.append((x, g.u16("score"), g.u16("world_speed")))

            while len(wmap.obstacles()) < OBSTACLES_PER_SEED + 1:
                wmap, x = record_world(g, 1024, wmap, chunk=16, on_sample=sample)
                assert g.state() == 1
            out[seed] = Run(wmap.obstacles()[:OBSTACLES_PER_SEED + 1], samples, x)
        finally:
            g.stop()
    return out


def all_obstacles(runs):
    for seed, r in runs.items():
        for i, o in enumerate(r.obstacles):
            yield seed, i, o, r


def test_obstacle_shapes(runs):
    for seed, i, o, _ in all_obstacles(runs):
        assert o.height in (16, 32), f"seed {seed} obstacle {i}: height {o.height}"
        assert o.width in (2, 4), f"seed {seed} obstacle {i}: {o.width} tiles wide"


def test_first_obstacle_after_first_gap(runs, cfg):
    for seed, r in runs.items():
        assert r.obstacles[0].start == 21 + 1 + cfg.FIRST_GAP, f"seed {seed}"


def test_doubles_only_after_double_score(runs, cfg):
    for seed, i, o, r in all_obstacles(runs):
        if r.gen_score[i] <= cfg.DOUBLE_SCORE:
            assert o.width == 2, f"seed {seed}: double column at score {r.gen_score[i]}"


def test_doubles_about_one_in_three(runs, cfg):
    eligible = doubles = 0
    for seed, i, o, r in all_obstacles(runs):
        if r.gen_score[i] > cfg.DOUBLE_SCORE:
            eligible += 1
            doubles += o.width == 4
    p = cfg.DOUBLE_CHANCE / 256
    assert eligible > 2000
    assert abs(doubles / eligible - p) < 0.04, f"{doubles}/{eligible} doubles, expected about {p:.3f}"


def test_heights_about_half_and_half(runs):
    c = Counter(o.height for _, _, o, _ in all_obstacles(runs))
    total = sum(c.values())
    assert abs(c[32] / total - 0.5) < 0.05, dict(c)


def gaps(r):
    for i in range(len(r.obstacles) - 1):
        a, b = r.obstacles[i], r.obstacles[i + 1]
        yield i, a, b, b.start - a.end


def test_gap_follows_the_spacing_rule(runs, cfg):
    """SPACING - 2 empty tiles after every obstacle, plus 0..SPACING_RAND,
    with SPACING from the ramp at the score the obstacle was made at."""
    extras = Counter()
    for seed, r in runs.items():
        for i, a, b, gap in gaps(r):
            spacing = spacing_for_score(cfg, r.gen_score[i])
            extra = gap - (spacing - 2)
            assert 0 <= extra <= cfg.SPACING_RAND, (
                f"seed {seed} obstacle {i} (score {r.gen_score[i]}): gap {gap}, spacing {spacing}")
            extras[extra] += 1
    assert set(extras) == set(range(cfg.SPACING_RAND + 1)), extras
    total = sum(extras.values())
    for k, n in extras.items():
        assert abs(n / total - 1 / (cfg.SPACING_RAND + 1)) < 0.05, extras


def test_gap_never_below_documented_minimum(runs, cfg):
    """config.h's table: the smallest clearable SPACING at each speed (the
    empty gap after an obstacle is SPACING - 2). The speed that matters is
    the one while the panda crosses the gap, i.e. once obstacle i has
    scored (score i + 1)."""
    for seed, r in runs.items():
        for i, a, b, gap in gaps(r):
            speed = speed_for_score(cfg, i + 1)
            need = documented_min_spacing(speed) - 2
            assert gap >= need, f"seed {seed}: gap {gap} after obstacle {i} at speed {speed}/256, need {need}"


def test_speed_ramp_matches_config(runs, cfg):
    for seed, r in runs.items():
        speeds = [s for (_, _, s) in r.samples]
        for (x, score, speed) in r.samples:
            assert speed == speed_for_score(cfg, score), f"seed {seed}: speed {speed} at score {score}"
        assert speeds == sorted(speeds)
        assert speeds[0] == cfg.SPEED_BASE
        assert max(speeds) == cfg.SPEED_MAX
    # the spacing ramp reaches its floor too
    assert spacing_for_score(cfg, OBSTACLES_PER_SEED) == cfg.SPACING_MIN


def test_score_matches_obstacles_passed(runs, cfg):
    hx0 = cfg.PANDA_X + cfg.HIT_X0
    for seed, r in runs.items():
        edges = [o.right_edge for o in r.obstacles]
        for (x, score, _) in r.samples:
            if x + hx0 < edges[-1]:
                assert score == bisect.bisect_right(edges, x + hx0), f"seed {seed} at world_x {x}"


def test_runs_past_world_x_wrap(runs):
    """world_x is 16 bits: these runs pass 65535 (about 12 minutes of play)
    and the generator and scoring keep going (the samples are unwrapped and
    the checks above cover the whole run)."""
    for seed, r in runs.items():
        assert r.end_x > 65536 + 32 * 8, f"seed {seed} only reached {r.end_x}"
