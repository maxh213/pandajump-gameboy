#!/usr/bin/env node
/*
 * Smoke test for the web player. Serves web/ under /pandajump-gameboy/ (the
 * sub-path GitHub Pages uses), opens it in headless Chromium and checks,
 * against the real game ROM:
 *
 *   - it boots, draws a picture and runs at Game Boy speed;
 *   - every key reaches the emulated Game Boy's joypad (read from the
 *     joypad register), Shift is not a game key, and Start and A change the
 *     game's own state (game_state, jumps_used, read from its RAM through
 *     build/pandajump.sym);
 *   - clicking the screen hands the keys back from a focused page control,
 *     and Space on a focused link doesn't scroll the page;
 *   - sound plays, loud enough and never above full scale;
 *   - tabs opened together all keep running, a new best in one stops
 *     another, a tab waiting in the background (not started yet) neither
 *     stops nor loses that best, and the best score survives a reload (a
 *     real game over);
 *   - a missing ROM shows a message;
 *   - phones: touch reaches the game, and the whole handheld fits on
 *     screen from 320 x 568 to 844 x 390, with no sideways scrolling;
 *   - at device pixel ratios 1, 1.25, 2.625 and 3, every Game Boy pixel is
 *     exactly k x k device pixels (checked in screenshots), also when the
 *     screen comes out a device pixel bigger than 160k x 144k.
 *
 *   make web
 *   cd web/tests && npm install && npx playwright install chromium && npm test
 *
 * It needs build/pandajump.sym (make web builds it) and no network.
 */
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');
const zlib = require('zlib');
const { chromium } = require('playwright');

const WEB = path.resolve(__dirname, '..');
const SYM = path.resolve(__dirname, '../../build/pandajump.sym');
const BASE = '/pandajump-gameboy/';
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.wasm': 'application/wasm',
};

// The game's states (src/config.h).
const TITLE = 0;
const PLAY = 1;
const DEAD = 2;
const PAUSED = 3;

let failures = 0;
function check(ok, what) {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) failures++;
}

// ------------------------------------------------------------ setup

// A tiny static file server for web/, under BASE like GitHub Pages.
function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === BASE.slice(0, -1)) {
      res.writeHead(301, { Location: BASE }).end();
      return;
    }
    if (!url.pathname.startsWith(BASE)) {
      res.writeHead(404).end('not found');
      return;
    }
    let file = path.join(WEB, decodeURIComponent(url.pathname.slice(BASE.length)));
    if (!file.startsWith(WEB)) {
      res.writeHead(403).end();
      return;
    }
    if (file === WEB || file.endsWith(path.sep)) file = path.join(file, 'index.html');
    fs.readFile(file, (err, data) => {
      if (err) {
        res.writeHead(404).end('not found');
        return;
      }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

// Addresses of the game's variables, from the linker's symbol file.
function readSymbols() {
  const syms = {};
  for (const line of fs.readFileSync(SYM, 'utf8').split('\n')) {
    const m = /^[0-9A-Fa-f]{2}:([0-9A-Fa-f]{4}) _(\w+)/.exec(line);
    if (m) syms[m[2]] = parseInt(m[1], 16);
  }
  for (const name of ['game_state', 'score', 'high_score', 'jumps_used', 'debug_invincible']) {
    if (!(name in syms)) throw new Error(`${name} is not in ${SYM}`);
  }
  return syms;
}

// Runs in the page before its scripts. Wraps binjgb's Binjgb() so the test
// can read and write the emulated Game Boy's memory (window.__gb), and
// records the sound the player queues (window.__audio).
function pageHooks() {
  let factory;
  Object.defineProperty(window, 'Binjgb', {
    configurable: true,
    set(value) {
      factory = value;
    },
    get() {
      return factory && ((options) => factory(options).then((m) => {
        const create = m._emulator_new_simple;
        m._emulator_new_simple = (...args) => {
          const e = create(...args);
          const peek = (addr) => m._emulator_read_mem(e, addr);
          const poke = (addr, value) => m._emulator_write_mem(e, addr, value);
          // The buttons the Game Boy sees, read from its joypad register
          // (P1, 0xFF00), in window.pandajump.joypad's bit order. The game's
          // own P1 selection is put back afterwards.
          const buttons = () => {
            const selected = peek(0xff00) & 0x30;
            poke(0xff00, 0x10);
            const action = ~peek(0xff00) & 0x0f;
            poke(0xff00, 0x20);
            const direction = ~peek(0xff00) & 0x0f;
            poke(0xff00, selected);
            return action | (direction << 4);
          };
          window.__gb = { peek, poke, buttons };
          return e;
        };
        return m;
      }));
    },
  });

  window.__audio = { peak: 0, chunks: 0, gain: null };
  const start = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function (...args) {
    const buffer = this.buffer;
    if (buffer) {
      for (let c = 0; c < buffer.numberOfChannels; c++) {
        for (const v of buffer.getChannelData(c)) window.__audio.peak = Math.max(window.__audio.peak, Math.abs(v));
      }
      window.__audio.chunks++;
    }
    return start.apply(this, args);
  };
  const createGain = AudioContext.prototype.createGain;
  AudioContext.prototype.createGain = function () {
    const node = createGain.call(this);
    window.__audio.gain = node.gain;
    return node;
  };
}

// Runs in the page before its scripts: the page is told it is hidden, as a
// tab opened in the background (middle click, session restore) is, until
// the test calls window.__show().
function hiddenUntilShown() {
  let hidden = true;
  Object.defineProperty(Document.prototype, 'hidden', { configurable: true, get: () => hidden });
  Object.defineProperty(Document.prototype, 'visibilityState', {
    configurable: true,
    get: () => (hidden ? 'hidden' : 'visible'),
  });
  window.__show = () => {
    hidden = false;
    document.dispatchEvent(new Event('visibilitychange'));
  };
}

// Opens the player in a new tab and, unless told not to, waits until the
// game runs. A background tab starts hidden (see hiddenUntilShown).
async function openPlayer(context, url, problems, { wait = true, background = false } = {}) {
  const page = await context.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') problems.push(m.text());
  });
  page.on('pageerror', (e) => problems.push(e.message));
  await page.addInitScript(pageHooks);
  if (background) await page.addInitScript(hiddenUntilShown);
  await page.goto(url);
  if (wait) await waitRunning(page);
  return page;
}

