"""Boot to the title screen, the save block written on a blank cartridge,
starting a run, and the RNG seeding (docs/DESIGN.md "States and controls",
"Save RAM", "Gameplay")."""
import pytest

from gb import hud_hi_row, record_world
from model import Scroll, WorldMap


def test_boots_to_title(make_game, cfg):
    """No battery file at all (PyBoy starts with blank RAM): high score 0,
    and nothing is written to the save RAM."""
    game = make_game(boot=False)
    blank = game.sram(0x2000)
    game.boot()
    assert game.state() == cfg.STATE_TITLE
    assert game.u16("high_score") == 0
    assert game.u8("debug_invincible") == 0
    assert game.sram(0x2000) == blank


def test_title_hud_shows_hi_0000_from_blank_save(game, cfg):
    assert game.win_row(0)[:20] == hud_hi_row(cfg, 0)
    assert hud_hi_row(cfg, 0)[:8] == [cfg.T_HUD_DARK, cfg.T_LFONT_ALPHA + 7, cfg.T_LFONT_ALPHA + 8, cfg.T_HUD_DARK] \
        + [cfg.T_LFONT_DIGIT] * 4


def test_title_hides_the_score(game, cfg):
    assert game.bg_row(1)[1:6] == [cfg.T_SKY] * 5


def test_title_draws_the_logo(game, cfg):
    for row in range(2, 6):
        tiles = game.bg_row(row)[1:19]
        assert all(t >= cfg.T_LOGO_BASE for t in tiles), f"row {row}: {tiles}"


def test_title_press_start_sprites(game, cfg):
    """PRESS START is sprite text (OAM 5..14) using the copy of the font at
    S_TEXT_BASE; it blinks every BLINK_FRAMES frames."""
    def prompt():
        return [(y, x, t) for (y, x, t, a) in game.oam()[cfg.OAM_TEXT:cfg.OAM_TEXT_END]
                if 0 <= y < 144 and 0 <= x < 160]

    seen_on, seen_off = None, False
    for _ in range(3 * cfg.BLINK_FRAMES):
        game.tick()
        p = prompt()
        if p:
            seen_on = p
        else:
            seen_off = True
    assert seen_on, "PRESS START never shown"
    assert seen_off, "PRESS START never blinks off"
    letters = [c for c in "PRESS START" if c != " "]
    assert [t for (_, _, t) in sorted(seen_on, key=lambda s: s[1])] == \
        [cfg.S_TEXT_BASE + ord(c) - ord("A") for c in letters]


def test_blank_save_is_left_alone(make_game):
    g = make_game(ram=bytes(0x2000))
    assert g.u16("high_score") == 0
    g.tick(60)
    g.stop(save=True)
    assert g.ram_path.read_bytes() == bytes(0x2000)


@pytest.mark.parametrize("button", ["start", "a"])
def test_start_or_a_begins_a_run(game, cfg, button):
    game.start_run(button)
    assert game.state() == cfg.STATE_PLAY
    assert game.u16("score") == 0
    assert game.u16("world_x") == 0
    assert game.u8("panda_on_ground") == 1
    assert game.u8("jumps_used") == 0
    assert game.col_height() == [0] * 32
    # The A that started the run is not also a jump.
    game.tick(3)
    assert game.u8("panda_on_ground") == 1


def test_select_does_not_start_a_run(game, cfg):
    game.tap("select")
    game.tap("b")
    game.tick(10)
    assert game.state() == cfg.STATE_TITLE


def test_run_shows_score_zero(game, cfg):
    game.start_run()
    game.tick(1)
    assert game.bg_row(1)[1:6] == [cfg.T_FONT_DIGIT] + [cfg.T_SKY] * 4


