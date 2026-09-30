/* The panda: jump physics in 8.8 fixed point, animation, and the dust puff.

   The panda stays at screen x PANDA_X; only its y moves. panda_y is the top
   of the 16x16 sprite, so it stands on the ground at GROUND_Y - 16. */
#include <gb/gb.h>
#include <gb/metasprites.h>
#include <stdint.h>

#include "config.h"
#include "tiles.h"
#include "player.h"
#include "world.h"
#include "panda.h"                /* generated from art/panda.png */
#include "fx.h"                   /* generated from art/fx.png */

int16_t panda_y;
int16_t panda_vy;
uint8_t panda_on_ground;
uint8_t jumps_used;
uint8_t jump_buffer;

#define FLOOR_Y      ((GROUND_Y - 16) << 8)   /* panda_y when standing */
#define SUNK_Y       (GROUND_Y << 8)          /* dead and fully below ground */

/* Frames of art/panda.png */
#define RUN_FRAMES   6
#define FRAME_JUMP   6
#define FRAME_DOUBLE 7
#define FRAME_FALL   8
#define FRAME_DEAD   9

static uint8_t run_frame;
static uint16_t run_acc;          /* 8.8 pixels travelled since the last frame */
static uint8_t dead;
static uint8_t hidden;

void player_reset(void) {
    panda_y = FLOOR_Y;
    panda_vy = 0;
    panda_on_ground = 1;
    jumps_used = 0;
    jump_buffer = 0;
    dead = 0;
    hidden = 0;
}

static void take_off(void) {
    panda_vy = -JUMP_VEL;
    panda_on_ground = 0;
    jumps_used = 1;
    jump_buffer = 0;
}

/* A pressed (before this frame's gravity). On the ground: jump. In the air
   the second press is the double jump, but only when it helps:
   - vy = -DJUMP_VEL must be a boost. In the first 14 frames of a jump the
     panda still rises faster than that, and the original's "set the
     velocity" rule would cut the jump short (too low for a 2-box column);
   - the panda must be at least BUFFER_HEIGHT px up. Lower down (the last
     4 frames of a fall from a jump) a full jump on landing is worth more
     than a short hop.
   Any other press in the air is kept for JUMP_BUFFER frames, and if the
   panda lands in that time it jumps again at once (player_physics), so a
   press that comes a little early is not lost. */
uint8_t player_press(void) {
    if (panda_on_ground) {
        take_off();
        return JUMPED;
    }
    if (jumps_used == 1 && panda_vy > -DJUMP_VEL &&
        panda_y <= FLOOR_Y - (BUFFER_HEIGHT << 8)) {
        panda_vy = -DJUMP_VEL;
        jumps_used = 2;
        jump_buffer = 0;
        return DOUBLE_JUMPED;
    }
    jump_buffer = JUMP_BUFFER;
    return 0;
}

static void fall(void) {
    panda_vy += GRAVITY;
    if (panda_vy > MAX_FALL) panda_vy = MAX_FALL;
    panda_y += panda_vy;
}

uint8_t player_physics(void) {
    if (panda_on_ground) return 0;
    fall();
    if (panda_y >= FLOOR_Y) {
        panda_y = FLOOR_Y;
        panda_vy = 0;
        panda_on_ground = 1;
        jumps_used = 0;
        if (jump_buffer) {
            take_off();           /* a kept press: straight back up, as if */
            return JUMPED;        /* pressed on the first frame on the ground */
        }
        return LANDED;
    }
    if (jump_buffer) jump_buffer--;
    if (panda_y < 0) {            /* can't leave the top of the screen */
        panda_y = 0;
        if (panda_vy < 0) panda_vy = 0;
    }
    return 0;
}

uint8_t player_feet(void) {
    return (uint8_t)(panda_y >> 8) + HIT_Y1;
}

void player_run(void) {
    run_acc += world_speed;
    while (run_acc >= RUN_ANIM_STEP) {
        run_acc -= RUN_ANIM_STEP;
        if (++run_frame == RUN_FRAMES) run_frame = 0;
    }
}

void player_die(void) {
    dead = 1;
    jump_buffer = 0;
    panda_on_ground = 0;
    panda_vy = -DEAD_HOP_VEL;
}

/* A little hop, then down through everything; once below its standing
   height the panda is drawn behind the ground, and hidden when it's gone. */
void player_dead_fall(void) {
    if (hidden) return;
    fall();
    if (panda_y < 0) {
        panda_y = 0;
        if (panda_vy < 0) panda_vy = 0;
    }
    if (panda_y >= SUNK_Y) hidden = 1;
}

uint8_t player_sunk(void) {
    return hidden;
}

void player_draw(void) {
    uint8_t frame;
    uint8_t prop = 0;
    uint8_t n;

    if (hidden) {
        hide_sprites_range(OAM_PANDA, OAM_PANDA + 4);
        return;
    }
    if (dead) {
        frame = FRAME_DEAD;
        if (panda_y > FLOOR_Y) prop = S_PRIORITY;
    } else if (panda_on_ground) {
        frame = run_frame;
    } else if (panda_vy < 0) {
        frame = (jumps_used == 2) ? FRAME_DOUBLE : FRAME_JUMP;
    } else {
        frame = FRAME_FALL;
    }
    n = move_metasprite_ex(panda_metasprites[frame], S_PANDA_BASE, prop, OAM_PANDA,
                           PANDA_X + DEVICE_SPRITE_PX_OFFSET_X,
                           (uint8_t)(panda_y >> 8) + DEVICE_SPRITE_PX_OFFSET_Y);
    if (n < 4) hide_sprites_range(OAM_PANDA + n, OAM_PANDA + 4);
}

/* ---- Dust puff (art/fx.png): on the double jump and on landing ---------- */
#define FX_FRAMES (sizeof(fx_metasprites) / sizeof(fx_metasprites[0]))
#define FX_OFF    0xFF

static uint8_t fx_frame = FX_OFF;
static uint8_t fx_tick;
static uint8_t fx_x;
static uint8_t fx_y;

void fx_start(uint8_t x, uint8_t y) {
    fx_frame = 0;
    fx_tick = 0;
    fx_x = x;
    fx_y = y;
}

void fx_update(uint8_t drift) {
    if (fx_frame == FX_OFF) return;
    fx_x -= drift;                /* the puff stays where it was made */
    if (++fx_tick >= FX_FRAME_TIME) {
        fx_tick = 0;
        if (++fx_frame >= FX_FRAMES) {
            fx_frame = FX_OFF;
            hide_sprite(OAM_FX);
            return;
        }
    }
    if (!move_metasprite_ex(fx_metasprites[fx_frame], S_FX_BASE, 0, OAM_FX,
                            fx_x + DEVICE_SPRITE_PX_OFFSET_X,
                            fx_y + DEVICE_SPRITE_PX_OFFSET_Y)) {
        hide_sprite(OAM_FX);      /* an empty frame */
    }
}
