/* The panda: jump physics, animation, and the dust puff. */
#ifndef PLAYER_H
#define PLAYER_H

#include <stdint.h>

/* Read by the tests (docs/DESIGN.md). 8.8 fixed point. */
extern int16_t panda_y;           /* top of the sprite, screen pixels */
extern int16_t panda_vy;          /* positive is down */
extern uint8_t panda_on_ground;
extern uint8_t jumps_used;        /* 0 on the ground, 1 jumped, 2 double jumped */

#define JUMPED        1           /* player_jump() results */
#define DOUBLE_JUMPED 2

void player_reset(void);          /* standing on the ground, alive */
uint8_t player_jump(void);        /* A pressed: 0, JUMPED or DOUBLE_JUMPED */
uint8_t player_physics(void);     /* one frame of gravity; 1 on landing */
uint8_t player_feet(void);        /* screen y of the hitbox's bottom row */
void player_run(void);            /* advance the run cycle with world_speed */
void player_die(void);            /* death pose and hop */
void player_dead_fall(void);      /* one frame of the fall after dying */
void player_draw(void);

void fx_start(uint8_t y);         /* dust puff under the panda, top at y */
void fx_update(uint8_t drift);    /* animate; drift left with the ground */

#endif
