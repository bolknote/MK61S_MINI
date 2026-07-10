#ifndef PROGRAM_STORE_HOST_TEST_SHIM_H
#define PROGRAM_STORE_HOST_TEST_SHIM_H

#include "rust_types.h"

// Suppress the firmware-wide tools.hpp dependency. program_store only needs
// these layout constants and the flash health flag from that header.
#ifndef TOOLS
#define TOOLS
static constexpr usize FLASH_SECTOR_SIZE = 4096;
static constexpr isize MAX_SLOT_FOR_PROGRAM = 99;
extern bool flash_is_ok;
#endif

#endif
