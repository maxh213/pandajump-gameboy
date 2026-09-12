# PandaJump for Game Boy — build prompt

Port **PandaJump** to the original Game Boy (DMG), written in C.

- Original game (2014, Phaser 1.1.5, JavaScript): https://github.com/maxh213/PandaJump
- Read `main.js` there first. It's ~300 lines and is the spec for the gameplay.

## The game, as it exists

A 400×490 endless runner. A panda runs in place while the world scrolls left.

- **Controls:** one input (click/touch) to jump. A second press mid-air gives a smaller double jump (-580 then -250 velocity, gravity 1000, slight bounce).
- **Obstacles:** every 1.5s a column of 1–2 stacked boxes spawns at the right edge and moves left at 200px/s. Once the score passes 10, a second column sometimes spawns right behind the first (1 in 3 chance).
- **Death:** touching a box restarts the game.
- **Score:** +1 per box column, shown top-left. The high score is kept in `localStorage` and shown bottom-left.
- **Scenery:** a scrolling grass-topped rock floor, and a slow-drifting cloud that bobs up and down.
- **Assets:** `assets/Panda.png` (20px-wide frames, 34 in the sheet; the run cycle is frames 17–22), 64×64 terrain tiles (`dirt_06` for boxes, `rock_06` for ground, `top_grass_01`), and `cloud_02`.

### Quirks in the original — don't copy these
- Whether the panda can jump is decided by its y position being between 390 and 470. Use a proper "on the ground" check instead.
- The score goes up when a column *spawns*, which is why the `firstbox` hack exists. Score when the panda *clears* a column.
- The cloud timer is 50–92 **seconds**, so you rarely see a second cloud. Pick a sensible rate.
- The scrolling floor is faked with three overlapping tile layers and a -10px fudge to hide gaps. On the Game Boy, hardware scrolling replaces all of this.

## Target and toolchain

- **GBDK-2020** (4.5.x; on Arch it's `gbdk-2020` in the AUR), which uses the SDCC compiler. Use `png2asset` to convert art.
- Output a `.gb` ROM using an **MBC5 cartridge with battery-backed save RAM** (for the high score).
- Test in **mGBA**, and use Emulicious when you need a debugger.
- Include a `Makefile` so `make` builds the ROM and `make run` launches it in mGBA.

## Translating the design

| Original | Game Boy |
|---|---|
| 400×490 portrait | 160×144 landscape; rescale all distances and speeds to roughly a third |
| Full-colour art | 4 shades |
| 20px panda frames | 16×16 metasprite (4 × 8×8 hardware sprites), 3 colours + transparent |
| Boxes as physics sprites | **Background tiles**, not sprites (limits: 40 sprites total, 10 per scanline) |
| Three fake scrolling tile layers | Scroll the background with the scroll register (`SCX`) and write new tile columns just off-screen |
| Cloud drifting slower than the floor | Parallax using a mid-screen scanline interrupt (LYC) that sets a different `SCX` for the sky band |
| Float physics | 8.8 fixed-point position and velocity |
| Sprite overlap checks | Look up which tiles are under the panda's hitbox |
| `Math.random()` | `rand()`, seeded from the `DIV` register when the player first presses a button |
| `localStorage` high score | Cartridge save RAM, checked with a magic byte so a blank or corrupt save reads as 0 |
| Click/touch | **A** button to jump; **Start** to begin or restart |

## The hard parts

1. **Art is the biggest job.** Automatic downscaling will look muddy (`sand_06.png` alone has 2,015 colours). Hand-pixel these:
   - a 16×16 panda run cycle (about 4–6 frames), plus jump and death poses
   - 16×16 box, ground and grass tiles
   - a cloud
   - a small digit font for the score

   Keep the original's look: sky-blue background (`#71c5cf`) becomes the lightest shade, a white panda, a dark ground.
2. **Timing new box columns** so they're written into background memory just before scrolling into view, and keeping the score in step with them.
3. **Drawing text** (score and high score) with background or window tiles.

## Milestones

1. A "hello panda" ROM: the panda metasprite animating on a blank screen, running in mGBA.
2. A scrolling ground using `SCX`, with jump and double jump physics in fixed point.
3. Box columns, tile-based collision, death and restart.
4. Score and high score, with the high score saved to cartridge RAM.
5. Cloud parallax using the LYC interrupt.
6. Sound: jump and death effects using the sound registers. Optional: music made with hUGETracker.
7. Polish: title screen, difficulty ramp, README with screenshots and a downloadable ROM.

## Related idea (keep in mind)

There's a parallel plan to also remake the web version in **Phaser 4 + Vite + TypeScript**. If art is made at Game Boy resolution (160×144, 4-shade palette, 16px tiles), one art pass can serve both versions. Store art as source PNGs in `art/` so the web version can reuse them. The web version could also embed this ROM in a browser emulator.
