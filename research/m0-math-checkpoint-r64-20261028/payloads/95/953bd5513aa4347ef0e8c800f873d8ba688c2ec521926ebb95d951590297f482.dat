#ifndef MK61_PROGRAM_LOAD_HPP
#define MK61_PROGRAM_LOAD_HPP
#include "rust_types.h"

// Synchronous CRC32 + ZX0 file loading, shared by terminal and M61.
namespace program_load {
enum class Syntax : u8 { LEGACY, BINARY, INVALID };
struct Request { u16 address; const char* path; };
Syntax parse(const char* args, Request& request);
bool load(u16 file_id, u16 address, u16 address_limit);
bool reject(const char* message);
void reset();
bool blocked();
const char* error();
u16 written();
} // namespace program_load
#endif
