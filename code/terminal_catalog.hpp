#ifndef MK61_TERMINAL_CATALOG_HPP
#define MK61_TERMINAL_CATALOG_HPP
#include "terminal_command_ids.hpp"
namespace terminal_catalog {
struct TerminalCommand {
  const char* name;
  u8 id;
  const char* desc;
};
// The interactive and script frontends use the same immutable catalog.
usize count();
TerminalCommand at(usize index); // index < count(); view into the Flash text pool
u8 lookup(const u8* line); // NUL-terminated command line; no leading spaces.
}
#endif
