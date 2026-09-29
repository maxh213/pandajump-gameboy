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
    dead = 0;
    hidden = 0;
}

/* The first press leaves the ground; one more press in the air *sets* the
   velocity to the smaller double jump, like the original. */
uint8_t player_jump(void) {
    if (panda_on_ground) {
        panda_vy = -JUMP_VEL;
        panda_on_ground = 0;
        jumps_used = 1;
        return JUMPED;
    }
    if (jumps_used == 1) {
        panda_vy = -DJUMP_VEL;
        jumps_used = 2;
        return DOUBLE_JUMPED;
    }
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
        return 1;
    }
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

void fx_start(uint8_t y) {
    fx_frame = 0;
    fx_tick = 0;
    fx_x = PANDA_X + 4;           /* centred under the 16 px panda */
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
