"""Helpers for driving build/pandajump.gb headless in PyBoy.

Frame timing (measured, and matching docs/DESIGN.md):

- One ``tick()`` is one Game Boy frame. PyBoy's frame boundary is at the
  start of line 0, so within tick *k* the game runs its logic for frame *k*
  (meant to start on line 1; it often starts on line 0, see
  test_frames.py), then in VBlank (line 144) it reads the joypad, bumps
  ``frame_count`` and writes the tiles that logic queued. When there are
  many tiles the writes run on into the first lines of tick *k+1*.
- After tick *k*: RAM holds the result of frame *k*'s logic, VRAM holds the
  tiles it queued, and the *screen* shows frame *k-1* (it was drawn before
  frame *k*'s logic ran). Compare RAM after tick *k* with the screen after
  tick *k+1*.
- A button held during tick *k* is read in tick *k*'s VBlank and acted on
  by the logic of tick *k+1*: "a press shows in RAM 2 frames after it
  starts". Presses are edge-triggered, so two presses need a released read
  between them (one tick is enough).
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

os.environ.setdefault("PYSDL2_DLL_PATH", "")
import warnings  # noqa: E402

warnings.filterwarnings("ignore", message="Using SDL2 binaries")

import numpy as np  # noqa: E402
from pyboy import PyBoy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
ROM = BUILD / "pandajump.gb"
SYM = BUILD / "pandajump.sym"
CONFIG_H = ROOT / "src" / "config.h"
TILES_H = ROOT / "src" / "tiles.h"

# Screen colours for shades 0..3 (the palette in docs/DESIGN.md). The screen
# is converted back to shade numbers, so the exact values only need to be
# distinct.
SHADE_RGB = (0xE0F8D0, 0x88C070, 0x346856, 0x081820)

BOOT_FRAME_CAP = 400      # PyBoy's boot logo takes ~70 frames

BG_MAP = 0x9800
WIN_MAP = 0x9C00

# Screen bands (docs/DESIGN.md "Screen layout"), as row slices of shades().
HUD = slice(0, 16)
SKY = slice(16, 48)
WORLD = slice(48, 136)
WINDOW = slice(136, 144)


def parse_defines(path: Path) -> dict[str, int]:
    """The plain ``#define NAME <integer>`` lines of a C header."""
    out = {}
    for line in path.read_text().splitlines():
        m = re.match(r"\s*#define\s+([A-Za-z_]\w*)\s+(-?(?:0x[0-9A-Fa-f]+|\d+))\b", line)
        if m:
            out[m.group(1)] = int(m.group(2), 0)
    return out


