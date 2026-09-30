# PandaJump GB — design contract

This is the shared contract between the art, game code, sound, web and test
work. `PROMPT.md` is the brief; this file pins down the details so the
pieces fit together. If you change something here, change every piece
that depends on it.

## Toolchain

- GBDK-2020 4.5.x, installed at `$(GBDK_HOME)` (default `/opt/gbdk/`).
- `make` builds `build/pandajump.gb`; `make run` opens it in mGBA;
  `make test` runs the Python test suite (PyBoy, headless);
  `make web` copies the ROM into `web/`.
- Cartridge: **MBC5 + RAM + battery** (header type `0x1B`), one 8 KiB RAM
  bank, DMG only. Title `PANDAJUMP`.
- Art in `art/*.png` is converted by `png2asset` into `build/res/*.c/.h`
  during the build. Nothing in `build/` is committed.
- The art's source is the text grids in `tools/make_art.py`. The PNGs are
  generated from them (`make art`) and committed with them; never edit a
  PNG by hand. `tools/make_art.py --check` compares the committed PNGs'
  pixels and palettes with the grids, writes nothing, and fails on any
  difference (for CI).
- The link step writes `build/pandajump.map`, `.noi` and `.sym` (RGBDS
  format, used by the tests to find variables).

## Screen layout (160×144, 20×18 tiles)

| Lines   | Tile rows | Band  | Horizontal scroll (`SCX`) | `SCY` |
|---------|-----------|-------|---------------------------|-------|
| 0–15    | 0–1       | HUD   | 0 (static)                | 0 |
| 16–47   | 2–5       | Sky   | `cloud_scx` (slow parallax) | `cloud_bob`, 0–4 |
| 48–135  | 6–16      | World | `world_scx` (the run)     | 0 |
| 136–143 | —         | Window (bottom HUD, `WY=136`, `WX=7`) | — | — |

- BG map at `0x9800`, window map at `0x9C00`.
- The bands are switched by the LYC interrupt: the VBlank handler sets
  `SCX=0, SCY=0, LYC=15`; the LCD handler at line 15 waits for HBlank then
  sets the sky band's `SCX/SCY` and `LYC=47`; at line 47 it waits for
  HBlank then sets the world `SCX` and `SCY=0` and `LYC=15`. Both split
  lines are plain sky on both sides, so a late write is invisible.
- The main loop writes "next" scroll values; the VBlank handler latches them
  into the values the LCD handler uses, so background scroll and sprites
  (copied to OAM in VBlank) change on the same frame.
- Tile row 1 holds the score (top-left). The sky band only ever bobs
  *down* (`SCY` 0–4), so it can read into tile row 6 (always sky) but never
  into the HUD rows.
- World band rows: 6–9 are always sky; 10–13 hold boxes (a 1-box column
  fills rows 12–13, a 2-box column rows 10–13); row 14 is the grass top of
  the ground; rows 15–16 are ground. **Ground surface `GROUND_Y` = 112**
  (top of row 14). Ground and grass repeat every 2 tiles, which divides the
  32-tile map width, so they are written once and hardware scrolling does
  the rest.
- Bottom HUD (window row 0): high score, light text on the dark ground
  colour, e.g. `HI 0042`.

## Tiles and VRAM

