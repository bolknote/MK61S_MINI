#include "terminal_catalog.hpp"
#include "config.h"
#include "terminal_core.hpp"
#include "dwt_profiler.hpp"
#include "deep_idle.hpp"
#include "crash_dump.hpp"
#include "independent_watchdog.hpp"
#include "mpu_guard.hpp"
#include "mk8_literal.hpp"
#include <cstring>

namespace terminal_catalog {
// Единственный источник истины: имя <-> id <-> описание для help.
// Добавление команды: строка здесь + case в execute().
// Compact string pool: no hash index or aligned offset table in MCU Flash.
// M61 scripts use this catalog too, so their hot IF lookup is handled below.
#if MK61_TERMINAL_HELP_IS_EXTERNAL
// ELF metadata for the host bundle builder; the linker marks it non-allocating.
// The signature is constant-folded; the resource never occupies MCU Flash/RAM.
#if defined(__ELF__)
#define MK61_HELP_METADATA __attribute__((used, section(".mk61_help")))
#else
// Native tests use Mach-O/PE section syntax, so only the firmware ELF needs
// the named metadata section. help_signature() still keeps this host copy.
#define MK61_HELP_METADATA __attribute__((used))
#endif
static constexpr char help_text_utf8[] =
#define COMMAND(name, id, desc) "  " name "\t" desc "\n"
#include "terminal_commands.inc"
#undef COMMAND
"  R<r>=   " "R<r>= <число|random|raw 12hex> — записать регистр" "\n"
"  set$    " "set$<адрес> <hex> — записать память программ" "\n";
MK61_HELP_METADATA static constexpr auto help_text = M8_ARRAY(help_text_utf8);
// Two 1536-byte TEXT files, each prefixed by the 9-byte help signature.
static_assert(sizeof(help_text) - 1 <= 3054, "increase HELP page count in reader and builder");
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
static constexpr char command_text_utf8[] =
#if MK61_TERMINAL_HELP_IS_EXTERNAL
#define COMMAND(name, id, desc) name "\0"
#else
#define COMMAND(name, id, desc) name "\0" desc "\0"
#endif
#include "terminal_commands.inc"
#undef COMMAND
;
static constexpr auto command_text = M8_ARRAY(command_text_utf8);
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
  const char* name = command_text.data();
  for(usize current = 0; current < index; ++current) {
    while(*name++ != 0) {}
#if !MK61_TERMINAL_HELP_IS_EXTERNAL
    while(*name++ != 0) {}
#endif
  }
  const char* next = name;
  while(*next++ != 0) {}
  return {name, command_ids[index],
#if MK61_TERMINAL_HELP_IS_EXTERNAL
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

constexpr TerminalCommand command_with_id(u8 id) {
  for(usize i = 0; i < TERMINAL_COMMAND_COUNT; ++i) {
    const auto command = entry(i);
    if(command.id == id) return command;
  }
  return {nullptr, CMD_UNKNOWN, nullptr};
}
static constexpr auto conditional = command_with_id(CMD_IF);
static_assert(conditional.id == CMD_IF, "IF must be in the shared catalog");
static_assert(conditional.name[0] != 0, "IF word must not be empty");
static_assert(conditional.name[1] != 0, "IF word must have two bytes");
static_assert(conditional.name[2] == 0, "IF word must have only two bytes");

const char* conditional_arguments(const char* line) {
  return line && line[0]==conditional.name[0] && line[1]==conditional.name[1] &&
      terminal_core::is_space(line[2]) ? line+2 : nullptr;
}

static constexpr auto open = command_with_id(CMD_OPEN);
static_assert(open.id == CMD_OPEN && open.name[0] && open.name[1] &&
              open.name[2] && open.name[3] && !open.name[4],
              "OPEN must have four bytes in the shared catalog");
const char* open_arguments(const char* line) {
  return line && line[0]==open.name[0] && line[1]==open.name[1] &&
      line[2]==open.name[2] && line[3]==open.name[3] &&
      terminal_core::is_space(line[4]) ? line+4 : nullptr;
}

// Команда по первому слову строки: CMD_xxx или CMD_UNKNOWN.
u8 lookup(const u8* line) {
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::TERMINAL_LOOKUP);
  usize len = 0;
  while(line[len] != 0 && !terminal_core::is_space((char) line[len])) len++;
  if(len == 0) return CMD_UNKNOWN;

  // Спец-формы, не разбираемые по первому слову (длина ограждает от чтения
  // остатков предыдущей команды за нулём-терминатором):
  if(len == 3 && line[0] == 'R' && line[2] == '=' && terminal_core::is_space((char) line[3])) return CMD_REG_SET; // R0= <значение>
  if(len >= 4 && line[0] == 's' && line[1] == 'e' && line[2] == 't' && line[3] == '$') return CMD_SET_CODE;  // set$<hex>

  // The name/ID still come from the single catalog. No game-specific command
  // or second dispatch table; execute() retains all script/trap permission checks.
  if(len == 2 && line[0] == (u8) conditional.name[0] &&
     line[1] == (u8) conditional.name[1])
    return conditional.id;

  const char* name = command_text.data();
  for(usize index = 0; index < TERMINAL_COMMAND_COUNT; ++index) {
    if(strncmp((const char*) line, name, len) == 0 && name[len] == 0) {
      return command_ids[index];
    }
    while(*name++ != 0) {}
#if !MK61_TERMINAL_HELP_IS_EXTERNAL
    while(*name++ != 0) {}
#endif
  }
  return CMD_UNKNOWN;
}

usize count() { return TERMINAL_COMMAND_COUNT; }
TerminalCommand at(usize index) { return entry(index); }
} // namespace terminal_catalog
