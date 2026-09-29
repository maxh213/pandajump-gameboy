/* Tuning constants. The tests parse the plain "#define NAME value" lines,
   so every value here is a single literal number. */
#ifndef CONFIG_H
#define CONFIG_H

/* ---- Game states (game_state) ---------------------------------------- */
#define STATE_TITLE   0
#define STATE_PLAY    1
#define STATE_DEAD    2
#define STATE_PAUSED  3

/* ---- Screen layout (docs/DESIGN.md) ------------------------------------ */
#define PANDA_X       32    /* screen x of the panda sprite's left edge */
#define GROUND_Y      112   /* ground surface: top of map row 14 */
#define SKY_LYC       15    /* LYC line: the sky band starts on the next line */
#define WORLD_LYC     47    /* LYC line: the world band starts on the next line */
#define WIN_X         7     /* window (bottom HUD) position */
#define WIN_Y         136

/* ---- Panda physics: 8.8 fixed point, 256 = 1 px (per frame, per frame^2) */
#define GRAVITY       25    /* added to vy every frame in the air */
#define JUMP_VEL      750   /* jump from the ground: vy = -JUMP_VEL */
#define DJUMP_VEL     400   /* second press in the air: vy = -DJUMP_VEL */
#define MAX_FALL      768   /* vy is capped here (3 px/frame) */
#define DEAD_HOP_VEL  448   /* the little hop when the panda dies */

/* Measured in the ROM (PyBoy) with these values: a jump rises for 30
   frames to a 42.5 px apex and is in the air for 59 frames. A double jump
   pressed at the apex tops out at 54 px (sprite top at y = 42, well below
   the top of the screen) and stays up for 80 frames. */

/* Hitbox: inclusive pixel offsets inside the 16x16 sprite. Smaller than the
   drawn panda so a graze doesn't kill. HIT_X1 - HIT_X0 must stay below 8 so
   the box check only needs the two columns under the hitbox edges. */
#define HIT_X0        4
#define HIT_X1        11
#define HIT_Y0        4
#define HIT_Y1        14

/* ---- Scrolling and the difficulty ramp --------------------------------- */
#define SPEED_BASE    256   /* world speed at the start of a run (1 px/frame) */
#define SPEED_STEP    16    /* added every RAMP_EVERY points ... */
#define SPEED_MAX     384   /* ... up to 1.5 px/frame (reached at score 40) */
#define RAMP_EVERY    5     /* points per difficulty step */
#define SPACING_BASE  16    /* obstacle start-to-start distance in tiles ... */
#define SPACING_MIN   14    /* ... minus 1 per step, down to this (score 10) */
#define SPACING_RAND  3     /* plus a random 0..3 extra tiles (bit mask) */
#define DOUBLE_SCORE  10    /* double columns only once score > this ... */
#define DOUBLE_CHANCE 85    /* ... with probability 85/256 (1 in 3) */
#define FIRST_GAP     2     /* empty tiles before a run's first obstacle */

/* The ramp, per step (every 5 points): speed / spacing / frames between
   obstacle starts (before the random extra)
       score  0: 1.0   px/frame, 16 tiles, 128 frames
       score  5: 1.06  px/frame, 15 tiles, 112 frames
       score 10: 1.125 px/frame, 14 tiles,  99 frames (double columns begin)
       score 20: 1.25  px/frame, 14 tiles,  89 frames
       score 40: 1.5   px/frame, 14 tiles,  74 frames (from here on)

   Why the generator can never build an unclearable sequence
   ---------------------------------------------------------
   A box column is 16 px wide and the hitbox 8 px, so the hitbox overlaps a
   single column for 16 + 8 = 24 px of travel and a double column for 40 px.
   A jump keeps the hitbox above a 16 px column for 48 frames and above a
   32 px column for 32 frames:
   - single columns: 24 px at >= 1 px/frame takes <= 24 frames, so one jump
     clears a 1-box column with 24 frames to spare and a 2-box column with 8
     (the window grows with speed, because the column goes by faster);
   - a double 2-box column needs 40 frames above 32 px at 1 px/frame, more
     than a jump gives, so it takes the double jump (+12 px, +18 frames).
   Landing and jumping again: the panda lands 27-60 px past the left edge of
   what it cleared (further after a double jump or at higher speed) and must
   take off 18-36 px before the next obstacle (earlier for a 2-box column).
   So the start-to-start gap has to cover landing distance + take-off
   distance + time on the ground, and all three grow with speed.

   To leave room for a human, the rule is: every jump must still clear if
   either press (take-off and double jump) is up to 3 frames early or late,
   and the panda gets at least 10 frames on the ground between landing and
   the earliest of those take-offs. A tight gap can force a later-landing
   jump, which squeezes the gap after it, so the check follows endless
   chains of worst-case obstacles (1 or 2 boxes high, single or double),
   trying every take-off and double-jump frame with the integer physics,
   until the latest possible landing stops growing. With the gap after an
   obstacle's end fixed at SPACING - 2 empty tiles (a double column is 2
   tiles wider, so it is followed by SPACING + 2 start-to-start), the
   smallest SPACING that keeps every chain clearable is:

       speed (px/frame)   1.0   1.125  1.25  1.375  1.5
       minimum SPACING    10    11     12    13     14   tiles

   The need only grows with speed, so it is enough that the tightest spacing
   covers the fastest speed: SPACING_MIN = 14 at SPEED_MAX = 1.5 px/frame
   (13 would fail from 1.44 px/frame). Spacing never drops below
   SPACING_MIN, speed never exceeds SPEED_MAX, and the random extra only
   adds room, so every sequence is clearable at every point of the ramp,
   including obstacles generated just before a speed step. At the limit the
   obstacle rate is set by the jump itself (about 60 frames in the air), so
   the ramp gets harder mostly through speed: less time to react, and
   obstacles every 74 instead of 128 frames. */

/* ---- Clouds in the sky band -------------------------------------------- */
#define CLOUD_SHIFT     2   /* sky scrolls at world speed >> 2 (1/4) */
#define CLOUD_GAP_MIN   3   /* empty sky columns between clouds: 3 ... */
#define CLOUD_GAP_RAND  7   /* ... plus 0..7 (bit mask). About 4-8 s apart */
#define CLOUD_BOB_FRAMES 12 /* frames per step of the bob cycle (16 steps) */

/* ---- Animation and timing ---------------------------------------------- */
#define RUN_ANIM_STEP   1536 /* 8.8 px of travel per run frame: 10 fps at 1 px/frame */
#define FX_FRAME_TIME   4    /* frames per dust puff frame */
#define DEAD_DELAY      60   /* frames of ignored input after dying */
#define BLINK_FRAMES    32   /* PRESS START is on/off for this many frames */

#endif