- LCDC bit 4 stays **0** (GBDK's default): BG/window tiles use `0x8800`
  addressing, so BG tile indices 0–255 are all usable.
- Sprite tiles: panda at 0 (`S_PANDA_BASE`), dust puff at 64
  (`S_FX_BASE`), and a copy of the dark font's A–Z at 96–121
  (`S_TEXT_BASE`) for sprite text such as the title's `PRESS START` (the
  world band scrolls under it, so it can't be BG text). OAM: 0–3 panda,
  4 dust, 5–14 text, the rest hidden.
- **Sprite tiles use indices 0–127 only** (`0x8000–0x87FF`), which BG never
  sees. BG tiles 128–255 share VRAM with sprite tiles 128–255, so sprites
  must never use 128+.
- BG tiles 0–127: the fixed game tileset, `art/bg_tiles.png`.
- BG tiles 128–255: the title logo (`art/title_logo.png`, **144×32 px**,
  converted with `-map -tile_origin 128`), loaded for the title screen, at
  most 128 unique tiles. The title screen draws it in the sky band (map rows
  2–5, columns 1–18) with the sky band's scroll held at 0.

### `art/bg_tiles.png` — 128×64 px, 16×8 tiles, index = row×16 + col

Converted with `-map -tiles_only -keep_duplicate_tiles -noflip
-keep_palette_order -no_palettes`, so the order is fixed.
`src/tiles.h` names every index; use those names in code.

| Index | Content |
|-------|---------|
| 0 | `T_SKY` — solid shade 0 (also the space character in the dark font) |
| 1 | `T_BLACK` — solid shade 3 |
| 2, 3 / 18, 19 | Box, 16×16 (top-left, top-right / bottom-left, bottom-right) |
| 4, 5 / 20, 21 | Box variant, 16×16, used for the upper box of a 2-box column |
| 6, 7 | Grass top of the ground (tile row 14), 2-tile repeating pattern |
| 8, 9 | Ground, first row under the grass (tile row 15), 2-tile repeat |
| 24, 25 | Ground, second row (tile row 16), 2-tile repeat |
| 10–13 / 26–29 | Cloud, 32×16 (top row / bottom row) |
| 14 | `T_HUD_DARK` — the window HUD background (dark, matches ground) |
| 15, 16, 17, 22, 23, 30, 31 | Spare (keep sky if unused) |
| 32–41 | Dark font `0`–`9` (shade 3 glyph on shade 0) |
| 42–67 | Dark font `A`–`Z` |
| 68–75 | Dark font `!` `-` `:` `.` `?` `'` `/` `x` |
| 76–79 | Spare |
| 80–89 | Light font `0`–`9` (shade 0 glyph on the `T_HUD_DARK` colour) |
| 90–115 | Light font `A`–`Z` |
| 116 | Light font space (same as `T_HUD_DARK`) |
| 117–119 | Light font `!` `-` `:` |
| 120–122 / 123–125 | Small cloud, 24×16 (top row / bottom row), so the sky isn't one repeated cloud |
| 126, 127 | Spare |

### `art/panda.png` — 16×16 frames in one row, 160×16 px

Converted with `-sw 16 -sh 16 -spr8x8 -px 0 -py 0 -keep_palette_order
-noflip -no_palettes`, so each frame is a metasprite of up to four 8×8
hardware sprites, positioned by its top-left corner.

| Frame | Pose |
|-------|------|
| 0–5 | Run cycle |
| 6 | Jump (rising) |
| 7 | Double jump (tucked) |
| 8 | Falling |
| 9 | Dead / hurt |

### `art/fx.png` — 8×8 sprite frames in a row, 32×8 px

A 4-frame dust puff (small to large, then fading) shown under the panda on
the double jump and on landing. Converted with `-sw 8 -sh 8 -spr8x8 -px 0
-py 0`, loaded at sprite tile `S_FX_BASE` (64). The panda's tiles must fit
below 64.

## Palette

Art PNGs are **indexed with exactly 4 palette entries**; the index is the
Game Boy colour number. The RGB values are only for viewing:

| Index | RGB       | Background (`BGP=0xE4`) | Sprites (`OBP0=0xD0`) |
|-------|-----------|-------------------------|------------------------|
| 0 | `#E0F8D0` | shade 0, sky (lightest)  | transparent |
| 1 | `#88C070` | shade 1                  | shade 0 (panda white) |
| 2 | `#346856` | shade 2                  | shade 1 (panda grey) |
| 3 | `#081820` | shade 3 (darkest)        | shade 3 (panda black) |

So in `panda.png`, draw the white fur with index 1, shading with index 2,
black fur and outline with index 3, and leave the background as index 0.
Because index 1 displays as `#88C070`, sprite PNGs look greener than the
game; `tools/preview_art.py` renders them with the in-game mapping.

The panda is white with a full black outline on a shade-0 sky, like
classic Game Boy characters. Boxes are dark (shade 3 body, shade 2 bevel);
the ground is dark (shade 2 and 3) with a shade 1 grass top; clouds are
shade 0 with a shade 1 outline.

## Gameplay

All positions and velocities are 8.8 fixed point (`int16_t`, 256 = 1 px).
Tuning constants live in `src/config.h` as plain `#define NAME value`
lines; the tests parse them.

- Panda: fixed screen X (`PANDA_X`), 16×16 sprite, smaller hitbox
  (`HIT_X0..HIT_X1`, `HIT_Y0..HIT_Y1`, offsets inside the sprite).
- Jump: pressing A on the ground sets `vy = -JUMP_VEL`. Gravity `GRAVITY`
  per frame, capped at `MAX_FALL`. The panda is on the ground when its
  feet reach `GROUND_Y`; that resets the double jump. It can't go above
  the top of the screen.
- Double jump: one more press in the air sets `vy = -DJUMP_VEL`, but only
  when that helps. Unlike the original (which always *sets* the velocity,
  so an early second press made the jump lower), a press while the panda
  still rises at least that fast (`vy <= -DJUMP_VEL`: the first 14 frames
  of a jump) is not the double jump, and neither is a press less than
  `BUFFER_HEIGHT` px above the ground (the last 4 frames of a jump's
  fall), where a full jump on landing is worth more than a short hop. No
  sound, no dust puff, and the double jump stays available.
- Jump buffer: any press in the air that doesn't double jump (including
  every press after the double jump) is kept for `JUMP_BUFFER` frames,
  its own frame included (`jump_buffer` counts down). If the panda lands
  in that time it jumps again in the landing frame (`vy = -JUMP_VEL`, still
  at the floor that frame, with the jump sound), which from then on is
  exactly a jump pressed on its first frame on the ground. Otherwise the
  press is dropped.