def test_logo_becomes_sky_over_4_frames(game, cfg):
    game.start_run()
    game.tick(3)
    assert any(t >= cfg.T_LOGO_BASE for r in range(2, 6) for t in game.bg_row(r)[1:19]), \
        "the logo should take 4 frames to go"
    game.tick(1)
    for row in range(2, 6):
        tiles = game.bg_row(row)
        assert all(t < cfg.T_LOGO_BASE for t in tiles), f"logo tiles left in row {row}: {tiles}"


def test_world_x_advances_by_world_speed(game, cfg):
    """world_x / world_sub advance by world_speed (8.8) every frame, the
    fraction carried; world_scx is the low byte."""
    game.start_run(invincible=True)
    assert game.u16("world_speed") == cfg.SPEED_BASE
    assert game.u8("world_sub") == 0
    s = Scroll(game.u16("world_x"), 0, game.u16("world_speed"))
    for _ in range(120):
        game.tick()
        s.step()
        assert (game.u16("world_x"), game.u8("world_sub")) == (s.x & 0xFFFF, s.sub)
        assert game.u8("world_scx") == s.x & 0xFF
        assert game.u16("world_speed") == cfg.SPEED_BASE


def first_obstacles(make_game, wait, name, count=8):
    g = make_game(name=name)
    g.tick(wait)
    g.start_run(invincible=True)
    wmap = WorldMap()
    while len(wmap.obstacles()) < count:
        record_world(g, 64, wmap)
    return [(o.start, o.width, o.height) for o in wmap.obstacles()[:count]]


def test_rng_is_seeded_by_the_press_frame(make_game):
    runs = {w: first_obstacles(make_game, w, f"w{w}") for w in (0, 1, 2, 9, 40)}
    seqs = list(runs.values())
    for i in range(len(seqs)):
        for j in range(i + 1, len(seqs)):
            assert seqs[i] != seqs[j], f"same obstacles for press frames {list(runs)[i]} and {list(runs)[j]}"


def test_same_press_frame_same_obstacles(make_game):
    assert first_obstacles(make_game, 5, "a") == first_obstacles(make_game, 5, "b")


def obstacles_after_select(make_game, gap, name, count=8):
    """Select on the title (seeds the RNG), then Start `gap` frames later."""
    g = make_game(name=name)
    g.tap("select")
    g.tap("select")                   # music off and on again
    g.tick(gap)
    g.start_run(invincible=True)
    wmap = WorldMap()
    while len(wmap.obstacles()) < count:
        record_world(g, 64, wmap)
    return [(o.start, o.width, o.height) for o in wmap.obstacles()[:count]]


def test_rng_is_stirred_while_the_title_is_up(make_game):
    """The seed comes from the first press on the title, but the run's
    obstacles also depend on how long the title stayed up after it."""
    runs = [obstacles_after_select(make_game, gap, f"s{gap}") for gap in (0, 1, 17)]
    assert runs[0] != runs[1] and runs[1] != runs[2] and runs[0] != runs[2]


@pytest.mark.parametrize("button", ["start", "a"])
def test_button_held_from_power_on_is_not_a_press(make_game, cfg, button):
    """A button held through power-on neither skips the title nor seeds
    the RNG: it has to be released and pressed again."""
    g = make_game(boot=False)
    g.hold(button)
    g.boot()
    g.tick(120)
    assert g.state() == cfg.STATE_TITLE, "a held button started a run"
    g.release(button)
    g.tick(3)
    assert g.state() == cfg.STATE_TITLE
    g.start_run(button)
    assert g.state() == cfg.STATE_PLAY


def test_press_start_blinks_every_blink_frames(game, cfg):
    shown = []
    for _ in range(6 * cfg.BLINK_FRAMES):
        game.tick()
        y, x, t, a = game.oam()[cfg.OAM_TEXT]
        shown.append(0 <= y < 144)
    changes = [i for i in range(1, len(shown)) if shown[i] != shown[i - 1]]
    assert len(changes) >= 4
    assert all(b - a == cfg.BLINK_FRAMES for a, b in zip(changes, changes[1:])), changes
