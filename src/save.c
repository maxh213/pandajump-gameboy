/* High score in battery-backed cartridge RAM (MBC5, bank 0 at 0xA000).

   Two copies ("slots") of 8 bytes, at 0xA000 and 0xA008:

   Offset 0-1  magic 'P' 'J'
          2    format version (2)
          3    sequence number: +1 per save, wrapping 255 -> 0
          4-5  high score, little-endian
          6    checksum: (uint8_t)~(sum of bytes 0-5)
          7    0 (unused)

   A save always goes to the slot that does NOT hold the newest good copy,
   so a power cut in the middle of it can only spoil the slot being
   written. That slot's first byte is cleared before anything else and
   written last, so until the very last write the slot fails the magic
   check. Loading takes the good slot with the newest sequence number
   (compared as a signed difference, so 0 is newer than 255). If neither
   slot is good the high score is 0 and nothing is written: the next save
   makes a good slot. */
#include <gb/gb.h>
#include <stdint.h>

#include "save.h"

#define SAVE_VERSION 2
#define SLOT_SIZE    8
#define NO_SLOT      0xFF

static uint8_t * const sram = (uint8_t *)0xA000;

static uint8_t cur_slot;          /* slot with the newest good copy, or NO_SLOT */
static uint8_t cur_seq;           /* its sequence number */

static uint8_t checksum(const uint8_t *p) {
    return (uint8_t)~(uint8_t)(p[0] + p[1] + p[2] + p[3] + p[4] + p[5]);
}

static uint8_t slot_good(const uint8_t *p) {
    return p[0] == 'P' && p[1] == 'J' && p[2] == SAVE_VERSION && p[6] == checksum(p);
}

uint16_t save_load(void) {
    const uint8_t *p;
    uint8_t good0, good1;
    uint16_t value = 0;

    ENABLE_RAM;
    SWITCH_RAM(0);
    good0 = slot_good(sram);
    good1 = slot_good(sram + SLOT_SIZE);
    if (good0 && good1) {
        cur_slot = ((int8_t)(uint8_t)(sram[SLOT_SIZE + 3] - sram[3]) > 0) ? 1 : 0;
    } else if (good0) {
        cur_slot = 0;
    } else if (good1) {
        cur_slot = 1;
    } else {
        cur_slot = NO_SLOT;
    }
    if (cur_slot != NO_SLOT) {
        p = sram + (cur_slot ? SLOT_SIZE : 0);
        cur_seq = p[3];
        value = p[4] | ((uint16_t)p[5] << 8);
    }
    DISABLE_RAM;
    return value;
}

void save_store(uint16_t value) {
    uint8_t block[SLOT_SIZE];
    volatile uint8_t *p;          /* volatile: keep every write, in this order */
    uint8_t i;

    /* The other slot (slot 0 when there is no good one yet). */
    cur_slot = (cur_slot == 0) ? 1 : 0;
    cur_seq++;
    block[0] = 'P';
    block[1] = 'J';
    block[2] = SAVE_VERSION;
    block[3] = cur_seq;
    block[4] = (uint8_t)value;
    block[5] = (uint8_t)(value >> 8);
    block[6] = checksum(block);
    block[7] = 0;

    p = sram + (cur_slot ? SLOT_SIZE : 0);
    ENABLE_RAM;
    SWITCH_RAM(0);
    p[0] = 0;                     /* not a good slot from here ... */
    for (i = 1; i < SLOT_SIZE; i++) p[i] = block[i];
    p[0] = block[0];              /* ... until this last write */
    DISABLE_RAM;
}
