/* The scrolling world: raster split, obstacle columns, clouds, collision. */
#ifndef WORLD_H
#define WORLD_H

#include <stdint.h>

/* Read by the tests (docs/DESIGN.md). */
extern uint16_t world_x;          /* whole pixels scrolled this run */
extern uint8_t world_scx;         /* low byte of world_x: the world band's SCX */
extern uint8_t world_sub;         /* the fraction of a pixel, 1/256ths */
extern uint8_t col_height[32];    /* box height in px (0, 16, 32) per map column */

extern uint16_t world_speed;      /* 8.8 px per frame */
extern uint8_t world_step;        /* whole pixels the world moved last frame */

void world_init(void);            /* once at boot, display off: map, ISRs */
void world_title(void);           /* title screen: logo, no boxes */
void world_start_run(uint8_t from_title);
void world_scroll(void);          /* advance the world by world_speed */
void world_clouds(uint16_t speed);/* drift the sky at speed >> CLOUD_SHIFT, bob */
uint8_t world_hit(uint8_t feet_y);/* 1 if a box reaches the hitbox's feet_y */
uint8_t world_cleared(void);      /* 1 when the panda has just passed an obstacle */
void world_ramp(void);            /* every RAMP_EVERY points: the difficulty ramp */
void world_vram(void);            /* right after vsync: queued tile writes */

#endif
