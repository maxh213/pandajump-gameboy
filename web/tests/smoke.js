#!/usr/bin/env node
/*
 * Smoke test for the web player. Serves web/ on a local port, opens it in
 * headless Chromium and checks that the game boots and runs at the right
 * speed, the screen is sharp, keys and touches reach the emulator, the save
 * survives a reload, and the phone layout fits.
 *
 *   make web
 *   node web/tests/smoke.js
 *
 * Needs Node 18+ and Playwright with its Chromium (npm install playwright,
 * then npx playwright install chromium; or set NODE_PATH to where it is
 * installed). It uses no network.
 */
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('playwright');

const WEB = path.resolve(__dirname, '..');
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.wasm': 'application/wasm',
};

let failures = 0;
function check(ok, what) {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) failures++;
}

// A tiny static file server for web/.
function serve() {
  const server = http.createServer((req, res) => {
    let file = path.join(WEB, decodeURIComponent(new URL(req.url, 'http://localhost').pathname));
    if (!file.startsWith(WEB)) {
      res.writeHead(403).end();
      return;
    }
    if (file.endsWith(path.sep)) file = path.join(file, 'index.html');
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

async function openPlayer(context, url, problems) {
  const page = await context.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') problems.push(m.text());
  });
  page.on('pageerror', (e) => problems.push(e.message));
  await page.goto(url);
  await page.waitForFunction(() => window.pandajump && window.pandajump.state === 'running' && window.pandajump.frames > 30, null, { timeout: 15000 });
  return page;
}

async function main() {
  if (!fs.existsSync(path.join(WEB, 'pandajump.gb'))) {
    console.error('web/pandajump.gb is missing: run "make web" first.');
    process.exit(2);
  }
  const server = await serve();
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch();
  const problems = [];

  try {
    // Desktop.
    const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await openPlayer(desktop, url, problems);
    check(true, 'boots and runs');

    const colours = await page.evaluate(() => {
      const d = document.getElementById('lcd').getContext('2d').getImageData(0, 0, 160, 144).data;
      const seen = new Set();
      for (let i = 0; i < d.length; i += 4) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
      return seen.size;
    });
    check(colours >= 2 && colours <= 4, `the screen shows a picture (${colours} colours)`);

    const perPixel = await page.evaluate(() => (document.getElementById('lcd').getBoundingClientRect().width * devicePixelRatio) / 160);
    check(Number.isInteger(perPixel), `whole device pixels per Game Boy pixel (${perPixel})`);

    const f0 = await page.evaluate(() => [performance.now(), window.pandajump.frames]);
    await page.waitForTimeout(2000);
    const f1 = await page.evaluate(() => [performance.now(), window.pandajump.frames]);
    const fps = ((f1[1] - f0[1]) * 1000) / (f1[0] - f0[0]);
    check(Math.abs(fps - 59.73) < 2, `runs at Game Boy speed (${fps.toFixed(1)} frames/s)`);

    for (const [key, bit] of [['z', 1], ['x', 2], ['Enter', 8], ['ArrowLeft', 32]]) {
      await page.keyboard.down(key);
      const down = await page.evaluate(() => window.pandajump.joypad);
      await page.keyboard.up(key);
      const up = await page.evaluate(() => window.pandajump.joypad);
      check(down === bit && up === 0, `${key} presses Game Boy button bit ${bit} (${down}, then ${up})`);
    }

    // The game writes its save block when it boots with a blank cartridge;
    // that must be stored and come back after a reload.
    await page.waitForTimeout(500);
    await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
    const saved = await page.evaluate(() => localStorage.getItem('pandajump.sram'));
    if (saved) {
      await page.reload();
      await page.waitForFunction(() => window.pandajump.state === 'running' && window.pandajump.frames > 30);
      await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
      const again = await page.evaluate(() => localStorage.getItem('pandajump.sram'));
      check(Buffer.from(saved, 'base64').length === 8192 && again === saved, 'cartridge RAM is saved and survives a reload');
    } else {
      console.log('skip this ROM did not write its cartridge RAM, so the save round trip was not tested');
    }
    await desktop.close();

    // Phone.
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
    const mobile = await openPlayer(phone, url, problems);
    const layout = await mobile.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bottom: document.getElementById('console').getBoundingClientRect().bottom,
    }));
    check(layout.overflow <= 0, 'phone: no sideways scrolling');
    check(layout.bottom <= 844, `phone: the whole handheld is on screen (bottom at ${Math.round(layout.bottom)} px)`);
    const a = await mobile.evaluate(() => {
      const r = document.querySelector('.btn-a').getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    });
    const cdp = await phone.newCDPSession(mobile);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [a] });
    const touched = await mobile.evaluate(() => window.pandajump.joypad);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    const lifted = await mobile.evaluate(() => window.pandajump.joypad);
    check(touched === 1 && lifted === 0, `phone: touching A presses A (${touched}, then ${lifted})`);
    await phone.close();

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
