# PandaJump tests

Headless tests of `build/pandajump.gb` in PyBoy, checked against
`PROMPT.md`, `docs/DESIGN.md` and the constants in `src/config.h` (parsed
from its `#define` lines, never copied).

## Running

```sh
make test                      # builds the ROM, then python3 -m pytest -q tests
python3 -m pytest -q tests     # same; runs `make` first when GBDK is installed
python3 -m pytest -q tests/test_physics.py -k double
```

Needs Python 3 with `pyboy==2.7.0`, `numpy`, `pillow` and `pytest`
(`requirements-dev.txt`). The whole suite takes about 40 s and uses no
wall-clock timing, so it gives the same result on every run. Each test runs
on its own copy of the ROM, `.sym` and battery RAM in a pytest temp
directory, so the tests don't share save files and nothing is written to the
repo.

## Layout

| File | What it checks |
|------|----------------|
| `gb.py` | Helpers: `GB` (one PyBoy on a private ROM copy: boot, tick, hold/press/tap, `run_until` with a frame cap, symbol reads u8/s8/u16/s16, BG/window map rows, OAM, screen as shades 0-3, cartridge RAM), `record_world`, save blocks, text as font tiles, `render_band` (the BG map drawn from the art), png2asset output parsers |
| `model.py` | An independent integer model of the rules: physics and the input rules (a double jump only as a boost and above BUFFER_HEIGHT, other presses in the air kept JUMP_BUFFER frames for a jump on landing), scroll with the 8.8 fraction, the world map recorded from `col_height`, obstacles, the ramp and the late ramp, the autoplayer's planners, and config.h's worst-case chain check |
| `conftest.py` | Session fixtures: `rom` (runs `make`), `cfg` (config.h + tiles.h), `make_game` / `game` |
| `test_rom_header.py` | Title, DMG only, MBC5+RAM+battery (0x1B), 8 KiB RAM, logo, header and global checksums, size |
| `test_art.py` | Every `art/*.png` indexed with exactly 4 entries of the contract palette and the contract size, fonts, tile budgets from `build/res/*.h` (panda < 64, logo <= 128), metasprites rebuild the art |
| `test_vram.py` | Tile data in VRAM: BG 0-127 = `bg_tiles.png` in order, logo at 128+, panda/dust/sprite font at their bases; nothing overwrites them in play |
| `test_boot.py` | Boot to the title, `HI 0000` from blank RAM (left unwritten), logo, PRESS START from the first frame and its 44/64 blink, Start or A begins a run, a button held from power-on is not a press, the ground doesn't jump when a run starts, `world_x`/`world_sub` follow `world_speed`, logo wipe in 4 frames and hidden behind plain sky, RNG seeded by the press frame and stirred while the title is up |
| `test_physics.py` | Jump, double jump (every timing), an early second press is not used up (no sound, no puff), the near-ground and after-double-jump presses kept for landing (jump buffer, with the jump sound), third press, holding A, landing, the top clamp: frame for frame against the model, `jump_buffer` included |
| `test_death.py` | No input dies at the first obstacle on the exact frame, collision edges of the hitbox for 1- and 2-box columns (too early / too late by one frame), the game-over messages only once the panda has sunk (ground and air deaths), their layout, PRESS START after PROMPT_DELAY with its blink, no restart before it or from a held button, the death hop and fall, restart is a fresh run (ground phase kept, no old boxes in view), its first frames draw clean with the panda, and its VBlank tile work ends early |
| `test_scoring.py` | Score +1 per obstacle (double columns once) on the exact frame, against obstacles counted from `col_height`; HUD digits follow |
| `test_generator.py` | 3 seeds x 1000 obstacles: heights 16/32 (the first always 16), widths 2/4, doubles only above DOUBLE_SCORE, double and 2-box rates following the ramp (including the late ramp after score 40), gaps = SPACING-2 + the random extra's mask at that score and never below config.h's table, speed ramp, past the `world_x` wrap |
| `test_fairness.py` | An exact autoplayer reaches 90 on 3 seeds (past the top speed and the late ramp); a "sloppy" one (every press up to 3 frames off, landing in the early-press and jump-buffer rules) reaches 120; config.h's worst-case chain rule holds at SPACING_MIN and fails one tile tighter |
| `test_world.py` | The BG map mirrors `col_height` with the right box tiles every frame; ground and sky rows never change |
| `test_sprites.py` | Panda frame per state (run cycle speed, jump, double, fall, dead, behind the ground), dust puff (the landing one visible at the heel), sprite tiles < 128, <= 10 per line (title, run, game over), text sprites only where allowed, spare OAM hidden |
| `test_hud.py` | LCDC/WY/WX/palettes, score row with the dark font, window `HI` with the light font, pixel-exact against the art |
| `test_parallax.py` | Band shifts measured on the screen (world = `world_x`, sky slower, HUD and window static), frame by frame; bob within 0-4; the screen equals the VRAM map drawn with each band's scroll; clouds (big and small) keep coming |
| `test_pause.py` | Start pauses, nothing moves for 60 frames (RAM and pixels), A ignored, Start resumes exactly where it stopped, the music holds its place (music_pause/music_resume), a pause during the logo wipe keeps the wipe hidden and shows `PAUSED` once |
| `test_save.py` | Two-slot save format, the window's `HI` changing on the screen frame that shows `NEW BEST!`, saves alternate slots, sequence wrap, the newest good slot is loaded, power cycle, worse/equal run writes nothing, corrupt/blank RAM reads 0 and is not written, a bad slot next to a good one, a save cut off after each of its writes, RAM disabled after use |
| `test_frames.py` | `frame_count` +1 every frame through a session with every transition; `vsync()` reached before VBlank (PyBoy hooks) |
| `test_sound.py` | APU on; jump, double jump, score and death sounds on channels 1/4; music only on 2/3 (channels isolated with NR51) |

## Timing (see `gb.py`)

A tick is a frame and starts at line 0. After tick *k* the RAM holds frame
*k*'s logic and the screen shows frame *k-1*. A button held during tick *k*
is acted on in tick *k+1*. PyBoy draws the window one line off on the first
rendered frame after unrendered ones, so `GB.tick(render=True)` always
renders the last two frames.

## Known game bugs

Tests for bugs in the game are kept and marked
`xfail(strict=True, reason="BUG <id>: ...")`; when the bug is fixed the test
passes, the strict xfail fails, and the marker should be removed. There are
none at the moment.
