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
// ====== Диспетчер команд: имя -> id через CRC-8 индекс ======
// Первое слово строки хешируется CRC-8 (полином 0x31) и служит входом в
// 128-байтный индекс, построенный на этапе компиляции. Совпадение хеша
// обязательно подтверждается сравнением полного имени: иначе опечатка с тем же
// CRC молча выполнила бы чужую команду (среди команд есть dfu и sera).
// Коллизии хешей разрешаются линейным пробированием при построении индекса,
// поэтому переименовывать команды при совпадении CRC не требуется.


// Единственный источник истины: имя <-> id <-> описание для help.
// Добавление команды: строка здесь + case в execute().
// No pointers/padding per entry: F401 stores one text pool and four bytes
// per command. Offsets are constructed and range-checked at compile time.
struct Entry { u16 offset; u8 id; u8 name_size; };
static_assert(sizeof(Entry) == 4, "command catalog Flash contract");
static constexpr char command_text[] =
#define COMMAND(name, id, desc) name "\0" desc "\0"
#include "terminal_commands.inc"
#undef COMMAND
;
static_assert(sizeof(command_text) <= 65535, "command text exceeds offset range");
static constexpr usize TERMINAL_COMMAND_COUNT = 0
#define COMMAND(name, id, desc) + 1
#include "terminal_commands.inc"
#undef COMMAND
;
struct Entries { Entry values[TERMINAL_COMMAND_COUNT]; };
constexpr Entries make_entries() {
  Entries result{{
#define COMMAND(name, id, desc) {0, id, sizeof(name) - 1},
#include "terminal_commands.inc"
#undef COMMAND
  }};
  usize offset = 0;
  for(usize i = 0; i < TERMINAL_COMMAND_COUNT; ++i) {
    result.values[i].offset = (u16) offset;
    offset += result.values[i].name_size + 1;
    while(command_text[offset++] != 0) {}
  }
  return result;
}
static constexpr Entries entries = make_entries();
constexpr TerminalCommand entry(usize index) {
  const auto& value = entries.values[index];
  const char* name = command_text + value.offset;
  return {name, value.id, name + value.name_size + 1};
}


constexpr u8 terminal_crc8(const char* str, usize len) {
  u8 crc = 0;
  for(usize i = 0; i < len; i++) {
    crc ^= (u8) str[i];
    for(u8 bit = 0; bit < 8; bit++) crc = (crc & 0x80) ? (u8) ((crc << 1) ^ 0x31) : (u8) (crc << 1);
  }
  return crc;
}

constexpr usize terminal_name_len(const char* s) {
  usize len = 0;
  while(s[len] != 0) len++;
  return len;
}

struct TerminalCommandIndex {
  u8 slot[128];  // 1 + номер в terminal_commands; 0 - пусто
};

static_assert(TERMINAL_COMMAND_COUNT < 128, "command index must have an empty slot");

constexpr TerminalCommandIndex make_terminal_command_index(void) {
  TerminalCommandIndex index = {};
  for(usize n = 0; n < TERMINAL_COMMAND_COUNT; n++) {
    const char* name = entry(n).name;
    usize probe = terminal_crc8(name, terminal_name_len(name)) & 0x7F;
    while(index.slot[probe] != 0) probe = (probe + 1) & 0x7F;
    index.slot[probe] = (u8) (n + 1);
  }
  return index;
}
static constexpr TerminalCommandIndex terminal_command_index = make_terminal_command_index();

// Доказательство на этапе компиляции: каждая команда таблицы достижима через
// индекс и разрешается именно в свой id. Ловит и переполнение кластера
// пробирования, и случайный дубль имени - прошивка с недостижимой командой
// просто не соберётся.
constexpr bool terminal_index_resolves_all(void) {
  for(usize n = 0; n < TERMINAL_COMMAND_COUNT; n++) {
    const char* name = entry(n).name;
    const usize len = terminal_name_len(name);
    usize probe = terminal_crc8(name, len) & 0x7F;
    bool resolved = false;
    while(true) {
      const u8 slot = terminal_command_index.slot[probe];
      if(slot == 0) break; // пустая ячейка - имя в индексе не найдено
      const TerminalCommand cmd = entry(slot - 1);
      bool equal = true;
      for(usize i = 0; i <= len; i++) {
        if(cmd.name[i] != name[i]) { equal = false; break; }
      }
      if(equal) {
        resolved = (slot == n + 1); // Reject duplicate names even with equal id.
        break;
      }
      probe = (probe + 1) & 0x7F;
    }
    if(!resolved) return false;
  }
  return true;
}
static_assert(terminal_index_resolves_all(), "terminal command index: a command is unreachable (CRC cluster or duplicate name)");

// Команда по первому слову строки: CMD_xxx или CMD_UNKNOWN.
u8 lookup(const u8* line) {
  usize len = 0;
  while(line[len] != 0 && !terminal_core::is_space((char) line[len])) len++;
  if(len == 0) return CMD_UNKNOWN;

  // Спец-формы, не разбираемые по первому слову (длина ограждает от чтения
  // остатков предыдущей команды за нулём-терминатором):
  if(len == 3 && line[0] == 'R' && line[2] == '=' && terminal_core::is_space((char) line[3])) return CMD_REG_SET; // R0= <значение>
  if(len >= 4 && line[0] == 's' && line[1] == 'e' && line[2] == 't' && line[3] == '$') return CMD_SET_CODE;  // set$<hex>

  usize probe = terminal_crc8((const char*) line, len) & 0x7F;
  while(true) {
    const u8 slot = terminal_command_index.slot[probe];
    if(slot == 0) return CMD_UNKNOWN;
    const TerminalCommand cmd = entry(slot - 1);
    if(strncmp((const char*) line, cmd.name, len) == 0 && cmd.name[len] == 0) return cmd.id;
    probe = (probe + 1) & 0x7F;
  }
}

usize count() { return TERMINAL_COMMAND_COUNT; }
TerminalCommand at(usize index) { return entry(index); }
} // namespace terminal_catalog
