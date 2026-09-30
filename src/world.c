/* The world: three scroll bands split by the LYC interrupt, the obstacle
   column generator, clouds in the sky band, and box collision.

   Map rows (docs/DESIGN.md): 0-1 HUD, 2-5 sky band (clouds, title logo),
   6-9 sky (and the messages, rows 7-9), 10-13 boxes, 14 grass, 15-16
   ground, 17 ground under the window, 18-31 never written after
   world_init (plain sky, used to hide the logo wipe). The ground repeats
   every 2 tiles, which divides the 32-tile map, so it is written once and
   hardware scrolling does the rest. Box columns are written one at a time,
   just off-screen to the right, whenever world_x crosses a tile boundary. */
#include <gb/gb.h>
#include <rand.h>
#include <stdint.h>

#include "config.h"
#include "tiles.h"
#include "game.h"
#include "world.h"
#include "title_logo.h"

uint16_t world_x;
uint8_t world_scx;
uint8_t col_height[32];
uint16_t world_speed;
uint8_t world_step;
uint8_t world_sub;

/* ---- Raster split ------------------------------------------------------
   The main loop writes the "next" scroll values (world_scx, sky_scx,
   sky_bob) during the frame; the VBlank handler latches them, so the
   background moves on the same frame as the sprites, which GBDK copies to
   OAM in the same VBlank. */
static uint8_t sky_scx;           /* next sky band SCX */
static uint8_t sky_bob;           /* next sky band SCY, 0..4 (only ever down) */
static uint8_t isr_world_scx;     /* latched copies used by the LCD handler */
static uint8_t isr_sky_scx;
static uint8_t isr_sky_bob;

static uint8_t logo_row = 4;      /* next title logo row to replace; 4 = done */

/* While the logo is being replaced (a row per frame), the sky band (lines
   16-47) shows map rows 18-21 instead. Nothing but world_init's
   init_bkg() ever writes map rows 18-31, so they are always plain sky
   and the wipe is never seen half done. (Rows 6-9 would not do: a
   PAUSED pressed during the wipe goes to row 8.) */
#define WIPE_SCY (18 * 8 - 16)

static void vbl_isr(void) {
    SCX_REG = 0;                  /* HUD band: lines 0-15 don't scroll */
    SCY_REG = 0;
    LYC_REG = SKY_LYC;
    isr_world_scx = world_scx;
    isr_sky_scx = sky_scx;
    isr_sky_bob = (logo_row < 4) ? WIPE_SCY : sky_bob;
}

/* Runs at the start of line 15 and line 47. Both lines are plain sky on
   both sides of the split, so waiting for HBlank before writing is enough
   and a slightly late write would not show. */
static void lcd_isr(void) {
    if (LYC_REG == SKY_LYC) {
        while (STAT_REG & STATF_BUSY) {}
        SCX_REG = isr_sky_scx;
        SCY_REG = isr_sky_bob;
        LYC_REG = WORLD_LYC;
    } else {
        while (STAT_REG & STATF_BUSY) {}
        SCX_REG = isr_world_scx;
        SCY_REG = 0;
        LYC_REG = SKY_LYC;
    }
}

/* ---- Queued tile writes --------------------------------------------------
   Map changes are prepared during the frame and written right after the
   next vsync, in the VBlank that also latches the new scroll values, so a
   frame never shows half an update. New columns are off-screen anyway.
   The jobs at the start of a run are kept small: at most 8 old box
   columns to clear (see world_start_run) and one logo row per frame. */
#define NO_COLUMN 0xFF
#define CLOUD_ROW 3                  /* clouds use map rows 3-4 (see below) */

/* One queued column of each kind is enough: below 8 px per frame the world
   crosses at most one tile boundary per frame (the sky, at a quarter of
   the speed, even fewer), and the queue is emptied every VBlank. */
#if SPEED_MAX >= 2048
#error "SPEED_MAX must stay below 8 px/frame: one new column per frame"
#endif

static uint8_t box_col = NO_COLUMN;  /* map column to write, rows 10-13 */
static uint8_t box_tiles[4];
static uint8_t sky_col = NO_COLUMN;  /* map column to write, rows 2-5 */
static uint8_t sky_tiles[4];
#define CLEAR_SPAN 22                /* map columns a new run shows before it rewrites them */
static uint8_t clear_list[CLEAR_SPAN];  /* map columns with old boxes to erase */
static uint8_t clear_n;

static const uint8_t empty_column[4] = { T_SKY, T_SKY, T_SKY, T_SKY };

/* What replaces the title logo (map columns 1-18, rows 2-5) when a run
   starts: sky with a big cloud at columns 3-6 and a small one at 13-15 of
   rows 3-4 (CLOUD_ROW). All 72 tiles don't fit in one VBlank, so it goes
   one row per frame over 4 frames, while the sky band shows plain sky
   (vbl_isr). */
