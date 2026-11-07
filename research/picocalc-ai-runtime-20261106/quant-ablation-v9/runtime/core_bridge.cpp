// Research-only C ABI for the same microcode core used by PicoCalc.
// Build together with code/mk61emu_core.cpp, with MK61_CORE_STANDALONE=1.
#include "mk61emu_core.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>

namespace {
constexpr char symbols[] = "0123456789ABCDEF";
struct Event { unsigned address, opcode; char x[16]; };
std::array<Event, 512> events;
unsigned event_count = 0, command_limit = 256;
bool limit_hit = false, ready = false;
core_61::ContextBuffer initial;

bool boundary(const core_61::Mk61ProgramBoundaryContext& context, void*) {
  if(event_count >= command_limit || event_count >= events.size()) {
    limit_hit = true;
    return true;
  }
  auto& event = events[event_count++];
  event.address = context.address;
  event.opcode = context.opcode;
  read_stack_register(stack::X, event.x, symbols);
  return false;
}
}

extern "C" {
int mk_reset() {
  core_61::clear_mk61_program_boundary_hook();
  if(!ready) {
    core_61::set_expanded_program_mode(false);
    core_61::configure_random_seed(false, 1);
    MK61Emu_SetAngleUnit(RADIAN);
    core_61::enable();
    ready = core_61::save_context(initial);
  } else if(!core_61::restore_context(initial)) return -1;
  event_count = 0;
  limit_hit = false;
  return ready ? 0 : -1;
}

int mk_load(const unsigned char* code, unsigned length) {
  if(length == 0 || length > MK61_CLASSIC_PROGRAM_STEPS) return -1;
  std::array<unsigned char, core_61::CODE_PAGE_BUFFER_SIZE> page;
  page.fill(0x50);
  std::copy(code, code + length, page.begin());
  core_61::set_code_page(page.data());
  core_61::set_IP(0);
  return 0;
}

int mk_set_register(unsigned index, const unsigned char* packed) {
  return MK61Emu_UnpackRegster(index, packed) ? 0 : -1;
}

int mk_set_stack(unsigned index, int negative, const char* digits, int exponent) {
  return write_stack_register(static_cast<stack>(index), negative ? '-' : ' ', digits, exponent) ? 0 : -1;
}

void mk_read_stack(unsigned index, char* out) {
  read_stack_register(static_cast<stack>(index), out, symbols);
}

void mk_read_register(unsigned index, char* out) {
  MK61Emu_ReadRegister(index, out, symbols);
}

int mk_run(unsigned max_commands, unsigned max_frames) {
  command_limit = std::min<unsigned>(max_commands, events.size());
  event_count = 0;
  limit_hit = false;
  if(!command_limit || !max_frames) return -1;
  if(!core_61::set_mk61_program_boundary_hook(boundary)) return -1;
  core_61::clear_displayed();
  for(unsigned i = 0; i < 4; ++i) {
    MK61Emu_SetKeyPress(2, 9); // Р/С, identical to the native core tests.
    core_61::step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0, 0);
  unsigned frames = 0;
  for(; frames < max_frames; ++frames) {
    if(limit_hit) break;
    core_61::step();
    if(!core_61::is_RUN() && core_61::is_displayed()) break;
  }
  core_61::clear_mk61_program_boundary_hook();
  if(limit_hit || frames == max_frames || core_61::is_RUN()) return 1;
  return core_61::has_error() ? 2 : 0;
}

unsigned mk_trace_size() { return event_count; }
unsigned mk_trace_address(unsigned index) { return index < event_count ? events[index].address : 0; }
unsigned mk_trace_opcode(unsigned index) { return index < event_count ? events[index].opcode : 0; }
void mk_trace_x(unsigned index, char* out) {
  if(index < event_count) std::memcpy(out, events[index].x, 15);
  else out[0] = 0;
}
unsigned mk_pc() { return core_61::get_IP(); }
unsigned mk_context_bytes() { return core_61::CONTEXT_BUFFER_SIZE; }
}
