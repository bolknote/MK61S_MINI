#include "ai_chat.hpp"
#include "canvas.hpp"
#include "lcd_color.hpp"
#include "lcd_scroll.hpp"
#include "terminal_mnemonics.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>

namespace {
using namespace picocalc;
using namespace picocalc::ai::chat;
constexpr char isa[] =
#include "terminal_classic_isa.inc"
;
void mnemonic(std::uint8_t byte, char *out) {
  terminal_mnemonics::display(isa, byte, out);
}
// Model physical GRAM, a copied asynchronous strip, and the separate scan
// origin. The pixel oracle below knows nothing about the renderer's dirty bands.
struct Display {
  std::array<std::uint16_t, 320 * 320> ram{};
  std::array<std::uint8_t, MK61_COLOR_SNAPSHOT_BYTES> snapshot{};
  mk61_service_color_frame pending_frame{};
  lcd::Scroll target{}, visible{};
  lcd::ColorScroll transaction;
  bool supported = true, pending = false, inject_fault = false, reject = false;
  unsigned bytes = 0, frames = 0, commits = 0, recoveries = 0, waits = 0;
  static Display *current;
  static std::uint32_t service(std::uint32_t id, std::uint32_t op,
                               std::uint32_t b, std::uint32_t size, void *data) {
    assert(id == MK61_SERVICE_COLOR_DISPLAY && b == 0);
    return current->call(op, size, data);
  }
  void complete() {
    ++waits;
    if (!pending) return;
    const auto &f = pending_frame;
    // A partially written DMA window must not publish the pending origin.
    const unsigned rows = inject_fault ? 1 : f.height;
    for (unsigned y = 0; y < rows; ++y)
      for (unsigned x = 0; x < f.width; ++x)
        ram[target.map(f.y + y) * 320 + f.x + x] = lcd::color_pixel(f, x, y);
    if (inject_fault) { transaction.fault(); inject_fault = false; }
    pending = false;
  }
  unsigned call(unsigned op, unsigned size, void *data) {
    if (op == MK61_COLOR_AVAILABLE) return 1;
    if (op == MK61_COLOR_END) {
      complete();
      if (transaction.open) target = visible;
      transaction.reset(); return 1;
    }
    if (op == MK61_COLOR_SCROLL_BEGIN) {
      if (!supported) return 0;
      assert(size == sizeof(mk61_service_color_scroll) && data);
      if (pending) return 2;
      return transaction.begin(target, *static_cast<mk61_service_color_scroll *>(data));
    }
    if (op == MK61_COLOR_SCROLL_END) {
      assert(!size && !data);
      if (pending) return 2;
      if (!transaction.ready()) { ++recoveries; return 0; }
      visible = target; transaction.committed(); ++commits; return 1;
    }
    assert(op == MK61_COLOR_PRESENT && size == sizeof(mk61_service_color_frame));
    if (pending) return 2;
    if (reject) { reject = false; return 0; }
    const auto &f = *static_cast<mk61_service_color_frame *>(data);
    assert(lcd::valid_color(f));
    if (!transaction.open) transaction.valid = false;
    lcd::copy_color(pending_frame, f, snapshot.data());
    bytes += f.width * f.height * 2; ++frames; pending = true; return 1;
  }
  auto pixels() const {
    std::array<std::uint16_t, 320 * 320> out{};
    for (unsigned y = 0; y < 320; ++y)
      for (unsigned x = 0; x < 320; ++x)
        out[y * 320 + x] = ram[visible.map(y) * 320 + x];
    return out;
  }
};
Display *Display::current;
}

