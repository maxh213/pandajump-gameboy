"""An independent Python model of the game rules in docs/DESIGN.md, using
the integer constants from src/config.h, plus the world tracker and the
autoplayer built on it.

Order of one frame of play (docs/DESIGN.md / the state machine):
  1. a press of A jumps (on the ground), or double jumps (once, in the air,
     when -DJUMP_VEL is faster upwards than vy and the panda is at least
     BUFFER_HEIGHT px up), or else is kept for JUMP_BUFFER frames
  2. gravity; landing on GROUND_Y (a kept press jumps again at once); the
     kept press counts down; the top of the screen clamps
  3. the world scrolls by world_speed (8.8, with a carried fraction)
  4. the hitbox is checked against the columns under its left/right edges
  5. an obstacle whose right edge the hitbox's left edge has reached scores
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Panda:
    y: int                 # 8.8, top of the sprite
    vy: int = 0            # 8.8, + is down
    on_ground: bool = True
    jumps: int = 0
    buffer: int = 0        # frames a kept press has left (jump_buffer)

    def copy(self) -> "Panda":
        return Panda(self.y, self.vy, self.on_ground, self.jumps, self.buffer)


JUMPED, LANDED = 1, 3      # Physics.step() results (src/player.h)


class Physics:
    def __init__(self, cfg):
        self.g = cfg["GRAVITY"]
        self.jump = cfg["JUMP_VEL"]
        self.djump = cfg["DJUMP_VEL"]
        self.max_fall = cfg["MAX_FALL"]
        self.floor = (cfg["GROUND_Y"] - 16) << 8
        self.buffer = cfg["JUMP_BUFFER"]
        self.low = self.floor - (cfg["BUFFER_HEIGHT"] << 8)   # double jump only at y <= low

    def standing(self) -> Panda:
        return Panda(self.floor)

    def press(self, p: Panda) -> int:
        """A pressed: 1 jumped, 2 double jumped, 0 kept for later."""
        if p.on_ground:
            p.vy = -self.jump
            p.on_ground = False
            p.jumps = 1
            p.buffer = 0
            return 1
        if p.jumps == 1 and p.vy > -self.djump and p.y <= self.low:
            p.vy = -self.djump
            p.jumps = 2
            p.buffer = 0
            return 2
        p.buffer = self.buffer
        return 0

    def step(self, p: Panda, press: bool = False) -> int:
        """One frame. Returns 0, LANDED, or JUMPED when it lands and a
        kept press takes off again in the same frame."""
        if press:
            self.press(p)
        if p.on_ground:
            return 0
        p.vy = min(p.vy + self.g, self.max_fall)
        p.y += p.vy
        if p.y >= self.floor:
            p.y = self.floor
            p.vy = 0
            p.on_ground = True
            p.jumps = 0
            if p.buffer:
                self.press(p)
                return JUMPED
            return LANDED
        if p.buffer:
            p.buffer -= 1
        if p.y < 0:
            p.y = 0
            if p.vy < 0:
                p.vy = 0
        return 0

    def trajectory(self, presses: set[int], frames: int, start: Panda | None = None):
        """panda states after each of `frames` frames; presses are frame
        numbers (1-based) whose logic sees A pressed."""
        p = (start or self.standing()).copy()
        out = []
        for n in range(1, frames + 1):
            self.step(p, n in presses)
            out.append(p.copy())
        return out


def speed_for_score(cfg, score: int) -> int:
    steps = score // cfg["RAMP_EVERY"]
    return min(cfg["SPEED_MAX"], cfg["SPEED_BASE"] + cfg["SPEED_STEP"] * steps)


def spacing_for_score(cfg, score: int) -> int:
    steps = score // cfg["RAMP_EVERY"]
    return max(cfg["SPACING_MIN"], cfg["SPACING_BASE"] - steps)


def late_steps(cfg, score: int) -> int:
    """Late ramp steps so far: one every LATE_EVERY points after the ramp
    step that reached SPEED_MAX."""
    top = -(-(cfg["SPEED_MAX"] - cfg["SPEED_BASE"]) // cfg["SPEED_STEP"])
    extra = score // cfg["RAMP_EVERY"] - top
    return max(0, extra) // (cfg["LATE_EVERY"] // cfg["RAMP_EVERY"])


def double_chance_for_score(cfg, score: int) -> int:
    """P(double column) * 256 for an obstacle made at this score."""
    if score <= cfg["DOUBLE_SCORE"]:
        return 0
    return min(cfg["DOUBLE_MAX"], cfg["DOUBLE_CHANCE"] + cfg["DOUBLE_STEP"] * late_steps(cfg, score))


def tall_chance_for_score(cfg, score: int) -> int:
    """P(2 boxes high) * 256 for an obstacle made at this score (not the
    run's first obstacle, which is always 1 box)."""
    return min(cfg["TALL_MAX"], cfg["TALL_CHANCE"] + cfg["TALL_STEP"] * late_steps(cfg, score))


def spacing_rand_for_score(cfg, score: int) -> int:
    """The bit mask of the random extra spacing after an obstacle made at
    this score."""
    if late_steps(cfg, score) and score >= cfg["LATE_RAND_SCORE"]:
        return cfg["LATE_RAND"]
    return cfg["SPACING_RAND"]


def documented_min_spacing(speed: int) -> int:
    """config.h's table of the smallest clearable SPACING (start-to-start
    tiles for single columns; the empty gap after any obstacle is this - 2)
    at 1.0/1.125/1.25/1.375/1.5 px per frame. Speeds between table rows use
    the next row up."""
    table = [(256, 10), (288, 11), (320, 12), (352, 13), (384, 14)]
    for s, sp in table:
        if speed <= s:
            return sp
    raise AssertionError(f"speed {speed} is above the documented table")


class Scroll:
    """world_x / world_sub / world_speed as the game advances them."""

    def __init__(self, world_x=0, sub=0, speed=256):
        self.x = world_x          # unwrapped (not mod 65536)
        self.sub = sub
        self.speed = speed

    def step(self) -> int:
        t = self.sub + (self.speed & 0xFF)
        self.sub = t & 0xFF
        s = (self.speed >> 8) + (t >> 8)
        self.x += s
        return s


@dataclass
class Obstacle:
    start: int             # first world tile
    width: int             # tiles: 2 single, 4 double
    height: int            # px: 16 or 32

    @property
    def end(self) -> int:  # first tile after it
        return self.start + self.width

    @property
    def right_edge(self) -> int:
        return self.end * 8


@dataclass
class WorldMap:
    """World tiles recorded from col_height as they are generated.

    The game generates map column (world_x >> 3) + 21 (mod 32) whenever
    world_x >> 3 changes, so after every frame the tiles up to
    (world_x >> 3) + 21 are final. They stay in col_height until the map
    wraps 32 tiles later, so sampling at least every ~10 tiles of travel
    misses nothing."""
    tiles: dict = field(default_factory=dict)   # world tile -> height px
    newest: int = -1                            # highest tile recorded

    def record(self, world_x: int, col_height: list[int]) -> None:
        top = (world_x >> 3) + 21
        lo = max(self.newest + 1, top - 31)
        assert lo == self.newest + 1 or self.newest < 0, (
            f"sampled too rarely: tiles {self.newest + 1}..{lo - 1} were overwritten")
        for t in range(lo, top + 1):
            self.tiles[t] = col_height[t & 31]
        self.newest = max(self.newest, top)

    def height(self, tile: int) -> int:
        return self.tiles.get(tile, 0)

    def obstacles(self, complete_only: bool = True) -> list[Obstacle]:
        """Runs of non-empty tiles. A run is complete once an empty tile
        after it is known."""
        out = []
        t = min(self.tiles) if self.tiles else 0
        end = self.newest
        while t <= end:
            h = self.tiles.get(t, 0)
            if h == 0:
                t += 1
                continue
            s = t
            heights = []
            while t <= end and self.tiles.get(t, 0) != 0:
                heights.append(self.tiles[t])
                t += 1
            if t > end and complete_only:
                break
            hs = set(heights)
            out.append(Obstacle(s, len(heights), max(hs) if len(hs) == 1 else -1))
        return out


class AutoPlayer:
    """Plans jumps with the integer model; the test drives the joypad.

    Frames are counted relative to "now" (RAM holds frame t): frame 1 is
    t+1, whose press (if any) is already committed, frame 2 is the first a
    new press can reach. Two presses need at least one frame between them.

    When an obstacle is coming, every take-off frame and every double-jump
    frame (or none) is tried; plans that touch a box or don't land past the
    obstacle are dropped, and the one that lands soonest wins (on the
    ground the panda can always wait, so the earliest landing leaves the
    most room for whatever comes next).
    """

    HORIZON = 200
    LOOKAHEAD = 100        # plan once the first box is this many frames away

    def __init__(self, cfg):
        self.cfg = cfg
        self.phys = Physics(cfg)
        self.hx0 = cfg["PANDA_X"] + cfg["HIT_X0"]
        self.hx1 = cfg["PANDA_X"] + cfg["HIT_X1"]
        self.hy1 = cfg["HIT_Y1"]
        self.ground_y = cfg["GROUND_Y"]
        # Trajectories from the ground, frame 0 = the take-off frame, to the
        # landing frame inclusive: single jump (key None) and with a second
        # press k frames after take-off, as long as that press comes before
        # the landing (it may double jump, do nothing, or be kept and jump
        # again on landing). Sprite-top pixel rows.
        self.np = np
        self.traj = {}
        for k in [None] + list(range(2, 70)):
            presses = {1} if k is None else {1, 1 + k}
            ys = []
            p = self.phys.standing()
            landed = False
            for n in range(1, 400):
                if n == max(presses) and n > 1 and p.on_ground:
                    break                   # landed before the second press
                self.phys.step(p, n in presses)
                ys.append(p.y)
                if p.on_ground and n >= max(presses):
                    landed = True
                    break
            if not landed:
                break
            self.traj[k] = np.array(ys, dtype=np.int64) >> 8

    def plan_ground(self, first: int, xs, hs, target: int):
        """Best (landing index, take-off frame, double offset or None) for a
        panda on the ground from frame 1 on, or None: the earliest landing,
        then the latest take-off, then a single jump over a double."""
        best = None
        for k, fmap in self.ok_table(first, xs, hs, target).items():
            for f, li in fmap.items():
                key = (li, -f, 0 if k is None else 1)
                if best is None or key < best[0]:
                    best = (key, f, k)
        if best is None:
            return None
        return best[0][0], best[1], best[2]

    def ok_table(self, first: int, xs, hs, target: int):
        """{k: {take-off frame f: landing index}} for every plan from the
        ground that clears everything and lands past target."""
        np = self.np
        H = np.asarray(hs, dtype=np.int64)
        X = np.asarray(xs, dtype=np.int64)
        n = len(H)
        boxes = np.nonzero(H)[0]
        out = {}
        if len(boxes) == 0:
            return out
        last_f = int(boxes[0]) + 1
        for k, ys in self.traj.items():
            L = len(ys)
            fs = np.arange(first, last_f + 1)
            fs = fs[fs - 1 + L - 1 < n]
            if len(fs) == 0:
                out[k] = {}
                continue
            idx = (fs - 1)[:, None] + np.arange(L)[None, :]
            h = H[idx]
            hit = (h > 0) & ((ys[None, :] + self.hy1) >= (self.ground_y - h))
            land = fs - 1 + L - 1
            ok = ~hit.any(axis=1) & (X[land] + self.hx0 >= target)
            out[k] = {int(f): int(li) for f, li in zip(fs[ok], land[ok])}
        return out

    def plan_ground_tolerant(self, first: int, xs, hs, target: int, slack: int):
        """The plan (f, k) that still clears if the take-off and the double
        jump are each up to `slack` frames early or late, with the earliest
        worst-case landing. Returns (worst landing, f, k) or None."""
        np = self.np
        table = self.ok_table(first, xs, hs, target)
        if not table:
            return None
        ks = [k for k in self.traj if k is not None]
        fmax = len(hs) + 1
        nf = fmax - first + 1
        BIG = 1 << 30
        # land[row, f - first]: landing index, BIG when the plan fails.
        # Row 0 is the single jump, row r >= 1 is the double jump k = ks[r-1].
        land = np.full((len(ks) + 1, nf), BIG, dtype=np.int64)
        for r, k in enumerate([None] + ks):
            for f, li in table.get(k, {}).items():
                land[r, f - first] = li
        best = None
        pad = slack
        # single jump: every take-off within +-slack must work
        worst = np.zeros(nf, dtype=np.int64)
        for a in range(-slack, slack + 1):
            shifted = np.full(nf, BIG, dtype=np.int64)
            if a >= 0:
                shifted[:nf - a] = land[0, a:]
            else:
                shifted[-a:] = land[0, :nf + a]
            worst = np.maximum(worst, shifted)
        worst[:pad] = BIG                       # the early press must still be ahead
        cand = [(int(worst[i]), -(i + first), 0, i + first, None) for i in np.nonzero(worst < BIG)[0]]
        # double jump: take-off f+a, double at f+k+b, so k' = k+b-a
        dl = land[1:]                           # rows: ks
        nk = len(ks)
        worst2 = np.zeros((nk, nf), dtype=np.int64)
        for a in range(-slack, slack + 1):
            for b in range(-slack, slack + 1):
                dk = b - a
                shifted = np.full((nk, nf), BIG, dtype=np.int64)
                r0, r1 = max(0, -dk), min(nk, nk - dk)
                c0, c1 = max(0, -a), min(nf, nf - a)
                if r0 < r1 and c0 < c1:
                    shifted[r0:r1, c0:c1] = dl[r0 + dk:r1 + dk, c0 + a:c1 + a]
                worst2 = np.maximum(worst2, shifted)
        worst2[:, :pad] = BIG
        for r, i in zip(*np.nonzero(worst2 < BIG)):
            cand.append((int(worst2[r, i]), -(i + first), 1, i + first, ks[r]))
        if not cand:
            return None
        w, _, _, f, k = min(cand)
        return w, int(f), k

    def evaluate(self, start: Panda, presses, xs, hs, target: int):
        """Landing index once on the ground past `target` after the last
        press, or None if a box is touched first / never lands in time."""
        p = start.copy()
        pr = set(presses)
        last = max(pr, default=0)
        for i in range(len(hs)):
            self.phys.step(p, (i + 1) in pr)
            if self.hit(p.y, hs[i]):
                return None
            if p.on_ground and i + 1 > last and xs[i] + self.hx0 >= target:
                return i
        return None

    def plan(self, panda: Panda, pending: bool, xs, hs, target: int):
        """Presses (relative frames >= 2) for the best plan, or None."""
        after1 = panda.copy()
        self.phys.step(after1, pending)
        if self.hit(after1.y, hs[0]):
            return None
        first = 3 if pending else 2
        base = (1,) if pending else ()
        if after1.on_ground:
            r = self.plan_ground(first, xs, hs, target)
            if r is None:
                return None
            _, f, k = r
            return (f,) if k is None else (f, f + k)
        options = [()]
        # one more press: a double jump, or kept for a jump on landing
        options += [(g,) for g in range(first, 120)]
        best = None
        for opt in options:
            li = self.evaluate(panda, base + opt, xs, hs, target)
            if li is None:
                continue
            key = (li, 0 if not opt else 1, -(opt[0] if opt else 0))
            if best is None or key < best[0]:
                best = (key, opt)
        return None if best is None else best[1]

    # ---- the world over the next frames (independent of the panda) -------
    def future_world(self, scroll: Scroll, score: int, wmap: WorldMap, n: int):
        """world_x after each of the next n frames, with the ramp applied as
        obstacles are passed. Also returns, per frame, the tallest box under
        the hitbox (0 if none known)."""
        s = Scroll(scroll.x, scroll.sub, scroll.speed)
        pending = [o for o in wmap.obstacles() if o.right_edge > s.x + self.hx0]
        xs, hs = [], []
        for _ in range(n):
            s.step()
            x = s.x
            h = max(wmap.height((x + self.hx0) >> 3), wmap.height((x + self.hx1) >> 3))
            xs.append(x)
            hs.append(h)
            if pending and x + self.hx0 >= pending[0].right_edge:
                pending.pop(0)
                score += 1
                s.speed = speed_for_score(self.cfg, score)
        return xs, hs

    def hit(self, y: int, h: int) -> bool:
        return h > 0 and (y >> 8) + self.hy1 >= self.ground_y - h


def worst_case_chains(cfg, speed: int, gap: int, slack: int = 3, ground: int = 10, max_fails: int = 3):
    """config.h's fairness rule, checked on synthetic worst cases: at a fixed
    speed, obstacles of every type (1 or 2 boxes, single or double) follow
    each other with `gap` empty tiles. From every reachable landing state
    there must be a jump plan that clears the next obstacle with both
    presses up to `slack` frames early or late and the earliest take-off at
    least `ground` frames after landing; the chain continues from the plan's
    latest possible landing. Returns (states explored, failures)."""
    ap = AutoPlayer(cfg)
    types = [(16, 2), (32, 2), (16, 4), (32, 4)]
    top_score = 10 ** 6        # future_world ramps by score: keep it at the top

    def step(dist, sub, seq):
        wm = WorldMap()
        start = t = 1000
        starts = []
        for h, w in seq:
            starts.append(t)
            for k in range(w):
                wm.tiles[t + k] = h
            t += w + gap
        for tt in range(start - 40, t + 40):
            wm.tiles.setdefault(tt, 0)
        wm.newest = t + 40
        s = Scroll(start * 8 - dist, sub, speed)
        xs, hs = ap.future_world(s, top_score, wm, 180)
        if speed != speed_for_score(cfg, top_score):
            s2 = Scroll(start * 8 - dist, sub, speed)
            xs = []
            for _ in range(180):
                s2.step()
                xs.append(s2.x)
            hs = [max(wm.height((x + ap.hx0) >> 3), wm.height((x + ap.hx1) >> 3)) for x in xs]
        r = ap.plan_ground_tolerant(ground, xs, hs, (starts[0] + seq[0][1]) * 8, slack)
        if r is None:
            return None
        s = Scroll(start * 8 - dist, sub, speed)
        for _ in range(r[0] + 1):
            s.step()
        return (starts[1] * 8 - s.x, s.sub)

    frontier, seen, fails = {(160, 0)}, set(), []   # landed well before the first obstacle
    while frontier and len(fails) < max_fails:
        st = frontier.pop()
        if st in seen:
            continue
        seen.add(st)
        for a in types:
            for b in types:
                for c in types:
                    nxt = step(st[0], st[1], [a, b, c])
                    if nxt is None:
                        fails.append((st, a, b, c))
                    elif nxt not in seen:
                        frontier.add(nxt)
    return seen, fails