class Config(dict):
    """config.h + tiles.h values, readable as attributes."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


def load_config() -> Config:
    cfg = Config(parse_defines(CONFIG_H))
    cfg.update(parse_defines(TILES_H))
    return cfg


class GB:
    """One emulator instance on a private copy of the ROM.

    ``workdir`` gets ``pandajump.gb``, ``pandajump.sym`` and, when ``ram`` is
    given, ``pandajump.gb.ram`` (8 KiB of cartridge RAM). ``stop(save=True)``
    writes the RAM back there, so a second GB on the same workdir is a
    power cycle with the battery kept.
    """

    def __init__(self, workdir: Path, ram: bytes | None = None, sound: bool = False,
                 rom: Path = ROM, sym: Path = SYM):
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rom = self.dir / "pandajump.gb"
        self.sym = self.dir / "pandajump.sym"
        if not self.rom.exists():
            shutil.copy(rom, self.rom)
            shutil.copy(sym, self.sym)
        self.ram_path = self.dir / "pandajump.gb.ram"
        if ram is not None:
            assert len(ram) == 0x2000, "cartridge RAM image must be 8 KiB"
            self.ram_path.write_bytes(bytes(ram))
        self.pb = PyBoy(str(self.rom), window="null", sound_emulated=sound,
                        symbols=str(self.sym), color_palette=SHADE_RGB,
                        log_level="ERROR")
        self.pb.set_emulation_speed(0)
        self.frames = 0          # ticks since power-on
        self._rendered = 0       # consecutive rendered ticks up to now
        self._held = set()
        self._addr = {}
        self._stopped = False
        self._rgb_to_shade = {}
        for i, c in enumerate(SHADE_RGB):
            self._rgb_to_shade[((c >> 16) & 255, (c >> 8) & 255, c & 255)] = i

    # ---- running -----------------------------------------------------------
    def tick(self, n: int = 1, render: bool = False) -> None:
        """Run n frames. With render, the screen is valid after the last one.

        PyBoy draws the window one line off on the first rendered frame
        after unrendered ones, so with render the last two frames are both
        rendered; a single rendered tick after an unrendered one leaves the
        screen marked invalid (shades() refuses it)."""
        if n <= 0:
            return
        if not render:
            self.pb.tick(n, False)
            self._rendered = 0
        else:
            if n >= 2:
                if n > 2:
                    self.pb.tick(n - 2, False)
                    self._rendered = 0
                self.pb.tick(1, True)
                self._rendered += 1
            self.pb.tick(1, True)
            self._rendered += 1
        self.frames += n

    def run_until(self, pred, max_frames: int, render: bool = False, what: str = "") -> int:
        """Tick one frame at a time until pred(self) is true; return the
        frames ticked. Fails the test if it takes more than max_frames."""
        for i in range(1, max_frames + 1):
            self.tick(1, render)
            if pred(self):
                return i
        raise AssertionError(f"condition {what or pred} not reached in {max_frames} frames")

    def hold(self, button: str) -> None:
        self.pb.button_press(button)
        self._held.add(button)

    def release(self, button: str) -> None:
        self.pb.button_release(button)
        self._held.discard(button)

    def press(self, button: str, frames: int = 1, after: int = 0, render: bool = False) -> None:
        """Hold a button for `frames` ticks, release it, then tick `after` more.
        The game acts on it in the logic of the tick after the first held one."""
        self.hold(button)
        self.tick(frames, render and after == 0)
        self.release(button)
        self.tick(after, render)

    def tap(self, button: str, render: bool = False) -> None:
        """Press for one tick and run one more, so the press has been acted on
        when this returns (RAM shows it)."""
        self.press(button, frames=1, after=1, render=render)

    def boot(self) -> int:
        """Run past PyBoy's boot logo until the game's main loop is running on
        the title screen. Returns the frames it took."""
        n = self.run_until(lambda g: g.u8("frame_count") != 0, BOOT_FRAME_CAP, what="game running")
        # A few frames of title logic, so the title's sprites and tiles are
        # up and the screen is past the partial frame after the LCD came on.
        self.tick(4)
        return n + 4

    def stop(self, save: bool = False) -> None:
        if not self._stopped:
            self.pb.stop(save=save)
            self._stopped = True

    # ---- memory --------------------------------------------------------------
    def addr(self, name: str) -> int:
        a = self._addr.get(name)
        if a is None:
            _bank, a = self.pb.symbol_lookup("_" + name)
            self._addr[name] = a
        return a

    def u8(self, name: str, offset: int = 0) -> int:
        return self.pb.memory[self.addr(name) + offset]

    def s8(self, name: str, offset: int = 0) -> int:
        v = self.u8(name, offset)
        return v - 256 if v >= 128 else v

    def u16(self, name: str) -> int:
        a = self.addr(name)
        return self.pb.memory[a] | (self.pb.memory[a + 1] << 8)

    def s16(self, name: str) -> int:
        v = self.u16(name)
        return v - 65536 if v >= 32768 else v

    def bytes(self, name: str, n: int) -> list[int]:
        a = self.addr(name)
        return list(self.pb.memory[a:a + n])

    def write8(self, name: str, value: int, offset: int = 0) -> None:
        self.pb.memory[self.addr(name) + offset] = value & 0xFF

    def write16(self, name: str, value: int) -> None:
        a = self.addr(name)
        self.pb.memory[a] = value & 0xFF
        self.pb.memory[a + 1] = (value >> 8) & 0xFF

    def io(self, reg: int) -> int:
        return self.pb.memory[reg]

    def sram(self, n: int = 6, offset: int = 0) -> list[int]:
        """Cartridge RAM bank 0 at 0xA000 (read directly, enabled or not)."""
        return [self.pb.memory[0, 0xA000 + offset + i] for i in range(n)]

    # ---- video -----------------------------------------------------------------
    def bg_tile(self, col: int, row: int) -> int:
        return self.pb.memory[BG_MAP + (row & 31) * 32 + (col & 31)]

    def bg_row(self, row: int) -> list[int]:
        a = BG_MAP + row * 32
        return list(self.pb.memory[a:a + 32])

    def win_row(self, row: int) -> list[int]:
        a = WIN_MAP + row * 32
        return list(self.pb.memory[a:a + 32])

    def oam(self) -> list[tuple[int, int, int, int]]:
        """40 sprites as (screen_y, screen_x, tile, attr), hardware offsets removed."""
        m = self.pb.memory
        out = []
        for i in range(40):
            a = 0xFE00 + 4 * i
            out.append((m[a] - 16, m[a + 1] - 8, m[a + 2], m[a + 3]))
        return out

    def shades(self) -> np.ndarray:
        """The last rendered screen as a 144x160 array of shades 0..3."""
        assert self._rendered >= 2, "render at least the last two frames before reading the screen"
        rgb =np.asarray(self.pb.screen.ndarray)[:, :, :3].astype(np.uint32)
        packed = (rgb[:, :, 0] << 16) | (rgb[:, :, 1] << 8) | rgb[:, :, 2]
        out = np.full(packed.shape, 255, dtype=np.uint8)
        for i, c in enumerate(SHADE_RGB):
            out[packed == c] = i
        assert (out != 255).all(), "screen has colours outside the 4-shade palette"
        return out

    def image(self):
        return self.pb.screen.image.copy()

    # ---- game-level shortcuts ---------------------------------------------------
    def state(self) -> int:
        return self.u8("game_state")

    def start_run(self, button: str = "start", invincible: bool = False) -> None:
        """From the title (or a finished run): press, and return on the first
        frame of the run (world_x is 0, nothing has scrolled yet)."""
        self.tap(button)
        assert self.state() == 1, f"{button} did not start a run (state {self.state()})"
        if invincible:
            self.write8("debug_invincible", 1)

    def col_height(self) -> list[int]:
        return self.bytes("col_height", 32)

    def panda(self):
        from model import Panda
        return Panda(self.s16("panda_y"), self.s16("panda_vy"),
                     bool(self.u8("panda_on_ground")), self.u8("jumps_used"))


def record_world(g: GB, frames: int, wmap=None, chunk: int = 16, on_sample=None):
    """Tick `frames` frames of a run, recording every generated column into
    a model.WorldMap (world_x unwrapped past 65535). Returns the map and the
    unwrapped world_x at the end."""
    from model import WorldMap
    wmap = wmap or WorldMap()
    raw = g.u16("world_x")
    if hasattr(wmap, "_x"):       # continue from the last call (frames may have passed)
        x = wmap._x + unwrap16(wmap._raw, raw)
    else:                         # a fresh map: the run has not wrapped yet
        x = raw
    left = frames
    while True:
        wmap.record(x, g.col_height())
        if on_sample:
            on_sample(g, x)
        if left <= 0:
            break
        n = min(chunk, left)
        g.tick(n)
        left -= n
        new = g.u16("world_x")
        x += unwrap16(raw, new)
        raw = new
    wmap._x = x
    wmap._raw = raw
    return wmap, x


def ram_image(block: bytes, fill: int = 0) -> bytes:
    """8 KiB of cartridge RAM starting with `block`."""
    return bytes(block) + bytes([fill]) * (0x2000 - len(block))


# ---- text as tiles (src/tiles.h fonts) -------------------------------------
def dark_text(cfg, text: str) -> list[int]:
    """Tiles of `text` in the dark font (space is T_SKY)."""
    special = {" ": cfg.T_SKY, "!": cfg.T_FONT_BANG, "-": cfg.T_FONT_DASH, ":": cfg.T_FONT_COLON,
               ".": cfg.T_FONT_DOT, "?": cfg.T_FONT_QUEST, "'": cfg.T_FONT_APOS, "/": cfg.T_FONT_SLASH}
    out = []
    for ch in text:
        if ch in special:
            out.append(special[ch])
        elif ch.isdigit():
            out.append(cfg.T_FONT_DIGIT + int(ch))
        else:
            out.append(cfg.T_FONT_ALPHA + ord(ch) - ord("A"))
    return out


def light_text(cfg, text: str) -> list[int]:
    """Tiles of `text` in the light font (space is T_HUD_DARK)."""
    out = []
    for ch in text:
        if ch == " ":
            out.append(cfg.T_HUD_DARK)
        elif ch.isdigit():
            out.append(cfg.T_LFONT_DIGIT + int(ch))
        else:
            out.append(cfg.T_LFONT_ALPHA + ord(ch) - ord("A"))
    return out


def score_row(cfg, value: int) -> list[int]:
    """Map row 1, columns 1-5: the score, left-aligned, dark font."""
    s = str(value)
    return dark_text(cfg, s) + [cfg.T_SKY] * (5 - len(s))


def hud_hi_row(cfg, value: int) -> list[int]:
    """Window row 0: " HI 0042" (at least 4 digits) in the light font, the
    rest T_HUD_DARK."""
    row = light_text(cfg, f" HI {value:04d}")
    return row + [cfg.T_HUD_DARK] * (20 - len(row))


def find_text(g: GB, row: int, tiles: list[int], scx: int):
    """Screen x where `tiles` sit in BG map row `row` (the text may wrap past
    column 31) when the band's scroll is `scx`, or None."""
    r = g.bg_row(row)
    n = len(tiles)
    for c in range(32):
        if [r[(c + i) & 31] for i in range(n)] == tiles:
            return (c * 8 - scx) % 256
    return None