void picocalc_ai_color_scroll_test() {
  using namespace mk61ai;
  mk61_app_api api{};
  api.service = [] { Display::current->complete(); };
  mk61_app_services services{}; services.call = Display::service;
  Session session{};
  std::snprintf(session.task, sizeof(session.task), "%s",
      "Сначала возьми R6 с противоположным знаком, затем найди арккосинус "
      "этого числа, извлеки квадратный корень и умножь на 53.76291. "
      "Режим: радианы. R6 = 0.5.");
  constexpr std::uint8_t code[]{0x66,0x0B,0x1A,0x21,0x0E,0x0D,0x05,0x03,
                               0x0A,0x07,0x06,0x02,0x09,0x01,0x12,0x50};
  session.program.version = 2;
  session.program.task_revision = session.task_revision;
  session.program.size = sizeof(code);
  std::memcpy(session.program.bytes, code, sizeof(code));
  session.state = RunState::FINISHED;
  Result result{}; result.version = 2; result.task_revision = session.task_revision;
  result.status = Execution::STOPPED; result.x = 77.805812;
  History history; history.observe(session, {}, result, 1);
  assert(history.count() == 1 && history[0].has_result);
  View view{}; view.history = &history; view.follow = false; view.expanded_code = true;
  Renderer renderer;
  Display display, reference;
  reference.supported = false;
  unsigned compared = 0, saved = 0;
  const auto verify = [&](bool first = false) {
    history.observe(session, {}, result, 1); // The real UI synchronizes before every paint.
    Display::current = &display;
    display.bytes = display.frames = 0;
    const auto height = renderer.paint(api, services, view, mnemonic);
    assert(height);
    display.complete();
    const auto actual = display.pixels();
    std::array<std::uint8_t, canvas::BYTES> mono;
    std::memcpy(mono.data(), canvas::frame(), mono.size());
    // A fresh legacy renderer sends all pixels; it is independent of the
    // accelerated renderer's history, pending mapping and source snapshot.
    Display::current = &reference;
    View fresh = view; Renderer ordinary;
    assert(ordinary.paint(api, services, fresh, mnemonic) == height);
    reference.complete();
    assert(actual == reference.pixels());
    if (std::memcmp(mono.data(), canvas::frame(), mono.size())) {
      unsigned at = 0;
      while (mono[at] == canvas::frame()[at]) ++at;
      std::fprintf(stderr, "Mono mismatch: case=%u scroll=%u bytes=%u at=(%u,%u) actual=%02X expected=%02X\n",
                   compared, view.scroll, display.bytes, (at % 40) * 8, at / 40, mono[at], canvas::frame()[at]);
      assert(false);
    }
    if (first) assert(display.bytes == 204800 && display.frames == 40);
    else if (display.bytes < 204800) ++saved;
    ++compared;
    Display::current = &display;
  };
  verify(true);
  const unsigned maximum = renderer.content_height() - 250;
  assert(maximum > 250);
  view.scroll = 18; verify();
  assert(display.bytes == 18 * 320 * 2 + 2 * 250 * 2);
  view.scroll = 19; verify(); // Pixel rows need not align to eight-row strips.
  assert(display.bytes == 320 * 2 + 1000);
  verify(); assert(display.bytes == 0 && display.frames == 0);
  view.draft = M8("Ещё пример"); view.typing = true; view.cursor = 3;
  verify(); assert(display.bytes == 70 * 320 * 2);
  view.notice = M8("Проверено 32/32"); view.scroll = 37; verify();
  assert(display.bytes == 18 * 320 * 2 + 1000 + 70 * 320 * 2);
  // Both directions, offset wrap at 250, end clamps, and scrolling back to
  // the initial image. Fixed header/editor pixels are checked every time.
  for (unsigned step = 0; step < 100; ++step) {
    view.scroll = (step * 37) % (maximum + 1);
    verify();
  }
  view.scroll = 0; verify();
  // Change the layout/content: old GRAM must not be reused.
  view.expanded_code = false; verify(); assert(display.bytes == 204800);
  view.expanded_metrics = true; verify(); assert(display.bytes == 204800);
  view.expanded_code = true; verify();
  // A lost asynchronous strip forces a complete recovery before scan publish.
  view.scroll = 18; display.inject_fault = true;
  const unsigned failures = display.recoveries;
  verify(); assert(display.recoveries == failures + 1 && display.bytes >= 204800);
  // A rejected submission cancels its pending origin and invalidates reuse.
  view.scroll = 36; display.reject = true;
  assert(!renderer.paint(api, services, view, mnemonic));
  assert(!display.transaction.open);
  verify(); assert(display.bytes == 204800);
  // Leaving graphics/re-entering cannot reuse another surface's GRAM.
  display.call(MK61_COLOR_END, 0, nullptr);
  renderer.invalidate(); view.scroll = 54; verify(); assert(display.bytes == 204800);
  view.scroll = 72; verify();
  // Dense programs can exhaust the bounded display list at a clipped edge.
  // Such a view must retain the exact ordinary-renderer result, too.
  session.program.size = PROGRAM_SIZE;
  std::memset(session.program.bytes, 0x02, PROGRAM_SIZE);
  session.program.bytes[PROGRAM_SIZE - 1] = 0x50;
  for (unsigned step = 0; step < 30; ++step) {
    view.scroll = step * 17;
    verify();
  }
  // An old host without the extension keeps its exact original full redraw.
  display.supported = false;
  display.call(MK61_COLOR_END, 0, nullptr);
  display.visible = display.target = {};
  view.scroll = 90; verify(); assert(display.bytes == 204800);
  // Validate public bounds without touching GRAM or entering a transaction.
  lcd::ColorScroll bounds; lcd::Scroll mapping;
  for (const auto bad : {mk61_service_color_scroll{319,32,0,0},
                         mk61_service_color_scroll{22,250,250,0},
                         mk61_service_color_scroll{22,250,0,250}})
    assert(!bounds.begin(mapping, bad) && !bounds.open && !mapping.region.valid());
  assert(bounds.begin(mapping, {22,250,0,0}) == 3);
  assert(!bounds.begin(mapping, {22,250,0,1}));
  bounds.fault(); assert(!bounds.ready() && bounds.open);
  assert(bounds.ready()); bounds.committed();
  assert(bounds.begin(mapping, {22,250,0,18}) == 1 && bounds.rows == 18);
  assert(saved > 80 && display.waits > 100);
  std::printf("Color harness scroll: %u exact RGB565/mono oracles, both directions, wrap, fixed areas, old host, DMA recovery PASS; 18px=12520B, 1px=1640B\n", compared);
  Display::current = nullptr;
}
