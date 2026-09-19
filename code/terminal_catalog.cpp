#include "terminal_catalog.hpp"
#include "config.h"
#include "terminal_core.hpp"
#include "dwt_profiler.hpp"
#include "deep_idle.hpp"
#include "crash_dump.hpp"
#include "independent_watchdog.hpp"
#include "mpu_guard.hpp"
#include <cstring>

namespace terminal_catalog {
// Единственный источник истины: имя <-> id <-> описание для help.
// Добавление команды: строка здесь + case в execute().
// Команды вводит человек, поэтому линейный проход по компактному пулу строк
// быстрее терминала на несколько порядков. Он заодно убирает из F401
// 128-байтный хеш-индекс и таблицу смещений с выравниванием.
#if MK61_SETUP_IS_LOADABLE
// ELF metadata for the host bundle builder; the linker marks it non-allocating.
// The signature is constant-folded; the resource never occupies MCU Flash/RAM.
#if defined(__ELF__)
#define MK61_HELP_METADATA __attribute__((used, section(".mk61_help")))
#else
// Native tests use Mach-O/PE section syntax, so only the firmware ELF needs
// the named metadata section. help_signature() still keeps this host copy.
#define MK61_HELP_METADATA __attribute__((used))
#endif
MK61_HELP_METADATA static constexpr char help_text[] =
#define COMMAND(name, id, desc) "  " name "\t" desc "\n"
#include "terminal_commands.inc"
#undef COMMAND
"  R<r>=   R<r>= <number|random|raw 12hex> - write register\n"
"  set$    set$<addr> <hex> - write program memory\n";
static_assert(sizeof(help_text) - 1 <= 2800, "increase HELP page count in reader and builder");
// Eight hexadecimal digits plus the line delimiter form the on-disk tag. Keep
// an explicit NUL because help_signature() is also a public C-string API.
struct HelpTag { char text[10]; };
constexpr HelpTag make_help_tag() {
  u32 hash = 2166136261U;
  for(usize i = 0; i < sizeof(help_text) - 1; ++i) hash = (hash ^ (u8) help_text[i]) * 16777619U;
  HelpTag result = {};
  for(unsigned i = 0; i < 8; ++i) result.text[i] = "0123456789abcdef"[(hash >> (28 - 4 * i)) & 15];
  result.text[8] = '\n';
  result.text[9] = 0;
  return result;
}
static constexpr HelpTag help_tag = make_help_tag();
const char* help_signature() { return help_tag.text; }
#undef MK61_HELP_METADATA
#endif
static constexpr char command_text[] =
#if MK61_SETUP_IS_LOADABLE
#define COMMAND(name, id, desc) name "\0"
#else
#define COMMAND(name, id, desc) name "\0" desc "\0"
#endif
#include "terminal_commands.inc"
#undef COMMAND
;
static_assert(sizeof(command_text) <= 65535, "command text exceeds offset range");
static constexpr usize TERMINAL_COMMAND_COUNT = 0
#define COMMAND(name, id, desc) + 1
#include "terminal_commands.inc"
#undef COMMAND
;
static constexpr u8 command_ids[TERMINAL_COMMAND_COUNT] = {
#define COMMAND(name, id, desc) id,
#include "terminal_commands.inc"
#undef COMMAND
};

constexpr TerminalCommand entry(usize index) {
  const char* name = command_text;
  for(usize current = 0; current < index; ++current) {
    while(*name++ != 0) {}
#if !MK61_SETUP_IS_LOADABLE
    while(*name++ != 0) {}
#endif
  }
  const char* next = name;
  while(*next++ != 0) {}
  return {name, command_ids[index],
#if MK61_SETUP_IS_LOADABLE
    nullptr
#else
    next
#endif
  };
}

constexpr bool terminal_names_are_unique(void) {
  for(usize left = 0; left < TERMINAL_COMMAND_COUNT; ++left) {
    const TerminalCommand a = entry(left);
    for(usize right = left + 1; right < TERMINAL_COMMAND_COUNT; ++right) {
      const TerminalCommand b = entry(right);
      usize offset = 0;
      while(a.name[offset] == b.name[offset] && a.name[offset] != 0) {
        ++offset;
      }
      if(a.name[offset] == b.name[offset]) return false;
    }
  }
  return true;
}
static_assert(terminal_names_are_unique(), "terminal command name is duplicated");

// Команда по первому слову строки: CMD_xxx или CMD_UNKNOWN.
u8 lookup(const u8* line) {
  usize len = 0;
  while(line[len] != 0 && !terminal_core::is_space((char) line[len])) len++;
  if(len == 0) return CMD_UNKNOWN;

  // Спец-формы, не разбираемые по первому слову (длина ограждает от чтения
  // остатков предыдущей команды за нулём-терминатором):
  if(len == 3 && line[0] == 'R' && line[2] == '=' && terminal_core::is_space((char) line[3])) return CMD_REG_SET; // R0= <значение>
  if(len >= 4 && line[0] == 's' && line[1] == 'e' && line[2] == 't' && line[3] == '$') return CMD_SET_CODE;  // set$<hex>

  const char* name = command_text;
  for(usize index = 0; index < TERMINAL_COMMAND_COUNT; ++index) {
    if(strncmp((const char*) line, name, len) == 0 && name[len] == 0) {
      return command_ids[index];
    }
    while(*name++ != 0) {}
#if !MK61_SETUP_IS_LOADABLE
    while(*name++ != 0) {}
#endif
  }
  return CMD_UNKNOWN;
}

usize count() { return TERMINAL_COMMAND_COUNT; }
TerminalCommand at(usize index) { return entry(index); }
} // namespace terminal_catalog
