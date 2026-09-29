/* High score in battery-backed cartridge RAM. */
#ifndef SAVE_H
#define SAVE_H

#include <stdint.h>

uint16_t save_load(void);         /* 0 (and a fresh block) if blank/corrupt */
void save_store(uint16_t value);

#endif
