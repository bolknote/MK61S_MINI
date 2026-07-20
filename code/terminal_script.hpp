#ifndef TERMINAL_SCRIPT_HPP
#define TERMINAL_SCRIPT_HPP

#include "terminal_protocol.hpp"

namespace terminal_script {

void reset(void);
terminal_protocol::Result execute(const char* line);

} // пространство имён terminal_script

#endif