#define S_  T_SKY
#define CT  T_CLOUD_TOP
#define CB  T_CLOUD_BOT
#define ST  T_CLOUD2_TOP
#define SB  T_CLOUD2_BOT
static const uint8_t run_sky[18 * 4] = {
    S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_,
    S_, S_, CT, CT + 1, CT + 2, CT + 3, S_, S_, S_, S_, S_, S_, ST, ST + 1, ST + 2, S_, S_, S_,
    S_, S_, CB, CB + 1, CB + 2, CB + 3, S_, S_, S_, S_, S_, S_, SB, SB + 1, SB + 2, S_, S_, S_,
    S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_, S_
};
#undef S_
#undef CT
#undef CB
#undef ST
#undef SB
static const uint8_t *logo_src;      /* next row of run_sky to write */

/* Sky in map rows 10-13 of a column: a leaner set_bkg_tiles(c, 10, 1, 4),
   since up to 8 of these run after VBlank has ended. Like GBDK's own
   copy loop it waits for a mode in which VRAM can be written before each
   byte (the interrupt handlers return in such a mode, too). */
static void clear_box_column(uint8_t c) {
    uint8_t *p = (uint8_t *)0x9800 + 10 * 32 + c;
    uint8_t i;

    for (i = 0; i < 4; i++) {
        while (STAT_REG & STATF_BUSY) {}
        *p = T_SKY;
        p += 32;
    }
}

void world_vram(void) {
    if (logo_row < 4) {
        set_bkg_tiles(1, 2 + logo_row, 18, 1, logo_src);
        logo_src += 18;
        logo_row++;
    }
    while (clear_n) clear_box_column(clear_list[--clear_n]);
    if (box_col != NO_COLUMN) {
        set_bkg_tiles(box_col, 10, 1, 4, box_tiles);
        box_col = NO_COLUMN;
    }
    if (sky_col != NO_COLUMN) {
        set_bkg_tiles(sky_col, 2, 1, 4, sky_tiles);
        sky_col = NO_COLUMN;
    }
}

/* ---- Obstacle generator ---------------------------------------------------
   Each new column is either empty, or one half of a 16 px wide box. An
   obstacle is 1 box column (2 tiles) or, once score > DOUBLE_SCORE, 1 time
   in 3 a double (2 box columns side by side, 4 tiles), 1 or 2 boxes high
   (the run's first obstacle is always 1 box). After an obstacle come
   SPACING - 2 + random(0..3) empty columns; see config.h for why that
   spacing is always clearable. The late ramp raises the double and 2-box
   chances and narrows the random extra. */
static uint16_t gen_tile;         /* world_x >> 3 for the last column made */
static uint8_t gen_on;            /* 0 on the title: no boxes */
static uint8_t gen_first;         /* 1 until the run's first obstacle is made */
static uint8_t gen_gap;           /* empty columns before the next obstacle */
static uint8_t gen_cols;          /* columns left in the current obstacle */
static uint8_t gen_height;        /* its height in pixels, 16 or 32 */
static uint8_t spacing;           /* current start-to-start spacing, tiles */
static uint8_t spacing_rand;      /* bit mask of the random extra spacing */
static uint8_t double_chance;     /* P(double column) * 256 once score > DOUBLE_SCORE */
static uint8_t tall_chance;       /* P(2 boxes high) * 256 */
static uint8_t late_count;        /* ramp steps since the last late step */

/* Right edges (world x) of obstacles the panda hasn't passed yet. */
#define OBS_MAX 8                 /* power of 2; 3 at most are ever queued */
static uint16_t obs_edge[OBS_MAX];
static uint8_t obs_head;
static uint8_t obs_count;

static void gen_column(void) {
    uint16_t tile = gen_tile + 21;   /* first column fully off-screen right */
    uint8_t col = (uint8_t)tile & 31;
    uint8_t h = 0;

    if (!gen_cols) {
        if (gen_gap) {
            gen_gap--;
        } else {
            if (gen_first) {
                gen_first = 0;
                gen_height = 16;      /* an easy first jump */
            } else {
                gen_height = (rand() < tall_chance) ? 32 : 16;
            }
            gen_cols = 2;
            if (score > DOUBLE_SCORE && rand() < double_chance) gen_cols = 4;
            gen_gap = spacing - 2 + (rand() & spacing_rand);
        }
    }

    box_tiles[0] = T_SKY;
    box_tiles[1] = T_SKY;
    box_tiles[2] = T_SKY;
    box_tiles[3] = T_SKY;
    if (gen_cols) {
        h = gen_height;
        if (gen_cols & 1) {           /* right half of a box */
            box_tiles[2] = T_BOX_TR;
            box_tiles[3] = T_BOX_BR;
            if (h == 32) {
                box_tiles[0] = T_BOX2_TR;
                box_tiles[1] = T_BOX2_BR;
            }
        } else {                      /* left half */
            box_tiles[2] = T_BOX_TL;
            box_tiles[3] = T_BOX_BL;
            if (h == 32) {
                box_tiles[0] = T_BOX2_TL;
                box_tiles[1] = T_BOX2_BL;
            }
        }
        if (--gen_cols == 0 && obs_count < OBS_MAX) {
            /* a double column is one obstacle: queue its right edge once */
            obs_edge[(obs_head + obs_count) & (OBS_MAX - 1)] = (tile + 1) << 3;
            obs_count++;
        }
    }
    col_height[col] = h;
    box_col = col;
}

