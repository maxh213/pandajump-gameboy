/* Sound effects and music. See docs/DESIGN.md ("Sound API").

   Sound effects play on channels 1 and 4, music on channels 2 and 3, so
   music keeps going underneath the effects. Starting a sound effect cuts
   off whatever effect was playing on its channel.

   Call sound_init() once at startup and sound_update() once per frame,
   from the main loop. The other calls only queue things up; the sound
   starts on the next sound_update(), so calling them just before it in
   the same frame gives no delay. Don't call any of these from an
   interrupt handler. */
#ifndef SOUND_H
#define SOUND_H

#include <stdint.h>

#define MUSIC_TITLE 0   /* calm and cheerful, for the title screen */
#define MUSIC_GAME  1   /* upbeat, for a run */

void sound_init(void);      /* turn the APU on, set volumes, silence everything */
void sound_update(void);    /* once per frame */

void sfx_jump(void);
void sfx_double_jump(void);
void sfx_score(void);
void sfx_death(void);
void sfx_start(void);       /* start a run / confirm */
void sfx_pause(void);

void music_play(uint8_t song);   /* MUSIC_TITLE or MUSIC_GAME, from the top */
void music_stop(void);

/* Optional: hold the music (silently) and carry on from the same place,
   e.g. while the game is paused. music_play() and music_stop() also
   clear the pause. */
void music_pause(void);
void music_resume(void);

#endif
