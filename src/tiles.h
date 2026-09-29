/* Tile indices in art/bg_tiles.png (index = row * 16 + column).
   See docs/DESIGN.md for the full layout. */
#ifndef TILES_H
#define TILES_H

#define T_SKY          0
#define T_BLACK        1

#define T_BOX_TL       2
#define T_BOX_TR       3
#define T_BOX_BL       18
#define T_BOX_BR       19

#define T_BOX2_TL      4
#define T_BOX2_TR      5
#define T_BOX2_BL      20
#define T_BOX2_BR      21

#define T_GRASS_0      6
#define T_GRASS_1      7
#define T_GROUND_A0    8
#define T_GROUND_A1    9
#define T_GROUND_B0    24
#define T_GROUND_B1    25

#define T_CLOUD_TOP    10   /* 4 tiles: 10..13 */
#define T_CLOUD_BOT    26   /* 4 tiles: 26..29 */

#define T_HUD_DARK     14

/* Dark font: shade 3 glyphs on sky. Space is T_SKY. */
#define T_FONT_DIGIT   32   /* '0'..'9' */
#define T_FONT_ALPHA   42   /* 'A'..'Z' */
#define T_FONT_BANG    68
#define T_FONT_DASH    69
#define T_FONT_COLON   70
#define T_FONT_DOT     71
#define T_FONT_QUEST   72
#define T_FONT_APOS    73
#define T_FONT_SLASH   74
#define T_FONT_TIMES   75

/* Light font: shade 0 glyphs on the dark HUD colour. */
#define T_LFONT_DIGIT  80   /* '0'..'9' */
#define T_LFONT_ALPHA  90   /* 'A'..'Z' */
#define T_LFONT_SPACE  116
#define T_LFONT_BANG   117
#define T_LFONT_DASH   118
#define T_LFONT_COLON  119

/* Title logo tiles are loaded from here up (png2asset -tile_origin 128). */
#define T_LOGO_BASE    128

/* Sprite tiles (0x8000 bank, never 128 or above). */
#define S_PANDA_BASE   0
#define S_FX_BASE      64
#define S_TEXT_BASE    96   /* 'A'..'Z' copied from the dark font (26 tiles) */

/* Hardware sprite (OAM) slots. */
#define OAM_PANDA      0    /* 4 sprites: 0..3 */
#define OAM_FX         4
#define OAM_TEXT       5    /* up to 10 sprites: 5..14 */
#define OAM_TEXT_END   15
#define OAM_USED       15   /* everything from here up stays hidden */

#endif
