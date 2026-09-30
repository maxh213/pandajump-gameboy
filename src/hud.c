/* Text on screen.

   - Score: map row 1 (the static HUD band), top-left, dark font. Only
     redrawn when it changes, right after vsync.
   - High score: the window's single visible row (WY = 136), light font on
     the dark HUD colour, e.g. "HI 0042".
   - Messages (SCORE / NEW BEST!, PAUSED): dark font written into the
     world band's always-sky row 7 (score) or 8 (PAUSED) while the world stands still, centred
     at its current scroll.
   - PRESS START (title and game over) and GAME OVER: sprites, using a copy
     of the dark font's letters. The world band scrolls under the title's
     prompt, and GAME OVER sits in the sky band, which drifts and bobs.
     While a message is up they share its centre line (see text_dx).

   Background text is queued and written right after vsync (hud_vram), so
   it never changes while its rows are being drawn. */
#include <gb/gb.h>
#include <stdint.h>

#include "config.h"
#include "tiles.h"
#include "hud.h"
#include "world.h"
#include "bg_tiles.h"

#define SCORE_COL  1
#define SCORE_ROW  1
#define SCORE_LEN  5              /* up to 65535 */

static uint8_t score_tiles[SCORE_LEN];
static uint8_t score_dirty;
static uint8_t high_tiles[20];
static uint8_t high_dirty;

#define MSG_MAX    20

/* The message: what is on screen now (to erase it), and what should be
   there after the next hud_vram(). */
static uint8_t msg_row;
static uint8_t msg_col;
static uint8_t msg_len;                   /* 0: nothing on screen */
static uint8_t next_row;
static uint8_t next_col;
static uint8_t next_len;                  /* 0: erase */
static uint8_t next_tiles[MSG_MAX];
static uint8_t msg_dirty;

/* A message can only start on the map's 8 px grid, so its centre is up to
   4 px off the screen's (-3..4). Sprite text is moved by the same amount,
   so GAME OVER, the score and PRESS START line up on one centre line
   instead of the middle line sitting a few pixels to one side. 0 when no
   message is up (the title's PRESS START is centred on the screen). */
static int8_t text_dx;

static const uint16_t powers[4] = { 10000, 1000, 100, 10 };

/* value -> 5 decimal digits, most significant first, without dividing */
static void to_digits(uint16_t v, uint8_t *d) {
    uint8_t i, n;

    for (i = 0; i < 4; i++) {
        n = 0;
        while (v >= powers[i]) {
            v -= powers[i];
            n++;
        }
        d[i] = n;
    }
    d[4] = (uint8_t)v;
}

/* Index of the first digit to show, keeping at least min_digits. */
static uint8_t first_digit(const uint8_t *d, uint8_t min_digits) {
    uint8_t i = 0;

    while (i < 5 - min_digits && d[i] == 0) i++;
    return i;
}

static uint8_t font_tile(char c) {
    if (c >= 'A' && c <= 'Z') return T_FONT_ALPHA + (c - 'A');
    if (c >= '0' && c <= '9') return T_FONT_DIGIT + (c - '0');
    switch (c) {
    case '!':  return T_FONT_BANG;
    case '-':  return T_FONT_DASH;
    case ':':  return T_FONT_COLON;
    case '.':  return T_FONT_DOT;
    case '?':  return T_FONT_QUEST;
    case '\'': return T_FONT_APOS;
    case '/':  return T_FONT_SLASH;
    }
    return T_SKY;
}

void hud_init(void) {
    set_sprite_data(S_TEXT_BASE, 26, bg_tiles_tiles + (T_FONT_ALPHA << 4));
    move_win(WIN_X, WIN_Y);
}

void hud_score(uint16_t value) {
    uint8_t d[5];
    uint8_t i, j = 0;

    to_digits(value, d);
    for (i = first_digit(d, 1); i < 5; i++) score_tiles[j++] = T_FONT_DIGIT + d[i];
    while (j < SCORE_LEN) score_tiles[j++] = T_SKY;
    score_dirty = 1;
}

void hud_score_hide(void) {
    uint8_t j;

    for (j = 0; j < SCORE_LEN; j++) score_tiles[j] = T_SKY;
    score_dirty = 1;
}

