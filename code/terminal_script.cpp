#include "terminal_script_backend.hpp"
#if !defined(MK61_CORE_STANDALONE)
#include "calculator_control.hpp"
#include "entropy_pool.hpp"
#include "menu.hpp"
#include "terminal.hpp"
#include "tools.hpp"

namespace terminal_script_backend {
static class_terminal terminal;
void reset() { terminal.init_script(); }
u16 program_limit() {
  return library_mk61::program_memory_mode() == ProgramMemoryMode::CLASSIC_105
             ? core_61::CLASSIC_PROGRAM_STEP
             : core_61::EXTENDED_ADDRESS_LIMIT;
}
bool write_program(u16 address, const u8 *bytes, u16 count) {
  if (!bytes || !count || address >= program_limit() ||
      count > program_limit() - address)
    return false;
  u8 page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  for (usize i = 0; i < core_61::MAX_PROGRAM_STEP; ++i)
    (void)core_61::read_absolute_program(i, page[i]);
  for (u16 i = 0; i < count; ++i)
    if (address + i < core_61::MAX_PROGRAM_STEP)
      page[address + i] = bytes[i];
  apply_program_memory_auto(page, core_61::MAX_PROGRAM_STEP, true,
                            address + count > core_61::MAX_PROGRAM_STEP);
  for (u16 i = 0; i < count; ++i)
    if (!core_61::write_absolute_program(address + i, bytes[i]))
      return false;
  return true;
}
bool press_key(u8 scan) { return hidden_press_scan_code(scan); }
u32 random_decimal7() {
  return entropy_pool::next_decimal7(entropy_pool::Domain::M61_INIT);
}
terminal_protocol::Result command(u8, const char *line, bool trap) {
  return terminal.execute_script_line(line, trap);
}
void error(const char *text) { Serial.println(text); }
} // namespace terminal_script_backend
#endif
