// Real ROM + production M61 parser/runner. Only storage, clock and board I/O
// are host adapters; movement and rendering execute the bundled calculator code.
#include "mk61emu_core.h"
#include "m61_text.hpp"
#include "mk61_ref.hpp"
#include "program_store.hpp"
#include "program_load.hpp"
#include "terminal_script.hpp"
#include "terminal_script_backend.hpp"
#include "segment_lcd1602.hpp"
#include <algorithm>
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

namespace {
struct File { std::string name, bytes; program_store::ProgramType type; };
std::vector<File> files;
u32 now_ms = 0;
unsigned steps = 0, manuals = 0;
u32 step_ms = 0, manual_ms = 0;
bool backend_error = false;

void step() { core_61::step(); ++steps; now_ms += step_ms; }
void check() {
  m61_text::Error problem{};
  if(m61_text::last_error(problem)) {
    std::cerr << problem.script << ':' << problem.line << ' ' << problem.message << '\n';
    std::exit(3);
  }
  if(core_61::extended_program_error()) std::exit(4);
}
void paused_frame() {
  for(unsigned limit = 0; limit < 300000; ++limit) {
    m61_text::service();
    check();
    if(!m61_text::active()) return;
    if(m61_text::test_waiting_for_time()) return;
    if(!m61_text::calculator_suspended()) step();
  }
  std::cerr << "Frame timeout: IP=" << core_61::active_program_bank() * 112 + core_61::get_IP() << '\n';
  std::exit(5);
}
void next_frame() { now_ms += 120; m61_text::service(); paused_frame(); }
double reg(unsigned index) {
  double value = 0;
  assert(mk61_ref::read({mk61_ref::Kind::R, (u8)index}, value));
  return value;
}
void dump() {
  check();
  std::cout << "{\"steps\":" << steps << ",\"ms\":" << now_ms
            << ",\"manuals\":" << manuals
            << ",\"timer_ms\":" << m61_text::timer_remaining_ms()
            << ",\"running\":" << (core_61::is_RUN() ? "true" : "false")
            << ",\"active\":" << (m61_text::active() ? "true" : "false")
            << ",\"auto\":" << (core_61::extended_display_auto() ? "true" : "false")
            << ",\"segmented\":" << (core_61::extended_display_segmented() ? "true" : "false")
            << ",\"regs\":[";
  for(unsigned i = 0; i < 16; ++i) {
    if(i) std::cout << ',';
    std::cout << std::setprecision(12) << reg(i);
  }
  std::cout << "],\"frame\":[";
  const u8 empty[12]{};
  const u8* frame = core_61::segment_display_frame();
  if(!frame) frame = empty;
  for(unsigned i = 0; i < 12; ++i) {
    if(i) std::cout << ',';
    std::cout << (frame ? (unsigned)frame[i] : 0);
  }
  const auto lcd = segment_lcd1602::plan(frame);
  assert(!lcd.overflow_count && lcd.custom_count <= 2);
  std::cout << "],\"lcd_custom\":" << (unsigned)lcd.custom_count << ",\"lcd_rows\":[";
  for(unsigned cell = 0; cell < 12; ++cell) {
    u8 rows[8]{}, native = 0;
    if(segment_lcd1602::native_character(frame[cell], native)) {
      if(native == '_') rows[7] = 31;
      else assert(native == ' ');
    } else segment_lcd1602::custom_rows(frame[cell], rows);
    for(unsigned row = 0; row < 8; ++row) {
      if(cell || row) std::cout << ',';
      std::cout << (unsigned)rows[row];
    }
  }
  std::cout << "]}" << std::endl;
}
}