void hud_high(uint16_t value) {
    uint8_t d[5];
    uint8_t i, j;

    to_digits(value, d);
    for (j = 0; j < 20; j++) high_tiles[j] = T_HUD_DARK;
    high_tiles[1] = T_LFONT_ALPHA + ('H' - 'A');
    high_tiles[2] = T_LFONT_ALPHA + ('I' - 'A');
    j = 4;
    for (i = first_digit(d, 4); i < 5; i++) high_tiles[j++] = T_LFONT_DIGIT + d[i];
    high_dirty = 1;
}

/* Write a row of tiles that may run past map column 31 and wrap to 0. */
static void put_row(uint8_t col, uint8_t row, uint8_t len, const uint8_t *tiles) {
    uint8_t first = 32 - col;

    if (len <= first) {
        set_bkg_tiles(col, row, len, 1, tiles);
    } else {
        set_bkg_tiles(col, row, first, 1, tiles);
        set_bkg_tiles(0, row, len - first, 1, tiles + first);
    }
}

void hud_vram(void) {
    static const uint8_t blank[MSG_MAX] = {
        T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY,
        T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY, T_SKY
    };

    /* Top of the screen first: the beam may catch up once VBlank ends. */
    if (score_dirty) {
        set_bkg_tiles(SCORE_COL, SCORE_ROW, SCORE_LEN, 1, score_tiles);
        score_dirty = 0;
    }
    if (msg_dirty) {
        if (msg_len) put_row(msg_col, msg_row, msg_len, blank);
        if (next_len) put_row(next_col, next_row, next_len, next_tiles);
        msg_row = next_row;
        msg_col = next_col;
        msg_len = next_len;
        msg_dirty = 0;
    }
    if (high_dirty) {
        set_win_tiles(0, 0, 20, 1, high_tiles);
        high_dirty = 0;
    }
}

void hud_message(uint8_t row, const char *text) {
    uint8_t len = 0;

    while (text[len] && len < MSG_MAX) {
        next_tiles[len] = font_tile(text[len]);
        len++;
    }
    /* Map column c shows at screen x c*8 - world_scx; centre the text
       (rounded to the nearest column) on the 160 px screen. */
    next_col = (uint8_t)(world_scx + 84 - (len << 2)) >> 3;
    text_dx = (int8_t)(uint8_t)((next_col << 3) - world_scx + (len << 2) - 80);
    next_row = row;
    next_len = len;
    msg_dirty = 1;
}

void hud_message_num(uint8_t row, const char *text, uint16_t value) {
    char buf[21];
    uint8_t d[5];
    uint8_t i, j = 0;

    while (text[j] && j < 14) {
        buf[j] = text[j];
        j++;
    }
    to_digits(value, d);
    for (i = first_digit(d, 1); i < 5; i++) buf[j++] = '0' + d[i];
    buf[j] = 0;
    hud_message(row, buf);
}

void hud_message_clear(void) {
    next_len = 0;
    text_dx = 0;
    msg_dirty = 1;
}

/* Capital letters and spaces, centred on the screen (or on the message's
   centre line) at y, one sprite per letter from OAM slot oam on. */
static void sprite_text(uint8_t oam, uint8_t y, const char *text, uint8_t len) {
    uint8_t x = ((uint8_t)(160 - (len << 3)) >> 1) + (uint8_t)text_dx;

    for (; *text; text++, x += 8) {
        if (*text == ' ') continue;
        set_sprite_tile(oam, S_TEXT_BASE + (*text - 'A'));
        move_sprite(oam, x + DEVICE_SPRITE_PX_OFFSET_X, y + DEVICE_SPRITE_PX_OFFSET_Y);
        oam++;
    }
}

void hud_prompt(uint8_t y) {
    sprite_text(OAM_TEXT, y, "PRESS START", 11);
}

void hud_prompt_hide(void) {
    hide_sprites_range(OAM_TEXT, OAM_TEXT_END);
}

void hud_game_over(uint8_t show) {
    if (show) sprite_text(OAM_OVER, OVER_TEXT_Y, "GAME OVER", 9);
    else hide_sprites_range(OAM_OVER, OAM_OVER_END);
}
