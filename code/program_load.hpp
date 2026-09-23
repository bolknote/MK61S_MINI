#ifndef MK61_PROGRAM_LOAD_HPP
#define MK61_PROGRAM_LOAD_HPP
#include "rust_types.h"

// Shared by the interactive terminal and all nested M61 scripts.
namespace program_load {
bool start(const char* args, u16 address_limit);
bool data(const char* args);
void reset();
void cancel();
bool blocked();
const char* error();
u16 written();
} // namespace program_load
#endif
