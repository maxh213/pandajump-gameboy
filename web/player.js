/*
 * PandaJump web player: runs pandajump.gb in the browser.
 *
 * The Game Boy itself is binjgb by Ben Smith (vendor/, MIT), compiled to
 * WebAssembly. This file is the glue between it and the page: it paces the
 * emulator in real time, draws its frames on the canvas, plays its sound
 * through Web Audio, feeds it the keyboard, gamepads and on-screen buttons,
 * and keeps the cartridge's battery RAM (the high score) in localStorage.
 *
 * How the emulator is driven (running it until a tick count each animation
 * frame, handing its audio buffers to Web Audio, reading and writing ext RAM)
 * follows binjgb's docs/simple.js, which is based on the GB Studio web player
 * by Chris Maltby (MIT). The rest is written for this page.
 *
 * A plain script, no build step: index.html loads vendor/binjgb.js first,
 * which defines the global Binjgb().
 */
(function () {
  'use strict';

  // ------------------------------------------------------------ settings

  const ROM_URL = 'pandajump.gb';

  // localStorage keys.
  const KEY_SAVE = 'pandajump.sram'; // cartridge RAM, base64
  const KEY_PALETTE = 'pandajump.palette';
  const KEY_SOUND = 'pandajump.sound'; // 'on' or 'off'

  // The Game Boy CPU clock. A frame is 70224 ticks, so 59.73 frames a second.
  const CPU_TICKS_PER_SECOND = 4194304;
  const FRAME_TICKS = 70224;
  // A button stays down in the emulator for at least this long, so a tap that
  // starts and ends between two display frames still reaches the game (which
  // reads the buttons once a frame).
  const MIN_HOLD_TICKS = 2 * FRAME_TICKS;
  // After a stall (a busy tab, a debugger), skip time instead of racing.
  const MAX_STEP_SECONDS = 0.1;

  const AUDIO_RATE = 48000; // samples a second the emulator makes
  const AUDIO_FRAMES = 1024; // samples in each chunk given to Web Audio (21 ms)
  const AUDIO_LATENCY = 0.08; // target seconds of sound queued ahead
  const AUDIO_MIN_AHEAD = 0.005; // less than this queued: start again at the target
  const AUDIO_MAX_AHEAD = 0.25; // more than this queued: drop the chunk
  // The audio clock and the page's clock drift apart slightly. Chunks play up
  // to 0.5% faster or slower (too little to hear) to keep the queue on target.
  const AUDIO_RATE_GAIN = 0.1; // playback rate change per second of queue error
  const AUDIO_MAX_RATE_CHANGE = 0.005;
  // Output gain. binjgb's samples only reach 240 of 255 even with all four
  // channels at full volume, so after the DC filter below the mix stays
  // within about +-0.94 and this full gain can't clip.
  const VOLUME = 1;
  const DC_POLE = 0.995; // high-pass filter, like the Game Boy's output capacitor

  const SAVE_DELAY_MS = 250; // gather ext RAM writes that come close together
  const MAX_CSS_SCALE = 6; // CSS pixels per Game Boy pixel, at most

  const SCREEN_W = 160;
  const SCREEN_H = 144;

  // What emulator_run_until returns (binjgb src/emulator.h).
  const EVENT_NEW_FRAME = 0x1;
  const EVENT_AUDIO_BUFFER_FULL = 0x2;
  const EVENT_UNTIL_TICKS = 0x4;
  const EVENT_BREAKPOINT = 0x8;
  const EVENT_INVALID_OPCODE = 0x10;

  // The emulator draws the four DMG shades with these RGBA values and the
  // page turns them into the chosen palette. The low two bits are 3 - shade,
  // so the pure white binjgb shows while the LCD is off also reads as shade 0.
  const SHADE_CODES = [0xff000003, 0xff000002, 0xff000001, 0xff000000];

  // Screen palettes, lightest shade first. The panda's white fur is shade 0,
  // the same as the sky, so shade 0 has to stay very light in all of them.
  const PALETTES = [
    { id: 'classic', name: 'Classic', colors: ['#e0f8d0', '#88c070', '#346856', '#081820'] },
    { id: 'grey', name: 'Grey', colors: ['#f2f2ee', '#aeaea6', '#5c5c56', '#1a1a18'] },
    { id: 'sky', name: 'Sky', colors: ['#e9f7f8', '#71c5cf', '#2d6b7a', '#10262d'] },
    { id: 'cream', name: 'Ice cream', colors: ['#fff6d3', '#f9a875', '#eb6b6f', '#7c3f58'] },
  ];
  const DEFAULT_PALETTE = 'classic';

  // Game Boy buttons: the bit each one has in window.pandajump.joypad, and
  // the binjgb function that sets it.
  const BUTTONS = {
    a: { bit: 0x01, setter: '_set_joyp_A' },
    b: { bit: 0x02, setter: '_set_joyp_B' },
    select: { bit: 0x04, setter: '_set_joyp_select' },
    start: { bit: 0x08, setter: '_set_joyp_start' },
    right: { bit: 0x10, setter: '_set_joyp_right' },
    left: { bit: 0x20, setter: '_set_joyp_left' },
    up: { bit: 0x40, setter: '_set_joyp_up' },
    down: { bit: 0x80, setter: '_set_joyp_down' },
  };

  // Keyboard, by KeyboardEvent.code (key positions, so other layouts work).
  // Up is also A, because in this game up means jump. Shift is not Select:
  // Shift+Tab moves focus back through the page, and on the title screen
  // Select switches the music off.
  const KEYS = {
    KeyZ: ['a'],
    Space: ['a'],
    KeyW: ['a'],
    ArrowUp: ['a', 'up'],
    KeyX: ['b'],
    Enter: ['start'],
    NumpadEnter: ['start'],
    KeyC: ['select'],
    Backspace: ['select'],
    ArrowDown: ['down'],
    ArrowLeft: ['left'],
    ArrowRight: ['right'],
  };
  const KEY_MUTE = 'KeyM';

  // Gamepads with the standard mapping: [button index, Game Boy button].
  // The bottom face button is A (jump); the top one is A too, the side ones B.
  const PAD_BUTTONS = [
    [0, 'a'], [3, 'a'], [1, 'b'], [2, 'b'], [8, 'select'], [9, 'start'],
    [12, 'up'], [13, 'down'], [14, 'left'], [15, 'right'],
  ];
  const STICK_DEADZONE = 0.5;

  // D-pad directions for the eight 45-degree sectors, clockwise from right.
  const DPAD_SECTORS = [
    ['right'], ['right', 'down'], ['down'], ['down', 'left'],
    ['left'], ['left', 'up'], ['up'], ['up', 'right'],
  ];

  // ------------------------------------------------------------ helpers

  // A problem to show on the screen: a short headline and a hint.
  class PlayerError extends Error {
    constructor(text, detail) {
      super(text);
      this.detail = detail;
    }
  }

  // localStorage can be missing or throw (private modes, blocked storage).
  const store = {
    get(key) {
      try {
        return window.localStorage.getItem(key);
      } catch (err) {
        return null;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, value);
        return true;
      } catch (err) {
        return false;
      }
    },
    works() {
      try {
        window.localStorage.setItem('pandajump.test', '1');
        window.localStorage.removeItem('pandajump.test');
        return true;
      } catch (err) {
        return false;
      }
    },
  };

  function bytesToBase64(bytes) {
    let text = '';
    for (let i = 0; i < bytes.length; i += 0x1000) {
      text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x1000));
    }
    return btoa(text);
  }

  function base64ToBytes(base64) {
    const text = atob(base64);
    const bytes = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
    return bytes;
  }

  // '#rrggbb' as a little-endian RGBA word, the byte order of ImageData.
  function rgbaWord(hex) {
    const n = parseInt(hex.slice(1), 16);
    return ((0xff << 24) | ((n & 0xff) << 16) | (n & 0xff00) | (n >> 16)) >>> 0;
  }

  function findPalette(id) {
    return PALETTES.find((p) => p.id === id) || PALETTES.find((p) => p.id === DEFAULT_PALETTE);
  }

  // Whether a focused page control needs this key itself: Space and Enter
  // press buttons, Enter follows links (Space on a link would only scroll
  // the page), Space and the arrows work radio buttons. Every other key, and
  // every key while nothing on the page has focus, goes to the game.
  function keyIsForControl(event) {
    const el = event.target;
    if (!(el instanceof Element)) return false;
    if (el.closest('#console') && !el.closest('.overlay')) return false;
    if (el.isContentEditable) return true;
    const code = event.code;
    const enter = code === 'Enter' || code === 'NumpadEnter';
    const activates = enter || code === 'Space';
    switch (el.tagName) {
      case 'INPUT':
        if (el.type === 'radio') return code === 'Space' || code.startsWith('Arrow');
        if (el.type === 'checkbox' || el.type === 'button') return activates;
        return true;
      case 'TEXTAREA':
      case 'SELECT':
        return true;
      case 'BUTTON':
      case 'SUMMARY':
        return activates;
      case 'A':
        return enter;
      default:
        return false;
    }
  }

  // ------------------------------------------------------------ emulator

  // One running cartridge in binjgb.
  class GameBoy {
    constructor(module, rom) {
      this.module = module;
      // binjgb wants a whole number of 32 KiB banks.
      const size = Math.max(0x8000, (rom.length + 0x7fff) & ~0x7fff);
      this.romPtr = module._malloc(size);
      module.HEAPU8.fill(0, this.romPtr, this.romPtr + size);
      module.HEAPU8.set(rom, this.romPtr);
      // The last argument is the colour curve for Game Boy Color games; unused.
      this.e = module._emulator_new_simple(this.romPtr, size, AUDIO_RATE, AUDIO_FRAMES, 0);
      if (!this.e) {
        module._free(this.romPtr);
        throw new PlayerError('This ROM would not start.', `The emulator did not accept ${ROM_URL}.`);
      }
      // Buttons reach the game through binjgb's joypad callback, which also
      // logs each change in this buffer.
      this.joypad = module._joypad_new();
      module._emulator_set_default_joypad_callback(this.e, this.joypad);
      // Background, OBJ 0 and OBJ 1 all draw the plain shade codes.
      for (let type = 0; type < 3; type++) {
        module._emulator_set_bw_palette_simple(this.e, type, ...SHADE_CODES);
      }
      // One reusable buffer for copying the cartridge RAM in and out.
      this.extRam = module._ext_ram_file_data_new(this.e);
      this.framePtr = module._get_frame_buffer_ptr(this.e);
      this.audioPtr = module._get_audio_buffer_ptr(this.e);
    }

    // A view of the emulator's memory (rebuilt each time, so it stays valid
    // even if the WebAssembly memory is ever replaced).
    view(Type, ptr, length) {
      return new Type(this.module.HEAPU8.buffer, ptr, length);
    }

    get ticks() {
      return this.module._emulator_get_ticks_f64(this.e);
    }

    runUntil(ticks) {
      return this.module._emulator_run_until_f64(this.e, ticks);
    }

    frame() {
      return this.view(Uint32Array, this.framePtr, SCREEN_W * SCREEN_H);
    }

    // Unsigned 8-bit stereo samples, left and right interleaved.
    audio() {
      return this.view(Uint8Array, this.audioPtr, AUDIO_FRAMES * 2);
    }

    setButton(name, down) {
      this.module[BUTTONS[name].setter](this.e, down ? 1 : 0);
    }

    // True once after the game writes to its cartridge RAM.
    extRamChanged() {
      return this.module._emulator_was_ext_ram_updated(this.e) !== 0;
    }

    extRamBytes() {
      const m = this.module;
      return this.view(Uint8Array, m._get_file_data_ptr(this.extRam), m._get_file_data_size(this.extRam));
    }

    readExtRam() {
      this.module._emulator_write_ext_ram(this.e, this.extRam);
      return this.extRamBytes().slice();
    }

    // Returns false (and changes nothing) if the size doesn't match.
    writeExtRam(bytes) {
      const target = this.extRamBytes();
      if (bytes.length !== target.length) return false;
      target.set(bytes);
      return this.module._emulator_read_ext_ram(this.e, this.extRam) === 0;
    }
  }

  // ------------------------------------------------------------ screen

  // Draws the Game Boy's frames on the page's canvas so that every Game Boy
  // pixel covers exactly k x k device pixels. player.js sizes the screen to
  // 160k x 144k device pixels, and the browser reports the device pixels the
  // canvas really covers (ResizeObserver's device-pixel-content-box):
  //   - exactly 160k x 144k: the canvas stays 160 x 144 and the browser's
  //     own pixelated upscale, by exactly k, does the rest (cheapest);
  //   - a device pixel more or less (the browser rounded the layout): the
  //     canvas takes one pixel per device pixel, and the frame is drawn into
  //     it k times bigger, the spare edge filled with the nearest colours;
  //   - not reported (Safari), or not believable (Chrome's emulated pixel
  //     ratios in DevTools report CSS pixels): 160 x 144, scaled by the
  //     browser, which is as good as it can be there.
  class Screen {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d', { alpha: false });
      // The frame at the Game Boy's own 160 x 144, copied up from here.
      this.frame = document.createElement('canvas');
      this.frame.width = SCREEN_W;
      this.frame.height = SCREEN_H;
      this.frameCtx = this.frame.getContext('2d', { alpha: false });
      this.image = this.frameCtx.createImageData(SCREEN_W, SCREEN_H);
      this.pixels = new Uint32Array(this.image.data.buffer);
      // The last frame as shade-code low bits (3 is the lightest shade), kept
      // so a palette change can redraw it, even while paused.
      this.shades = new Uint8Array(SCREEN_W * SCREEN_H).fill(3);
      this.colors = new Uint32Array(4);
      this.watchSize();
    }

    watchSize() {
      if (typeof ResizeObserver !== 'function') return;
      const observer = new ResizeObserver((entries) => {
        const entry = entries[entries.length - 1];
        const device = entry.devicePixelContentBoxSize && entry.devicePixelContentBoxSize[0];
        const css = entry.contentBoxSize && entry.contentBoxSize[0];
        const dpr = window.devicePixelRatio || 1;
        const believable = Boolean(device && css) &&
          Math.abs(device.inlineSize - css.inlineSize * dpr) < 2 &&
          Math.abs(device.blockSize - css.blockSize * dpr) < 2;
        this.fit(believable ? device.inlineSize : 0, believable ? device.blockSize : 0);
      });
      try {
        observer.observe(this.canvas, { box: 'device-pixel-content-box' });
      } catch (err) {
        observer.observe(this.canvas); // no device pixels here
      }
    }

    // Sizes the canvas for a box of width x height device pixels (0: unknown).
    fit(width, height) {
      let w = SCREEN_W;
      let h = SCREEN_H;
      const k = width / SCREEN_W;
      if (width > 0 && height > 0 && !(Number.isInteger(k) && height === SCREEN_H * k)) {
        w = width;
        h = height;
      }
      const canvas = this.canvas;
      if (canvas.width === w && canvas.height === h) return;
      canvas.width = w;
      canvas.height = h;
      this.draw();
    }

    setPalette(colors) {
      colors.forEach((hex, shade) => {
        this.colors[3 - shade] = rgbaWord(hex);
      });
      this.paint();
    }

    capture(frame) {
      const shades = this.shades;
      for (let i = 0; i < shades.length; i++) shades[i] = frame[i] & 3;
    }

    paint() {
      const { pixels, shades, colors } = this;
      for (let i = 0; i < pixels.length; i++) pixels[i] = colors[shades[i]];
      this.frameCtx.putImageData(this.image, 0, 0);
      this.draw();
    }

    // Copies the frame onto the canvas at the largest whole scale that fits,
    // centred. On a canvas a device pixel too big, the frame stretched to the
    // whole canvas first fills the spare edge with the picture's edge colours;
    // on one a device pixel too small, the outermost device pixel is cut.
    draw() {
      const { canvas, ctx, frame } = this;
      const width = canvas.width;
      const height = canvas.height;
      const k = Math.max(1, Math.min(Math.floor((width + 1) / SCREEN_W), Math.floor((height + 1) / SCREEN_H)));
      const w = SCREEN_W * k;
      const h = SCREEN_H * k;
      ctx.imageSmoothingEnabled = false;
      if (w !== width || h !== height) ctx.drawImage(frame, 0, 0, width, height);
      ctx.drawImage(frame, Math.floor((width - w) / 2), Math.floor((height - h) / 2), w, h);
    }
  }

  // ------------------------------------------------------------ sound

  // Each full audio buffer from the emulator becomes a short AudioBuffer,
  // queued to start right after the previous one. Browsers only allow sound
  // after a click, tap or key press, so the AudioContext is made (or resumed)
  // by unlock(), which the page calls from those events.
  class Sound {
    constructor() {
      this.ctx = null;
      this.gain = null;
      this.enabled = true;
      this.nextTime = 0; // audio clock time where the next chunk starts
      this.lead = AUDIO_LATENCY; // smoothed seconds of sound queued
      this.filter = [0, 0, 0, 0]; // high-pass state: last in and out, left and right
    }

    unlock() {
      if (!this.enabled) return;
      if (!this.ctx) {
        const Context = window.AudioContext || window.webkitAudioContext;
        if (!Context) return;
        try {
          this.ctx = new Context({ latencyHint: 'interactive' });
        } catch (err) {
          try {
            this.ctx = new Context();
          } catch (err2) {
            return;
          }
        }
        this.gain = this.ctx.createGain();
        this.gain.gain.value = VOLUME;
        this.gain.connect(this.ctx.destination);
      }
      if (this.ctx.state !== 'running') this.ctx.resume().catch(() => {});
    }

    get playing() {
      return this.enabled && this.ctx !== null && this.ctx.state === 'running';
    }

    push(samples) {
      if (!this.playing) {
        this.nextTime = 0;
        return;
      }
      const ctx = this.ctx;
      const now = ctx.currentTime;
      if (this.nextTime < now + AUDIO_MIN_AHEAD) {
        // Starting, or the queue ran dry: leave some room again.
        this.nextTime = now + AUDIO_LATENCY;
        this.lead = AUDIO_LATENCY;
      } else if (this.nextTime > now + AUDIO_MAX_AHEAD) {
        // Far ahead of the sound card (after a hiccup); let it catch up.
        return;
      }
      // Smoothed queue length, and the playback rate that steers it back
      // to the target.
      this.lead += 0.1 * (this.nextTime - now - this.lead);
      const change = AUDIO_RATE_GAIN * (this.lead - AUDIO_LATENCY);
      const rate = 1 + Math.max(-AUDIO_MAX_RATE_CHANGE, Math.min(AUDIO_MAX_RATE_CHANGE, change));
      const buffer = ctx.createBuffer(2, AUDIO_FRAMES, AUDIO_RATE);
      const left = buffer.getChannelData(0);
      const right = buffer.getChannelData(1);
      let [inL, outL, inR, outR] = this.filter;
      for (let i = 0; i < AUDIO_FRAMES; i++) {
        const l = samples[2 * i] / 255;
        const r = samples[2 * i + 1] / 255;
        outL = l - inL + DC_POLE * outL;
        outR = r - inR + DC_POLE * outR;
        inL = l;
        inR = r;
        left[i] = outL;
        right[i] = outR;
      }
      this.filter = [inL, outL, inR, outR];
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.playbackRate.value = rate;
      source.connect(this.gain);
      source.start(this.nextTime);
      this.nextTime += AUDIO_FRAMES / AUDIO_RATE / rate;
    }

    pause() {
      this.nextTime = 0;
      if (this.ctx && this.ctx.state === 'running') this.ctx.suspend().catch(() => {});
    }

    resume() {
      if (this.ctx && this.enabled && this.ctx.state !== 'running') this.ctx.resume().catch(() => {});
    }

    setEnabled(on) {
      this.enabled = on;
      this.nextTime = 0;
      if (this.gain) this.gain.gain.value = on ? VOLUME : 0;
    }
  }

  // ------------------------------------------------------------ buttons

  // The state of the eight Game Boy buttons. A button is down while any
  // source holds it: a key, a finger or mouse pointer, a gamepad, so two
  // keys for A, or a key and a finger, never cancel each other out.
  class Buttons {
    constructor(onChange) {
      this.onChange = onChange;
      this.held = {};
      for (const name of Object.keys(BUTTONS)) this.held[name] = new Set();
    }

    press(name, source) {
      const held = this.held[name];
      if (held.has(source)) return;
      held.add(source);
      if (held.size === 1) this.onChange(name, true);
    }

    release(name, source) {
      const held = this.held[name];
      if (held.delete(source) && held.size === 0) this.onChange(name, false);
    }

    releaseAll() {
      for (const name of Object.keys(this.held)) {
        if (this.held[name].size) {
          this.held[name].clear();
          this.onChange(name, false);
        }
      }
    }

    isDown(name) {
      return this.held[name].size > 0;
    }

    get bits() {
      let bits = 0;
      for (const name of Object.keys(BUTTONS)) if (this.isDown(name)) bits |= BUTTONS[name].bit;
      return bits;
    }
  }

  // ------------------------------------------------------------ player

  class Player {
    constructor() {
      this.device = document.getElementById('console'); // the handheld
      this.screenEl = document.getElementById('screen');
      this.overlay = document.getElementById('overlay');
      this.soundButton = document.getElementById('sound');
      this.saveNote = document.getElementById('save-note');

      this.screen = new Screen(document.getElementById('lcd'));
      this.sound = new Sound();
      this.buttons = new Buttons((name, down) => this.buttonChanged(name, down));

      this.gb = null;
      // 'loading' -> 'running' <-> 'paused'; or 'stopped' after an error.
      this.state = 'loading';
      this.waitingForInput = false; // paused until the player presses something
      this.played = false; // the player has pressed a game button
      this.frames = 0;
      this.targetTicks = 0;
      this.lastTime = 0;

      this.pressedAt = {}; // button -> emulator ticks when it went down
      this.releaseAt = {}; // button -> ticks when a held-back release applies
      this.pointers = new Map(); // pointerId -> { el, names }
      this.lastPointerTime = -Infinity; // last press or release on the device
      this.gamepadsSeen = false;
      this.padDown = new Set();
      this.taps = 0;

      this.saveTimer = 0;
      this.saveDirty = false;
      this.canSave = true; // localStorage works
      this.lastSaved = null;
      this.saveBlocked = false; // another tab has saved since we loaded

      this.loop = this.loop.bind(this);
    }

    // -------------------------------------------------------- start up

    async start() {
      this.setupPalettes();
      this.setupSound();
      this.setupInput();
      this.setupLayout();
      this.setupPageEvents();
      this.canSave = store.works();
      if (!this.canSave) {
        this.note('This browser is blocking storage, so your best score will be lost when you leave.');
      }

      try {
        if (location.protocol === 'file:') {
          throw new PlayerError(
            'Open this page from a web server.',
            'Browsers do not let a page opened from a file load the game. In this folder run: python3 -m http.server, then open http://localhost:8000/.',
          );
        }
        const [module, rom] = await Promise.all([loadEmulator(), loadRom()]);
        this.gb = new GameBoy(module, rom);
      } catch (err) {
        this.fail(err);
        return;
      }

      this.loadSave();
      // Buttons held while loading go straight to the game.
      for (const name of Object.keys(BUTTONS)) this.gb.setButton(name, this.buttons.isDown(name));
      this.hideMessage();
      this.state = 'paused';
      if (!document.hidden) this.resume();
      requestAnimationFrame(this.loop);
    }

    fail(err) {
      this.state = 'stopped';
      this.device.classList.remove('is-on');
      if (err instanceof PlayerError) {
        this.showMessage(err.message, err.detail, null, true);
        console.error(`PandaJump: ${err.message} ${err.detail}`);
      } else {
        this.showMessage('Something went wrong starting the game.', String(err && err.message ? err.message : err), null, true);
        console.error('PandaJump:', err);
      }
    }

    // -------------------------------------------------------- main loop

    loop(now) {
      requestAnimationFrame(this.loop);
      this.pollGamepads();
      if (this.state !== 'running') return;

      // Run the emulator for exactly the real time since the last display
      // frame, whatever the display's refresh rate.
      const seconds = this.lastTime ? Math.min(Math.max((now - this.lastTime) / 1000, 0), MAX_STEP_SECONDS) : 0;
      this.lastTime = now;
      this.targetTicks += seconds * CPU_TICKS_PER_SECOND;

      const gb = this.gb;
      let newFrame = false;
      for (;;) {
        // Stop early where a held-back button release is due.
        const until = Math.min(this.targetTicks, this.nextReleaseTicks());
        const events = gb.runUntil(until);
        if (events & EVENT_NEW_FRAME) {
          this.screen.capture(gb.frame());
          this.frames++;
          newFrame = true;
        }
        if (events & EVENT_AUDIO_BUFFER_FULL) this.sound.push(gb.audio());
        if (events & (EVENT_INVALID_OPCODE | EVENT_BREAKPOINT)) {
          this.crash();
          return;
        }
        if (events & EVENT_UNTIL_TICKS) {
          this.applyDueReleases();
          if (until >= this.targetTicks) break;
        }
      }
      if (newFrame) this.screen.paint();
      if (gb.extRamChanged()) this.scheduleSave();
    }

    crash() {
      this.stop();
      this.flushSave();
      this.showMessage(
        'The game has stopped.',
        'The Game Boy ran into an instruction it does not know. Reload to start again.',
        { label: 'Reload', action: () => location.reload() },
        true,
      );
      console.error('PandaJump: the emulated CPU stopped (invalid opcode) at tick', this.gb.ticks);
    }

    pause() {
      if (this.state !== 'running') return;
      this.state = 'paused';
      this.device.classList.remove('is-on');
      this.sound.pause();
      this.buttons.releaseAll();
      this.flushSave();
    }

    resume() {
      if (this.state !== 'paused') return;
      this.state = 'running';
      this.waitingForInput = false;
      this.hideMessage();
      this.device.classList.add('is-on');
      this.targetTicks = this.gb.ticks;
      this.lastTime = 0;
      this.sound.resume();
    }

    stop() {
      if (this.state === 'running') this.pause();
      this.state = 'stopped';
    }

    // -------------------------------------------------------- messages

    // Shows text over the game screen, with an optional button. Errors are
    // alerts, so screen readers announce them straight away.
    showMessage(text, detail, button, isAlert) {
      const overlay = this.overlay;
      overlay.textContent = '';
      const body = document.createElement('div');
      body.className = 'overlay-body';
      if (isAlert) body.setAttribute('role', 'alert');
      const title = document.createElement('p');
      title.className = 'overlay-text';
      title.textContent = text;
      body.append(title);
      if (detail) {
        const more = document.createElement('p');
        more.className = 'detail';
        more.textContent = detail;
        body.append(more);
      }
      overlay.append(body);
      if (button) {
        const el = document.createElement('button');
        el.type = 'button';
        el.textContent = button.label;
        el.addEventListener('click', button.action);
        overlay.append(el);
      }
      overlay.hidden = false;
    }

    hideMessage() {
      this.overlay.hidden = true;
      this.overlay.textContent = '';
    }

    note(text) {
      this.saveNote.textContent = text;
      this.saveNote.hidden = false;
    }

    // -------------------------------------------------------- saves

    loadSave() {
      const text = store.get(KEY_SAVE);
      if (!text) return;
      let bytes;
      try {
        bytes = base64ToBytes(text);
      } catch (err) {
        console.warn('PandaJump: ignoring an unreadable save');
        return;
      }
      if (this.gb.writeExtRam(bytes)) {
        this.lastSaved = text;
      } else {
        console.warn('PandaJump: ignoring a save of the wrong size');
      }
    }

    scheduleSave() {
      this.saveDirty = true;
      if (!this.saveTimer) this.saveTimer = setTimeout(() => this.flushSave(), SAVE_DELAY_MS);
    }

    flushSave() {
      clearTimeout(this.saveTimer);
      this.saveTimer = 0;
      if (!this.saveDirty || !this.gb || !this.canSave || this.saveBlocked) return;
      this.saveDirty = false;
      const text = bytesToBase64(this.gb.readExtRam());
      if (text === this.lastSaved) return;
      if (store.set(KEY_SAVE, text)) {
        this.lastSaved = text;
      } else {
        this.note('Your best score could not be saved: this browser’s storage is full or blocked.');
      }
    }

    // Another tab saved. If its save differs from the cartridge RAM here,
    // carrying on could overwrite a better score with this tab's older one,
    // so stop and offer a reload. The same save (two tabs opened together,
    // each writing the blank save block at boot) is no conflict.
    onStorage(event) {
      if (event.key !== KEY_SAVE || event.newValue === null || event.newValue === this.lastSaved) return;
      if (this.state === 'loading' || this.state === 'stopped') return;
      if (event.newValue === bytesToBase64(this.gb.readExtRam())) {
        this.lastSaved = event.newValue;
        return;
      }
      this.saveBlocked = true;
      this.stop();
      this.showMessage(
        'PandaJump was played in another tab.',
        'Reload to carry on here with the latest save.',
        { label: 'Reload', action: () => location.reload() },
      );
    }

    // -------------------------------------------------------- input

    buttonChanged(name, down) {
      for (const el of this.device.querySelectorAll(`[data-gb="${name}"]`)) {
        el.classList.toggle('is-pressed', down);
      }
      const gb = this.gb;
      if (!gb) return; // still loading; start() hands over what is held
      if (down) {
        this.played = true;
        this.pressedAt[name] = gb.ticks;
        delete this.releaseAt[name];
        gb.setButton(name, true);
      } else {
        const earliest = (this.pressedAt[name] || 0) + MIN_HOLD_TICKS;
        if (gb.ticks < earliest) {
          this.releaseAt[name] = earliest; // applied by the main loop
        } else {
          gb.setButton(name, false);
        }
      }
    }

    nextReleaseTicks() {
      let next = Infinity;
      for (const name of Object.keys(this.releaseAt)) next = Math.min(next, this.releaseAt[name]);
      return next;
    }

    applyDueReleases() {
      const now = this.gb.ticks;
      for (const name of Object.keys(this.releaseAt)) {
        if (this.releaseAt[name] <= now) {
          delete this.releaseAt[name];
          this.gb.setButton(name, false);
        }
      }
    }

    // Any game button carries on after the tab was hidden. That press is
    // used up, so it doesn't also jump.
    resumeByInput() {
      if (this.state === 'paused' && this.waitingForInput) {
        this.resume();
        return true;
      }
      return false;
    }

    setupInput() {
      window.addEventListener('keydown', (e) => this.onKeyDown(e));
      window.addEventListener('keyup', (e) => this.onKeyUp(e));
      // Keys let go while the window is in the background never send keyup.
      window.addEventListener('blur', () => this.buttons.releaseAll());

      const device = this.device;
      device.addEventListener('pointerdown', (e) => this.onPointerDown(e));
      device.addEventListener('pointermove', (e) => this.onPointerMove(e));
      for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        device.addEventListener(type, (e) => this.onPointerEnd(e));
      }
      device.addEventListener('click', (e) => this.onClick(e));
      device.addEventListener('contextmenu', (e) => {
        if (!e.target.closest('.overlay a')) e.preventDefault();
      });

      window.addEventListener('gamepadconnected', () => {
        this.gamepadsSeen = true;
      });

      // Sound may only start from a user gesture; try on each one until it plays.
      const unlock = () => this.sound.unlock();
      for (const type of ['pointerdown', 'pointerup', 'touchend', 'keydown', 'click']) {
        window.addEventListener(type, unlock, true);
      }
    }

    onKeyDown(event) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.code === KEY_MUTE && !keyIsForControl(event)) {
        if (!event.repeat) this.setSoundEnabled(!this.sound.enabled, true);
        return;
      }
      const names = KEYS[event.code];
      if (!names || keyIsForControl(event)) return;
      event.preventDefault(); // no scrolling on Space or the arrows
      if (event.repeat || this.resumeByInput()) return;
      for (const name of names) this.buttons.press(name, 'key:' + event.code);
    }

    onKeyUp(event) {
      const names = KEYS[event.code];
      if (!names) return;
      for (const name of names) this.buttons.release(name, 'key:' + event.code);
    }

    onPointerDown(event) {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      if (event.target.closest('.overlay button, .overlay a')) return;
      const el = event.target.closest('.dpad') || event.target.closest('[data-gb], .screen');
      if (!el) return;
      event.preventDefault(); // no text selection, and the button doesn't take focus
      // Playing hands the keys back to the game: a page control that still
      // has focus (reached with Tab) would otherwise keep Space and Enter.
      const focused = document.activeElement;
      if (focused && focused !== document.body && !this.device.contains(focused)) focused.blur();
      this.lastPointerTime = performance.now();
      if (this.resumeByInput()) return;
      if (this.state === 'stopped') return;
      try {
        el.setPointerCapture(event.pointerId);
      } catch (err) {
        // Not capturable (already released); the pointerup still arrives.
      }
      this.pointers.set(event.pointerId, { el, names: [] });
      this.trackPointer(event);
    }

    onPointerMove(event) {
      const pointer = this.pointers.get(event.pointerId);
      if (pointer && pointer.el.classList.contains('dpad')) this.trackPointer(event);
    }

    onPointerEnd(event) {
      const pointer = this.pointers.get(event.pointerId);
      if (!pointer) return;
      this.lastPointerTime = performance.now();
      this.setPointerButtons(event.pointerId, pointer, []);
      this.pointers.delete(event.pointerId);
    }

    // Which buttons a pointer holds: the button it went down on; for the
    // D-pad, the direction it points from the centre (it can slide round);
    // for the screen, A (tap to jump).
    trackPointer(event) {
      const pointer = this.pointers.get(event.pointerId);
      const el = pointer.el;
      let names;
      if (el.classList.contains('dpad')) {
        const r = el.getBoundingClientRect();
        const dx = (event.clientX - r.left) / r.width - 0.5;
        const dy = (event.clientY - r.top) / r.height - 0.5;
        if (Math.hypot(dx, dy) < 0.12) {
          names = [];
        } else {
          const sector = Math.round(Math.atan2(dy, dx) / (Math.PI / 4));
          names = DPAD_SECTORS[(sector + 8) % 8];
        }
      } else if (el.classList.contains('screen')) {
        names = ['a'];
      } else {
        names = [el.dataset.gb];
      }
      this.setPointerButtons(event.pointerId, pointer, names);
    }

    setPointerButtons(id, pointer, names) {
      const source = 'pointer:' + id;
      for (const name of pointer.names) if (!names.includes(name)) this.buttons.release(name, source);
      for (const name of names) if (!pointer.names.includes(name)) this.buttons.press(name, source);
      pointer.names = names;
    }

    // A click that no pointer made (a screen reader, or Enter on a focused
    // button): press the button briefly. Clicks that end a real press were
    // already handled by the pointer events; they name their pointer type,
    // or (where browsers don't say) come right after a pointer release.
    onClick(event) {
      const el = event.target.closest('[data-gb]');
      if (!el || event.pointerType) return;
      if (event.detail > 0 && performance.now() - this.lastPointerTime < 500) return;
      if (this.resumeByInput()) return;
      const name = el.dataset.gb;
      const source = 'tap:' + ++this.taps;
      this.buttons.press(name, source);
      setTimeout(() => this.buttons.release(name, source), 150);
    }

    pollGamepads() {
      if (!this.gamepadsSeen) return;
      let pads;
      try {
        pads = navigator.getGamepads();
      } catch (err) {
        return;
      }
      const down = new Set();
      for (const pad of pads) {
        if (!pad || !pad.connected) continue;
        for (const [index, name] of PAD_BUTTONS) {
          const button = pad.buttons[index];
          if (button && (button.pressed || button.value > 0.5)) down.add(name);
        }
        const x = pad.axes[0] || 0;
        const y = pad.axes[1] || 0;
        if (x < -STICK_DEADZONE) down.add('left');
        if (x > STICK_DEADZONE) down.add('right');
        if (y < -STICK_DEADZONE) down.add('up');
        if (y > STICK_DEADZONE) down.add('down');
      }
      let fresh = false;
      for (const name of down) if (!this.padDown.has(name)) fresh = true;
      if (fresh) {
        this.sound.unlock();
        if (this.resumeByInput()) {
          this.padDown = down;
          return;
        }
      }
      for (const name of this.padDown) if (!down.has(name)) this.buttons.release(name, 'pad');
      for (const name of down) if (!this.padDown.has(name)) this.buttons.press(name, 'pad');
      this.padDown = down;
    }

    // -------------------------------------------------------- page

    setupPageEvents() {
      document.addEventListener('visibilitychange', () => this.onVisibilityChange());
      window.addEventListener('pageshow', () => this.onVisibilityChange());
      window.addEventListener('pagehide', () => this.flushSave());
      window.addEventListener('storage', (e) => this.onStorage(e));

      // After a mouse or touch click on a page control, give the keys back to
      // the game (Space would otherwise press that control again). Keyboard
      // users keep their focus: their clicks have detail 0.
      document.querySelector('.settings').addEventListener('click', (e) => {
        const control = e.target.closest('button, a, input');
        if (control && e.detail > 0) control.blur();
      });
    }

    // Pause while the tab is hidden. Coming back mid-game waits for a button
    // press, so the panda doesn't run into a box before you're ready.
    onVisibilityChange() {
      if (document.hidden) {
        if (this.state === 'running') {
          this.pause();
          this.waitingForInput = this.played;
        }
        this.flushSave();
      } else if (this.state === 'paused') {
        if (this.waitingForInput) {
          this.showMessage('Paused', 'Press a button or tap the screen to carry on.');
        } else {
          this.resume();
        }
      }
    }

    setupPalettes() {
      const container = document.getElementById('palettes');
      const current = findPalette(store.get(KEY_PALETTE)).id;
      for (const palette of PALETTES) {
        const option = document.createElement('div');
        option.className = 'palette-option';
        const input = document.createElement('input');
        input.type = 'radio';
        input.name = 'palette';
        input.id = 'palette-' + palette.id;
        input.value = palette.id;
        input.checked = palette.id === current;
        const label = document.createElement('label');
        label.htmlFor = input.id;
        const swatch = document.createElement('span');
        swatch.className = 'swatch';
        swatch.setAttribute('aria-hidden', 'true');
        for (const color of palette.colors) {
          const chip = document.createElement('span');
          chip.style.background = color;
          swatch.append(chip);
        }
        label.append(swatch, palette.name);
        option.append(input, label);
        container.append(option);
      }
      container.addEventListener('change', (e) => {
        if (e.target.name === 'palette') this.setPalette(e.target.value, true);
      });
      this.setPalette(current, false);
    }

    setPalette(id, remember) {
      const palette = findPalette(id);
      this.screen.setPalette(palette.colors);
      const style = this.device.style;
      const darkest = rgbaWord(palette.colors[3]);
      style.setProperty('--lcd-0', palette.colors[0]);
      style.setProperty('--lcd-3', palette.colors[3]);
      style.setProperty('--lcd-3-rgb', `${darkest & 0xff} ${(darkest >> 8) & 0xff} ${(darkest >> 16) & 0xff}`);
      if (remember) store.set(KEY_PALETTE, palette.id);
    }

    setupSound() {
      this.setSoundEnabled(store.get(KEY_SOUND) !== 'off', false);
      this.soundButton.addEventListener('click', () => this.setSoundEnabled(!this.sound.enabled, true));
    }

    // byUser: the player switched it (a gesture, so sound may start now);
    // otherwise this is the remembered setting, applied at start-up.
    setSoundEnabled(on, byUser) {
      this.sound.setEnabled(on);
      this.soundButton.setAttribute('aria-pressed', String(on));
      if (byUser) {
        if (on) this.sound.unlock();
        store.set(KEY_SOUND, on ? 'on' : 'off');
      }
    }

    // Size the screen to a whole number of device pixels per Game Boy pixel,
    // as big as fits: the full width the layout allows (--fit-w in
    // style.css), and the window height if possible.
    setupLayout() {
      let queued = false;
      const refit = () => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => {
          queued = false;
          this.fitScreen();
        });
      };
      window.addEventListener('resize', refit);
      window.addEventListener('orientationchange', refit);
      // Moving the window to a screen with a different pixel density.
      const watchDensity = () => {
        if (!window.matchMedia) return;
        const query = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
        const changed = () => {
          query.removeEventListener('change', changed);
          watchDensity();
          refit();
        };
        if (query.addEventListener) query.addEventListener('change', changed);
      };
      watchDensity();
      this.fitScreen();
    }

    fitScreen() {
      const dpr = window.devicePixelRatio || 1;
      const style = getComputedStyle(this.device);
      const fitW = parseFloat(style.getPropertyValue('--fit-w')) || 0;
      // Height needed besides the screen: the page above the device, the
      // device's own frame and controls, and a small margin below.
      const deviceBox = this.device.getBoundingClientRect();
      const screenBox = this.screenEl.getBoundingClientRect();
      const fitH = deviceBox.top + window.scrollY + deviceBox.height - screenBox.height + 12;

      const byWidth = Math.floor(((document.documentElement.clientWidth - fitW) * dpr) / SCREEN_W + 1e-6);
      const byHeight = Math.floor(((window.innerHeight - fitH) * dpr) / SCREEN_H + 1e-6);
      // Never shrink below about 2 CSS pixels a pixel just to fit the height:
      // a little scrolling beats a tiny screen.
      let scale = Math.max(Math.min(byWidth, byHeight), Math.min(byWidth, Math.round(2 * dpr)));
      scale = Math.max(1, Math.min(scale, Math.floor(MAX_CSS_SCALE * dpr)));

      // A 256th of a device pixel more, so float rounding in the layout
      // never leaves the screen a device pixel short of 160k x 144k.
      this.device.style.setProperty('--screen-w', (SCREEN_W * scale + 1 / 256) / dpr + 'px');
      this.device.style.setProperty('--screen-h', (SCREEN_H * scale + 1 / 256) / dpr + 'px');
    }
  }

  async function loadEmulator() {
    if (typeof WebAssembly !== 'object') {
      throw new PlayerError('This browser can’t run the game.', 'It needs WebAssembly: try a current Firefox, Chrome, Edge or Safari.');
    }
    if (typeof window.Binjgb !== 'function') {
      throw new PlayerError('The emulator didn’t load.', 'vendor/binjgb.js is missing or could not be read. Reload to try again.');
    }
    try {
      // binjgb prints the cartridge header when it starts; keep that at
      // debug level. Its error output stays on console.error.
      return await window.Binjgb({ print: (text) => console.debug('binjgb:', text) });
    } catch (err) {
      throw new PlayerError('The emulator didn’t load.', 'vendor/binjgb.wasm is missing or could not be read. Reload to try again.');
    }
  }

  async function loadRom() {
    let response;
    try {
      // Revalidate, so a new build of the game is picked up straight away.
      response = await fetch(ROM_URL, { cache: 'no-cache' });
    } catch (err) {
      throw new PlayerError('The game didn’t download.', 'Check your connection and reload the page.');
    }
    if (!response.ok) {
      throw new PlayerError(
        'The game ROM is missing.',
        `${ROM_URL} could not be loaded (HTTP ${response.status}). If you built PandaJump yourself, run make web first.`,
      );
    }
    const rom = new Uint8Array(await response.arrayBuffer());
    if (rom.length < 0x150) {
      throw new PlayerError('The game ROM is damaged.', `${ROM_URL} is too small to be a Game Boy ROM.`);
    }
    return rom;
  }

  // ------------------------------------------------------------ go

  const player = new Player();

  // A small read-only window into the player, for tests and the curious.
  window.pandajump = {
    get state() {
      return player.state;
    },
    get frames() {
      return player.frames; // Game Boy frames shown
    },
    get ticks() {
      return player.gb ? player.gb.ticks : 0; // CPU clock ticks run
    },
    get joypad() {
      return player.buttons.bits; // buttons held, see BUTTONS for the bits
    },
  };

  player.start();
})();
