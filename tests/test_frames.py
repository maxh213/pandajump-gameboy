"""Frame budget: the game never drops a frame. frame_count goes up by
exactly one per frame through a long session with every transition in it,
and (white box, with PyBoy hooks) each frame's logic reaches vsync()
before that frame's VBlank.

PyBoy's frame starts at line 0; the position inside it is measured in
clock cycles (456 per line) from the start of the tick."""
import pytest

from gb import ram_image, sram_block

LINE = 456


class Timed:
    """Ticks one frame at a time, remembering where each frame starts, and
    logs the line at which hooked functions are entered."""

    def __init__(self, g):
        self.g = g
        self.start = 0
        self.log = []

    def hook(self, name):
        _bank, addr = self.g.pb.symbol_lookup(name)
        self.g.pb.hook_register(0, addr, self._hit, name)

    def _hit(self, name):
        cyc = self.g.pb._cycles() - self.start
        self.log.append((name, self.g.frames, cyc // LINE, self.g.pb.memory[0xFF44], self.g.u8("game_state")))

    def tick(self):
        self.start = self.g.pb._cycles()
        self.g.tick(1)


def session(g, cfg, step, press):
    """Every state and transition: title, music toggle, start (logo wipe),
    jump, double jump and landing puffs, pause/resume, the ramp to top speed
    with double columns, a new best (save RAM write), the death fall, a
    restart (clearing boxes and messages), a worse run, another restart."""
    step(100)
    press("select")
    press("select")
    press("start")
    assert g.state() == cfg.STATE_PLAY
    step(10)
    press("a")
    step(10)
    press("a")
    step(40)
    press("start")
    assert g.state() == cfg.STATE_PAUSED
    step(30)
    press("start")
    assert g.state() == cfg.STATE_PLAY
    g.write8("debug_invincible", 1)
    n = 0
    while g.u16("score") < 45:
        step()
        n += 1
        assert n < 20000
    g.write8("debug_invincible", 0)
    while g.state() == cfg.STATE_PLAY:
        step()
    assert g.u16("high_score") == 45
    step(cfg.DEAD_DELAY + 40)
    press("a")
    assert g.state() == cfg.STATE_PLAY
    while g.state() == cfg.STATE_PLAY:
        step()
    step(cfg.DEAD_DELAY + 5)
    press("start")
    step(200)


def run_session(make_game, cfg, hooks):
    g = make_game(ram=ram_image(sram_block(1)), boot=False)
    t = Timed(g)
    for h in hooks:
        t.hook(h)
    g.boot()
    fc = [g.u8("frame_count")]
    t.log.clear()

    def step(n=1):
        for _ in range(n):
            t.tick()
            new = g.u8("frame_count")
            assert new == (fc[0] + 1) & 0xFF, \
                f"frame {g.frames}: frame_count {fc[0]} -> {new} (state {g.state()}): a dropped frame"
            fc[0] = new

    def press(button):
        g.hold(button)
        step()
        g.release(button)
        step()

    session(g, cfg, step, press)
    return t.log


def test_one_frame_count_per_frame_and_vsync_in_time(make_game, cfg):
    log = run_session(make_game, cfg, ["_vsync"])
    assert len(log) > 5000
    late = [e for e in log if e[2] >= 144]
    assert not late, f"logic still running at VBlank (name, frame, line, LY, state): {late[:10]}"


@pytest.mark.xfail(strict=True, reason="BUG logic-starts-before-line-1: the wait loop in main() "
                   "reads LY twice, so it can leave during line 153/0 instead of line 1")
def test_logic_starts_on_line_1_or_later(make_game, cfg):
    """docs/DESIGN.md: "the game reads the joypad right after VBlank and runs
    its logic from line 1". The first thing each state's logic calls
    (world_scroll on the title and in play, player_dead_fall when dead) must
    be entered with LY in 1..143."""
    log = run_session(make_game, cfg, ["_world_scroll", "_player_dead_fall"])
    early = [e for e in log if not 1 <= e[3] <= 143]
    assert not early, (f"{len(early)} of {len(log)} frames start their logic outside lines 1-143, "
                       f"e.g. (name, frame, line, LY, state) {early[:5]}")
