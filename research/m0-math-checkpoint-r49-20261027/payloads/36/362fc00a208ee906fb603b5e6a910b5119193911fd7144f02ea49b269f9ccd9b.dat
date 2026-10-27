#ifndef TERMINAL_SCRIPT_HPP
#define TERMINAL_SCRIPT_HPP

#include "terminal_protocol.hpp"

namespace terminal_script {

// Syntax only: no register reads, actions, or eager resolution of an IF tail.
// The compact form is optional; all other conditions keep the normal parser.
struct PreparedIf {
  i16 literal;
  u8 reference;
  u8 operation;
};
static_assert(sizeof(PreparedIf) == 4, "prepared IF cache entry changed");
enum class IfResult : u8 { FALSE, TRUE, ERROR, FALLBACK };

void reset(void);
terminal_protocol::Result execute(const char* line, bool trap_mode = false);
bool prepare_if(const char* line, PreparedIf& out, u8& tail_offset);
IfResult evaluate_if(const PreparedIf& condition, bool trap_mode = false);
// Assembly shares parsing and writes; a board lends its mnemonic view only
// for this call (front-coded SRAM lease on F401, immutable Flash on Pico).
bool assemble(const char* arguments, isize& next_address, const char* mnemonics);
bool command_supported(u8 id);

} // пространство имён terminal_script

#endif
