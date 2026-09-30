# PandaJump in the browser

A static page that plays `pandajump.gb` in the [binjgb](https://github.com/binji/binjgb)
Game Boy emulator (WebAssembly). No build step and no dependencies from the
network: plain HTML, CSS and a script, all loaded by relative paths, so the
folder works on GitHub Pages (at `/pandajump-gameboy/`) or any other static
host as it is.

| File | What it is |
|------|------------|
| `index.html` | The page: the handheld, settings, how to play |
| `style.css` | Layout and look (light and dark) |
| `player.js` | Drives the emulator: timing, screen, sound, input, saves |
| `favicon.svg` | Pixel panda icon |
| `vendor/` | binjgb's prebuilt `binjgb.js` and `binjgb.wasm` (MIT, see `vendor/README.md`) |
| `pandajump.gb` | The ROM, copied here by `make web` |
| `tests/` | Browser smoke test with its own `package.json` (below) |

## Run it locally

```sh
make web                              # builds the ROM and copies it here
python3 -m http.server -d web 8000    # then open http://localhost:8000/
```

Opening `index.html` straight from disk doesn't work: browsers won't let a
`file://` page load the ROM, and the page says so.

## Keys

| Game Boy | Keys |
|----------|------|
| A (jump) | `Z`, `Space`, `W` or `↑`; on a touch screen, A or the game screen |
| B | `X` |
| Start | `Enter` |
| Select | `C` or `Backspace` (on the title screen it switches the music) |
| D-pad | Arrow keys |
| Sound on/off | `M` |

Shift is not a game key, so Shift+Tab only moves focus back through the
page. Gamepads with the standard mapping work too: the bottom and top face
buttons are A, the side ones B, plus Start, Select, the D-pad and the left
stick.

## What the player does

- **Speed.** Each animation frame runs the emulator for exactly the real time
  that has passed, counted in Game Boy CPU ticks (4,194,304 a second), so the
  game runs at 59.73 frames a second on 60 Hz, 120 Hz or 144 Hz displays alike.
  After a stall it skips ahead at most 0.1 s rather than racing to catch up.
- **Screen.** As big as the window allows, at a whole number k of device
  pixels per Game Boy pixel, so every Game Boy pixel is exactly k × k device
  pixels, at any pixel ratio (3× phones, 2.625× Pixels, 125% zoom). The page
  sizes the screen to 160k × 144k device pixels and a ResizeObserver
  (`device-pixel-content-box`) reports what the browser really laid out: if
  it's exact, the browser scales the 160×144 canvas (`image-rendering:
  pixelated`); if rounding left it a device pixel off, the player draws each
  frame at device resolution itself. Browsers that can't report device pixels
  (Safari) and Chrome's emulated devices get the browser's scaling. Palettes
  are applied by the page, so switching is instant, even while paused.
- **Layout.** The whole handheld, screen and buttons, fits on screen from
  320 × 568 phones upright to 568 × 320 phones on their side. Short windows
  that are wider than tall put the controls either side of the screen; very
  short upright ones get smaller buttons. A swipe on the handheld's shell
  still scrolls the page; the screen and buttons keep every touch.
- **Sound.** The emulator's audio goes to Web Audio in 21 ms chunks, queued
  about 80 ms ahead, at full level: the Game Boy mix never goes past about
  94% of full scale, so it can't clip. Browsers only allow sound after a
  click, tap or key press; the first one turns it on. Playback speed is
  nudged by at most 0.5% to keep the queue steady as the audio and page
  clocks drift.
- **Input.** Keyboard, gamepads (standard mapping) and the on-screen buttons
  (multi-touch; the D-pad can be slid across). Tapping or clicking the screen
  is A. Every press reaches the game for at least two frames, however quick
  the tap. Keys only go to the game when no page control needs them: Space
  and Enter press a focused button, Enter follows a focused link, Space and
  the arrows work the palette radios. Clicking or tapping the game hands the
  keys back to it, even if a control still had focus from the keyboard.
- **Saves.** The cartridge's battery RAM (8 KiB, where the game keeps its high
  score) is stored in `localStorage` as base64 under `pandajump.sram`: loaded
  before the game starts, written whenever the game writes to it, and again
  when the page is hidden or closed. If another tab saves something different
  from this tab's cartridge RAM, this tab stops and offers a reload, so an
  older copy can't overwrite a newer high score. Two cases are no conflict:
  the same save (a game that boots on a blank cartridge may write a fresh
  save block, the same in every tab opened together), and a tab whose game
  hasn't run yet, such as one opened or restored in the background: it
  hasn't read its cartridge RAM, so it simply starts from the newer save.
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

`tests/smoke.js` serves this folder under `/pandajump-gameboy/`, as GitHub
Pages does, opens it in headless Chromium and plays the real ROM. It reads
the game's own RAM (addresses from `build/pandajump.sym`) and the emulated
joypad register, and checks that:

- the game boots, draws a picture and runs at Game Boy speed;
- every key reaches the Game Boy's joypad, Shift doesn't, and Start and A
  start, pause and jump in the game itself;
- clicking the screen takes the keys back from a focused control, and Space
  on a focused link doesn't scroll the page;
- sound plays at a good level and never above full scale;
- tabs opened together keep running, a real new best in one stops another,
  a tab waiting in the background doesn't stop and starts with that best
  once it comes to the front, and the best score survives a reload;
- a missing ROM shows a message;
- touch works on a phone, and the whole handheld fits from 320 × 568 to
  844 × 390;
- at pixel ratios 1, 1.25, 2.625 and 3 every Game Boy pixel is exactly
  k × k device pixels (from screenshots), also when the layout comes out a
  device pixel bigger.

It needs Node 18+, and Playwright with its Chromium, installed in `tests/`
(not the repository root). It uses no network once installed, and takes
about 30 s:

```sh
make web
cd web/tests
npm install                      # Playwright, pinned in package-lock.json
npx playwright install chromium  # once, the browser Playwright drives
npm test
```

A Playwright installed elsewhere works too: `NODE_PATH=<its node_modules>
node web/tests/smoke.js`.

## Credits

- Emulator: binjgb by Ben Smith, MIT licence (`vendor/LICENSE`).
- The way `player.js` drives binjgb follows binjgb's `docs/simple.js`, which
  builds on the GB Studio web player by Chris Maltby (MIT).
