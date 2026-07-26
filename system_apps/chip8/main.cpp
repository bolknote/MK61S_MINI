// Standalone CHIP-8 console System APP translation unit.
//
// The emulator, graphical runner and C1 file-handler entry point form one
// ARM object.  Shared display, storage and timing calls are resolved from the
// exact resident ELF during the APP link.

#define MK61_BUILD_CHIP8_MODULE 1
#define run_entry mk61_standalone_chip8_run_entry

#include "../../code/chip8.cpp"
#include "../../code/chip8_runner.cpp"
#include "../../code/chip8_module_entry.cpp"
