#include "ai_chat.hpp"
#include "mk61emu_core.h"
#include "services.hpp"
#include "lcd_color.hpp"
#include "terminal_mnemonics.hpp"
#include "ui_font.hpp"
#include <array>
#include <cstdio>
#include <cassert>
#include <cstring>
#include <map>
#include <string>
#include <vector>

void picocalc_ai_color_scroll_test();

namespace {
using namespace mk61ai;
using namespace picocalc::ai::chat;
std::array<std::uint16_t,320*320> opaque_pixels;
std::array<unsigned,320*320> opaque_writes;
unsigned opaque_frames=0;
constexpr char classic_isa[] =
#include "terminal_classic_isa.inc"
;
void display_mnemonics_test() {
  // These are the operations in the verified Russian acos/sqrt example.
  // Their wire/assembler spellings must not leak into calculator screen text.
  struct Label { std::uint8_t opcode; const char *text; };
  const Label expected[] = {
      {0x66, M8("ИП 6")}, {0x1A, "F acos"}, {0x21, M8("F √")},
      {0x0E, M8("В↑")}, {0x0D, M8("Сx")}, {0x12, M8("×")},
      {0x13, M8("÷")}, {0x50, M8("С/П")}};
  for (const auto &label : expected) {
    char out[terminal_mnemonics::MAX_LENGTH + 1];
    terminal_mnemonics::display(classic_isa, label.opcode, out);
    assert(!std::strcmp(out, label.text));
  }
  // The terminal syntax still accepts the historical ASCII mnemonic.
  char wire[terminal_mnemonics::MAX_LENGTH + 1];
  terminal_mnemonics::csv(classic_isa, 0x21, wire);
  assert(!std::strcmp(wire, "V\"\"\""));
  for (unsigned opcode = 0; opcode < 256; ++opcode) {
    std::array<char, terminal_mnemonics::MAX_LENGTH + 3> guarded;
    guarded.fill('!');
    char *out = guarded.data() + 1;
    terminal_mnemonics::display(classic_isa, std::uint8_t(opcode), out);
    assert(guarded.front() == '!' && guarded.back() == '!');
    const auto length = std::strlen(out);
    assert(length && length <= terminal_mnemonics::MAX_LENGTH);
    assert(mk8::text_valid(reinterpret_cast<const u8 *>(out), length));
  }
  // All new mathematical glyphs must exist in every face used by the chat.
  for (const auto size : {ui_font::Size::PX12, ui_font::Size::PX14,
                          ui_font::Size::PX16}) {
    const ui_font::Face face{ui_font::Family::PIXEL, size};
    const auto missing = ui_font::glyph(face, '?');
    for (const auto symbol : {mk8::BYTE_SQRT, mk8::BYTE_UP_ARROW,
                              mk8::BYTE_MULTIPLY, mk8::BYTE_DIVIDE}) {
      const auto glyph = ui_font::glyph(face, mk8::codepoint(symbol));
      assert(glyph.bitmap != missing.bitmap && glyph.width && glyph.height);
    }
  }
}
std::uint32_t opaque_call(std::uint32_t service,std::uint32_t operation,std::uint32_t,std::uint32_t,void* payload) {
 assert(service==MK61_SERVICE_COLOR_DISPLAY);
 if(operation==MK61_COLOR_AVAILABLE)return 1;
 if(operation==MK61_COLOR_SCROLL_BEGIN)return 0; // Older host compatibility.
 assert(operation==MK61_COLOR_PRESENT && payload);
 const auto &f=*static_cast<const mk61_service_color_frame*>(payload);
 assert(picocalc::lcd::valid_color(f));
 for(unsigned y=0;y<f.height;++y)for(unsigned x=0;x<f.width;++x) {
  unsigned at=(f.y+y)*320+f.x+x;
  opaque_pixels[at]=picocalc::lcd::color_pixel(f,x,y);
  ++opaque_writes[at];
 }
 ++opaque_frames;return 1;
}
struct Journal {
  std::map<std::string, std::vector<std::uint8_t>> data;
  Store store() {
    return {
        this,
        [](void *raw, const char *path, void *out, unsigned cap, unsigned &n) {
          auto &d = static_cast<Journal *>(raw)->data;
          auto at = d.find(path);
          if (at == d.end() || at->second.size() > cap)
            return false;
          n = unsigned(at->second.size());
          std::memcpy(out, at->second.data(), n);
          return true;
        },
        [](void *raw, const char *path, const void *bytes, unsigned n) {
          const auto p = static_cast<const std::uint8_t *>(bytes);
          static_cast<Journal *>(raw)->data[path] = {p, p + n};
          return true;
        },
        [](void *raw, const char *path) {
          return static_cast<Journal *>(raw)->data.count(path) != 0;
        },
        [](void *raw, const char *path, unsigned &n) {
          auto &d = static_cast<Journal *>(raw)->data;
          auto at = d.find(path);
          if (at == d.end())
            return false;
          n = unsigned(at->second.size());
          return true;
        }};
  }
};
} // namespace