# ---- art and generated assets ------------------------------------------------
_TILE_PX = None


def bg_tile_pixels() -> np.ndarray:
    """The 128 8x8 tiles of art/bg_tiles.png as colour indices, (128, 8, 8)."""
    global _TILE_PX
    if _TILE_PX is None:
        from PIL import Image
        art = np.array(Image.open(ROOT / "art" / "bg_tiles.png"))
        _TILE_PX = art.reshape(8, 8, 16, 8).transpose(0, 2, 1, 3).reshape(128, 8, 8)
    return _TILE_PX


def bg_picture(g: GB) -> np.ndarray:
    """The whole 256x256 BG map in VRAM drawn with art/bg_tiles.png."""
    m = np.array(g.pb.memory[BG_MAP:BG_MAP + 1024], dtype=np.intp).reshape(32, 32)
    assert (m < 128).all(), "BG map uses logo tiles"
    return bg_tile_pixels()[m].transpose(0, 2, 1, 3).reshape(256, 256)


def render_band(g: GB, lines, scx: int, scy: int, picture: np.ndarray | None = None) -> np.ndarray:
    """What the BG shows on screen `lines` with this scroll (BGP 0xE4, so
    colour index = shade)."""
    pic = bg_picture(g) if picture is None else picture
    ys = (np.asarray(list(lines)) + scy) & 255
    xs = (np.arange(160) + scx) & 255
    return pic[ys][:, xs].astype(np.uint8)


