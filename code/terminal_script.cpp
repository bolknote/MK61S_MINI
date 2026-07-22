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

} // пространство имён terminal_script
