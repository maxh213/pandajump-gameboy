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
#define DJUMP_VEL     400   /* double jump: vy = -DJUMP_VEL, only if that is a boost */
#define MAX_FALL      768   /* vy is capped here (3 px/frame) */
#define DEAD_HOP_VEL  448   /* the little hop when the panda dies */

/* Input: a press in the air that can't double jump (the double jump is
   used up, it would not speed the panda up, or the panda is less than
   BUFFER_HEIGHT px above the ground) is kept for JUMP_BUFFER frames and
   jumps the moment the panda lands. See "The jump buffer" below. */
#define JUMP_BUFFER   6     /* frames a press is kept, its own included */
#define BUFFER_HEIGHT 12    /* px above the ground: below it a press waits for the ground */

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
#define SPEED_BASE    288   /* world speed at the start of a run (1.125 px/frame) */
#define SPEED_STEP    12    /* added every RAMP_EVERY points ... */
#define SPEED_MAX     384   /* ... up to 1.5 px/frame (reached at score 40) */
#define RAMP_EVERY    5     /* points per difficulty step */
#define SPACING_BASE  14    /* obstacle start-to-start distance in tiles ... */
#define SPACING_MIN   14    /* ... minus 1 per step down to this (equal: no spacing ramp) */
#define SPACING_RAND  3     /* plus a random 0..3 extra tiles (bit mask) */
#define DOUBLE_SCORE  10    /* double columns only once score > this ... */
#define DOUBLE_CHANCE 85    /* ... with probability 85/256 (1 in 3) */
#define TALL_CHANCE   128   /* a column is 2 boxes high with probability 128/256 */
#define FIRST_GAP     2     /* empty tiles before a run's first obstacle (always 1 box) */

/* Past the top speed, every LATE_EVERY points (score 50, 60, 70, 80) more
   of the obstacles are doubles and 2 boxes high, and from LATE_RAND_SCORE
   the random extra spacing shrinks. None of these can make a sequence
   unclearable: every mix of obstacle types is covered below, and the
   spacing never drops under SPACING_MIN. */
#define LATE_EVERY    10
#define DOUBLE_STEP   11    /* double chance +11/256 per late step ... */
#define DOUBLE_MAX    128   /* ... up to 1 in 2 (score 80) */
#define TALL_STEP     8     /* 2-box chance +8/256 per late step ... */
#define TALL_MAX      160   /* ... up to 5 in 8 (score 80) */
#define LATE_RAND_SCORE 60  /* from this late step on ... */
#define LATE_RAND     1     /* ... the random extra is 0..1 tiles (bit mask) */

