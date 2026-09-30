/* Text: score, high score, messages, and the PRESS START / GAME OVER sprites. */
#ifndef HUD_H
#define HUD_H

#include <stdint.h>

void hud_init(void);              /* display off: window row, sprite font */
void hud_score(uint16_t value);   /* top-left score (drawn after vsync) */
void hud_score_hide(void);
void hud_high(uint16_t value);    /* window: "HI 0042" (drawn after vsync) */
void hud_vram(void);              /* right after vsync: redraw what changed */

/* One message at a time (SCORE / NEW BEST!, PAUSED) in the world band's
   always-sky row 7 (score) or 8 (PAUSED), centred on the screen at the current (frozen)
   scroll, drawn after the next vsync. A new one replaces the old one,
   which is remembered so it can be erased. */
void hud_message(uint8_t row, const char *text);
void hud_message_num(uint8_t row, const char *text, uint16_t value);
void hud_message_clear(void);

/* Sprite text (the world band scrolls, so these can't be BG text), with
   a copy of the dark font's letters. Centred on the screen, or, while a
   message is up, on the message's centre (BG text is on an 8 px grid), so
   stacked lines line up: show the message first. */
void hud_prompt(uint8_t y);       /* PRESS START at screen y, OAM_TEXT.. */
void hud_prompt_hide(void);
void hud_game_over(uint8_t show); /* GAME OVER at OVER_TEXT_Y, OAM_OVER.. */

#endif