function waitRunning(page) {
  return page.waitForFunction(
    () => window.pandajump && window.pandajump.state === 'running' && window.pandajump.frames > 30 && window.__gb,
    null,
    { timeout: 15000 },
  );
}

// Waits until the game has run for a moment, or the player has stopped.
function waitStarted(page) {
  return page.waitForFunction(
    () => window.pandajump && (window.pandajump.state === 'stopped' || (window.pandajump.frames > 30 && window.__gb)),
    null,
    { timeout: 15000 },
  );
}

// The player's state, the CPU ticks it has run, and any message over the
// game screen.
function playerStatus(page) {
  return page.evaluate(() => {
    const overlay = document.getElementById('overlay');
    const message = overlay.hidden ? '' : [...overlay.querySelectorAll('p')].map((p) => p.textContent).join(' ');
    return { state: window.pandajump.state, ticks: window.pandajump.ticks, message };
  });
}

// ------------------------------------------------------------ game memory

function peek(page, addr) {
  return page.evaluate((a) => window.__gb.peek(a), addr);
}

function poke(page, addr, value) {
  return page.evaluate(([a, v]) => window.__gb.poke(a, v), [addr, value]);
}

async function waitFor(page, addr, value, timeout = 3000) {
  try {
    await page.waitForFunction(([a, v]) => window.__gb.peek(a) === v, [addr, value], { timeout });
    return true;
  } catch (err) {
    return false;
  }
}

async function tapKey(page, key) {
  await page.keyboard.down(key);
  await page.waitForTimeout(60);
  await page.keyboard.up(key);
  await page.waitForTimeout(60);
}

// ------------------------------------------------------------ screenshots

