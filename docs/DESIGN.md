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
| 120–127 | Spare / decorations |

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
- Jump: pressing A on the ground sets `vy = -JUMP_VEL`. One more press in
  the air sets `vy = -DJUMP_VEL` (the double jump, like the original: it
  *sets* the velocity). Gravity `GRAVITY` per frame, capped at
  `MAX_FALL`. The panda is on the ground when its feet reach `GROUND_Y`;
  that resets the double jump. It can't go above the top of the screen.
- Scroll: `world_x` advances by the current speed (starts at `SPEED_BASE`
  px/frame) each frame; `world_scx` is its low byte. When `world_x >> 3`
  changes, the column `(world_x >> 3) + 21` (mod 32), which is off-screen
  to the right, is generated and written to the map (rows 10–13 only).
- Obstacles: a column is 2 tiles wide with 1 or 2 boxes (50/50). Once the
  score is above 10, one in three obstacles is a double column (two
  columns side by side, same height). After each obstacle the generator
  leaves `SPACING - 2` empty tiles (plus a random 0–3), so single columns
  start `SPACING` tiles apart and a double column is followed by
  `SPACING + 2`; `src/config.h` derives the safe minimum from the physics; the difficulty ramp raises the speed and shortens the spacing as
  the score grows, down to limits that the physics can still clear.
- `col_height[32]` mirrors the box height in pixels (0, 16 or 32) of each
  map column, so collision never reads VRAM: the hitbox is checked against
  the columns under its left and right edges.
- Score: +1 when an obstacle's right edge passes the panda's left edge
  (single or double column counts once). High score is updated and saved
  when the run ends.
- RNG: `rand()`/`initrand()`, seeded from `DIV` on the first button press
  on the title screen.
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
  `PAUSED`); Start again resumes.
- Dead: death pose and fall, `GAME OVER`, score, `NEW BEST!` when it is.
  After a short delay Start or A starts a new run.

## Save RAM

At `0xA000` (enable with `ENABLE_RAM`, `SWITCH_RAM(0)`, disable after):

| Offset | Value |
|--------|-------|
| 0–1 | Magic `'P' 'J'` |
| 2 | Format version, 1 |
| 3–4 | High score, little-endian `uint16_t` |
| 5 | Checksum: `(uint8_t)~(sum of bytes 0–4)` |

If any check fails, the high score is 0 and the block is rewritten.

## Symbols the tests read

Plain (non-`static`) globals, found through `build/pandajump.sym`
(C names get a leading `_`):

`game_state`, `score`, `high_score`, `panda_y` (8.8, top of the sprite in
screen pixels), `panda_vy` (8.8, positive is down), `panda_on_ground`,
`jumps_used`, `world_x` (`uint16_t`, whole pixels scrolled this run),
`world_scx`, `col_height[32]`, `frame_count` (`uint8_t`, +1 per frame),
`debug_invincible` (`uint8_t`, 0 in normal play; when a test sets it,
collisions are ignored), `world_speed` (8.8 px/frame, shows the ramp).

Timing that tests can rely on: a button press shows in RAM 2 frames after
it starts (the game reads the joypad right after VBlank and runs its logic
from line 1); each state change sets `game_state` last; BG text appears
one frame after a state change; the title logo turns into sky over 4
frames when a run starts.

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
