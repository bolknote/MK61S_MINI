#include "terminal_script.hpp"

#include "terminal.hpp"

namespace terminal_script {

static class_terminal terminal;

void reset(void) {
  terminal.init_script();
}

terminal_protocol::Result execute(const char* line) {
  return terminal.execute_script_line(line);
}

} // пространство имён terminal_script