void picocalc_ai_chat_test() {
  using namespace mk61ai;
  using namespace picocalc::ai::chat;
  display_mnemonics_test();
  picocalc_ai_color_scroll_test();
  core_61::enable();
  core_61::set_expanded_program_mode(false);
  Journal disk;
  Session s;
  s.id = 9001;
  assert(set_task(s, "Вычисли синус 22.", false));
  assert(append_event(disk.store(), s, "USER", s.task));
  const std::uint8_t code[] = {0x02, 0x02, 0x1c, 0x50};
  assert(accept_program(disk.store(), s, code, 4));
  Example example;
  example.angle = 0;
  const auto result = execute(s.program, example, s.task_revision);
  assert(result.status == Execution::STOPPED && result.x == 0.3746066);
  Agent::Metrics before, now;
  before.output_tokens = 4;
  before.prefill_tokens = 2;
  now = before;
  now.output_tokens += 27;
  now.prefill_tokens += 134;
  now.prefill_us = 5185000;
  now.decode_us = 129000;
  now.tool_us = 19000;
  now.decode_tokens = 26;
  const auto real = difference(now, before, 9876);
  assert(real.output == 27 && real.input == 134 && real.elapsed_ms == 9876 &&
         real.decode_us == 129000 && real.measured);
  History history;
  assert(history.sync(disk.store(), s));
  s.state = RunState::FINISHED;
  history.observe(s, real, result, 0);
  assert(history.count() == 1 && history[0].has_result);
  assert(history.save(disk.store(), s, real, result, 0));
  History resumed;
  assert(resumed.sync(disk.store(), s));
  assert(resumed.count() == 1 && resumed[0].has_result &&
         resumed[0].result.x == result.x && resumed[0].angle == 0 &&
         resumed[0].telemetry.output == 27 &&
         resumed[0].telemetry.elapsed_ms == 9876 &&
         resumed[0].program.bytes[2] == 0x1c);
  // Incomplete reports cannot replace a previously committed core answer.
  assert(append_event(disk.store(), s, "CHAT",
                      "CHAT1 999 999 0 4 1 999 0 1 1 1 1 1\nRUN 1 1234 4 0 999 "
                      "999 1\nHEX ZZ\nTEXT broken"));
  assert(resumed.sync(disk.store(), s));
  assert(resumed[0].result.x == result.x && resumed[0].telemetry.output == 27);
  // A follow-up invalidates an old core answer, even before another program is
  // generated.
  assert(set_task(s, "А теперь в радианах.", true));
  assert(append_event(disk.store(), s, "USER", "А теперь в радианах."));
  assert(resumed.sync(disk.store(), s));
  resumed.observe(s, {}, result, 0);
  assert(!resumed[resumed.count() - 1].has_result);
  // A page is bounded in RAM, but all older and newer turns remain reachable.
  for (unsigned i = 0; i < 11; ++i) {
    const std::string text = "Ещё сообщение " + std::to_string(i);
    assert(set_task(s, text.c_str(), false) &&
           append_event(disk.store(), s, "USER", text.c_str()));
    assert(resumed.sync(disk.store(), s));
  }
  assert(resumed.count() == History::CAPACITY && resumed.at_latest() &&
         resumed.has_older());
  unsigned pages = 0;
  while (resumed.has_older()) {
    assert(resumed.older(disk.store(), s));
    assert(++pages < 20);
  }
  assert(pages >= 2 && !resumed.at_latest());
  // Finishing a live request while an older page is open still saves its
  // result.
  assert(accept_program(disk.store(), s, code, 4));
  const auto later = execute(s.program, example, s.task_revision);
  assert(later.status == Execution::STOPPED && later.x == result.x);
  assert(resumed.save(disk.store(), s, real, later, 0));
  assert(!resumed.at_latest());
  pages = 0;
  while (!resumed.at_latest()) {
    assert(resumed.newer(disk.store(), s));
    assert(++pages < 20);
  }
  assert(pages >= 2 && resumed.count() == History::CAPACITY);
  assert(resumed[resumed.count() - 1].has_result &&
         resumed[resumed.count() - 1].result.x == later.x);
  // Render over two unrelated previous frames. Every LCD pixel must be
  // replaced, and the resulting RGB565 image must not depend on either.
  mk61_app_api api{};api.service=[]{};
  mk61_app_services services{};services.call=opaque_call;
  View view{};view.history=&resumed;view.active=true;
  Renderer renderer;
  opaque_pixels.fill(0xF81F);opaque_writes.fill(0);opaque_frames=0;
  renderer.paint(api,services,view,[](std::uint8_t,char *out){std::strcpy(out,"OP");});
  assert(opaque_frames==40);
  for(auto n:opaque_writes)assert(n==1);
  const auto first=opaque_pixels;
  opaque_pixels.fill(0x07E0);opaque_writes.fill(0);opaque_frames=0;
  renderer.paint(api,services,view,[](std::uint8_t,char *out){std::strcpy(out,"OP");});
  assert(opaque_frames==40&&opaque_pixels==first);
  for(auto n:opaque_writes)assert(n==1);
  std::puts("Opaque harness: all102400 pixels replaced exactly once; identical RGB565 over magenta/green previous frames PASS");
  char time[32];
  duration(125820, time, sizeof(time));
  assert(!std::strcmp(time, "2:05"));
}
