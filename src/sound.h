/* Sound effects and music. See docs/DESIGN.md. */
#ifndef SOUND_H
#define SOUND_H

#include <stdint.h>

#define MUSIC_TITLE 0
#define MUSIC_GAME  1

void sound_init(void);
void sound_update(void);

void sfx_jump(void);
void sfx_double_jump(void);
void sfx_score(void);
void sfx_death(void);
void sfx_start(void);
void sfx_pause(void);

void music_play(uint8_t song);
void music_stop(void);

#endif
