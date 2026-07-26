#include "config.h"

// Отдельный объект для Arduino IDE hook: resident отбрасывает его секции,
// post-build повторно линкует тот же объект точно в SRAM-overlay.
#if defined(MK61_ARDUINO_IDE_SYSTEM_APPS) && MK61_CHIP8_IS_LOADABLE

#define MK61_BUILD_CHIP8_MODULE 1
#define mk61_module_entry mk61_ide_chip8_module_entry
#define run_entry mk61_ide_chip8_run_entry

#include "chip8.cpp"
#include "chip8_runner.cpp"
#include "chip8_module_entry.cpp"

#endif
