"""Fairness: with invincibility off, an autoplayer that only reads what a
player could see (col_height, world_x, world_speed, the panda) and only
acts through the A button reaches a score of 90 on several seeds: past
the top speed (score 40) and the end of the late ramp (score 80).

It plans with the integer model in tests/model.py and checks, every
frame, that the ROM did exactly what the model predicted (panda state,
kept press and scroll), so a death here means either the game generated a
sequence the physics can't clear, or the ROM left the documented rules.
The model includes the input rules (an early second press is not a double
jump, a press near or after the end of a flight is kept and jumps on
landing), so the sloppy player's mistimed presses land in them too.

A second, "sloppy" player checks the stronger promise in src/config.h:
every jump still clears when either press is up to 3 frames early or late,
with at least 10 frames on the ground before the earliest take-off. It
picks plans that survive every such error and then really presses up to 3
frames off (seeded random), so it has to survive whatever it gets, up to a
score of 120 (80 obstacles at the top speed, most of them after the late
ramp has made doubles and 2-box columns more common)."""
import random

import pytest

from model import AutoPlayer, WorldMap, speed_for_score

TARGET = 90              # past the end of the late ramp (score 80)
SLOPPY_TARGET = 120      # well past the top speed (score 40) and the late ramp
SEEDS = (0, 13, 77)
SLACK = 3                 # config.h: "up to 3 frames early or late"
GROUND_FRAMES = 10        # config.h: "at least 10 frames on the ground"


