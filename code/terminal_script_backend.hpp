#ifndef MK61_TERMINAL_SCRIPT_BACKEND_HPP
#define MK61_TERMINAL_SCRIPT_BACKEND_HPP
#include "rust_types.h"
#include "terminal_protocol.hpp"
// Only board effects live here. Script syntax, permissions, register writes
// and control flow are shared by every model in terminal_script_runtime.cpp.
namespace terminal_script_backend {
void reset();
u16 program_limit();
bool write_program(u16 address, const u8 *bytes, u16 count);
bool press_key(u8 scan);
u32 random_decimal7();
bool assemble(const char *arguments, isize &next_address);
terminal_protocol::Result command(u8 id, const char *line, bool trap);
void error(const char *message);
} // namespace terminal_script_backend
#endif