/* The ramp: speed and frames between obstacle starts (single columns,
   14 tiles apart, before the random extra of 0-3 tiles, 1.5 on average)
       score  0: 1.125 px/frame, 100 frames (1.8 s with the extra)
       score 10: 1.22  px/frame,  92 frames (double columns begin)
       score 20: 1.31  px/frame,  85 frames
       score 30: 1.41  px/frame,  80 frames (1.5 s with the extra)
       score 40: 1.5   px/frame,  75 frames (the top speed)
       score 50-80: doubles 1 in 3 -> 1 in 2, 2-box columns 1/2 -> 5/8;
                    from 60 the random extra is 0-1 tiles
   The original sent a column every 1.5 s at 200 px/s (1.11 px/frame at a
   third of the size). This starts at that speed with obstacles a little
   further apart, and is at the original's rate from about score 30.

   The input rules (player_press in player.c)
   ------------------------------------------
   - A second press while the panda still rises at least as fast as
     DJUMP_VEL (the first 14 frames of a jump) is not the double jump. The
     original sets vy = -DJUMP_VEL there too, which slows the panda down: a
     nervous double tap 2-8 frames apart peaked at 17-32 px, too low for a
     2-box column (31 px). Now it does nothing, and the double jump is
     still there for later.
   - Below BUFFER_HEIGHT (12 px) a press isn't the double jump either. After
     a jump that is the last 4 frames of the fall (2.8 px/frame): a double
     jump there peaks at only 15-23 px and keeps the panda in the air 33
     frames longer, so a slightly early press for the next jump used to
     turn into a weak hop that killed the full jump. Such a hop can still
     clear a 1-box column that is just arriving, so something is given up,
     but a full jump on landing is what a press this close to the ground is
     almost always meant as. From 12 px up (5 frames early and more) the
     double jump peaks at 25 px or more and clears a 1-box column.
   - Every other press in the air (these two, and any press after the
     double jump) is kept for JUMP_BUFFER (6) frames, its own included, and
     if the panda lands in that time it jumps on the landing frame, which is
     exactly a jump pressed on the first frame on the ground. A press up to
     5 frames early after a double jump, or up to 3 after a single jump, is
     no longer lost. The buffer is short on purpose: at the top speed a jump
     fired on landing can come too early for the next obstacle, and a longer
     buffer would turn more stray presses into such jumps.
   A player who presses on the ground loses nothing to these rules, and the
   check below simulates them for every mistimed press.

   Why the generator can never build an unclearable sequence
   ---------------------------------------------------------
   A box column is 16 px wide and the hitbox 8 px, so the hitbox overlaps a
   single column for 16 + 8 = 24 px of travel and a double column for 40 px.
   A jump keeps the hitbox above a 16 px column for 48 frames and above a
   32 px column for 32 frames:
   - single columns: 24 px at >= 1.125 px/frame takes <= 22 frames, so one
     jump clears a 1-box column with 26 frames to spare and a 2-box column
     with 10 (the window grows with speed: the column goes by faster);
   - a double 2-box column needs 36 frames above 32 px at 1.125 px/frame,
     more than a jump gives, so early on it takes the double jump (+12 px,
     +18 frames); from about 1.3 px/frame one well-timed jump will do.
   Landing and jumping again: the panda lands 27-60 px past the left edge of
   what it cleared (further after a double jump or at higher speed) and must
   take off 18-36 px before the next obstacle (earlier for a 2-box column).
   So the start-to-start gap has to cover landing distance + take-off
   distance + time on the ground, and all three grow with speed.

   To leave room for a human, the rule is: every jump must still clear if
   either press (take-off and double jump) is up to 3 frames early or late,
   and the panda gets at least 10 frames on the ground between landing and
   the earliest of those take-offs. A mistimed double jump press can fall
   in the first 14 frames or under BUFFER_HEIGHT; it then does what the
   rules above say (nothing, or a jump on landing), and the plan has to
   survive that too. A tight gap can force a later-landing jump, which
   squeezes the gap after it, so the check (worst_case_chains in
   tests/model.py) follows endless chains of worst-case obstacles (1 or 2
   boxes high, single or double, in every order), trying every take-off and
   double-jump frame with the integer physics, until the latest possible
   landing stops growing. With the gap after an obstacle's end fixed at
   SPACING - 2 empty tiles (a double column is 2 tiles wider, so it is
   followed by SPACING + 2 start-to-start), the smallest SPACING that keeps
   every chain clearable is:

       speed (px/frame)   1.0   1.125  1.25  1.375  1.5
       minimum SPACING    10    11     12    13     14   tiles

   SPACING_MIN = 14 is checked at every speed of the ramp (1.125 to 1.5 in
   steps of 12/256), and 13 already fails from 1.41 px/frame (score 30),
   so it is the tightest spacing the top speed allows. The spacing is 14 all the way, the speed
   never exceeds SPEED_MAX, and the random extra only adds room, so every
   sequence is clearable at every point of the ramp, including obstacles
   generated just before a speed step. The late ramp only changes how often
   each obstacle type comes, and every mix of types is in the check. */

/* ---- Clouds in the sky band -------------------------------------------- */
#define CLOUD_SHIFT     2   /* sky scrolls at world speed >> 2 (1/4) */
#define CLOUD_GAP_MIN   3   /* empty sky columns between clouds: 3 ... */
#define CLOUD_GAP_RAND  7   /* ... plus 0..7 (bit mask). About 4-8 s apart */
#define CLOUD_BOB_FRAMES 12 /* frames per step of the bob cycle (16 steps) */

/* ---- Animation and timing ---------------------------------------------- */
#define RUN_ANIM_STEP   1536 /* 8.8 px of travel per run frame: 11 fps at 1.125 px/frame */
#define FX_FRAME_TIME   4    /* frames per dust puff frame */

/* ---- Text on the title and game-over screens ---------------------------
   After a death the messages wait until the panda has sunk out of sight
   (so its death hop can't cover them), then:
       y 44  GAME OVER             sprites, over plain sky (map rows 5-6)
       y 56  SCORE 12 / NEW BEST! 12   BG text, world map row 7
       y 68  PRESS START           sprites, PROMPT_DELAY frames later
   12 px apart. The glyphs are 7 px tall, so there are 5 px of sky between
   the lines, and 5 px between PRESS START and y 80, the top of a 2-box
   column: the column the panda ran into is always right under the text.
   The clouds end by y 37, 6 px above GAME OVER. Start or A restarts only
   once PRESS START shows, and only with a new press (a button held from
   the run doesn't count). The title's PRESS START is at y 64 from its
   first frame. Both blink: on for BLINK_ON frames of every BLINK_PERIOD. */
#define TITLE_PROMPT_Y  64
#define OVER_TEXT_Y     44
#define OVER_SCORE_ROW  7
#define OVER_PROMPT_Y   68
#define PROMPT_DELAY    30   /* frames from the messages to PRESS START */
#define BLINK_PERIOD    64   /* a power of 2 */
#define BLINK_ON        44   /* about 0.7 s on, 0.3 s off */

#endif
