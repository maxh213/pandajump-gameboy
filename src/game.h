/* Game-wide state owned by main.c. The tests read these by name. */
#ifndef GAME_H
#define GAME_H

#include <stdint.h>

extern uint8_t game_state;        /* STATE_* in config.h */
extern uint16_t score;
extern uint16_t high_score;
extern uint8_t frame_count;       /* +1 per frame */
extern uint8_t debug_invincible;  /* set by tests: boxes don't kill */

#endif