def autoplay(g, cfg, target, max_frames=12000, slack=0, rng=None, nervous=None):
    """Play to `target`; returns (frames, rescues, nervous taps). With
    `nervous` (an RNG) the player also taps A again 2..14 frames after
    every take-off, while the panda still rises faster than DJUMP_VEL."""
    ap = AutoPlayer(cfg)
    phys = ap.phys
    hx0 = ap.hx0
    g.start_run()
    assert g.u8("debug_invincible") == 0
    scroll = g.scroll()
    wmap = WorldMap()
    presses = set()          # logic frames (counted from the run's first) that see A
    expected = None
    log = []
    landed_at = -1000        # the run starts on the ground
    prev_ground = True
    plan_target = 0          # right edge the current jump was planned to clear
    rescues = 0
    taps = 0
    for t in range(max_frames):
        state = g.state()
        score = g.u16("score")
        panda = g.panda()
        if expected is not None:
            assert panda == expected, f"frame {t}: panda {panda} but the model says {expected}"
        assert (g.u16("world_x"), g.u8("world_sub")) == (scroll.x & 0xFFFF, scroll.sub), \
            f"frame {t}: world_x off the model"
        if state != cfg.STATE_PLAY:
            upcoming = [o for o in wmap.obstacles(False) if o.right_edge > scroll.x]
            pytest.fail(f"died at score {score}, frame {t}, world_x {scroll.x}; "
                        f"next obstacles {upcoming[:3]}; last plans {log[-3:]}")
        if score >= target:
            return t, rescues, taps
        speed = g.u16("world_speed")
        assert speed == speed_for_score(cfg, score)
        scroll.speed = speed
        assert panda.y >= 0
        if panda.on_ground and not prev_ground:
            landed_at = t
        if nervous and not panda.on_ground and prev_ground:
            p = t + nervous.randint(2, 14)          # t is the take-off frame
            if not presses & {p - 1, p, p + 1}:
                presses.add(p)
                taps += 1
        prev_ground = panda.on_ground
        wmap.record(scroll.x, g.col_height())

        pending = (t + 1) in presses
        ahead = [o for o in wmap.obstacles() if o.right_edge > scroll.x + hx0]
        if ahead:
            xs, hs = ap.future_world(scroll, score, wmap, 180)
            rel = tuple(sorted(p - t for p in presses if p > t + 1))
            base = (1,) if pending else ()
            if panda.on_ground:
                # plan for the next obstacle once it is close
                target_x = ahead[0].right_edge
                near = any(hs[:AutoPlayer.LOOKAHEAD])
            else:
                # in the air: the flight must land safely past what it was
                # planned for; only replan if it no longer does
                target_x = plan_target if plan_target > scroll.x + hx0 else 0
                near = True
            if near and ap.evaluate(panda, base + rel, xs, hs, target_x) is None:
                plan = None
                plan_target = target_x
                if slack and panda.on_ground and not pending:
                    first = max(2, landed_at + GROUND_FRAMES - t)
                    r = ap.plan_ground_tolerant(first, xs, hs, target_x, slack)
                    if r is None:
                        pytest.fail(
                            f"score {score}, frame {t}: no plan clears the next obstacle "
                            f"({ahead[0]}) with both presses {slack} frames early or late "
                            f"and {GROUND_FRAMES} frames on the ground after landing "
                            f"(landed {t - landed_at} frames ago; next {ahead[1:3]})")
                    _, f, k = r
                    a = rng.randint(-slack, slack)
                    plan = (f + a,)
                    if k is not None:
                        plan += (f + k + rng.randint(-slack, slack),)
                else:
                    if slack:
                        rescues += 1
                    plan = ap.plan(panda, pending, xs, hs, target_x)
                presses = {p for p in presses if p <= t + 1}
                if plan is not None:
                    presses |= {t + p for p in plan}
                log.append((t, score, target_x, plan))
        if (t + 2) in presses:
            g.hold("a")
        else:
            g.release("a")
        expected = panda.copy()
        phys.step(expected, pending)
        g.tick()
        scroll.step()
    pytest.fail(f"score {g.u16('score')} after {max_frames} frames")


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
def test_autoplayer_reaches_90(make_game, cfg, seed):
    g = make_game()
    g.tick(seed)
    autoplay(g, cfg, TARGET)
    assert g.u16("score") >= TARGET


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
def test_sloppy_player_reaches_120(make_game, cfg, seed):
    g = make_game()
    g.tick(seed)
    _, rescues, _ = autoplay(g, cfg, SLOPPY_TARGET, max_frames=20000, slack=SLACK, rng=random.Random(seed))
    assert g.u16("score") >= SLOPPY_TARGET
    assert rescues == 0, f"{rescues} tolerant plans had to be replaced mid-jump"


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
def test_nervous_double_tap_is_harmless(make_game, cfg, seed):
    """The exact autoplayer, plus a nervous second tap 2..14 frames after
    every take-off, where the original's rule (the second press *sets*
    vy = -DJUMP_VEL) cut the jump too short for a 2-box column. The taps
    are not double jumps: the ROM matches the model frame for frame and the
    run still reaches 50."""
    g = make_game()
    g.tick(seed)
    _, _, taps = autoplay(g, cfg, 50, nervous=random.Random(seed))
    assert g.u16("score") >= 50
    assert taps >= 40


@pytest.mark.slow
def test_spacing_min_is_safe_and_tight(cfg):
    """Model only: config.h derives SPACING_MIN as the smallest spacing that
    keeps every chain of obstacles clearable at SPEED_MAX with 3 frames of
    slack on each press and 10 frames on the ground. Check both halves:
    SPACING_MIN - 2 empty tiles always works, one tile less does not."""
    from model import worst_case_chains
    states, fails = worst_case_chains(cfg, cfg.SPEED_MAX, cfg.SPACING_MIN - 2, SLACK, GROUND_FRAMES)
    assert not fails, f"unclearable chains at SPACING_MIN: {fails}"
    assert len(states) > 5
    _, fails = worst_case_chains(cfg, cfg.SPEED_MAX, cfg.SPACING_MIN - 3, SLACK, GROUND_FRAMES)
    assert fails, "SPACING_MIN - 1 would also be safe: config.h's minimum is not the smallest"
