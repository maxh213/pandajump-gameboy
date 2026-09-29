/* Text: score, high score, messages and the title's PRESS START. */
#ifndef HUD_H
#define HUD_H

#include <stdint.h>

#define MSG_SLOTS 3

void hud_init(void);              /* display off: window row, sprite font */
void hud_score(uint16_t value);   /* top-left score (drawn after vsync) */
void hud_score_hide(void);
void hud_high(uint16_t value);    /* window: "HI 0042" (drawn after vsync) */
void hud_vram(void);              /* right after vsync: redraw what changed */

/* Messages go in the world band's always-sky rows 7-9, centred on the
   screen at the current (frozen) scroll, and are drawn after the next
   vsync. Each slot remembers where it was written so it can be erased. */
void hud_message(uint8_t slot, uint8_t row, const char *text);
void hud_message_num(uint8_t slot, uint8_t row, const char *text, uint16_t value);
void hud_message_clear(uint8_t slot);
void hud_messages_clear(void);

void hud_prompt(uint8_t show);    /* PRESS START as sprites (title) */

#endif