// Decodes an 8-bit RGB or RGBA PNG (what Chromium's screenshots are).
function decodePng(buf) {
  let pos = 8;
  let width = 0;
  let height = 0;
  let bpp = 0;
  const data = [];
  while (pos < buf.length) {
    const length = buf.readUInt32BE(pos);
    const type = buf.toString('latin1', pos + 4, pos + 8);
    const chunk = buf.subarray(pos + 8, pos + 8 + length);
    if (type === 'IHDR') {
      width = chunk.readUInt32BE(0);
      height = chunk.readUInt32BE(4);
      bpp = { 2: 3, 6: 4 }[chunk[9]];
      if (chunk[8] !== 8 || !bpp || chunk[12] !== 0) throw new Error('unsupported PNG');
    } else if (type === 'IDAT') {
      data.push(chunk);
    }
    pos += 12 + length;
  }
  const raw = zlib.inflateSync(Buffer.concat(data));
  const stride = width * bpp;
  const px = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = y * (stride + 1) + 1;
    const row = y * stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? px[row + x - bpp] : 0;
      const b = y ? px[row - stride + x] : 0;
      const c = x >= bpp && y ? px[row - stride + x - bpp] : 0;
      let v = raw[src + x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a);
        const pb = Math.abs(p - b);
        const pc = Math.abs(p - c);
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      px[row + x] = v & 0xff;
    }
  }
  return { width, height, rgb: (x, y) => px.readUIntBE(y * stride + x * bpp, 3) };
}

// Whether the screenshot shows the 160 x 144 picture as k x k blocks of one
// colour each, on a grid near (x0, y0). Returns the best grid found.
function findGrid(img, x0, y0, k) {
  let best = null;
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      const ox = x0 + dx;
      const oy = y0 + dy;
      if (ox < 0 || oy < 0 || ox + 160 * k > img.width || oy + 144 * k > img.height) continue;
      let uneven = 0;
      const colours = new Set();
      for (let j = 0; j < 144; j++) {
        for (let i = 0; i < 160; i++) {
          const colour = img.rgb(ox + i * k, oy + j * k);
          colours.add(colour);
          let same = true;
          for (let y = 0; y < k && same; y++) {
            for (let x = 0; x < k && same; x++) same = img.rgb(ox + i * k + x, oy + j * k + y) === colour;
          }
          if (!same) uneven++;
        }
      }
      if (!best || uneven < best.uneven) best = { uneven, colours: colours.size };
    }
  }
  return best || { uneven: 160 * 144, colours: 0 };
}

// ------------------------------------------------------------ checks

