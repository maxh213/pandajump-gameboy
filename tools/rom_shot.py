#!/usr/bin/env python3
"""Run the ROM headless in PyBoy, press buttons on a schedule, save screenshots.

Examples:
  # a screenshot after 120 frames
  tools/rom_shot.py --frames 120 --out shot.png
  # press Start at frame 60, A at 120 and 150, then a contact sheet of every 10th frame
  tools/rom_shot.py --frames 300 --press 60:start --press 120:a --press 150:a \
      --sheet sheet.png --every 10
  # print variables (by C name) at the end
  tools/rom_shot.py --frames 300 --press 60:start --var score --var game_state

PyBoy shows its own boot logo for about 70 frames before the game starts.

Buttons: a b start select up down left right. A press lasts 2 frames unless
given as frame:button:length.
"""
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYSDL2_DLL_PATH", "")
from pyboy import PyBoy  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "build" / "pandajump.gb"))
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--press", action="append", default=[], help="frame:button[:length]")
    ap.add_argument("--out", help="final screenshot path")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--sheet", help="contact sheet path")
    ap.add_argument("--every", type=int, default=10, help="contact sheet frame interval")
    ap.add_argument("--start", type=int, default=0, help="first frame of the contact sheet")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--var", action="append", default=[], help="print a variable (C name) at the end")
    ap.add_argument("--ram", help="battery RAM file to load (copied, never modified)")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    rom = tmp / "rom.gb"
    shutil.copy(args.rom, rom)
    sym = Path(args.rom).with_suffix(".sym")
    if sym.exists():
        shutil.copy(sym, tmp / "rom.sym")
    if args.ram:
        shutil.copy(args.ram, tmp / "rom.gb.ram")

    presses = {}
    for p in args.press:
        parts = p.split(":")
        frame, button = int(parts[0]), parts[1]
        length = int(parts[2]) if len(parts) > 2 else 2
        presses.setdefault(frame, []).append((button, length))

    pb = PyBoy(str(rom), window="null", sound_emulated=False)
    releases = {}
    shots = []
    for frame in range(args.frames):
        for button, length in presses.get(frame, []):
            pb.button_press(button)
            releases.setdefault(frame + length, []).append(button)
        for button in releases.pop(frame, []):
            pb.button_release(button)
        pb.tick(1, True)
        if args.sheet and frame >= args.start and (frame - args.start) % args.every == 0:
            shots.append((frame, pb.screen.image.copy().convert("RGB")))

    if args.out:
        img = pb.screen.image.copy().convert("RGB")
        img.resize((160 * args.scale, 144 * args.scale), Image.NEAREST).save(args.out)
        print(f"wrote {args.out}")
    if args.sheet and shots:
        cols = min(args.cols, len(shots))
        rows = (len(shots) + cols - 1) // cols
        s = max(1, args.scale - 1)
        sheet = Image.new("RGB", (cols * (160 * s + 4), rows * (144 * s + 4)), (255, 0, 255))
        for i, (_, img) in enumerate(shots):
            x, y = (i % cols) * (160 * s + 4), (i // cols) * (144 * s + 4)
            sheet.paste(img.resize((160 * s, 144 * s), Image.NEAREST), (x, y))
        sheet.save(args.sheet)
        print(f"wrote {args.sheet} ({len(shots)} frames: {[f for f, _ in shots]})")
    for name in args.var:
        try:
            bank, addr = pb.symbol_lookup("_" + name)
        except ValueError:
            print(f"{name}: no such symbol", file=sys.stderr)
            continue
        lo, hi = pb.memory[addr], pb.memory[addr + 1]
        print(f"{name} @ {addr:#06x}: u8={lo} u16={lo | hi << 8}")
    pb.stop(save=False)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