void world_scroll(void) {
    uint16_t t = (uint16_t)world_sub + (uint8_t)world_speed;
    world_sub = (uint8_t)t;
    world_step = (uint8_t)(world_speed >> 8) + (uint8_t)(t >> 8);
    world_x += world_step;
    world_scx = (uint8_t)world_x;
    if (gen_on) {
        /* world_x wraps at 65536 px (about 12 minutes at full speed), so
           tiles are counted modulo 8192 too; the world coordinates made
           from them wrap the same way. */
        t = world_x >> 3;
        while (gen_tile != t) {
            gen_tile = (gen_tile + 1) & 0x1FFF;
            gen_column();
        }
    }
}

uint8_t world_hit(uint8_t feet_y) {
    uint8_t h = col_height[(uint8_t)(world_scx + (PANDA_X + HIT_X0)) >> 3];
    uint8_t h2 = col_height[(uint8_t)(world_scx + (PANDA_X + HIT_X1)) >> 3];
    if (h2 > h) h = h2;
    return h && feet_y >= (uint8_t)(GROUND_Y - h);
}

/* Scoring: an obstacle counts once its right edge has passed the left edge
   of the panda's hitbox (it can't be hit any more). */
uint8_t world_cleared(void) {
    if (obs_count &&
        (int16_t)(world_x + (PANDA_X + HIT_X0) - obs_edge[obs_head]) >= 0) {
        obs_head = (obs_head + 1) & (OBS_MAX - 1);
        obs_count--;
        return 1;
    }
    return 0;
}

/* Every RAMP_EVERY points: faster (and closer, if SPACING_BASE is above
   SPACING_MIN) up to SPEED_MAX; after that, every LATE_EVERY points, more
   double and 2-box obstacles and less random room between them. */
void world_ramp(void) {
    if (spacing > SPACING_MIN) spacing--;
    if (world_speed < SPEED_MAX) {
        world_speed += SPEED_STEP;
        if (world_speed > SPEED_MAX) world_speed = SPEED_MAX;
        return;
    }
    if (++late_count < LATE_EVERY / RAMP_EVERY) return;
    late_count = 0;
    double_chance = (double_chance < DOUBLE_MAX - DOUBLE_STEP) ? double_chance + DOUBLE_STEP : DOUBLE_MAX;
    tall_chance = (tall_chance < TALL_MAX - TALL_STEP) ? tall_chance + TALL_STEP : TALL_MAX;
    if (score >= LATE_RAND_SCORE) spacing_rand = LATE_RAND;
}

/* ---- Sky band: clouds ----------------------------------------------------
   The sky scrolls at a quarter of the world speed. Like the boxes, a column
   is written just off-screen right each time the sky crosses a tile, either
   empty or one column of a cloud: the big 32x16 one or the small 24x16
   one, picked at random for each cloud so the sky doesn't look like
   wallpaper.

   Clouds sit at map rows 3-4 (CLOUD_ROW). The bob raises the band's
   content by up to 4 px (SCY 0-4), which would cut the top off a cloud at
   rows 2-3 against the static HUD band above; rows 3-4 stay whole at every
   bob height. Row 5 stays plain sky: GAME OVER is drawn there. */
static uint16_t sky_pos;          /* 8.8 sky scroll position */
static uint8_t sky_tile;          /* sky_scx >> 3 for the last column made */
static uint8_t cloud_cols;        /* columns left of the current cloud */
static uint8_t cloud_width;       /* 4: the big cloud, 3: the small one */
static uint8_t cloud_gap;         /* empty columns before the next cloud */
static uint8_t bob_timer;
static uint8_t bob_phase;

/* A slow up-and-down drift, pausing at the ends. */
static const uint8_t bob_table[16] = {
    0, 0, 1, 1, 2, 3, 3, 4, 4, 4, 3, 3, 2, 1, 1, 0
};