async function desktopChecks(browser, url, syms, problems) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await openPlayer(context, url, problems);
  check(true, 'boots and runs from a sub-path');
  check(await peek(page, syms.game_state) === TITLE, 'the game is on its title screen');

  const colours = await page.evaluate(() => {
    const canvas = document.getElementById('lcd');
    const d = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const seen = new Set();
    for (let i = 0; i < d.length; i += 4) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
    return seen.size;
  });
  check(colours >= 2 && colours <= 4, `the screen shows a picture (${colours} colours)`);

  const f0 = await page.evaluate(() => [performance.now(), window.pandajump.frames]);
  await page.waitForTimeout(2000);
  const f1 = await page.evaluate(() => [performance.now(), window.pandajump.frames]);
  const fps = ((f1[1] - f0[1]) * 1000) / (f1[0] - f0[0]);
  check(Math.abs(fps - 59.73) < 2, `runs at Game Boy speed (${fps.toFixed(1)} frames/s)`);

  // The game itself responds: Start begins a run, A jumps, Start pauses.
  await tapKey(page, 'Enter');
  check(await waitFor(page, syms.game_state, PLAY), 'Enter (Start) begins a run in the game');
  await poke(page, syms.debug_invincible, 1); // the run must not end during the checks
  await page.waitForTimeout(100);
  await tapKey(page, 'Space');
  check(await waitFor(page, syms.jumps_used, 1), 'Space (A) makes the panda jump');
  await tapKey(page, 'Enter');
  check(await waitFor(page, syms.game_state, PAUSED), 'Enter (Start) pauses the game');
  await tapKey(page, 'Enter');
  check(await waitFor(page, syms.game_state, PLAY), 'Enter (Start) carries on');

  // Every key, as the Game Boy's joypad register sees it.
  const KEYS = [
    ['z', 0x01], ['Space', 0x01], ['w', 0x01], ['x', 0x02], ['c', 0x04], ['Backspace', 0x04], ['Enter', 0x08],
    ['ArrowRight', 0x10], ['ArrowLeft', 0x20], ['ArrowUp', 0x41], ['ArrowDown', 0x80], ['Shift', 0],
  ];
  for (const [key, bits] of KEYS) {
    await page.keyboard.down(key);
    const down = await page.evaluate(() => window.__gb.buttons());
    await page.keyboard.up(key);
    await page.waitForTimeout(80); // a press lasts at least two frames
    const up = await page.evaluate(() => window.__gb.buttons());
    check(down === bits && up === 0, `${key} reaches the Game Boy as buttons ${bits} (${down}, then ${up})`);
  }
  await page.waitForTimeout(100);
  if (await peek(page, syms.game_state) === PAUSED) await tapKey(page, 'Enter');

  // Shift+Tab moves focus and nothing else.
  await page.keyboard.down('Shift');
  await page.keyboard.press('Tab');
  const shiftTab = await page.evaluate(() => [window.pandajump.joypad, window.__gb.buttons()]);
  await page.keyboard.up('Shift');
  check(shiftTab[0] === 0 && shiftTab[1] === 0, 'Shift+Tab presses no Game Boy button');

  // A page control reached with Tab gives the keys back when the screen is
  // clicked: Space then jumps instead of pressing the control.
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  for (let i = 0; i < 12 && (await page.evaluate(() => document.activeElement.id)) !== 'sound'; i++) {
    await page.keyboard.press('Tab');
  }
  const tabbed = await page.evaluate(() => document.activeElement.id);
  await page.evaluate(() => window.scrollTo(0, 0));
  const lcd = await page.locator('#lcd').boundingBox();
  await page.mouse.click(lcd.x + lcd.width / 2, lcd.y + lcd.height / 2);
  const afterClick = await page.evaluate(() => document.activeElement.tagName);
  await page.waitForTimeout(150); // the click's own A press ends
  await page.keyboard.down('Space');
  const spaceBits = await page.evaluate(() => window.__gb.buttons());
  await page.keyboard.up('Space');
  const soundOn = await page.getAttribute('#sound', 'aria-pressed');
  check(tabbed === 'sound' && afterClick === 'BODY' && spaceBits === 1 && soundOn === 'true',
    `clicking the screen takes the keys back from a focused control (focus ${tabbed} -> ${afterClick}, Space ${spaceBits}, sound ${soundOn})`);

  await page.waitForTimeout(150);
  await page.focus('#download');
  const scrollBefore = await page.evaluate(() => window.scrollY);
  await page.keyboard.down('Space');
  const linkBits = await page.evaluate(() => window.__gb.buttons());
  await page.keyboard.up('Space');
  await page.waitForTimeout(100);
  const scrollAfter = await page.evaluate(() => window.scrollY);
  check(linkBits === 1 && scrollAfter === scrollBefore, `Space with the Download link focused jumps and doesn't scroll (${linkBits}, scroll ${scrollBefore} -> ${scrollAfter})`);

  // Sound: the clicks and keys above allowed it to start.
  await page.waitForTimeout(500);
  const audio = await page.evaluate(() => ({ ...window.__audio, gain: window.__audio.gain && window.__audio.gain.value }));
  const level = audio.peak * (audio.gain || 0);
  check(audio.chunks > 20 && level > 0.2 && level <= 1, `sound plays at a good level (${audio.chunks} chunks, peak output ${level.toFixed(2)})`);

  await context.close();
}

