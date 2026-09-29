/* Milestone 1 placeholder: the panda metasprite running on a blank field. */
#include <gb/gb.h>
#include <gb/metasprites.h>
#include <stdint.h>

#include "config.h"
#include "tiles.h"
#include "sound.h"
#include "bg_tiles.h"
#include "panda.h"

uint8_t frame_count;

void main(void) {
    uint8_t x;

    DISPLAY_OFF;
    set_bkg_data(0, bg_tiles_TILE_COUNT, bg_tiles_tiles);
    set_sprite_data(S_PANDA_BASE, panda_TILE_COUNT, panda_tiles);
    init_bkg(T_SKY);
    for (x = 0; x < 32; x++) {
        set_bkg_tile_xy(x, 14, (x & 1) ? T_GRASS_1 : T_GRASS_0);
        set_bkg_tile_xy(x, 15, (x & 1) ? T_GROUND_A1 : T_GROUND_A0);
        set_bkg_tile_xy(x, 16, (x & 1) ? T_GROUND_B1 : T_GROUND_B0);
        set_bkg_tile_xy(x, 17, (x & 1) ? T_GROUND_B1 : T_GROUND_B0);
    }
    BGP_REG = 0xE4;
    OBP0_REG = 0xD0;
    sound_init();
    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;

    while (1) {
        vsync();
        frame_count++;
        SCX_REG++;
        move_metasprite_ex(panda_metasprites[(frame_count >> 2) % 6], S_PANDA_BASE, 0, 0,
                           PANDA_X + DEVICE_SPRITE_PX_OFFSET_X, GROUND_Y - 16 + DEVICE_SPRITE_PX_OFFSET_Y);
        sound_update();
    }
}
