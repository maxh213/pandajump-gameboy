"""The obstacle generator over long invincible runs on several seeds
(docs/DESIGN.md "Gameplay", src/config.h's spacing derivation and ramp).

Everything is checked from what the ROM put in col_height, recorded as the
columns are generated. The score when an obstacle starting at world tile S
was generated is derived from positions: the column is made when
world_x >> 3 reaches S - 21, before that frame's scoring, so every obstacle
whose right edge is at or before world x 8 * (S - 17) had been passed."""
import bisect
import math
from collections import Counter

import pytest

from gb import record_world
from model import (WorldMap, documented_min_spacing, double_chance_for_score, late_steps,
                   spacing_for_score, spacing_rand_for_score, speed_for_score, tall_chance_for_score)

SEEDS = (0, 7, 50)          # frames on the title before pressing Start
OBSTACLES_PER_SEED = 1000


class Run:
    def __init__(self, obstacles, samples, end_x, start_x):
        self.obstacles = obstacles
        self.start_x = start_x           # world_x on the run's first frame
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
            start_x = g.u16("world_x")
            samples = []
            wmap = WorldMap()

            def sample(g, x):
                samples.append((x, g.u16("score"), g.u16("world_speed")))

            while len(wmap.obstacles()) < OBSTACLES_PER_SEED + 1:
                wmap, x = record_world(g, 1024, wmap, chunk=16, on_sample=sample)
                assert g.state() == 1
            out[seed] = Run(wmap.obstacles()[:OBSTACLES_PER_SEED + 1], samples, x, start_x)
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
    """The first column generated is (world_x >> 3) + 22; FIRST_GAP empty
    ones, then the first obstacle, which is always a single 1-box column."""
    for seed, r in runs.items():
        first = r.obstacles[0]
        assert first.start == (r.start_x >> 3) + 22 + cfg.FIRST_GAP, f"seed {seed}"
        assert (first.width, first.height) == (2, 16), f"seed {seed}: first obstacle {first}"


def test_first_obstacle_is_always_one_box(make_game, cfg):
    """Over many start frames (so many seeds), a run never opens with a
    2-box column."""
    for wait in range(24):
        g = make_game(name=f"w{wait}")
        g.tick(wait * 7)
        g.start_run(invincible=True)
        wmap = WorldMap()
        while not wmap.obstacles():
            record_world(g, 32, wmap)
        assert wmap.obstacles()[0].height == 16, f"start frame {wait * 7}: {wmap.obstacles()[0]}"
        g.stop()


def test_doubles_only_after_double_score(runs, cfg):
    for seed, i, o, r in all_obstacles(runs):
        if r.gen_score[i] <= cfg.DOUBLE_SCORE:
            assert o.width == 2, f"seed {seed}: double column at score {r.gen_score[i]}"


def check_rate(events, what):
    """events: (probability, happened) pairs. The count must be within 4
    standard deviations of what the probabilities predict."""
    n = len(events)
    want = sum(p for p, _ in events)
    sd = math.sqrt(sum(p * (1 - p) for p, _ in events))
    got = sum(1 for _, e in events if e)
    assert n > 100 and sd > 0
    assert abs(got - want) <= 4 * sd, f"{what}: {got} of {n}, expected {want:.1f} +- {sd:.1f}"


def test_doubles_follow_the_ramp(runs, cfg):
    """1 in 3 (DOUBLE_CHANCE) above DOUBLE_SCORE, then DOUBLE_STEP more per
    late step up to DOUBLE_MAX."""
    events = []
    for seed, i, o, r in all_obstacles(runs):
        if i > 0 and r.gen_score[i] > cfg.DOUBLE_SCORE:
            events.append((double_chance_for_score(cfg, r.gen_score[i]) / 256, o.width == 4))
    check_rate(events, "doubles")
    early = [(p, e) for p, e in events if p == cfg.DOUBLE_CHANCE / 256]
    late = [(p, e) for p, e in events if p == cfg.DOUBLE_MAX / 256]
    check_rate(early, "doubles before the late ramp")
    check_rate(late, "doubles at the end of the late ramp")
    assert len(late) > 2000
    assert abs(sum(e for _, e in late) / len(late) - cfg.DOUBLE_MAX / 256) < 0.04


def test_heights_follow_the_ramp(runs, cfg):
    """2 boxes high with TALL_CHANCE/256, TALL_STEP more per late step, up
    to TALL_MAX (the run's first obstacle is always 1 box)."""
    events = []
    for seed, i, o, r in all_obstacles(runs):
        if i > 0:
            events.append((tall_chance_for_score(cfg, r.gen_score[i]) / 256, o.height == 32))
    check_rate(events, "2-box columns")
    late = [(p, e) for p, e in events if p == cfg.TALL_MAX / 256]
    assert len(late) > 2000
    assert abs(sum(e for _, e in late) / len(late) - cfg.TALL_MAX / 256) < 0.04


def test_late_ramp_schedule(cfg):
    """Model only: the late steps come every LATE_EVERY points once the
    speed is at SPEED_MAX (score 40), and reach their limits."""
    top = next(s for s in range(0, 1000, cfg.RAMP_EVERY) if speed_for_score(cfg, s) == cfg.SPEED_MAX)
    assert top == 40
    steps = [s for s in range(1, 200) if late_steps(cfg, s) != late_steps(cfg, s - 1)]
    assert steps[:4] == [top + cfg.LATE_EVERY * k for k in range(1, 5)]
    assert double_chance_for_score(cfg, top) == cfg.DOUBLE_CHANCE
    assert tall_chance_for_score(cfg, top) == cfg.TALL_CHANCE
    assert double_chance_for_score(cfg, 200) == cfg.DOUBLE_MAX
    assert tall_chance_for_score(cfg, 200) == cfg.TALL_MAX
    assert spacing_rand_for_score(cfg, cfg.LATE_RAND_SCORE - 1) == cfg.SPACING_RAND
    assert spacing_rand_for_score(cfg, cfg.LATE_RAND_SCORE) == cfg.LATE_RAND


def gaps(r):
    for i in range(len(r.obstacles) - 1):
        a, b = r.obstacles[i], r.obstacles[i + 1]
        yield i, a, b, b.start - a.end


def test_gap_follows_the_spacing_rule(runs, cfg):
    """SPACING - 2 empty tiles after every obstacle, plus a random extra
    within the bit mask (SPACING_RAND, then LATE_RAND from
    LATE_RAND_SCORE), with SPACING and the mask from the ramp at the score
    the obstacle was made at."""
    extras = {}
    for seed, r in runs.items():
        for i, a, b, gap in gaps(r):
            spacing = spacing_for_score(cfg, r.gen_score[i])
            mask = spacing_rand_for_score(cfg, r.gen_score[i])
            extra = gap - (spacing - 2)
            assert 0 <= extra <= mask, (
                f"seed {seed} obstacle {i} (score {r.gen_score[i]}): gap {gap}, spacing {spacing}")
            extras.setdefault(mask, Counter())[extra] += 1
    assert set(extras) == {cfg.SPACING_RAND, cfg.LATE_RAND}
    for mask, c in extras.items():
        assert set(c) == set(range(mask + 1)), (mask, c)
        total = sum(c.values())
        for k in c:
            p = 1 / (mask + 1)
            assert abs(c[k] - total * p) <= 4 * math.sqrt(total * p * (1 - p)), (mask, c)


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
