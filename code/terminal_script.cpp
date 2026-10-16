#include "terminal_script.hpp"

#include "terminal.hpp"

namespace terminal_script {

static class_terminal terminal;

void reset(void) {
  terminal.init_script();
}

terminal_protocol::Result execute(const char* line, bool trap_mode) {
  return terminal.execute_script_line(line, trap_mode);
}

bool prepare_if(const char* line, PreparedIf& out, u8& tail_offset) {
  return class_terminal::prepare_script_if(line, out, tail_offset);
}

IfResult evaluate_if(const PreparedIf& condition, bool trap_mode) {
  return terminal.evaluate_script_if(condition, trap_mode);
}

} // пространство имён terminal_script