static void sky_column(void) {
    uint8_t i;

    sky_tiles[0] = T_SKY;
    sky_tiles[1] = T_SKY;
    sky_tiles[2] = T_SKY;
    sky_tiles[3] = T_SKY;
    if (!cloud_cols) {
        if (cloud_gap) {
            cloud_gap--;
        } else {
            cloud_width = (rand() & 1) ? 4 : 3;
            cloud_cols = cloud_width;
            cloud_gap = CLOUD_GAP_MIN + (rand() & CLOUD_GAP_RAND);
        }
    }
    if (cloud_cols) {
        i = cloud_width - cloud_cols;
        if (cloud_width == 4) {
            sky_tiles[CLOUD_ROW - 2] = T_CLOUD_TOP + i;
            sky_tiles[CLOUD_ROW - 1] = T_CLOUD_BOT + i;
        } else {
            sky_tiles[CLOUD_ROW - 2] = T_CLOUD2_TOP + i;
            sky_tiles[CLOUD_ROW - 1] = T_CLOUD2_BOT + i;
        }
        cloud_cols--;
    }
    sky_col = (sky_tile + 21) & 31;
}

void world_clouds(uint16_t speed) {
    uint8_t tile;

    sky_pos += speed >> CLOUD_SHIFT;
    sky_scx = (uint8_t)(sky_pos >> 8);
    tile = sky_scx >> 3;
    if (tile != sky_tile) {
        sky_tile = tile;
        sky_column();
    }
    if (++bob_timer >= CLOUD_BOB_FRAMES) {
        bob_timer = 0;
        bob_phase = (bob_phase + 1) & 15;
        sky_bob = bob_table[bob_phase];
    }
}

/* ---- Setup ---------------------------------------------------------------- */
void world_init(void) {
    uint8_t x;

    init_bkg(T_SKY);
    for (x = 0; x < 32; x += 2) {
        set_bkg_tile_xy(x, 14, T_GRASS_0);
        set_bkg_tile_xy(x + 1, 14, T_GRASS_1);
        set_bkg_tile_xy(x, 15, T_GROUND_A0);
        set_bkg_tile_xy(x + 1, 15, T_GROUND_A1);
        set_bkg_tile_xy(x, 16, T_GROUND_B0);
        set_bkg_tile_xy(x + 1, 16, T_GROUND_B1);
        set_bkg_tile_xy(x, 17, T_GROUND_B0);   /* under the window */
        set_bkg_tile_xy(x + 1, 17, T_GROUND_B1);
    }

    CRITICAL {
        STAT_REG = STATF_LYC;
        LYC_REG = SKY_LYC;
        add_VBL(vbl_isr);
        add_LCD(lcd_isr);
    }
    set_interrupts(VBL_IFLAG | LCD_IFLAG);
}

void world_title(void) {
    set_bkg_tiles(1, 2, title_logo_WIDTH >> 3, title_logo_HEIGHT >> 3, title_logo_map);
    sky_pos = 0;
    sky_scx = 0;                  /* the logo sits still */
    sky_bob = 0;
    gen_on = 0;
    world_speed = SPEED_BASE;
}

void world_start_run(uint8_t from_title) {
    uint8_t c;
    uint8_t first;

    /* The ground repeats every 16 px, so starting the run at world_x & 15
       keeps it exactly where it was: no jump in the grass. */
    world_x &= 15;
    world_sub = 0;
    world_scx = (uint8_t)world_x;
    world_step = 0;
    gen_tile = world_x >> 3;

    /* Remove the last run's boxes (col_height says where they are). Map
       columns gen_tile .. gen_tile + 21 can be seen before the generator
       gets to them (it writes gen_tile + 22 on), so old boxes there are
       erased at the next vsync, together with the scroll change; boxes in
       the other 10 columns get overwritten before they scroll into view.
       Obstacles are at least 14 tiles apart, so that's at most 8 columns. */
    first = (uint8_t)gen_tile;
    clear_n = 0;
    for (c = 0; c < 32; c++) {
        if (col_height[c]) {
            if ((uint8_t)((c - first) & 31) < CLEAR_SPAN) clear_list[clear_n++] = c;
            col_height[c] = 0;
        }
    }
    box_col = NO_COLUMN;

    if (from_title) {
        logo_row = 0;             /* the logo makes way for sky and clouds */
        logo_src = run_sky;
        sky_pos = 0;
        sky_scx = 0;
        sky_tile = 0;
        sky_col = NO_COLUMN;
        cloud_cols = 0;
        cloud_gap = 2 + (rand() & 3);
    }

    world_speed = SPEED_BASE;
    spacing = SPACING_BASE;
    spacing_rand = SPACING_RAND;
    double_chance = DOUBLE_CHANCE;
    tall_chance = TALL_CHANCE;
    late_count = 0;
    gen_on = 1;
    gen_first = 1;
    gen_gap = FIRST_GAP;
    gen_cols = 0;
    obs_head = 0;
    obs_count = 0;
}