namespace program_store {
u32 media_revision() { return 1; }
bool entry_by_id(u16 id, Entry& out) {
  if(id >= files.size()) return false;
  out = {}; out.type = files[id].type; out.kind = NodeKind::FILE;
  out.id = id; out.parent_id = ROOT_ID; out.data_len = files[id].bytes.size();
  std::strncpy(out.name, files[id].name.c_str(), NAME_SIZE - 1);
  return true;
}
int count(ProgramType type) {
  int count = 0;
  for(const auto& file : files) if(file.type == type) ++count;
  return count;
}
bool entry(ProgramType type, int index, Entry& out) {
  for(unsigned i = 0; i < files.size(); ++i)
    if(files[i].type == type && index-- == 0) return entry_by_id(i, out);
  return false;
}
int child_count(u16 parent) { return parent == ROOT_ID ? files.size() : 0; }
bool child(u16 parent, int index, Entry& out) {
  return parent == ROOT_ID && index >= 0 && entry_by_id(index, out);
}
bool read_range_id(u16 id, u16 offset, u8* output, u16 length, u16* got) {
  if(got) *got = 0;
  if(id >= files.size()) return false;
  const auto& source = files[id].bytes;
  if(offset >= source.size()) return true;
  const auto size = std::min<size_t>(length, source.size() - offset);
  std::memcpy(output, source.data() + offset, size);
  if(got) *got = size;
  return true;
}
}
bool m61_text_host_resolve_file(u16 parent, const char* name, program_store::Entry& out) {
  if(parent != program_store::ROOT_ID) return false;
  for(unsigned i = 0; i < files.size(); ++i)
    if(files[i].name == name) return program_store::entry_by_id(i, out);
  return false;
}
u8 m61_text_host_open_entry(const program_store::Entry& entry) {
  if(entry.type == program_store::ProgramType::MARKDOWN) { ++manuals; now_ms += manual_ms; return 0; }
  return entry.type == program_store::ProgramType::MK61 && m61_text::open_program(entry.id) ? 0 : 2;
}
u8 m61_text_host_open_file(const char* name, u16 directory) {
  program_store::Entry entry{};
  return m61_text_host_resolve_file(directory, name, entry) ? m61_text_host_open_entry(entry) : 2;
}
bool OpenStoredFile(const char* name) { return m61_text::open_program(name); }
void hidden_start_loaded_program(u8 address) {
  core_61::set_IP(address); core_61::clear_displayed();
  for(unsigned i = 0; i < 4 && !core_61::is_RUN(); ++i) {
    MK61Emu_SetKeyPress(2, 9); step();
  }
  MK61Emu_SetKeyPress(0, 0);
  for(unsigned i = 0; i < 512 && !core_61::is_RUN(); ++i) step();
  assert(core_61::is_RUN());
}
void mk61_program_started() { assert(core_61::is_RUN()); }
void reinit_mk61_calculator_state() {
  core_61::clear_extended_program_banks(); core_61::enable();
}
void lcd_std_display_redraw() {}
u32 m61_text_host_millis() { return now_ms; }
i32 program_store_text_font_begin() { return -1; }
i32 program_store_text_font_load_from(const char*, u16) { return -1; }
i32 program_store_text_font_restore() { return 1; }
i32 program_store_text_font_end() { return 1; }
bool load_binary_program(u16 directory, const char* args) {
  program_load::Request request{};
  if(program_load::parse(args, request) != program_load::Syntax::BINARY) return false;
  program_store::Entry entry{};
  return m61_text_host_resolve_file(directory, request.path, entry) &&
         program_load::load(entry.id, request.address, 10000);
}
namespace terminal_script_backend {
void reset() { backend_error = false; }
u16 program_limit() { return 10000; }
bool write_program(u16 address, const u8* bytes, u16 count) {
  for(unsigned i = 0; i < count; ++i)
    if(!core_61::write_absolute_program(address + i, bytes[i])) return false;
  return true;
}
bool press_key(u8) { return false; }
u32 random_decimal7() { return 1234567; }
bool assemble(const char*, isize&) { return false; }
terminal_protocol::Result command(u8, const char*, bool) { return terminal_protocol::Result::error(); }
void error(const char* message) { std::cerr << message << '\n'; backend_error = true; }
}

int main(int argc, char** argv) {
  if(argc != 2) return 2;
  if(const char* start = std::getenv("MK61_RUNNER_START_MS")) now_ms = std::strtoul(start, nullptr, 0);
  for(const auto& path : std::filesystem::directory_iterator(argv[1])) {
    const auto extension = path.path().extension();
    if(extension != ".m61" && extension != ".bin" && extension != ".md") continue;
    std::ifstream input(path.path(), std::ios::binary);
    files.push_back({path.path().filename().string(), {std::istreambuf_iterator<char>(input), {}},
      extension == ".bin" ? program_store::ProgramType::MK61_BINARY :
      extension == ".md" ? program_store::ProgramType::MARKDOWN : program_store::ProgramType::MK61});
  }
  core_61::set_expanded_program_mode(true); core_61::enable();
  if(!m61_text::load_program("autoexec.m61")) { check(); return 3; }
  paused_frame(); dump();
  std::string line;
  while(std::getline(std::cin, line)) {
    std::istringstream input(line);
    std::string command; input >> command;
    steps = 0;
    if(command == "down" || command == "up" || command == "tap") {
      unsigned key = 0; input >> std::hex >> key;
      const bool captured = m61_text::handle_key_event(key, command != "up");
      assert(captured);
      if(command == "tap") assert(m61_text::handle_key_event(key, false));
    } else if(command == "frame") {
      unsigned count = 1; input >> count;
      for(unsigned i = 0; i < count; ++i) next_frame();
    } else if(command == "advance") {
      unsigned ms = 0; input >> ms; now_ms += ms;
      m61_text::service();
      if(!m61_text::calculator_suspended()) paused_frame();
    } else if(command == "step-ms") {
      input >> step_ms;
    } else if(command == "manual-ms") {
      input >> manual_ms;
    } else if(command == "fixture") {
      // Fixture only: expose every frame and hole word to the independent
      // art oracle. Normal input tests never write game state from the host.
      unsigned column, floor, hole = 0, timer = 0, redraw_request = 0;
      input >> column >> floor >> hole >> timer >> redraw_request;
      assert(redraw_request);
      // Request the existing no-op action through the normal input decoder.
      // A stationary production tick deliberately retains its old picture.
      for(auto entry : {std::pair<unsigned, double>{4, column}, {5, floor},
                        {0xB, hole ? 16*112 + (hole-1)*28 + 12 : 0}, {0xD, hole ? 1 : 0},
                        {0, redraw_request}, {0xA, redraw_request},
                        {0xE, 16*112 + (floor-1)*336 - 27}, {0xF, 8*112 + (floor-1)*144 - 12}})
        assert(mk61_ref::write({mk61_ref::Kind::R, (u8)entry.first}, entry.second));
      next_frame();
    } else if(command == "cancel") {
      m61_text::cancel();
    } else return 6;
    assert(!backend_error);
    dump();
  }
}