- Scroll: `world_x` advances by the current speed (starts at `SPEED_BASE`
  px/frame) each frame; `world_scx` is its low byte. When `world_x >> 3`
  changes, the column `(world_x >> 3) + 21` (mod 32), which is off-screen
  to the right, is generated and written to the map (rows 10–13 only).
- Obstacles: a column is 2 tiles wide with 1 or 2 boxes (2 boxes with
  probability `TALL_CHANCE`/256, one half; a run's first obstacle is
  always 1 box). Once the score is above `DOUBLE_SCORE` (10), `DOUBLE_CHANCE`
  /256 (one in three) of obstacles are double columns (two columns side by
  side, same height). After each obstacle the generator leaves
  `SPACING - 2` empty tiles plus a random extra (`rand() & SPACING_RAND`,
  0–3), so single columns start `SPACING` tiles apart and a double column
  is followed by `SPACING + 2`. `src/config.h` derives the smallest safe
  spacing from the physics and the input rules.
- Difficulty ramp: every `RAMP_EVERY` (5) points the speed goes up by
  `SPEED_STEP`, from `SPEED_BASE` (1.125 px/frame) to `SPEED_MAX` (1.5,
  score 40); the spacing stays at `SPACING_MIN` (14 tiles), which is safe at
  every speed up to the top (`SPACING_BASE` = `SPACING_MIN`: no spacing
  ramp). After that, every `LATE_EVERY` (10) points the double chance goes
  up by `DOUBLE_STEP` (to `DOUBLE_MAX`, one half) and the 2-box chance by
  `TALL_STEP` (to `TALL_MAX`, five eighths), both reached at score 80, and
  from `LATE_RAND_SCORE` (60) the random extra is `rand() & LATE_RAND`
  (0–1). None of this can make a sequence unclearable: the safety check
  covers every mix of obstacle types, and the spacing never goes below
  `SPACING_MIN` nor the speed above `SPEED_MAX`.
- `col_height[32]` mirrors the box height in pixels (0, 16 or 32) of each
  map column, so collision never reads VRAM: the hitbox is checked against
  the columns under its left and right edges.
- Score: +1 when an obstacle's right edge passes the panda's left edge
  (single or double column counts once). High score is updated and saved
  when the run ends.
- RNG: `rand()`/`initrand()`, seeded from `DIV` on the first button press
  on the title screen, then stirred (one `rand()` per frame) while the
  title stays up, so a run depends on when Start came too. A button held
  since power-on is not a press until it is released and pressed again.
