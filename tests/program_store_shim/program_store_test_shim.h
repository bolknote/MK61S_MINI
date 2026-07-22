#ifndef PROGRAM_STORE_HOST_TEST_SHIM_H
#define PROGRAM_STORE_HOST_TEST_SHIM_H

#include "rust_types.h"

#define PROGRAM_STORE_HOST_TEST 1

// Подавляем общую для прошивки зависимость tools.hpp. Из этого заголовка
// program_store нужны лишь константы разметки и флаг исправности flash.
#ifndef TOOLS
#define TOOLS
static constexpr usize FLASH_SECTOR_SIZE = 4096;
static constexpr isize MAX_SLOT_FOR_PROGRAM = 99;
extern bool flash_is_ok;
#endif

#endif