// On a fresh browser: a tab opened in the background (hidden, so its game
// hasn't started), then three tabs opened together, then a real new best
// in one of them. Before the fixes the three
// tabs caught the false "played in another tab" about 8 runs in 10 (it
// depends on the order the saves land in), and the background tab every
// time.
async function saveChecks(browser, url, syms, problems) {
  const context = await browser.newContext({ viewport: { width: 1000, height: 700 } });
  const background = await openPlayer(context, url, problems, { wait: false, background: true });
  await background.waitForFunction(() => window.pandajump && window.pandajump.state === 'paused' && window.__gb, null, { timeout: 15000 });
  const tabs = await Promise.all([1, 2, 3].map(() => openPlayer(context, url, problems, { wait: false })));
  await Promise.all(tabs.map(waitStarted));
  await tabs[0].waitForTimeout(1000);
  const states = await Promise.all(tabs.map((p) => p.evaluate(() => window.pandajump.state)));
  check(states.every((s) => s === 'running'), `three tabs opened together all keep running (${states.join(', ')})`);
  let waiting = await playerStatus(background);
  check(waiting.state === 'paused' && waiting.ticks === 0 && !waiting.message,
    `a tab opened in the background waits, game not started, and doesn't stop (${waiting.state}, ${waiting.ticks} ticks${waiting.message ? ', "' + waiting.message + '"' : ''})`);
  const [a, b] = tabs;
  if (states[1] !== 'running') {
    await context.close();
    return;
  }

  // A real game over with a new best of 7 in tab B: the score is set in the
  // game's RAM, then the panda runs into the first box.
  const blank = await b.evaluate(() => localStorage.getItem('pandajump.sram'));
  await tapKey(b, 'Enter');
  const started = await waitFor(b, syms.game_state, PLAY);
  await poke(b, syms.score, 7);
  await poke(b, syms.score + 1, 0);
  const died = started && await waitFor(b, syms.game_state, DEAD, 20000);
  await waitFor(b, syms.high_score, 7, 5000);
  const best = await peek(b, syms.high_score) | (await peek(b, syms.high_score + 1) << 8);
  check(died && best === 7, `a game over with score 7 sets the best score (${best})`);
  const saved = await b.waitForFunction((old) => {
    const text = localStorage.getItem('pandajump.sram');
    return text !== old && text;
  }, blank, { timeout: 5000 }).then((handle) => handle.jsonValue(), () => null);
  check(saved !== null && Buffer.from(saved, 'base64').length === 8192, 'the new best is saved in localStorage (8 KiB of cartridge RAM)');
  await b.waitForTimeout(200); // the storage event reaches the other tabs

  const other = await a.evaluate(() => [window.pandajump.state, document.getElementById('overlay').textContent]);
  check(other[0] === 'stopped' && /another tab/.test(other[1]), `another tab stops after the new best (${other[0]})`);

  // The background tab's game hasn't read its cartridge RAM yet, so it
  // takes the new save and starts from it when it comes to the front.
  waiting = await playerStatus(background);
  check(waiting.state === 'paused' && !waiting.message,
    `the background tab doesn't stop after the new best (${waiting.state}${waiting.message ? ', "' + waiting.message + '"' : ''})`);
  await background.evaluate(() => window.__show());
  const shown = waiting.state === 'paused' && await waitRunning(background).then(() => true, () => false);
  const adopted = shown ? await peek(background, syms.high_score) | (await peek(background, syms.high_score + 1) << 8) : -1;
  check(adopted === 7, `brought to the front, the background tab starts with the new best (${adopted})`);

  await b.reload();
  await waitRunning(b);
  const reloaded = await peek(b, syms.high_score) | (await peek(b, syms.high_score + 1) << 8);
  check(reloaded === 7 && await peek(b, syms.game_state) === TITLE, `the best score survives a reload (${reloaded})`);
  await context.close();
}

async function missingRomCheck(browser, url) {
  const context = await browser.newContext({ viewport: { width: 1000, height: 700 } });
  await context.route('**/pandajump.gb', (route) => route.fulfill({ status: 404, body: 'not found' }));
  const page = await context.newPage();
  await page.goto(url);
  const shown = await page.waitForFunction(() => window.pandajump && window.pandajump.state === 'stopped', null, { timeout: 15000 })
    .then(() => page.textContent('#overlay'), () => '');
  check(/ROM is missing/.test(shown), 'a missing ROM shows a message');
  await context.close();
}

async function phoneChecks(browser, url, syms, problems) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  const page = await openPlayer(context, url, problems);
  const cdp = await context.newCDPSession(page);
  const touch = async (selector) => {
    const r = await page.locator(selector).boundingBox();
    const point = { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point] });
    await page.waitForTimeout(50);
    const bits = await page.evaluate(() => window.__gb.buttons());
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(100);
    return bits;
  };
  const a = await touch('.btn-a');
  check(a === 1 && await waitFor(page, syms.game_state, PLAY), `phone: touching A presses A and begins a run (${a})`);
  await poke(page, syms.debug_invincible, 1);
  await page.waitForTimeout(1200); // land again
  const jumps = await peek(page, syms.jumps_used);
  const screen = await touch('#screen');
  check(screen === 1 && await waitFor(page, syms.jumps_used, jumps === 1 ? 2 : 1), `phone: tapping the screen jumps (${screen})`);
  await context.close();
}