- Clouds live in the sky band's map and scroll at a fraction of the world
  speed; new clouds are written into sky-band columns off-screen, at a
  fixed height (map rows 3–4; rows 2–3 would let the downward bob clip the
  cloud's top against the static HUD band) every few seconds. The band bobs
  gently with `cloud_bob`.

Messages (`GAME OVER`, `SCORE` / `NEW BEST!`, `PAUSED`) are BG text in
world rows 7–9, written only while the world is frozen. Row 6 stays plain
sky because the bobbing sky band reads into it.

## States and controls

`game_state`: `STATE_TITLE` 0, `STATE_PLAY` 1, `STATE_DEAD` 2,
`STATE_PAUSED` 3 (defined in `src/config.h`).

- Title: logo, running panda, `PRESS START`, high score. Start or A begins.
- Play: A jumps / double jumps. Start pauses (`STATE_PAUSED`, shows
  `PAUSED`, the music holds its place with `music_pause()`); Start again
  resumes (`music_resume()`, unless the music was switched off).
- Dead: death pose and fall, `GAME OVER`, score, `NEW BEST!` when it is.
  After a short delay Start or A starts a new run.

## Save RAM

At `0xA000` (enable with `ENABLE_RAM`, `SWITCH_RAM(0)`, disable after), two
copies ("slots") of 8 bytes: slot 0 at `0xA000`, slot 1 at `0xA008`.

| Offset | Value |
|--------|-------|
| 0–1 | Magic `'P' 'J'` |
| 2 | Format version, 2 |
| 3 | Sequence number: +1 per save, wraps 255 → 0 |
| 4–5 | High score, little-endian `uint16_t` |
| 6 | Checksum: `(uint8_t)~(sum of bytes 0–5)` |
| 7 | 0 (unused) |

- A slot is good when magic, version and checksum all match.
- Loading uses the good slot with the newest sequence number: slot 1 is
  newer when `(int8_t)(seq1 - seq0) > 0`, so 0 follows 255. If neither
  slot is good the high score is 0 and **nothing is written**; the next
  new best creates a good slot. Loading never writes.
- A save (only on a new best) goes to the slot that does not hold the
  newest good copy (slot 0 when there is none), with the next sequence
  number. It clears byte 0 first, then writes bytes 1–7, then writes
  byte 0 (`'P'`) last, so a power cut at any point leaves that slot bad
  and the other slot, with the previous best, untouched.
- Format 1 (a single 6-byte block at `0xA000`, from before the release) is
  not read.

## Symbols the tests read

Plain (non-`static`) globals, found through `build/pandajump.sym`
(C names get a leading `_`):

`game_state`, `score`, `high_score`, `panda_y` (8.8, top of the sprite in
screen pixels), `panda_vy` (8.8, positive is down), `panda_on_ground`,
`jumps_used`, `jump_buffer` (frames a kept press has left, 0 if none),
`world_x` (`uint16_t`, whole pixels scrolled this run), `world_sub`
(`uint8_t`, the fraction of a pixel in 1/256ths), `world_scx`,
`col_height[32]`, `frame_count` (`uint8_t`, +1 per frame),
`debug_invincible` (`uint8_t`, 0 in normal play; when a test sets it,
collisions are ignored), `world_speed` (8.8 px/frame, shows the ramp).

Timing that tests can rely on: a button press shows in RAM 2 frames after
it starts (the game reads the joypad right after VBlank and runs its logic
from line 1), except that a kept press acts on the landing frame; each
state change sets `game_state` last; BG text appears one frame after a
state change; the title logo turns into sky over 4 frames when a run
starts.

## Web player

`web/` runs the ROM in binjgb. It keeps the 8 KiB cartridge RAM in
`localStorage` under `pandajump.sram` (base64), plus `pandajump.palette`
and `pandajump.sound`, and exposes a read-only `window.pandajump` (state,
frames, ticks, joypad) for tests.

## Sound API (`src/sound.h`)

```c
void sound_init(void);      /* turn the APU on, set volumes */
void sound_update(void);    /* once per frame */
void sfx_jump(void);
void sfx_double_jump(void);
void sfx_score(void);
void sfx_death(void);
void sfx_start(void);       /* start a run / confirm */
void sfx_pause(void);
void music_play(uint8_t song);   /* MUSIC_TITLE or MUSIC_GAME */
void music_stop(void);
void music_pause(void);     /* silence, keeping the song's position */
void music_resume(void);    /* carry on from where music_pause() stopped */
```

`sfx_*()` only queue an effect; it starts on the next `sound_update()`. Call
none of these from an interrupt handler.

Sound effects use channels 1 and 4, so any music uses channels 2 and 3.

## Files

| Path | Owner |
|------|-------|
| `Makefile`, `docs/DESIGN.md` | shared |
| `art/*.png`, `tools/make_art.py`, `tools/preview_art.py` | art |
| `src/*` except `src/sound.*` | game code |
| `src/sound.c`, `src/sound.h` | sound |
| `web/*` | web player |
| `tests/*`, `tools/rom_shot.py` | tests |
| `ci/*` (copy to `.github/workflows/`), `README.md` | release |
