/* High score in battery-backed cartridge RAM (MBC5, bank 0 at 0xA000).

   Offset 0-1  magic 'P' 'J'
          2    format version
          3-4  high score, little-endian
          5    checksum: (uint8_t)~(sum of bytes 0-4)

   Anything that fails a check reads as 0 and the block is rewritten. */
#include <gb/gb.h>
#include <stdint.h>

#include "save.h"

#define SAVE_VERSION 1
#define SAVE_SIZE    6

static uint8_t * const sram = (uint8_t *)0xA000;

static uint8_t checksum(const uint8_t *p) {
    return (uint8_t)~(uint8_t)(p[0] + p[1] + p[2] + p[3] + p[4]);
}

static void write_block(uint16_t value) {
    uint8_t block[SAVE_SIZE];
    uint8_t i;

    block[0] = 'P';
    block[1] = 'J';
    block[2] = SAVE_VERSION;
    block[3] = (uint8_t)value;
    block[4] = (uint8_t)(value >> 8);
    block[5] = checksum(block);
    for (i = 0; i < SAVE_SIZE; i++) sram[i] = block[i];
}

uint16_t save_load(void) {
    uint16_t value = 0;

    ENABLE_RAM;
    SWITCH_RAM(0);
    if (sram[0] == 'P' && sram[1] == 'J' && sram[2] == SAVE_VERSION &&
        sram[5] == checksum(sram)) {
        value = sram[3] | ((uint16_t)sram[4] << 8);
    } else {
        write_block(0);
    }
    DISABLE_RAM;
    return value;
}

void save_store(uint16_t value) {
    ENABLE_RAM;
    SWITCH_RAM(0);
    write_block(value);
    DISABLE_RAM;
}