def generated_array(name: str, array: str) -> list[int]:
    """A byte array from png2asset's build/res/<name>.c."""
    text = (BUILD / "res" / f"{name}.c").read_text()
    m = re.search(rf"{array}\[\d+\] = \{{(.*?)\}};", text, re.S)
    return [int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", m.group(1))]


def metasprites(name: str) -> dict:
    """{frame: sorted ((y, x, tile), ...)} from build/res/<name>.c."""
    text = (BUILD / "res" / f"{name}.c").read_text()
    out = {}
    for idx, body in re.findall(rf"const metasprite_t {name}_metasprite(\d+)\[\] = \{{(.*?)\}};", text, re.S):
        y = x = 0
        items = []
        for dy, dx, tile in re.findall(r"METASPR_ITEM\((-?\d+),\s*(-?\d+),\s*(\d+)", body):
            y += int(dy)
            x += int(dx)
            items.append((y, x, int(tile)))
        out[int(idx)] = tuple(sorted(items))
    return out


def unwrap16(prev: int, new: int) -> int:
    """Forward distance from prev to new on a 16-bit counter."""
    return (new - prev) & 0xFFFF


def sram_block(value: int, magic=b"PJ", version: int = 1) -> bytes:
    """The 6-byte save block of docs/DESIGN.md."""
    b = bytearray(magic) + bytes([version, value & 0xFF, (value >> 8) & 0xFF])
    b.append((~sum(b)) & 0xFF)
    return bytes(b)