// The whole handheld fits on screen, with no sideways scrolling.
async function fitChecks(browser, url, problems) {
  const SIZES = [[390, 844, 3], [360, 780, 3], [375, 553, 3], [320, 568, 2], [844, 390, 3], [640, 360, 3], [568, 320, 2]];
  for (const [width, height, dpr] of SIZES) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: dpr, isMobile: true, hasTouch: true });
    const page = await openPlayer(context, url, problems);
    const layout = await page.evaluate(() => {
      let bottom = 0;
      let right = 0;
      for (const el of document.querySelectorAll('#console, #console button, #screen')) {
        const r = el.getBoundingClientRect();
        bottom = Math.max(bottom, r.bottom);
        right = Math.max(right, r.right);
      }
      return {
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        bottom: Math.round(bottom),
        right: Math.round(right),
        screen: Math.round(document.getElementById('screen').getBoundingClientRect().width),
      };
    });
    check(layout.overflow <= 0 && layout.bottom <= height && layout.right <= width,
      `${width} x ${height}: the whole handheld is on screen (bottom ${layout.bottom}, screen ${layout.screen} px wide)`);
    await context.close();
  }
}

// Every Game Boy pixel is k x k device pixels. Each pixel ratio needs its
// own browser: Chromium's emulated ratios don't draw at device resolution.
// The screen is normally exactly 160k x 144k device pixels; the "bigger"
// cases make it one device pixel wider and taller, as a browser's rounding
// might, so the player has to draw at device resolution itself.
async function pixelChecks(url, syms, problems) {
  const CASES = [
    [1280, 800, 1], [1280, 800, 1.25], [412, 915, 2.625], [360, 780, 3], [844, 390, 3],
    [412, 915, 2.625, 'bigger'], [360, 780, 3, 'bigger'],
  ];
  for (const [width, height, dpr, bigger] of CASES) {
    const browser = await chromium.launch({ args: [`--force-device-scale-factor=${dpr}`, `--window-size=${width},${height}`] });
    try {
      const context = await browser.newContext({ viewport: null });
      const page = await openPlayer(context, url, problems);
      if (bigger) {
        const extra = `${1 / dpr}px`;
        await page.addStyleTag({
          content: `.screen { width: calc(var(--screen-w) + ${extra}) !important; height: calc(var(--screen-h) + ${extra}) !important; }`,
        });
        await page.waitForTimeout(200);
      }
      // A paused game shows a still picture.
      await tapKey(page, 'Enter');
      await waitFor(page, syms.game_state, PLAY);
      await page.waitForTimeout(300);
      await tapKey(page, 'Enter');
      const paused = await waitFor(page, syms.game_state, PAUSED);
      await page.evaluate(() => document.getElementById('lcd').scrollIntoView({ block: 'nearest' }));
      await page.waitForTimeout(200);
      const box = await page.evaluate(() => {
        const r = document.getElementById('lcd').getBoundingClientRect();
        return { left: r.left, top: r.top, width: r.width, dpr: window.devicePixelRatio };
      });
      const k = Math.round((box.width * box.dpr) / 160);
      const grid = findGrid(decodePng(await page.screenshot()), Math.round(box.left * box.dpr), Math.round(box.top * box.dpr), k);
      check(paused && box.dpr === dpr && grid.uneven === 0 && grid.colours >= 3 && grid.colours <= 4,
        `${width} x ${height} at ${dpr}x${bigger ? ', screen a device pixel bigger' : ''}: every Game Boy pixel is ${k} x ${k} device pixels (${grid.uneven} uneven, ${grid.colours} colours)`);
    } finally {
      await browser.close();
    }
  }
}

async function main() {
  if (!fs.existsSync(path.join(WEB, 'pandajump.gb')) || !fs.existsSync(SYM)) {
    console.error('web/pandajump.gb or build/pandajump.sym is missing: run "make web" first.');
    process.exit(2);
  }
  const syms = readSymbols();
  const server = await serve();
  const url = `http://127.0.0.1:${server.address().port}${BASE}`;
  const browser = await chromium.launch();
  const problems = [];

  try {
    await desktopChecks(browser, url, syms, problems);
    await saveChecks(browser, url, syms, problems);
    await missingRomCheck(browser, url);
    await phoneChecks(browser, url, syms, problems);
    await fitChecks(browser, url, problems);
    await pixelChecks(url, syms, problems);
    check(problems.length === 0, `no console errors or warnings${problems.length ? ': ' + problems.join(' | ') : ''}`);
  } finally {
    await browser.close();
    server.close();
  }
  console.log(failures ? `${failures} check(s) failed` : 'all checks passed');
  process.exit(failures ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
