#include "config.h"
#include "terminal_catalog.hpp"
#include "terminal_core.hpp"
#include "dwt_profiler.hpp"
#include "deep_idle.hpp"
#include "crash_dump.hpp"
#include "independent_watchdog.hpp"
#include "mpu_guard.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
using terminal_catalog::TerminalCommand;
#include "terminal_catalog_legacy.hpp"

static u8 linear_lookup(const std::string& text) {
  for(const auto& command : legacy_commands)
    if(text == command.name) return command.id;
  return CMD_UNKNOWN;
}

int main() {
  const usize count = sizeof(legacy_commands) / sizeof(legacy_commands[0]);
  assert(terminal_catalog::count() == count);
  for(usize i = 0; i < count; ++i) {
    const auto actual = terminal_catalog::at(i);
    const auto& expected = legacy_commands[i];
    if(std::strcmp(actual.name, expected.name) || actual.id != expected.id ||
       std::strcmp(actual.desc, expected.desc)) {
      std::fprintf(stderr, "catalog[%zu]: expected %s / %u / %s; got %s / %u / %s\n",
                   (size_t) i, expected.name, expected.id, expected.desc,
                   actual.name, actual.id, actual.desc);
      return 1;
    }
    // Both frontends strip the physical line terminator before dispatch.
    for(const char* suffix : {"", " argument", "\targument"}) {
      const std::string line = std::string(actual.name) + suffix;
      assert(terminal_catalog::lookup((const u8*) line.c_str()) == actual.id);
    }
    // Similar names and hash collisions must not resolve to a destructive command.
    for(usize pos = 0; pos < std::strlen(actual.name); ++pos) {
      for(char c = 'a'; c <= 'z'; ++c) {
        std::string mutation = actual.name;
        mutation[pos] = c;
        assert(terminal_catalog::lookup((const u8*) mutation.c_str()) == linear_lookup(mutation));
      }
    }
    const std::string extended = std::string(actual.name) + 'x';
    assert(terminal_catalog::lookup((const u8*) extended.c_str()) == CMD_UNKNOWN);
  }
  assert(terminal_catalog::lookup((const u8*) "") == CMD_UNKNOWN);
  assert(terminal_catalog::lookup((const u8*) "R0= 12") == CMD_REG_SET);
  assert(terminal_catalog::lookup((const u8*) "R0=") == CMD_UNKNOWN);
  assert(terminal_catalog::lookup((const u8*) "set$1234") == CMD_SET_CODE);
  assert(terminal_catalog::lookup((const u8*) "R") == CMD_UNKNOWN);
  assert(terminal_catalog::lookup((const u8*) "se") == CMD_UNKNOWN);
  std::puts("terminal catalog/help/lookup characterization: PASS");
}
