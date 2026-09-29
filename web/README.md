# PandaJump in the browser

A static page that plays `pandajump.gb` in the [binjgb](https://github.com/binji/binjgb)
Game Boy emulator (WebAssembly). No build step and no dependencies from the
network: plain HTML, CSS and a script, all loaded by relative paths, so the
folder works on GitHub Pages or any other static host as it is.

| File | What it is |
|------|------------|
| `index.html` | The page: the handheld, settings, how to play |
| `style.css` | Layout and look (light and dark) |
| `player.js` | Drives the emulator: timing, screen, sound, input, saves |
| `favicon.svg` | Pixel panda icon |
| `vendor/` | binjgb's prebuilt `binjgb.js` and `binjgb.wasm` (MIT, see `vendor/README.md`) |
| `pandajump.gb` | The ROM, copied here by `make web` |
| `tests/smoke.js` | Browser smoke test (below) |

## Run it locally

```sh
make web                              # builds the ROM and copies it here
python3 -m http.server -d web 8000    # then open http://localhost:8000/
```

Opening `index.html` straight from disk doesn't work: browsers won't let a
`file://` page load the ROM, and the page says so.

## What the player does

- **Speed.** Each animation frame runs the emulator for exactly the real time
  that has passed, counted in Game Boy CPU ticks (4,194,304 a second), so the
  game runs at 59.73 frames a second on 60 Hz, 120 Hz or 144 Hz displays alike.
  After a stall it skips ahead at most 0.1 s rather than racing to catch up.
- **Screen.** A 160×144 canvas scaled by a whole number of device pixels per
  Game Boy pixel (`image-rendering: pixelated`), as big as the window allows.
  Palettes are applied by the page, so switching is instant, even while paused.
- **Sound.** The emulator's audio goes to Web Audio in 21 ms chunks, queued
  about 80 ms ahead. Browsers only allow sound after a click, tap or key press;
  the first one turns it on. Playback speed is nudged by at most 0.5% to keep
  the queue steady as the audio and page clocks drift.
- **Input.** Keyboard, gamepads (standard mapping) and the on-screen buttons
  (multi-touch; the D-pad can be slid across). Tapping or clicking the screen
  is A. Every press reaches the game for at least two frames, however quick
  the tap. Keys only go to the game when no page control needs them.
- **Saves.** The cartridge's battery RAM (8 KiB, where the game keeps its high
  score) is stored in `localStorage` as base64 under `pandajump.sram`: loaded
  before the game starts, written whenever the game writes to it, and again
  when the page is hidden or closed. If another tab saves, this tab stops and
  offers a reload, so an older copy can't overwrite a newer high score.
- **Pausing.** Emulation pauses while the tab is hidden. Coming back in the
  middle of a game waits for a button press (which doesn't also jump).
- **Settings.** The screen palette and the sound on/off switch (`M`) are
  remembered in `localStorage` (`pandajump.palette`, `pandajump.sound`).
- **Errors.** A missing ROM or emulator, a `file://` URL, a crashed CPU or
  blocked storage each show a plain message on the screen.

`window.pandajump` is a small read-only view of the player for tests:
`state` (`loading`, `running`, `paused` or `stopped`), `frames` (Game Boy
frames shown), `ticks` (CPU ticks run) and `joypad` (buttons held: A 1, B 2,
Select 4, Start 8, Right 16, Left 32, Up 64, Down 128).

## Test

`tests/smoke.js` serves this folder on a local port, opens it in headless
Chromium and checks the game boots, runs at Game Boy speed, draws a sharp
picture, takes keyboard and touch input, keeps its save across a reload and
fits a phone screen. It needs Node 18+ and Playwright with Chromium
(`npm install playwright && npx playwright install chromium`), but no network:

```sh
make web
node web/tests/smoke.js
```

## Credits

- Emulator: binjgb by Ben Smith, MIT licence (`vendor/LICENSE`).
- The way `player.js` drives binjgb follows binjgb's `docs/simple.js`, which
  builds on the GB Studio web player by Chris Maltby (MIT).
