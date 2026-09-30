/* High score in battery-backed cartridge RAM. */
#ifndef SAVE_H
#define SAVE_H

#include <stdint.h>

uint16_t save_load(void);         /* 0 if no good copy; never writes */
void save_store(uint16_t value);  /* into the older (or bad) of the two slots */

#endif
