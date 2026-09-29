/* Text on screen.

   - Score: map row 1 (the static HUD band), top-left, dark font. Only
     redrawn when it changes, right after vsync.
   - High score: the window's single visible row (WY = 136), light font on
     the dark HUD colour, e.g. "HI 0042".
   - Messages (GAME OVER, PAUSED, ...): dark font written into the world
     band's always-sky rows 7-9 while the world stands still, centred at
     its current scroll.
   - PRESS START on the title: the world band scrolls there, so the prompt
     is made of sprites, using a copy of the dark font's letters.

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
#define PROMPT_Y   64             /* screen y of the title's PRESS START */

static uint8_t score_tiles[SCORE_LEN];
static uint8_t score_dirty;
static uint8_t high_tiles[20];
static uint8_t high_dirty;

#define MSG_MAX    20

/* Each message slot: what is on screen now (to erase it), and what should
   be there after the next hud_vram(). */
static uint8_t msg_row[MSG_SLOTS];
static uint8_t msg_col[MSG_SLOTS];
static uint8_t msg_len[MSG_SLOTS];        /* 0: nothing on screen */
static uint8_t next_row[MSG_SLOTS];
static uint8_t next_col[MSG_SLOTS];
static uint8_t next_len[MSG_SLOTS];       /* 0: erase */
static uint8_t next_tiles[MSG_SLOTS][MSG_MAX];
static uint8_t msg_dirty;                 /* bit per slot */

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
    uint8_t s;

    /* Top of the screen first: the beam may catch up once VBlank ends. */
    if (score_dirty) {
        set_bkg_tiles(SCORE_COL, SCORE_ROW, SCORE_LEN, 1, score_tiles);
        score_dirty = 0;
    }
    if (msg_dirty) {
        for (s = 0; s < MSG_SLOTS; s++) {
            if (!(msg_dirty & (1 << s))) continue;
            if (msg_len[s]) put_row(msg_col[s], msg_row[s], msg_len[s], blank);
            if (next_len[s]) put_row(next_col[s], next_row[s], next_len[s], next_tiles[s]);
            msg_row[s] = next_row[s];
            msg_col[s] = next_col[s];
            msg_len[s] = next_len[s];
        }
        msg_dirty = 0;
    }
    if (high_dirty) {
        set_win_tiles(0, 0, 20, 1, high_tiles);
        high_dirty = 0;
    }
}

void hud_message(uint8_t slot, uint8_t row, const char *text) {
    uint8_t len = 0;

    while (text[len] && len < MSG_MAX) {
        next_tiles[slot][len] = font_tile(text[len]);
        len++;
    }
    /* Map column c shows at screen x c*8 - world_scx; centre the text
       (rounded to the nearest column) on the 160 px screen. */
    next_col[slot] = (uint8_t)(world_scx + 84 - (len << 2)) >> 3;
    next_row[slot] = row;
    next_len[slot] = len;
    msg_dirty |= (uint8_t)(1 << slot);
}

void hud_message_num(uint8_t slot, uint8_t row, const char *text, uint16_t value) {
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
    hud_message(slot, row, buf);
}

void hud_message_clear(uint8_t slot) {
    next_len[slot] = 0;
    msg_dirty |= (uint8_t)(1 << slot);
}

void hud_messages_clear(void) {
    uint8_t s;

    for (s = 0; s < MSG_SLOTS; s++) hud_message_clear(s);
}

void hud_prompt(uint8_t show) {
    static const char text[] = "PRESS START";
    uint8_t i;
    uint8_t oam = OAM_TEXT;
    uint8_t x = (160 - (sizeof(text) - 1) * 8) / 2;

    if (!show) {
        hide_sprites_range(OAM_TEXT, OAM_TEXT_END);
        return;
    }
    for (i = 0; text[i]; i++, x += 8) {
        if (text[i] == ' ') continue;
        set_sprite_tile(oam, S_TEXT_BASE + (text[i] - 'A'));
        move_sprite(oam, x + DEVICE_SPRITE_PX_OFFSET_X, PROMPT_Y + DEVICE_SPRITE_PX_OFFSET_Y);
        oam++;
    }
}
