#include "ai_harness.hpp"
#include "ai_chat.hpp"
#include "ai_clock.hpp"
#include "ai_m3.hpp"
#include "ai_presentation.hpp"
#include "mk61_ai_perf.hpp"
#include "mk61_ai_long_bench.hpp"
#include "mk61_ai_linear.hpp"
#include "mk61_ai_kernels.h"
#if defined(PICO_ON_DEVICE)
#include "io_worker.hpp"
#include "psram.hpp"
#include "pico/stdio_usb.h"
#endif
#include "mk61_ai_agent.hpp"
#include "mk61emu_core.h"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "shared_memory_buffer.hpp"
#include "storage.hpp"
#include "terminal_core.hpp"
#include "terminal_mnemonics.hpp"
#include "text_input.hpp"
#include <algorithm>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#if defined(PICO_ON_DEVICE)
#include "hardware/sync.h"
#include <malloc.h>
extern "C" {
extern char __end__, __HeapLimit, __StackBottom, __StackTop;
}
#endif

#if defined(PICO_ON_DEVICE)
#define AI_COLD_CODE __attribute__((section(".ai_diagnostic_extension"),noinline))
#else
#define AI_COLD_CODE
#endif

namespace picocalc::ai {
namespace {
using namespace mk61ai;
static constexpr char isa[] =
#include "terminal_classic_isa.inc"
    ;
bool store_read(void *, const char *path, void *out, unsigned cap,
                unsigned &used) {
  files::Entry e{};
  return files::stat(path, e) && !e.directory && e.size <= cap &&
         files::read(path, static_cast<u8 *>(out), cap, used) && used == e.size;
}
bool store_write(void *, const char *path, const void *bytes, unsigned n) {
  return files::write(path, static_cast<const u8 *>(bytes), n);
}
bool store_exists(void *, const char *path) { return files::exists(path); }
bool store_size(void *, const char *path, unsigned &n) {
  files::Entry e{};
  if (!files::stat(path, e) || e.directory)
    return false;
  n = e.size;
  return true;
}
Store disk() {
  return {nullptr, store_read, store_write, store_exists, store_size};
}
unsigned m8(const char *text, char *out, unsigned cap) {
  unsigned used = 0;
  const auto *p = reinterpret_cast<const u8 *>(text);
  usize n = std::strlen(text);
  while (n && used + 1 < cap) {
    const auto d = utf8_codec::decode(p, n);
    u8 byte = '?';
    if (d.valid)
      mk8::from_codepoint(d.codepoint, byte);
    out[used++] = char(byte);
    const unsigned take = d.valid ? d.size : 1;
    p += take;
    n -= take;
  }
  out[used] = 0;
  return used;
}
bool utf8(const char *text, char *out, unsigned cap) {
  usize used = 0;
  if (!mk8::to_utf8(reinterpret_cast<const u8 *>(text), std::strlen(text),
                    reinterpret_cast<u8 *>(out), cap - 1, used))
    return false;
  out[used] = 0;
  return true;
}
enum class Screen : u8 {
  HOME,
  SESSION,
  MENU,
  VERSIONS,
  INTENT,
  SETTINGS,
  APPLY,
  TRACE,
  LOG,
  FORM,
  CASE,
  ATTACH
};
enum Action : unsigned {
  NEW_TASK,
  OPEN_BINARY,
  CURRENT,
  ADD_TEST,
  RUN_TESTS,
  EDIT_CODE,
  VERSIONS,
  EXPORT,
  APPLY,
  LOAD_INPUTS,
  SHOW_TRACE,
  LOG,
  SETTINGS,
  INTENT,
  SESSIONS,
  ATTACH,
  OPEN_ID,
  QUIT,
  SAVE_METRICS,
  SHOW_TESTS,
  TOGGLE_METRICS,
  TOGGLE_CODE
};
bool parse_code(const char *source, u8 out[PROGRAM_SIZE], unsigned &count) {
  count = 0;
  while (*source) {
    while (*source == ' ' || *source == '\t' || *source == '\r' ||
           *source == '\n')
      ++source;
    if (!*source)
      break;
    const char *end = source;
    while (*end && *end != ' ' && *end != '\t' && *end != '\n' && *end != '\r')
      ++end;
    unsigned opcode = 256;
    auto digit = [](char c) {
      return c >= '0' && c <= '9'   ? c - '0'
             : c >= 'a' && c <= 'f' ? c - 'a' + 10
             : c >= 'A' && c <= 'F' ? c - 'A' + 10
                                    : -1;
    };
    if (end - source == 2 && digit(source[0]) >= 0 && digit(source[1]) >= 0) {
      opcode = unsigned(digit(source[0]) * 16 + digit(source[1]));
      source = end;
    } else {
      usize consumed = 0;
      const auto found = terminal_core::match_mnemonic(isa, source, consumed);
      if (found >= 0) {
        opcode = unsigned(found);
        source += consumed;
      } else {
        const auto english =
            terminal_mnemonics::find(source, usize(end - source));
        if (english < 0)
          return false;
        opcode = unsigned(english);
        source = end;
      }
    }
    if (opcode > 255 || count == PROGRAM_SIZE)
      return false;
    out[count++] = u8(opcode);
  }
  return count != 0;
}
struct UI {
  explicit UI(const Host &h) : host(h), store(disk()), agent(s, store, model) {
    auto memory_plan=model.execution();memory_plan.tile_rows=28;
    model.execution(memory_plan);
    agent.clock(
        [](void *p) { return static_cast<UI *>(p)->call(MK61_SERVICE_MICROS); },
        this);
  }
  ~UI() { leave_fast_clock();ai_m3::close(); }
  Host host;
  Store store;
  Session s;
  Model model;
  Agent agent;
  shared_memory::Buffer package, cache;
  std::unique_ptr<std::uint64_t[]> workspace;
  bool model_ready = false, loading = false, cancel = false, quit = false,
       dirty = true, save_pending = false, typing = false, russian = true;
  Screen screen = Screen::HOME;
  unsigned selected = 0, selected_test = 0, cursor = 0, scroll[4]{};
  unsigned rows = 18, width = 304, line_count = 0, line_limit = 128,
           render_start = 0, model_loaded = 0, reads = 0;
  std::uint32_t last_draw = 0, last_edit = 0, started = 0;
  PresentationCadence presentation;
  std::uint32_t sessions[16]{};
  unsigned session_count = 0;
  char prefix[1024]{}, notice[128]{}, lines[40][96]{}, text[2305]{};
  int deferred = -1;
  bool submit_pending = false;
  bool show_trace_after = false, follow_cursor = false;
  unsigned caret_row = 0;
  unsigned source_id = 0, source_offset = 0, source_shown = 0;
  char source_page[513]{};
  char model_tag[65]{};
  std::uint32_t heap_peak = 0, heap_capacity = 0, stack_peak = 0,
                service_gap = 0, last_service = 0;
  std::uint64_t psram_reads = 0, psram_writes = 0;
  std::uintptr_t stack_fill_end = 0;
  bool benchmarking = false, computing = false, freeze_screen = true;
  bool compute_polled = false;
  bool legacy_painted = false;
  std::uint32_t compute_poll_stamp = 0;
  bool dual_core = true, filter_head = false, double_buffer = true;
  bool m3_core = false;
  char m3_module_path[128] = "/AI/M3LINE.S3M";
  unsigned freeze_count = 0, thaw_count = 0, freeze_violations = 0, frozen_revision = 0;
  LinearKernel linear_kernel = LinearKernel::SRAM;
  std::uint32_t cancel_observed = 0, cancel_return_us = 0;
  std::uint32_t model_load_us = 0;
  Arithmetic arithmetic = Arithmetic::INT8;
  ai_clock::State fast_clock;
  char pending_result[768]{};
  void profile_stage(const char *phase) {
    if(benchmarking || !s.id)return;
    sample_memory();
    char path[64],line[192];
    std::snprintf(path,sizeof(path),"/AI/SESSIONS/%08lu.PRF",(unsigned long)s.id);
    const int n=std::snprintf(line,sizeof(line),
      "AI_CHAT_STAGE phase=%s model_bytes=%u elapsed_ms=%llu hz=%lu heap_peak=%lu stack_peak=%lu\r\n",
      phase,model_loaded,(unsigned long long)request_ms,(unsigned long)ai_clock::hz(),
      (unsigned long)heap_peak,(unsigned long)stack_peak);
    if(n>0 && unsigned(n)<sizeof(line)) {
      files::write(path,reinterpret_cast<const u8*>(line),unsigned(n));
      debug_write(line,unsigned(n));
    }
  }
  bool debug_write(const char *text, unsigned size) {
    // NativeHost accepts at most128 bytes per call, including a long
    // profiler line. Keep one logical line while respecting that boundary.
    for(unsigned at=0;at<size;) {
      const unsigned take=std::min(128U,size-at);
      if(!call(MK61_SERVICE_DEBUG_WRITE,take,0,0,const_cast<char*>(text+at)))return false;
      at+=take;
    }
    return true;
  }
  void announce_result() {
    if(!pending_result[0]) return;
#if defined(PICO_ON_DEVICE)
    if(!stdio_usb_connected()) return;
#endif
    if(debug_write(pending_result,unsigned(std::strlen(pending_result))))pending_result[0]=0;
  }
  bool enter_fast_clock() {
    if(benchmarking || fast_clock.changed) return true;
#if !defined(PICO_ON_DEVICE)
    if(!ai_clock::hz()) return true;
#endif
    fast_clock={};
    profile_stage("clock-enter");
    // Long requests retain input on the PicoCalc keyboard and save their
    // complete profiler to SD. Re-enumerate CDC after returning to125MHz,
    // rather than exposing a fresh USB controller during the long compute.
    if(ai_clock::begin(270,fast_clock,true)) {
      profile_stage("clock-ready");
      char text[96];const int n=std::snprintf(text,sizeof(text),
          "AI_CHAT_FAST hz=%lu arithmetic=%u session=%lu\r\n",
          (unsigned long)ai_clock::hz(),unsigned(arithmetic),(unsigned long)s.id);
      call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,text);
      return true;
    }
    leave_fast_clock();message(M8("Не удалось включить270 МГц."));return false;
  }
  void leave_fast_clock() {
    if(!fast_clock.changed) return;
    profile_stage("clock-restore");
    if(!ai_clock::restore(fast_clock)) message(M8("Ошибка возврата частоты."));
    profile_stage("clock-restored");
    char text[64];const int n=std::snprintf(text,sizeof(text),
        "AI_CHAT_CLOCK restored=%lu\r\n",(unsigned long)ai_clock::hz());
    call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,text);
  }
  Trace manual_trace[16]{};
  chat::History history;
  chat::Renderer chat_renderer;
  chat::View chat_view;
  Agent::Metrics metric_baseline{};
  std::uint64_t request_ms = 0;
  std::uint64_t profile_attention_us=0,profile_attention_io_us=0,profile_attention_jobs=0;
  std::uint64_t profile_read_us=0,profile_matmul_us=0,profile_wait_us=0;
  unsigned profile_steps=0;
  std::uint32_t request_stamp = 0;
  bool request_measured = false, request_running = false, chat_graphics = false;
  void time_request(bool running) {
    const auto now = host.api->millis_ms();
    if (request_running) request_ms += std::uint32_t(now - request_stamp);
    request_stamp = now;
    request_running = running;
  }
  void begin_request() {
    metric_baseline = agent.metrics();
    request_ms = 0;
    profile_attention_us=profile_attention_io_us=profile_attention_jobs=0;
    profile_read_us=profile_matmul_us=profile_wait_us=0;profile_steps=0;
    request_measured = true;
    request_running = false;
    time_request(true);
  }
  void sync_chat(bool save = false) {
    if (!history.sync(store, s)) message(M8("Не удалось прочитать историю."));
    chat::Telemetry telemetry;
    if (request_measured) telemetry = chat::difference(agent.metrics(), metric_baseline, request_ms);
    history.observe(s, telemetry, agent.last_result(), agent.last_angle());
    if (save && !history.save(store, s, telemetry, agent.last_result(), agent.last_angle())) message(M8("Не удалось сохранить историю."));
  }
  void latest_chat() {
    if (!history.at_latest()) history.latest(store, s);
    chat_view.follow = true;
  }
  void angle_for_run() {
    const auto angle = call(MK61_SERVICE_SETTINGS, MK61_SERVICE_ANGLE);
    agent.default_angle(angle == DEGREE || angle == DEGREE_ERASE ? 0U : angle == GRADE ? 2U : 1U);
  }
  void end_chat_graphics() {
    if (!chat_graphics) return;
    call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_END);
    host.api->graphics_end();
    chat_graphics = false;
  }
  const char *phase_name() const {
    if (loading)
      return M8("Загружаю модель");
    if (benchmarking)
      return M8("Измеряю скорость");
    switch (agent.phase()) {
    case Agent::Phase::PREFILL:
      return M8("Читаю условие");
    case Agent::Phase::DECODE:
    case Agent::Phase::ADVANCE:
    case Agent::Phase::HEADER:
      return M8("Пишу ответ");
    case Agent::Phase::TESTS:
      return M8("Проверяю");
    case Agent::Phase::TRACE:
      return M8("Трассирую");
    default:
      break;
    }
    switch (s.state) {
    case RunState::DRAFT:
      return M8("Готов к запуску");
    case RunState::NEEDS_INPUT:
      return M8("Нужен ответ");
    case RunState::PAUSED:
      return M8("Пауза");
    case RunState::LIMIT:
      return M8("Лимит попыток");
    case RunState::ERROR:
      return M8("Ошибка");
    case RunState::FINISHED:
      return !s.program.size && s.intent != Intent::EXPLAIN
                 ? M8("Ответ не получен")
                 : M8("Попытка завершена");
    default:
      return M8("Готов");
    }
  }
  std::uint32_t presentation_phase() const {
    const auto phase=agent.phase()==Agent::Phase::ADVANCE?Agent::Phase::DECODE:agent.phase();
    return (unsigned(screen)<<16) | (unsigned(s.view)<<12) |
        (loading?0x800U:benchmarking?0x400U:unsigned(phase));
  }
  bool draw_due(std::uint32_t now) const {
    return (!loading && !benchmarking && !agent.active()) ||
        presentation.due(now,presentation_phase(),loading?1000U:2000U);
  }
  u32 call(u32 op, u32 a = 0, u32 b = 0, u32 c = 0, void *p = nullptr) {
    return host.services->call(op, a, b, c, p);
  }
  u32 display(u32 op, u32 b = 0, u32 c = 0, void *p = nullptr) {
    return call(MK61_SERVICE_DISPLAY, op, b, c, p);
  }
  void row(unsigned index, const char *value, char marker = 0) {
    display(MK61_SERVICE_DISPLAY_UI_LINE, index, u8(marker),
            const_cast<char *>(value));
  }
  void message(const char *value) {
    std::snprintf(notice, sizeof(notice), "%s", value);
    dirty = true;
  }
  void message_utf8(const char *value) {
    m8(value, notice, sizeof(notice));
    dirty = true;
  }
  bool checkpoint() {
    save_pending = false;
    if (!s.id)
      return true;
    if (save_session(store, s))
      return true;
    message(M8("Ошибка SD: задача не сохранена"));
    return false;
  }
  void changed() {
    save_pending = true;
    last_edit = host.api->millis_ms();
    dirty = true;
  }
  void line(const char *format, ...) {
    if (line_count == line_limit)
      return;
    const unsigned at = line_count++;
    if (at < render_start || at - render_start >= 40)
      return;
    va_list args;
    va_start(args, format);
    std::vsnprintf(lines[at - render_start], 96, format, args);
    va_end(args);
  }
  unsigned measure(const char *value) {
    return display(MK61_SERVICE_DISPLAY_MEASURE_UI_TEXT, 0, 0,
                   const_cast<char *>(value));
  }
  unsigned wrap_m8(const char *value, int caret = -1) {
    const char *start = value;
    while (*value && line_count < line_limit) {
      if (*value == '\n' || *value == '\r') {
        if (*value == '\n')
          line("");
        ++value;
        continue;
      }
      char buffer[96];
      unsigned n = 0, space = 0;
      while (value[n] && value[n] != '\n' && value[n] != '\r' && n < 94) {
        buffer[n] = value[n];
        buffer[n + 1] = 0;
        if (measure(buffer) > width)
          break;
        if (value[n] == ' ')
          space = n;
        ++n;
      }
      if (!n)
        n = 1;
      if (value[n] && value[n] != '\n' && value[n] != '\r' && space)
        n = space;
      if (caret >= 0 && unsigned(caret) >= unsigned(value - start) &&
          unsigned(caret) < unsigned(value - start) + n)
        caret_row = line_count;
      std::memcpy(buffer, value, n);
      buffer[n] = 0;
      line("%s", buffer);
      value += n;
      while (*value == ' ')
        ++value;
      if (*value == '\r')
        ++value;
      if (*value == '\n')
        ++value;
    }
    return unsigned(value - start);
  }
  void wrap(const char *value) {
    m8(value, text, sizeof(text));
    wrap_m8(text);
  }
  static bool package_read(void *context, std::uint32_t at, void *out,
                           unsigned n) {
    auto &u = *static_cast<UI *>(context);
    if (u.loading && (++u.reads & 63U) == 0 && !u.pump())
      return false;
    u.psram_reads += n;
    return u.package.read(at, out, n);
  }
  static bool cache_read(void *p, std::uint32_t at, void *out, unsigned n) {
    auto &u = *static_cast<UI *>(p);
    u.psram_reads += n;
    return u.cache.read(at, out, n);
  }
  static bool package_read_begin(void *p, const block_io::ReadSpan *spans, unsigned count) {
    auto &u = *static_cast<UI *>(p);
    if (!u.package.read_begin(spans, count)) return false;
    for (unsigned i = 0; i < count; ++i) u.psram_reads += spans[i].bytes;
    return true;
  }
  static bool package_read_finish(void *p) {
    return static_cast<UI *>(p)->package.read_finish();
  }
  static bool cache_read_begin(void *p,const block_io::ReadSpan *spans,unsigned count) {
    auto &u=*static_cast<UI*>(p);
    if(!u.cache.read_begin(spans,count)) return false;
    for(unsigned i=0;i<count;++i) u.psram_reads+=spans[i].bytes;
    return true;
  }
  static bool cache_read_finish(void *p) { return static_cast<UI*>(p)->cache.read_finish(); }
  static bool cache_write(void *p, std::uint32_t at, const void *out,
                          unsigned n) {
    auto &u = *static_cast<UI *>(p);
    u.psram_writes += n;
    return u.cache.write(at, out, n);
  }
  void configure_execution() {
    ComputeExecution e{};
    e.context = this;e.kernel = linear_kernel;e.filter_head = filter_head;
    e.tile_rows = benchmarking && m3_core ? 64 : 28;
    e.prefetch = double_buffer;
    e.micros = [](void *p) {
      return static_cast<UI *>(p)->call(MK61_SERVICE_MICROS);
    };
    e.busy = [](void *raw, bool active) {
      auto &u = *static_cast<UI *>(raw);
      if (active && u.freeze_screen) {
        if (u.dirty && u.draw_due(u.host.api->millis_ms())) u.draw();
        if (u.host.render) u.host.render(false);
        ++u.freeze_count;
        if (u.host.revision) u.frozen_revision = u.host.revision();
      }
      u.computing = active;
      if (active) u.compute_polled = false;
      if (!active && u.freeze_screen) {
        if (u.host.revision && u.host.revision() != u.frozen_revision) ++u.freeze_violations;
        if (u.host.render) u.host.render(true);
        ++u.thaw_count;
      }
    };
#if defined(PICO_ON_DEVICE)
    if (dual_core) {
      e.submit = [](void *, void (*function)(void *), void *job) {
        return io_worker::submit_compute(job, function);
      };
      e.join = [](void *) { io_worker::join_compute(); };
    }
#endif
    if (m3_core && (arithmetic == Arithmetic::LUT_FLOAT32 || arithmetic == Arithmetic::INT8) &&
        linear_kernel != LinearKernel::REFERENCE && ai_m3::open(m3_module_path)) {
      e.remote_prepare = [](void *, const LinearBatch *b) { return ai_m3::prepare(b); };
      e.remote_submit = [](void *, LinearBatch *b) { return ai_m3::submit(b); };
      e.remote_join = [](void *) { return ai_m3::join(); };
    } else ai_m3::close();
    model.execution(e);
  }
  static bool service(void *p) { return static_cast<UI *>(p)->pump(); }
  bool pump();
  void key(unsigned key);
  void act(Action action);
  void submit();
  void draw();
  bool ensure_model();
  void start();
  bool new_session(Intent intent = Intent::WRITE);
  void scan_sessions();
  u32 unused_id();
  void open_form(unsigned kind, const char *value = nullptr,
                 unsigned index = 0);
  void open_binary();
  void body();
  unsigned menu_count() const;
  void menu_label(unsigned index, char out[96]);
  void tick();
  unsigned run();
  unsigned bench();
  unsigned perf(const char *directory,const PerfConfig &config);
  unsigned long_perf(const char *directory);
  void sample_memory();
  void begin_measurements();
  bool write_metrics(const char *path);
};

void UI::begin_measurements() {
#if defined(PICO_ON_DEVICE)
  heap_capacity = std::uint32_t(reinterpret_cast<std::uintptr_t>(&__HeapLimit) -
                                reinterpret_cast<std::uintptr_t>(&__end__));
  std::uintptr_t sp = 0;
  __asm volatile("mov %0, sp" : "=r"(sp));
  const auto bottom = reinterpret_cast<std::uintptr_t>(&__StackBottom),
             top = reinterpret_cast<std::uintptr_t>(&__StackTop);
  if (sp > bottom + 1024 && sp <= top) {
    stack_fill_end = (sp - 1024) & ~std::uintptr_t(3);
    const auto irq = save_and_disable_interrupts();
    for (auto p = bottom; p < stack_fill_end; p += 4)
      *reinterpret_cast<volatile std::uint32_t *>(p) = 0xA17A0BCAU;
    restore_interrupts(irq);
  }
#endif
  allocation_observer([](void *p) { static_cast<UI *>(p)->sample_memory(); },
                      this);
  sample_memory();
}
void UI::sample_memory() {
#if defined(PICO_ON_DEVICE)
  const auto heap = mallinfo();
  heap_peak = std::max(heap_peak, std::uint32_t(heap.uordblks));
  if (stack_fill_end) {
    auto p = reinterpret_cast<std::uintptr_t>(&__StackBottom);
    while (p < stack_fill_end &&
           *reinterpret_cast<volatile std::uint32_t *>(p) == 0xA17A0BCAU)
      p += 4;
    stack_peak = std::max(
        stack_peak,
        std::uint32_t(reinterpret_cast<std::uintptr_t>(&__StackTop) - p));
  }
#endif
}
bool UI::write_metrics(const char *path) {
  sample_memory();
  const auto &m = agent.metrics();
  char json[1024];
  const auto buffers = shared_memory::buffer_statistics();
  const int n = std::snprintf(
      json, sizeof(json),
      "{\"schema\":2,\"device\":%s,\"prefill_tokens\":%lu,\"prefill_us\":%llu,"
      "\"decode_tokens\":%lu,\"output_tokens\":%lu,\"decode_us\":%llu,\"reused_tokens\":%lu,\"tool_"
      "us\":%llu,\"max_tick_us\":%lu,\"service_gap_us\":%lu,\"heap_capacity\":%"
      "lu,\"sampled_heap_peak\":%lu,\"stack_high_water\":%lu,\"psram_used\":%"
      "lu,\"psram_read_bytes\":%llu,\"psram_write_bytes\":%llu,\"model_load_"
      "us\":%lu}\n",
      heap_capacity ? "true" : "false", (unsigned long)m.prefill_tokens,
      (unsigned long long)m.prefill_us, (unsigned long)m.decode_tokens, (unsigned long)m.output_tokens,
      (unsigned long long)m.decode_us, (unsigned long)m.reused_tokens,
      (unsigned long long)m.tool_us, (unsigned long)m.max_tick_us,
      (unsigned long)service_gap, (unsigned long)heap_capacity,
      (unsigned long)heap_peak, (unsigned long)stack_peak,
      (unsigned long)buffers.external_used, (unsigned long long)psram_reads,
      (unsigned long long)psram_writes, (unsigned long)model_load_us);
  return n > 0 && unsigned(n) < sizeof(json) &&
         files::write(path, reinterpret_cast<const u8 *>(json), unsigned(n));
}

AI_COLD_CODE void UI::scan_sessions() {
  session_count = 0;
  unsigned skip = 0;
  bool more = true;
  files::Entry entries[8];
  while (more) {
    unsigned used = 0;
    if (!files::list("/AI/SESSIONS", skip, entries, 8, used, more, ".AIS"))
      break;
    skip += used;
    for (unsigned i = 0; i < used; ++i) {
      if (entries[i].directory)
        continue;
      char *end = nullptr;
      const unsigned long id = std::strtoul(entries[i].name, &end, 10);
      if (!id || !end || std::strcmp(end, ".AIS"))
        continue;
      if (session_count < 16)
        sessions[session_count++] = u32(id);
      else if (id > sessions[15])
        sessions[15] = u32(id);
      std::sort(sessions, sessions + session_count,
                [](u32 a, u32 b) { return a > b; });
    }
    if (!used)
      break;
  }
}
u32 UI::unused_id() {
  scan_sessions();
  u32 id = 0;
  return reserve_session_id(store, session_count ? sessions[0] : 0, id) ? id
                                                                        : 0;
}
bool UI::new_session(Intent intent) {
  if (!checkpoint())
    return false;
  std::unique_ptr<Session> next(new (std::nothrow) Session);
  if (!next) {
    message(M8("Недостаточно памяти для задачи"));
    return false;
  }
  next->id = unused_id();
  next->intent = intent;
  if (!next->id || !save_session(store, *next)) {
    message(M8("Не удалось создать задачу на SD"));
    return false;
  }
  agent.reset();
  s = *next;
  request_measured = request_running = false;
  chat_view = {};
  selected = selected_test = 0;
  std::fill(scroll, scroll + 4, 0);
  screen = Screen::SESSION;
  typing = true;
  notice[0] = 0;
  dirty = true;
  return true;
}
void UI::open_form(unsigned kind, const char *value, unsigned index) {
  if (s.form_kind != kind || s.form_index != index) {
    if (value)
      std::snprintf(s.form, sizeof(s.form), "%s", value);
    else
      s.form[0] = 0;
  }
  s.form_kind = u8(kind);
  s.form_index = u8(index);
  cursor = unsigned(std::strlen(s.form));
  screen = Screen::FORM;
  typing = true;
  follow_cursor = true;
  russian = kind == 1;
  changed();
}
AI_COLD_CODE bool UI::ensure_model() {
  if (model_ready) {
    std::snprintf(s.model, sizeof(s.model), "%s", model_tag);
    return true;
  }
  files::Entry info{};
  char diagnostic_model[128];const char *model_path="/AI/MODEL.MKA";
  if(benchmarking && host.diagnostic_directory) {
    std::snprintf(diagnostic_model,sizeof(diagnostic_model),"%s/MODEL.MKA",host.diagnostic_directory);
    if(files::exists(diagnostic_model)) model_path=diagnostic_model;
  }
  if (!files::stat(model_path, info) || info.directory) {
    message(M8("Нет /AI/MODEL.MKA. Установи пакет модели."));
    return false;
  }
  package.reset();
  cache.reset();
  workspace.reset();
  const auto load_started = call(MK61_SERVICE_MICROS);
  cancel = false;
  loading = true;
  model_loaded = 0;
  reads = 0;
  dirty = true;
  bool ok = package.acquire(shared_memory::Owner::APPLICATION, info.size,
                            shared_memory::BufferAccess::EXTERNAL_ONLY);
  profile_stage("load-start");
  // Keep the proven1KiB I/O/stack bound, servicing input/display every8KiB.
  // This reduces UI/FAT cursor churn without increasing transfer buffers.
  alignas(4) u8 block[1024];
  auto read_package = [&]() {
    model_loaded = 0;
    while (ok && model_loaded < info.size) {
      unsigned n = 0;
      const unsigned take =
          std::min<unsigned>(unsigned(sizeof(block)), info.size - model_loaded);
      ok = files::read_range(model_path, model_loaded, block, take, n) &&
           n == take && package.write(model_loaded, block, n);
      model_loaded += ok ? n : 0;
      dirty = true;
      if(ok && (!(model_loaded&131071U) || model_loaded==info.size))profile_stage("load-data");
      if (ok && (!(model_loaded&8191U) || model_loaded==info.size) && !pump()) {
        ok = false;
        break;
      }
    }
  };
  read_package();
  profile_stage("model-open");
  ModelStatus status = ModelStatus::MEMORY;
  if (ok) {
    status = model.open({this, info.size, package_read, nullptr,
                         package_read_begin, package_read_finish});
    ok = status == ModelStatus::OK;
  }
  if (ok) {
    profile_stage("cache-allocate");
    const auto cache_bytes=model.cache_bytes();
    ok = cache.acquire(shared_memory::Owner::APPLICATION, cache_bytes,
                       shared_memory::BufferAccess::EXTERNAL_ONLY);
    if(!ok && package.reset()) {
      // A retained optional cache can place the package in the middle of
      // PSRAM. After eviction, reserve the larger KV buffer first so both
      // required allocations fit. Sizes come from the validated package.
      ok=cache.acquire(shared_memory::Owner::APPLICATION,cache_bytes,
                       shared_memory::BufferAccess::EXTERNAL_ONLY) &&
         package.acquire(shared_memory::Owner::APPLICATION,info.size,
                         shared_memory::BufferAccess::EXTERNAL_ONLY);
      read_package();
      if(ok) {
        status=model.open({this,info.size,package_read,nullptr,
                           package_read_begin,package_read_finish});
        ok=status==ModelStatus::OK && model.cache_bytes()==cache_bytes;
      }
    }
    if (ok) {
      profile_stage("workspace-allocate");
      workspace.reset(new (std::nothrow)
                          std::uint64_t[(model.workspace_bytes() + 7) / 8]);
      ok = bool(workspace);
    }
    if (ok) {
      profile_stage("workspace-bind");
      status = model.bind(workspace.get(), model.workspace_bytes(),
                          {this, u32(cache.size()), cache_read, cache_write,cache_read_begin,cache_read_finish});
      ok = status == ModelStatus::OK;
    }
  }
  loading = false;
  model_load_us = call(MK61_SERVICE_MICROS) - load_started;
  if (benchmarking) {
    char marker[96];
    const int n = std::snprintf(marker, sizeof(marker),
                                "AI_LOAD bytes=%u us=%lu ok=%u\r\n", info.size,
                                (unsigned long)model_load_us, unsigned(ok));
    call(MK61_SERVICE_DEBUG_WRITE, unsigned(n), 0, 0, marker);
  }
  dirty = true;
  if (!ok) {
    profile_stage("load-failed");
    s.state = cancel ? RunState::PAUSED : RunState::ERROR;
    message(cancel ? M8("Загрузка приостановлена")
                   : M8("Не удалось загрузить модель: память или формат"));
    package.reset();
    cache.reset();
    workspace.reset();
    return false;
  }
  u32 crc = 0;
  package.read(124, &crc, 4);
  std::snprintf(model_tag, sizeof(model_tag), "MKA-%08lX-%lu",
                (unsigned long)crc, (unsigned long)info.size);
  std::snprintf(s.model, sizeof(s.model), "%s", model_tag);
  unsigned n = 0;
  prefix[0] = 0;
  if (files::exists("/AI/PROMPT.TXT")) {
    files::Entry e{};
    if (!files::stat("/AI/PROMPT.TXT", e) || e.size >= sizeof(prefix) ||
        !files::read("/AI/PROMPT.TXT", reinterpret_cast<u8 *>(prefix),
                     sizeof(prefix) - 1, n) ||
        std::memchr(prefix, 0, n)) {
      message(M8("Некорректный /AI/PROMPT.TXT"));
      return false;
    }
    prefix[n] = 0;
  }
  model_ready = true;
  profile_stage("model-ready");
  char protocol[16]{}; unsigned protocol_size=0;
  char protocol_path[128];
  std::snprintf(protocol_path,sizeof(protocol_path),"/AI/MODEL.PRO");
  if(benchmarking && host.diagnostic_directory && model_path==diagnostic_model)
    std::snprintf(protocol_path,sizeof(protocol_path),"%s/MODEL.PRO",host.diagnostic_directory);
  const bool spec_model=files::exists(protocol_path);
  if(spec_model && (!files::read(protocol_path,reinterpret_cast<u8*>(protocol),sizeof(protocol)-1,protocol_size) ||
      std::strcmp(protocol,"MK61SPEC1\n") || model.config().vocab!=8224 || model.config().context!=1024)) {
    model_ready=false; message(M8("Не совпадает формат модели MODEL.PRO.")); return false;
  }
  agent.spec_protocol(spec_model);
  if(spec_model) { arithmetic=Arithmetic::INT8; filter_head=true; }
  return true;
}
void UI::start() {
  if (agent.active() || loading) {
    cancel = true;
    agent.request_pause();
    return;
  }
  if (!s.id) {
    if (new_session())
      open_form(1);
    return;
  }
  if (agent.paused()) {
    cancel = false;
    if(!enter_fast_clock()) return;
    started = host.api->millis_ms();
    agent.start();
    if(!agent.active()) leave_fast_clock();
    time_request(agent.active());
    screen = Screen::SESSION;
    s.view = 0;
    typing = false;
    changed();
    return;
  }
  if (s.state == RunState::NEEDS_INPUT) {
    s.view = 0;
    screen = Screen::SESSION;
    typing = true;
    cursor = unsigned(std::strlen(s.draft));
    dirty = true;
    return;
  }
  begin_request();
  angle_for_run();
  if (!ensure_model()) {
    time_request(false);
    sync_chat(true);
    return;
  }
  cancel = false;
  started = host.api->millis_ms();
  if(!enter_fast_clock()) { time_request(false);return; }
  configure_execution();
  agent.arithmetic(arithmetic);
  agent.start(prefix[0] ? prefix : nullptr);
  if(!agent.active()) leave_fast_clock();
  time_request(agent.active());
  screen = Screen::SESSION;
  s.view = 0;
  latest_chat();
  typing = false;
  changed();
}
unsigned UI::menu_count() const {
  switch (screen) {
  case Screen::HOME:
    return 4 + session_count;
  case Screen::MENU:
    return 19;
  case Screen::VERSIONS:
    return std::min(9999U, unsigned(s.last_version));
  case Screen::INTENT:
    return 3;
  case Screen::SETTINGS:
    return 7;
  case Screen::APPLY:
    return 2;
  default:
    return 0;
  }
}
void UI::menu_label(unsigned i, char out[96]) {
  out[0] = 0;
  if (screen == Screen::HOME) {
    static const char *const labels[] = {
        M8("Новая задача"), M8("Открыть программу"), M8("Текущая программа"),
        M8("Открыть задачу по номеру")};
    if (i < 4)
      std::snprintf(out, 96, "%s", labels[i]);
    else
      std::snprintf(out, 96, M8("Продолжить #%lu"),
                    (unsigned long)sessions[i - 4]);
    return;
  }
  if (screen == Screen::MENU) {
    static const char *const labels[] = {M8("Уточнить условие"),
                                         M8("Добавить пример"),
                                         M8("Выполнить тесты"),
                                         M8("Править программу"),
                                         M8("История версий"),
                                         M8("Сохранить программу"),
                                         M8("В калькулятор"),
                                         M8("Входы примера в калькулятор"),
                                         M8("Трасса примера"),
                                         M8("Журнал действий"),
                                         M8("Параметры"),
                                         M8("Режим задачи"),
                                         M8("Приложить фрагмент текста"),
                                         M8("Список задач"),
                                         M8("Выйти"),
                                         M8("Контрольные примеры"),
                                         M8("Счётчики: раскрыть / свернуть"),
                                         M8("Код: раскрыть / свернуть"),
                                         M8("Сохранить замеры в JSON")};
    std::snprintf(out, 96, "%s", labels[i]);
    return;
  }
  if (screen == Screen::VERSIONS) {
    std::snprintf(out, 96, M8("Версия v%lu"),
                  (unsigned long)(s.last_version - i));
    return;
  }
  if (screen == Screen::INTENT) {
    static const char *const names[] = {M8("Написать программу"),
                                        M8("Исправить программу"),
                                        M8("Объяснить программу")};
    std::snprintf(out, 96, "%s", names[i]);
    return;
  }
  if (screen == Screen::SETTINGS) {
    switch (i) {
    case 0:
      std::snprintf(out, 96, M8("Лимит попыток: %u"),
                    unsigned(s.attempt_limit));
      break;
    case 1: {
      static const char *const names[] = {"FP32 reference", "INT8", "LUT INT8",
                                          "LUT FP32"};
      std::snprintf(out, 96, M8("Математика: %s"), names[unsigned(arithmetic)]);
      break;
    }
    case 2:
      std::snprintf(out, 96, "KV: %lu; work: %lu",
                    (unsigned long)model.cache_bytes(),
                    (unsigned long)model.workspace_bytes());
      break;
    case 3:
      std::snprintf(out, 96, "%s", M8("Память программы: 105 команд"));
      break;
    case 4:
      std::snprintf(out, 96, "%s",
                    s.planning ? M8("Краткий план: включён")
                               : M8("Краткий план: выключен"));
      break;
    case 5:
      std::snprintf(out, 96, "%s", m3_core ? M8("Ядра: 2 Pico + STM32") : M8("Ядра: 2 Pico"));
      break;
    case 6:
      std::snprintf(out, 96, "%s", M8("Назад"));
      break;
    }
    return;
  }
  if (screen == Screen::APPLY)
    std::snprintf(out, 96, "%s", i ? M8("Назад") : M8("Загрузить программу"));
}
void UI::body() {
  line_count = 0;
  line_limit = 128;
  if (screen == Screen::FORM) {
    static const char *const titles[] = {"",
                                         M8("Условие задачи"),
                                         M8("Пример: R0=7 R1=5 => X=12"),
                                         M8("Код: HEX через пробел"),
                                         M8("Имя .bin в /AI/Exports"),
                                         M8("Лимит попыток: число 1..64"),
                                         M8("Номер сохранённой задачи")};
    line("%s", titles[s.form_kind]);
    if (s.form_kind == 2) {
      line("X=?; ATOL=2e-6; RTOL=2e-6");
      line("ANGLE=RAD; STEPS=256");
    }
    char visible[sizeof(s.form) + 1];
    const unsigned n = unsigned(std::strlen(s.form)), at = std::min(cursor, n);
    std::memcpy(visible, s.form, at);
    visible[at] = '|';
    std::memcpy(visible + at + 1, s.form + at, n - at + 1);
    wrap_m8(visible, int(at));
    return;
  }
  if (screen == Screen::CASE) {
    if (selected_test >= s.test_count)
      return;
    const auto &e = s.tests[selected_test];
    line(M8("Пример %u | v%lu"), selected_test + 1,
         (unsigned long)s.program.version);
    for (unsigned j = 0; j < INPUT_COUNT; ++j)
      if (e.inputs & (1U << j)) {
        if (j < 15)
          line("R%X = %.8g", j, e.values[j]);
        else
          line("%c = %.8g", "XYZT"[j - 15], e.values[j]);
      }
    const auto mask = expectation_mask(e);
    for (unsigned j = 0; j < INPUT_COUNT; ++j)
      if (mask & (1U << j)) {
        if (j < 15)
          line(M8("Ожидается R%X = %.8g"), j, expected_value(e, j));
        else
          line(M8("Ожидается %c = %.8g"), "XYZT"[j - 15], expected_value(e, j));
      }
    if (!has_expectations(e))
      line(M8("Ожидаемый ответ не задан"));
    for (unsigned j = 0; j < INPUT_COUNT; ++j)
      if (e.preserve & (1U << j)) {
        if (j < 15)
          line(M8("Сохранить R%X"), j);
        else
          line(M8("Сохранить %c"), "XYZT"[j - 15]);
      }
    if (!e.public_case)
      line(M8("Данные скрыты от модели"));
    if (result_current(s, selected_test)) {
      const auto &r = s.results[selected_test];
      line(M8("Получено X = %.8g"), r.x);
      line("status=%u; PC=%u; steps=%lu", unsigned(r.status), unsigned(r.pc),
           (unsigned long)r.commands);
    }
    for (unsigned j = 0; j < e.scenario_count; ++j) {
      const auto &a = e.scenario[j];
      line(M8("Остановка %u: KEY=%02X"), j + 2, unsigned(a.key));
      if (a.output_index != 255)
        line(M8("Ожидалось %.8g; получено %.8g"), a.expected,
             s.results[selected_test].stage_values[j]);
    }
    line("ATOL=%.3g RTOL=%.3g", e.absolute, e.relative);
    line("ANGLE=%s STEPS=%u FRAMES=%u",
         e.angle == 0   ? "DEG"
         : e.angle == 2 ? "GRAD"
                        : "RAD",
         unsigned(e.max_commands), unsigned(e.max_frames));
    line(M8("Enter: править | Tab: действия"));
    return;
  }
  if (screen == Screen::TRACE) {
    line(M8("Трасса v%lu"), (unsigned long)s.program.version);
    for (unsigned i = 0; i < agent.trace_count(); ++i) {
      const auto &t = agent.trace()[i];
      line("%02u  %02X  X=%.8g", unsigned(t.pc), unsigned(t.opcode), t.x);
    }
    if (!agent.trace_count())
      line(M8("Команд в трассе нет"));
    return;
  }
  if (screen == Screen::LOG) {
    char path[96];
    std::snprintf(path, sizeof(path), "/AI/SESSIONS/%08lu-%08lu.TXT",
                  (unsigned long)s.id,
                  (unsigned long)std::max<unsigned>(1U, s.event - selected));
    unsigned n = 0;
    if (store_read(nullptr, path, text, sizeof(text) - 1, n)) {
      text[n] = 0;
      char copy[2305];
      std::memcpy(copy, text, n + 1);
      wrap(copy);
    } else
      line(M8("Запись журнала недоступна"));
    return;
  }
  if (screen == Screen::ATTACH) {
    unsigned n = 0;
    if (!host.api->file_read ||
        (n = host.api->file_read(source_id, source_offset,
                                 reinterpret_cast<u8 *>(source_page), 512)) >
            512) {
      line(M8("Не удалось прочитать текст"));
      source_shown = 0;
      return;
    }
    source_page[n] = 0;
    line_limit = rows > 5 ? rows - 5 : 1;
    source_shown = wrap_m8(source_page);
    line_limit = 128;
    return;
  }
  if (screen == Screen::APPLY) {
    line(M8("В калькулятор | v%lu"), (unsigned long)s.program.version);
    line(M8("%u команд; примеры %u/%u"), unsigned(s.program.size),
         passed_examples(s), unsigned(s.test_count));
    line(M8("Предыдущая программа сохранится."));
    line(M8("Регистры останутся прежними."));
    line("");
    for (unsigned i = 0; i < 2; ++i) {
      char label[96];
      menu_label(i, label);
      line("%c %s", i == selected ? '>' : ' ', label);
    }
    return;
  }
  if (screen != Screen::SESSION) {
    const unsigned count = menu_count(), visible = rows > 5 ? rows - 4 : 1,
                   first = selected >= visible ? selected - visible + 1 : 0;
    for (unsigned i = first; i < count && i < first + visible; ++i) {
      char label[96];
      menu_label(i, label);
      line("%c %s", i == selected ? '>' : ' ', label);
    }
    return;
  }
  if (s.view == 0) {
    line(M8("Вы:"));
    wrap(s.task[0] ? s.task : "Опиши, какую программу написать.");
    line("");
    line(M8("Помощник:"));
    if (s.state == RunState::FINISHED && s.intent == Intent::EXPLAIN &&
        s.reply[0] && s.reply[0] != '<')
      wrap(s.reply);
    else {
      if (s.plan[0])
        wrap(s.plan);
      if (s.feedback[0])
        wrap(s.feedback);
      else if (s.program.size)
        line(M8("Версия v%lu | %u команд"), (unsigned long)s.program.version,
             unsigned(s.program.size));
      else if (s.state == RunState::FINISHED) {
        line(M8("Модель завершила ответ без программы."));
        line(M8("Расчёт не выполнен. F5: повторить."));
      }
      else
        line(M8("Добавь примеры или нажми F5."));
    }
  } else if (s.view == 1) {
    line(M8("v%lu | %u/105 команд"), (unsigned long)s.program.version,
         unsigned(s.program.size));
    if (!s.program.size)
      line(M8("Программы пока нет."));
    for (unsigned i = 0; i < s.program.size; ++i) {
      char command[16];
      terminal_mnemonics::csv(isa, s.program.bytes[i], command);
      if (!command[0])
        terminal_mnemonics::hex(s.program.bytes[i], command);
      line("%03u  %-8s  %02X", i, command, s.program.bytes[i]);
    }
  } else if (s.view == 2) {
    if (!s.test_count) {
      line(M8("Контрольных примеров пока нет."));
      line(M8("Tab → Добавить пример"));
    }
    for (unsigned i = 0; i < s.test_count; ++i) {
      const auto &e = s.tests[i];
      const auto &r = s.results[i];
      line(M8("%c Пример %u%s"), i == selected_test ? '>' : ' ', i + 1,
           has_expectations(e) ? "" : " (?)");
      if (!result_current(s, i))
        line(M8("  Нужен новый прогон"));
      else if (!has_expectations(e))
        line(M8("  X=%.8g | наблюдение"), r.x);
      else if (r.passed)
        line(M8("  X=%.8g | совпало"), r.x);
      else
        line(M8("  Не совпало; Enter: подробности"));
    }
  } else {
    line("%s", phase_name());
    if (loading)
      line(M8("Прочитано %lu КБ"), (unsigned long)(model_loaded / 1024));
    else if (agent.phase() == Agent::Phase::PREFILL)
      line(M8("Контекст: %u/%u токенов"), model.position(),
           agent.prompt_size());
    else if (agent.phase() == Agent::Phase::TESTS)
      line(M8("Пример %u/%u"), agent.test_index() + 1,
           std::max(1U, unsigned(s.test_count)));
    else if (agent.active())
      line(M8("Ответ: %u/%u токенов"), agent.generated(),
           agent.generation_limit());
    if (agent.reused_prefix())
      line(M8("Повторно использовано: %u"), agent.reused_prefix());
    line(M8("Попытки: %u/%u"), unsigned(s.attempts), unsigned(s.attempt_limit));
    line(M8("Версия v%lu; примеры %u/%u"), (unsigned long)s.program.version,
         passed_examples(s), unsigned(s.test_count));
    if (agent.active())
      line(M8("Прошло %lu с"),
           (unsigned long)((host.api->millis_ms() - started) / 1000));
    if (s.plan[0]) {
      line(M8("План:"));
      wrap(s.plan);
    }
    if (s.feedback[0]) {
      line(M8("Последнее действие:"));
      wrap(s.feedback);
    }
  }
}
void UI::draw() {
  if (screen == Screen::SESSION && !benchmarking) {
    legacy_painted = false;
    sync_chat();
    if (!chat_graphics) {
      display(MK61_SERVICE_DISPLAY_END_UI_TEXT);
      chat_graphics = host.api->graphics_begin() != 0;
    }
    if (chat_graphics) {
      chat_view.history = &history;
      chat_view.draft = s.draft;
      chat_view.cursor = cursor;
      chat_view.typing = typing;
      chat_view.russian = russian;
      chat_view.active = agent.active();
      chat_view.paused = agent.paused();
      chat_view.loading = loading;
      chat_view.load_kb = model_loaded / 1024;
      chat_view.phase = phase_name();
      chat_view.live_reply = agent.active() ? s.reply : "";
      chat_view.notice = notice;
      chat_renderer.paint(*host.api, *host.services, chat_view, [](std::uint8_t byte, char *out) {
        terminal_mnemonics::csv(isa, byte, out);
        if (!out[0]) terminal_mnemonics::hex(byte, out);
      });
      dirty = false;
      last_draw = host.api->millis_ms();
      presentation.presented(last_draw,presentation_phase());
      return;
    }
  }
  end_chat_graphics();
  display(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT);
  display(MK61_SERVICE_DISPLAY_UI_COLORS, 0xE77E, 0x10C4);
  rows = std::max<unsigned>(4U, host.api->display_rows());
  width = display(MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH);
  if (!width)
    width = 304;
  display(MK61_SERVICE_DISPLAY_BEGIN_UPDATE);
  if(!legacy_painted) display(MK61_SERVICE_DISPLAY_CLEAR);
  char header[96];
  std::snprintf(header, sizeof(header), M8("МК-61 #%lu | %s"),
                (unsigned long)s.id, phase_name());
  row(0, header);
  static const char *const tabs[] = {M8("Диалог"), M8("Код"), M8("Тесты"),
                                     M8("Ход")};
  if (screen == Screen::SESSION) {
    std::snprintf(header, sizeof(header), "%s%s%s %s%s%s %s%s%s %s%s%s",
                  s.view == 0 ? "[" : "", tabs[0], s.view == 0 ? "]" : "",
                  s.view == 1 ? "[" : "", tabs[1], s.view == 1 ? "]" : "",
                  s.view == 2 ? "[" : "", tabs[2], s.view == 2 ? "]" : "",
                  s.view == 3 ? "[" : "", tabs[3], s.view == 3 ? "]" : "");
    if (measure(header) > width) {
      unsigned used = 0;
      const char *short_tabs = M8("ДКТХ");
      for (unsigned i = 0; i < 4; ++i)
        used += unsigned(std::snprintf(header + used, sizeof(header) - used,
                                       "%s%c%s%s", s.view == i ? "[" : "",
                                       short_tabs[i], s.view == i ? "]" : "",
                                       i < 3 ? " " : ""));
    }
    row(1, header);
  } else
    row(1, screen == Screen::HOME       ? M8("Задачи")
           : screen == Screen::MENU     ? M8("Действия")
           : screen == Screen::VERSIONS ? M8("История версий")
           : screen == Screen::INTENT   ? M8("Что сделать?")
           : screen == Screen::FORM     ? M8("Ввод")
           : screen == Screen::ATTACH   ? M8("Выбери видимый фрагмент")
                                        : M8("Просмотр"));
  unsigned count = std::min<unsigned>(40U, rows - 4);
  const bool composer = screen == Screen::SESSION && s.view == 0;
  if (composer && count > 2)
    count -= 2;
  unsigned offset = screen == Screen::SESSION ? scroll[s.view]
                    : screen == Screen::LOG || screen == Screen::TRACE ||
                            screen == Screen::CASE || screen == Screen::FORM
                        ? scroll[0]
                        : 0;
  render_start = offset;
  body();
  if (screen == Screen::FORM && follow_cursor) {
    if (caret_row < offset)
      offset = caret_row;
    else if (caret_row >= offset + count)
      offset = caret_row - count + 1;
    scroll[0] = offset;
    follow_cursor = false;
  }
  if (offset >= line_count)
    offset = line_count ? line_count - 1 : 0;
  if (offset != render_start) {
    render_start = offset;
    body();
  }
  for (unsigned r = 0; r < count; ++r)
    row(2 + r, offset + r < line_count ? lines[r] : "");
  if (composer) {
    row(rows - 4, russian ? M8("Ввод RU (F8):") : M8("Ввод EN (F8):"));
    char input[96];
    const unsigned n = unsigned(std::strlen(s.draft)), at = std::min(cursor, n),
                   start = at > 24 ? at - 24 : 0;
    unsigned used = 0;
    for (unsigned i = start; i < n && used < 88; ++i) {
      if (i == at && typing)
        input[used++] = '|';
      input[used++] = s.draft[i];
    }
    if (at == n && typing && used < 90)
      input[used++] = '|';
    input[used] = 0;
    row(rows - 3, input);
  }
  const char *keys =
      screen == Screen::SESSION
          ? (agent.active() ? M8("F5:пауза F6:ввод Tab:меню")
                            : M8("F5:решать F6:ввод Tab:меню"))
      : screen == Screen::FORM   ? M8("Enter:принять F8:RU/EN Esc:назад")
      : screen == Screen::ATTACH ? M8("Enter:приложить ↑↓:страницы")
                                 : M8("↑↓:выбор Enter:открыть Esc:назад");
  row(rows - 2, keys);
  row(rows - 1, notice[0] ? notice
                : screen == Screen::SESSION
                    ? M8("F1-F4:вкладки Esc:пауза/назад")
                    : "");
  display(MK61_SERVICE_DISPLAY_END_UPDATE);
  legacy_painted = true;
  display(MK61_SERVICE_DISPLAY_FLUSH);
  dirty = false;
  last_draw = host.api->millis_ms();
  presentation.presented(last_draw,presentation_phase());
}
void UI::open_binary() {
  mk61_service_choice choice{};
  choice.parent = MK61_SERVICE_ROOT_ID;
  if (!call(MK61_SERVICE_FILE_CHOOSE, MK61_SERVICE_FILE_MK61_BINARY, 0, 0,
            &choice)) {
    dirty = true;
    return;
  }
  const unsigned n = host.api->file_size(choice.file.id);
  u8 code[PROGRAM_SIZE];
  if (!n || n > PROGRAM_SIZE ||
      host.api->file_read(choice.file.id, 0, code, n) != n) {
    message(M8("Нужен BIN до 105 байт."));
    return;
  }
  if (!s.id && !new_session(Intent::FIX))
    return;
  agent.reset();
  if (!accept_program(store, s, code, n, true)) {
    message(M8("Не удалось сохранить исходную программу"));
    return;
  }
  s.view = 1;
  screen = Screen::SESSION;
  s.state = RunState::NEEDS_INPUT;
  std::snprintf(s.feedback, sizeof(s.feedback),
                "Что нужно исправить или объяснить?");
  checkpoint();
  dirty = true;
}
void UI::act(Action action) {
  if ((loading || agent.active()) && action != TOGGLE_METRICS && action != TOGGLE_CODE) {
    deferred = int(action);
    cancel = true;
    agent.request_pause();
    return;
  }
  notice[0] = 0;
  selected = 0;
  switch (action) {
  case NEW_TASK:
    new_session();
    break;
  case OPEN_BINARY:
    if (screen == Screen::HOME && !new_session(Intent::FIX))
      return;
    open_binary();
    break;
  case CURRENT: {
    if ((!s.id || screen == Screen::HOME) && !new_session(Intent::FIX))
      return;
    Program source{};
    if (!capture_program(source) ||
        !accept_program(store, s, source.bytes, source.size, true)) {
      message(M8("Останови калькулятор; нужен банк 0."));
      break;
    }
    agent.reset();
    s.view = 1;
    screen = Screen::SESSION;
    s.state = RunState::NEEDS_INPUT;
    std::snprintf(s.feedback, sizeof(s.feedback),
                  "Что нужно исправить или объяснить?");
    checkpoint();
    break;
  }
  case ADD_TEST:
    if (s.test_count == TEST_COUNT) {
      message(M8("Максимум 8 примеров в задаче."));
      break;
    }
    open_form(2, nullptr, s.test_count);
    break;
  case RUN_TESTS:
    if (!valid_program(s.program)) {
      message(M8("Сначала нужна программа."));
      break;
    }
    cancel = false;
    begin_request();
    angle_for_run();
    started = host.api->millis_ms();
    agent.run_tests();
    s.view = 0;
    screen = Screen::SESSION;
    typing = false;
    break;
  case EDIT_CODE: {
    if (s.intent == Intent::EXPLAIN) {
      message(M8("Для правки выбери режим «Исправить»."));
      break;
    }
    char code[PROGRAM_SIZE * 3 + 1]{};
    unsigned used = 0;
    for (unsigned i = 0; i < s.program.size; ++i)
      used += unsigned(std::snprintf(code + used, sizeof(code) - used, "%s%02X",
                                     i ? " " : "", s.program.bytes[i]));
    open_form(3, code);
    break;
  }
  case VERSIONS:
    if (!s.last_version) {
      message(M8("Версий пока нет."));
      break;
    }
    screen = Screen::VERSIONS;
    break;
  case EXPORT:
    if (!valid_program(s.program)) {
      message(M8("Сначала нужна программа."));
      break;
    }
    open_form(4, "PROGRAM.bin");
    break;
  case APPLY:
    if (!valid_program(s.program)) {
      message(M8("Сначала нужна программа."));
      break;
    }
    screen = Screen::APPLY;
    break;
  case LOAD_INPUTS:
    if (selected_test >= s.test_count ||
        !load_example_inputs(s.tests[selected_test]))
      message(M8("Не удалось загрузить входы примера."));
    else
      message(M8("Входы выбранного примера загружены."));
    screen = Screen::SESSION;
    break;
  case SHOW_TRACE:
    if (!valid_program(s.program)) {
      message(M8("Сначала нужна программа."));
      break;
    }
    cancel = false;
    show_trace_after = true;
    started = host.api->millis_ms();
    agent.run_tests(true, selected_test);
    s.view = 3;
    screen = Screen::SESSION;
    typing = false;
    break;
  case LOG:
    screen = Screen::LOG;
    scroll[0] = 0;
    break;
  case SETTINGS:
    screen = Screen::SETTINGS;
    break;
  case INTENT:
    screen = Screen::INTENT;
    break;
  case SESSIONS:
    checkpoint();
    scan_sessions();
    screen = Screen::HOME;
    typing = false;
    break;
  case ATTACH: {
    mk61_service_choice choice{};
    choice.parent = MK61_SERVICE_ROOT_ID;
    if (call(MK61_SERVICE_FILE_CHOOSE, MK61_SERVICE_FILE_TEXT, 0, 0, &choice)) {
      source_id = choice.file.id;
      source_offset = source_shown = 0;
      screen = Screen::ATTACH;
      typing = false;
    }
    break;
  }
  case OPEN_ID:
    open_form(6);
    break;
  case QUIT:
    if (checkpoint())
      quit = true;
    break;
  case SAVE_METRICS:
    message(write_metrics("/AI/METRICS.JSON")
                ? M8("Замеры: /AI/METRICS.JSON")
                : M8("Не удалось сохранить замеры."));
    break;
  case SHOW_TESTS:
    if (!s.test_count) message(M8("Tab → Добавить пример"));
    else { screen = Screen::CASE; selected_test = 0; scroll[0] = 0; }
    break;
  case TOGGLE_METRICS:
    screen = Screen::SESSION; s.view = 0;
    chat_view.expanded_metrics = !chat_view.expanded_metrics;
    break;
  case TOGGLE_CODE:
    screen = Screen::SESSION; s.view = 0;
    chat_view.expanded_code = !chat_view.expanded_code;
    break;
  }
  dirty = true;
}
void UI::submit() {
  if (loading || agent.active()) {
    submit_pending = true;
    cancel = true;
    agent.request_pause();
    return;
  }
  notice[0] = 0;
  if (screen != Screen::FORM) {
    char value[1025];
    if (!s.draft[0])
      return;
    if (!utf8(s.draft, value, sizeof(value)) || !set_task(s, value, true)) {
      message(M8("Условие длинное. Tab → изменить условие."));
      s.state = RunState::NEEDS_INPUT;
      return;
    }
    agent.reset();
    if (!append_event(store, s, "USER", value)) {
      message(M8("Не удалось сохранить сообщение."));
      return;
    }
    s.draft[0] = 0;
    cursor = 0;
    typing = false;
    checkpoint();
    latest_chat();
    start();
    dirty = true;
    return;
  }
  const unsigned kind = s.form_kind;
  bool ok = false;
  if (kind == 1) {
    char value[1025];
    ok = utf8(s.form, value, sizeof(value)) && set_task(s, value, false);
    if (ok) {
      agent.reset();
      ok = append_event(store, s, "TASK", value);
    }
  } else if (kind == 2) {
    Example example{};
    char value[2049];
    ok = utf8(s.form, value, sizeof(value)) && parse_example(value, example);
    if (ok) {
      std::snprintf(example.name, sizeof(example.name), "Test %u",
                    unsigned(s.form_index) + 1);
      ok = set_example(s, s.form_index, example);
      if (ok) {
        agent.reset();
        ok = append_event(store, s, "EXAMPLE", value);
      }
    }
  } else if (kind == 3) {
    u8 code[PROGRAM_SIZE];
    unsigned count = 0;
    ok = parse_code(s.form, code, count) &&
         accept_program(store, s, code, count);
    if (ok) {
      agent.reset();
      reset_attempt_history(s);
      s.state = RunState::DRAFT;
      s.view = 0;
      ok = append_event(store, s, "MANUAL", "program edited");
    }
  } else if (kind == 4) {
    char name[256];
    unsigned n = unsigned(std::strlen(s.form));
    ok = n > 0 && n < 80 && std::strchr(s.form, '/') == nullptr &&
         std::strchr(s.form, '\\') == nullptr &&
         std::strchr(s.form, ':') == nullptr &&
         std::strstr(s.form, "..") == nullptr;
    char leaf[161];
    if (ok)
      ok = utf8(s.form, leaf, sizeof(leaf));
    if (ok) {
      std::snprintf(name, sizeof(name), "/AI/Exports/%s", leaf);
      ok = files::write(name, s.program.bytes, s.program.size);
      if (ok)
        message(M8("Программа сохранена в /AI/Exports"));
    }
  } else if (kind == 5) {
    char *end = nullptr;
    const auto n = std::strtoul(s.form, &end, 10);
    ok = end && !*end && n > 0 && n <= 64;
    if (ok) {
      s.attempt_limit = std::uint16_t(n);
      s.state = RunState::PAUSED;
    }
  } else if (kind == 6) {
    char *end = nullptr;
    const auto id = std::strtoul(s.form, &end, 10);
    if (id && end && !*end) {
      ok = load_session(store, u32(id), s);
      if (ok) {
        agent.reset();
        request_measured = request_running = false;
        chat_view = {};
        s.form_kind = 0;
        screen = Screen::SESSION;
        typing = false;
      }
    }
  }
  if (!ok) {
    message(kind == 2 ? M8("Пример: R0=7 R1=5 => X=12 (F8:EN)")
                      : M8("Не удалось принять или сохранить ввод."));
    return;
  }
  s.form_kind = 0;
  screen = Screen::SESSION;
  typing = false;
  cursor = unsigned(std::strlen(s.draft));
  std::fill(scroll, scroll + 4, 0);
  checkpoint();
  dirty = true;
  if (kind == 3) act(RUN_TESTS);
}
bool UI::pump() {
  const auto micros = call(MK61_SERVICE_MICROS);
  // The model checks cancellation at every tile. Full native service pumps
  // twice (service and key input), so do that work at a bounded8ms cadence
  // instead of thousands of times per token. Loading and normal UI stay live.
  if (computing) {
    if (compute_polled && std::uint32_t(micros-compute_poll_stamp)<8000)
      return !cancel && !quit;
    compute_polled=true;compute_poll_stamp=micros;
  }
  time_request(request_measured && (loading || agent.active()));
  if (last_service)
    service_gap = std::max(service_gap, micros - last_service);
  last_service = micros;
  host.api->service();
  announce_result();
  for (unsigned n = 0; n < 8; ++n) {
    const int code = host.key();
    if (code < 0)
      break;
    key(unsigned(code));
    if (cancel || quit)
      break;
  }
  const u32 now = host.api->millis_ms();
  if (screen == Screen::SESSION && request_running && now - last_draw >= 1000) dirty = true;
  if (dirty && !(computing && freeze_screen) && draw_due(now) &&
      (now - last_draw >= 80 || (!agent.active() && !loading && !benchmarking)))
    draw();
  return !cancel && !quit;
}
void UI::key(unsigned wire) {
  presentation.invalidate();
  if (benchmarking) {
    if (!cancel && (wire == 0x1B || wire == 0xB1 || wire == 0x85)) {
      cancel_observed = call(MK61_SERVICE_MICROS);
      cancel = true;
      const char *marker = "AI_CANCEL\r\n";
      call(MK61_SERVICE_DEBUG_WRITE, unsigned(std::strlen(marker)), 0, 0,
           const_cast<char *>(marker));
    }
    return;
  }
  if (wire == 0x87) {
    if (!s.id && !new_session()) return;
    latest_chat();
    act(TOGGLE_METRICS);
    return;
  }
  if (wire >= 0x81 && wire <= 0x84) {
    if (!s.id && !new_session())
      return;
    latest_chat();
    if (wire == 0x81) act(TOGGLE_CODE);
    else act(wire == 0x82 ? APPLY : wire == 0x83 ? EDIT_CODE : EXPORT);
    return;
  }
  if (wire == 0x85) {
    if (!agent.active() && screen == Screen::SESSION && s.draft[0]) { submit(); return; }
    start();
    return;
  }
  if (wire == 0x86) {
    if (!s.id && !new_session())
      return;
    screen = Screen::SESSION;
    s.view = 0;
    latest_chat();
    typing = true;
    cursor = unsigned(std::strlen(s.draft));
    dirty = true;
    return;
  }
  if (wire == 0x88) {
    russian = !russian;
    dirty = true;
    return;
  }
  mk61_service_text_event event{};
  text_input::event(u8(wire), russian, event);
  if (event.kind == MK61_TEXT_CANCEL) {
    if (agent.active() || loading) {
      cancel = true;
      agent.request_pause();
      return;
    }
    if (screen == Screen::HOME) {
      if (checkpoint())
        quit = true;
      return;
    }
    if (screen == Screen::FORM) {
      s.form_kind = 0;
      screen = Screen::SESSION;
      typing = false;
      changed();
      return;
    }
    if (screen == Screen::SESSION) {
      if (typing) { typing = false; dirty = true; return; }
      checkpoint();
      scan_sessions();
      screen = Screen::HOME;
      selected = 0;
      typing = false;
    } else {
      screen = Screen::SESSION;
      typing = false;
    }
    dirty = true;
    return;
  }
  if (event.kind == MK61_TEXT_MENU) {
    if (!s.id && !new_session())
      return;
    if (agent.active() || loading) {
      cancel = true;
      agent.request_pause();
    }
    screen = Screen::MENU;
    selected = 0;
    typing = false;
    dirty = true;
    return;
  }
  if (event.kind == MK61_TEXT_SUBMIT) {
    if (screen == Screen::FORM ||
        (screen == Screen::SESSION && s.view == 0 && typing)) {
      submit();
      return;
    }
    if (screen == Screen::HOME) {
      if (selected == 0)
        act(NEW_TASK);
      else if (selected == 1)
        act(OPEN_BINARY);
      else if (selected == 2)
        act(CURRENT);
      else if (selected == 3)
        act(OPEN_ID);
      else if (load_session(store, sessions[selected - 4], s)) {
        agent.reset();
        request_measured = request_running = false;
        chat_view = {};
        screen = s.form_kind ? Screen::FORM : Screen::SESSION;
        typing = s.form_kind || s.view == 0;
        cursor = unsigned(std::strlen(s.form_kind ? s.form : s.draft));
        dirty = true;
      } else
        message(M8("Не удалось открыть задачу."));
      return;
    }
    if (screen == Screen::MENU) {
      static constexpr Action actions[] = {
          NEW_TASK, ADD_TEST, RUN_TESTS,   EDIT_CODE,  VERSIONS,
          EXPORT,   APPLY,    LOAD_INPUTS, SHOW_TRACE, LOG,
          SETTINGS, INTENT,   ATTACH,      SESSIONS,   QUIT};
      static constexpr Action extra[] = {SHOW_TESTS, TOGGLE_METRICS, TOGGLE_CODE, SAVE_METRICS};
      if (selected == 0) {
        if (agent.active()) {
          deferred = -2;
          cancel = true;
          agent.request_pause();
        } else {
          m8(s.task, text, sizeof(text));
          open_form(1, text);
        }
      } else if (selected < 15)
        act(actions[selected]);
      else act(extra[selected - 15]);
      return;
    }
    if (screen == Screen::VERSIONS) {
      if (select_program(store, s, s.last_version - selected)) {
        agent.reset();
        s.view = 1;
        screen = Screen::SESSION;
        checkpoint();
      } else
        message(M8("Версия недоступна."));
      dirty = true;
      return;
    }
    if (screen == Screen::INTENT) {
      agent.reset();
      s.intent = Intent(selected);
      s.state = RunState::DRAFT;
      screen = Screen::SESSION;
      if (s.intent != Intent::WRITE && !s.program.size) {
        Program source{};
        if (capture_program(source))
          accept_program(store, s, source.bytes, source.size, true);
      }
      if (s.intent == Intent::EXPLAIN) {
        if (!s.task[0])
          set_task(s, "Объясни программу и порядок её запуска.", false);
        s.view = 0;
        checkpoint();
      } else if (!s.task[0])
        open_form(1);
      else
        checkpoint();
      dirty = true;
      return;
    }
    if (screen == Screen::SETTINGS) {
      if (selected == 0) {
        char value[12];
        std::snprintf(value, sizeof(value), "%u", unsigned(s.attempt_limit));
        open_form(5, value);
      } else if (selected == 1) {
        arithmetic = Arithmetic((unsigned(arithmetic) + 1) % 4);
        if (arithmetic != Arithmetic::LUT_FLOAT32) { m3_core = false; ai_m3::close(); }
        agent.reset();
        dirty = true;
      } else if (selected == 4) {
        s.planning = !s.planning;
        agent.reset();
        checkpoint();
        dirty = true;
      } else if (selected == 5) {
        m3_core = !m3_core;
        if (m3_core) arithmetic = Arithmetic::LUT_FLOAT32;
        configure_execution();
        if (m3_core && !ai_m3::statistics().active) {
          m3_core = false;
          message(M8("STM32 недоступен. Нужен M3LINE.S3M."));
        }
        agent.reset(); dirty = true;
      } else if (selected == 6) {
        screen = Screen::SESSION;
        dirty = true;
      }
      return;
    }
    if (screen == Screen::APPLY) {
      if (selected) {
        screen = Screen::SESSION;
        dirty = true;
        return;
      }
      Program previous{};
      if (!capture_program(previous)) {
        message(M8("Сначала останови калькулятор."));
        return;
      }
      char path[96];
      unsigned sequence = s.event + 1;
      do {
        std::snprintf(path, sizeof(path), "/AI/SESSIONS/%08lu-B%08lu.bin",
                      (unsigned long)s.id, (unsigned long)sequence++);
      } while (files::exists(path) && sequence);
      if (!files::write(path, previous.bytes, previous.size)) {
        message(M8("Не удалось сохранить предыдущую программу."));
        return;
      }
      if (!apply_program(s.program)) {
        message(M8("Для переноса нужен режим 105 команд, банк 0."));
        return;
      }
      if (agent.last_result().status != Execution::NONE &&
          agent.last_result().version == s.program.version &&
          agent.last_result().task_revision == s.task_revision)
        MK61Emu_SetAngleUnit(agent.last_angle() == 0 ? DEGREE : agent.last_angle() == 2 ? GRADE : RADIAN);
      append_event(store, s, "APPLY", path);
      checkpoint();
      screen = Screen::SESSION;
      message(M8("Загружено. Регистры сохранены."));
      return;
    }
    if (screen == Screen::ATTACH) {
      if (!source_shown)
        return;
      char fragment[1025];
      const char saved = source_page[source_shown];
      source_page[source_shown] = 0;
      const bool converted = utf8(source_page, fragment, sizeof(fragment));
      source_page[source_shown] = saved;
      if (converted && set_task(s, fragment, true) &&
          append_event(store, s, "SOURCE", fragment)) {
        agent.reset();
        checkpoint();
        screen = Screen::SESSION;
        message(M8("Выбранный фрагмент добавлен к условию."));
      } else
        message(M8("Фрагмент не помещается. Выбери короче."));
      return;
    }
    if (screen == Screen::SESSION) {
      s.view = 0;
      typing = true;
      latest_chat();
      cursor = unsigned(std::strlen(s.draft));
      dirty = true;
      return;
    }
    if (screen == Screen::CASE && selected_test < s.test_count) {
      char value[1537];
      if (format_example(s.tests[selected_test], value, sizeof(value)))
        open_form(2, value, selected_test);
      else
        message(M8("Пример слишком длинный для формы."));
      return;
    }
  }
  const bool up = event.kind == MK61_TEXT_UP,
             down = event.kind == MK61_TEXT_DOWN;
  if (screen == Screen::ATTACH && (up || down)) {
    if (up)
      source_offset =
          source_offset > source_shown ? source_offset - source_shown : 0;
    else if (source_shown)
      source_offset += source_shown;
    dirty = true;
    return;
  }
  if (up || down) {
    if (screen == Screen::SESSION) {
      chat_view.follow = false;
      const unsigned maximum = chat_renderer.content_height() > 250 ? chat_renderer.content_height() - 250 : 0;
      if (up && !chat_view.scroll && history.has_older()) {
        if (history.older(store, s)) chat_view.scroll = 1000000U;
      } else if (down && chat_view.scroll >= maximum && !history.at_latest()) {
        if (history.newer(store, s)) chat_view.scroll = 0;
      } else if (up) chat_view.scroll = chat_view.scroll > 18 ? chat_view.scroll - 18 : 0;
      else chat_view.scroll = std::min(maximum, chat_view.scroll + 18);
      dirty = true; return;
    }
    const unsigned count = menu_count();
    if (count) {
      if (up && selected)
        --selected;
      else if (down && selected + 1 < count)
        ++selected;
    } else if (screen == Screen::SESSION && s.view == 2) {
      if (up && selected_test)
        --selected_test;
      else if (down && selected_test + 1 < s.test_count)
        ++selected_test;
      scroll[2] = selected_test * 2;
    } else if (screen == Screen::LOG) {
      if (up && selected)
        --selected;
      else if (down && selected + 1 < s.event)
        ++selected;
      scroll[0] = 0;
    } else {
      unsigned &offset = scroll[screen == Screen::SESSION ? s.view : 0];
      if (up && offset)
        --offset;
      else if (down && offset + 1 < line_count)
        ++offset;
    }
    dirty = true;
    return;
  }
  if (screen == Screen::CASE && (event.kind == MK61_TEXT_LEFT || event.kind == MK61_TEXT_RIGHT) && s.test_count) {
    selected_test = (selected_test + (event.kind == MK61_TEXT_RIGHT ? 1 : s.test_count - 1)) % s.test_count;
    scroll[0] = 0; dirty = true; return;
  }
  if (!typing && screen == Screen::SESSION && event.kind == MK61_TEXT_CHAR) {
    typing = true; cursor = unsigned(std::strlen(s.draft));
  }
  if (!typing)
    return;
  char *input = screen == Screen::FORM ? s.form : s.draft;
  unsigned n = unsigned(std::strlen(input));
  cursor = std::min(cursor, n);
  if (event.kind == MK61_TEXT_LEFT) {
    if (cursor)
      --cursor;
  } else if (event.kind == MK61_TEXT_RIGHT) {
    if (cursor < n)
      ++cursor;
  } else if (event.kind == MK61_TEXT_HOME)
    cursor = 0;
  else if (event.kind == MK61_TEXT_END_LINE)
    cursor = n;
  else if (event.kind == MK61_TEXT_BACKSPACE) {
    if (cursor) {
      std::memmove(input + cursor - 1, input + cursor, n - cursor + 1);
      --cursor;
    }
  } else if (event.kind == MK61_TEXT_DELETE) {
    if (cursor < n)
      std::memmove(input + cursor, input + cursor + 1, n - cursor);
  } else if (event.kind == MK61_TEXT_CHAR && event.value) {
    if (n + 1 >= (screen == Screen::FORM ? sizeof(s.form) : sizeof(s.draft))) {
      message(M8("Строка заполнена."));
      return;
    }
    std::memmove(input + cursor + 1, input + cursor, n - cursor + 1);
    input[cursor++] = char(event.value);
  } else
    return;
  follow_cursor = true;
  changed();
}
void UI::tick() {
  if (agent.active()) {
    const unsigned before_position=model.position();
    agent.tick(service, this);
    if(model.position()==before_position+1) {
      const auto &m=model.compute_metrics();
      profile_attention_us+=m.attention_us;profile_attention_io_us+=m.attention_io_us;
      profile_attention_jobs+=m.attention_worker_jobs;
      profile_read_us+=m.read_us;profile_matmul_us+=m.matmul_us;profile_wait_us+=m.wait_us;
      ++profile_steps;
      if((profile_steps%32)==0 || !agent.active()) {
        char progress[200];const auto &a=agent.metrics();
        const int n=std::snprintf(progress,sizeof(progress),
          "AI_CHAT_PROGRESS position=%u prompt=%u prefill_us=%llu decode_us=%llu attention_us=%llu io_us=%llu\r\n",
          model.position(),agent.prompt_size(),
          (unsigned long long)(a.prefill_us-metric_baseline.prefill_us),
          (unsigned long long)(a.decode_us-metric_baseline.decode_us),
          (unsigned long long)profile_attention_us,(unsigned long long)profile_attention_io_us);
        if(n>0 && unsigned(n)<sizeof(progress)) {
          char path[64];std::snprintf(path,sizeof(path),"/AI/SESSIONS/%08lu.PRF",(unsigned long)s.id);
          files::write(path,reinterpret_cast<const u8*>(progress),unsigned(n));
          debug_write(progress,unsigned(n));
        }
      }
    }
    if(!agent.active()) leave_fast_clock();
    time_request(agent.active());
    dirty = true;
    if (!agent.active()) {
      cancel = false;
      sync_chat(true);
      checkpoint();
      if (agent.last_result().status != Execution::NONE &&
          agent.last_result().version == s.program.version &&
          agent.last_result().task_revision == s.task_revision) {
        sample_memory();
        const int n=std::snprintf(pending_result,sizeof(pending_result),
          "AI_CHAT_RESULT task=%lu program=%lu tokens=%lu elapsed_ms=%llu execution=%u X=%.9g\r\n",
          (unsigned long)s.id,(unsigned long)s.program.version,
          (unsigned long)(agent.metrics().output_tokens-metric_baseline.output_tokens),
          (unsigned long long)request_ms,unsigned(agent.last_result().status),agent.last_result().x);
        const auto &a=agent.metrics();
        if(n>0 && unsigned(n)<sizeof(pending_result)) {
          const int extra=std::snprintf(pending_result+n,sizeof(pending_result)-unsigned(n),
            "AI_CHAT_PROFILE input=%lu reused=%lu prefill_us=%llu decode_us=%llu tool_us=%llu load_us=%lu attention_us=%llu attention_io_us=%llu linear_read_us=%llu matmul_us=%llu wait_us=%llu workers=%llu heap_peak=%lu stack_peak=%lu service_gap_us=%lu\r\n",
            (unsigned long)(a.prefill_tokens-metric_baseline.prefill_tokens),
            (unsigned long)(a.reused_tokens-metric_baseline.reused_tokens),
            (unsigned long long)(a.prefill_us-metric_baseline.prefill_us),
            (unsigned long long)(a.decode_us-metric_baseline.decode_us),
            (unsigned long long)(a.tool_us-metric_baseline.tool_us),(unsigned long)model_load_us,
            (unsigned long long)profile_attention_us,(unsigned long long)profile_attention_io_us,
            (unsigned long long)profile_read_us,(unsigned long long)profile_matmul_us,
            (unsigned long long)profile_wait_us,(unsigned long long)profile_attention_jobs,
            (unsigned long)heap_peak,(unsigned long)stack_peak,(unsigned long)service_gap);
          if(extra<0 || unsigned(extra)>=sizeof(pending_result)-unsigned(n))pending_result[0]=0;
        } else pending_result[0]=0;
        if(pending_result[0]) {
          char path[64];std::snprintf(path,sizeof(path),"/AI/SESSIONS/%08lu.PRF",(unsigned long)s.id);
          if(!files::write(path,reinterpret_cast<const u8*>(pending_result),unsigned(std::strlen(pending_result))))
            message(M8("Не удалось сохранить профиль запроса."));
        }
        announce_result();
      }
      if (show_trace_after) {
        show_trace_after = false;
        screen = Screen::TRACE;
        scroll[0] = 0;
      }
    }
  }
  if (!agent.active() && !loading) {
    cancel = false;
    if (deferred != -1) {
      const int action = deferred;
      deferred = -1;
      if (action == -2) {
        m8(s.task, text, sizeof(text));
        open_form(1, text);
      } else
        act(Action(action));
    }
    if (submit_pending) {
      submit_pending = false;
      submit();
    }
  }
  if (!loading && save_pending && host.api->millis_ms() - last_edit >= 500)
    checkpoint();
}
AI_COLD_CODE unsigned UI::bench() {
  benchmarking = true;
  s.view = 3;
  screen = Screen::SESSION;
  const char *directory =
      host.diagnostic_directory ? host.diagnostic_directory : "/AI/DIAG";
  files::Entry entry{};
  if (files::exists(directory)
          ? !files::stat(directory, entry) || !entry.directory
          : !files::mkdir(directory))
    return 3;
  char config_path[128],config_text[513];unsigned config_size=0;
  std::snprintf(config_path,sizeof(config_path),"%s/LONG.CFG",directory);
  if(files::exists(config_path)) {
    if(!files::read_text(config_path,config_text,sizeof(config_text)-1,config_size) ||
       config_size!=8 || std::memcmp(config_text,"AILONG1\n",8)) return 3;
    return long_perf(directory);
  }
  std::snprintf(config_path,sizeof(config_path),"%s/PERF.CFG",directory);
  if(files::exists(config_path)) {
    PerfConfig config;
    if(!files::read_text(config_path,config_text,sizeof(config_text)-1,config_size) ||
       !parse_perf_config(config_text,config_size,config)) return 3;
    return perf(directory,config);
  }
  char state_path[128], json_path[128];
  std::snprintf(state_path, sizeof(state_path), "%s/BENCH.STATE", directory);
  std::snprintf(json_path, sizeof(json_path), "%s/BENCH.JSON", directory);
  if (!ensure_model())
    return 3;
  cancel = false;
  configure_execution();
  sample_memory();
  // The same actual token trajectory is used for both kernels. No model
  // quality claim follows from this short, cold-KV arithmetic benchmark.
  std::uint16_t ids[64]{};
  unsigned count = 0;
  if (model.encode("Задача: вычисли выражение в регистрах.", ids, 64, count) !=
          ModelStatus::OK ||
      count < 8)
    return 3;
  constexpr unsigned PREFILL = 8, DECODE = 4;
  struct Row {
    std::uint32_t prefill = 0, decode = 0, max_step = 0;
    std::uint16_t next[DECODE]{};
    unsigned prefill_count = 0, decode_count = 0;
  };
  Row result[3]{};
  std::uint16_t trajectory[DECODE]{};
  struct Policy {
    UI *ui;
    ToolGrammar grammar;
  };
  Policy policy{this, {}};
  policy.grammar.reset(false, false, false);
  auto allowed = [](void *raw, std::uint16_t token) {
    auto &p = *static_cast<Policy *>(raw);
    if (token == p.ui->model.config().eos)
      return p.grammar.complete();
    if (token == 0 || token == p.ui->model.config().bos)
      return false;
    char piece[2049];
    unsigned n = 0;
    if (p.ui->model.decode(token, piece, sizeof(piece), n) != ModelStatus::OK ||
        !n)
      return false;
    auto next = p.grammar;
    return next.accept(piece, n) && next.minimum_tail() < 128;
  };
  bool valid_prefix = true;
  for (unsigned mode = 0; mode < 3 && !cancel; ++mode) {
    model.reset();
    auto &r = result[mode];
    const auto arithmetic =
        mode ? Arithmetic::LUT_FLOAT32 : Arithmetic::FLOAT32;
    std::uint16_t next = 0;
    for (unsigned i = 0; i < PREFILL + DECODE; ++i) {
      std::snprintf(s.feedback, sizeof(s.feedback),
                    "Benchmark %s %u/%u; Esc: stop", mode ? "LUT FP32" : "FP32",
                    i + 1, PREFILL + DECODE);
      dirty = true;
      char marker[64];
      const int marker_size =
          std::snprintf(marker, sizeof(marker),
                        "AI_BENCH mode=%u step=%u begin\r\n", mode, i);
      call(MK61_SERVICE_DEBUG_WRITE, unsigned(marker_size), 0, 0, marker);
      const auto before = call(MK61_SERVICE_MICROS);
      const auto token = i < PREFILL ? ids[i]
                         : mode == 2 ? next
                                     : trajectory[i - PREFILL];
      const auto status = model.forward(
          token, i >= PREFILL - 1, next, service, this, arithmetic, nullptr,
          mode == 2 ? +allowed : nullptr, &policy);
      const auto elapsed = call(MK61_SERVICE_MICROS) - before;
      r.max_step = std::max(r.max_step, elapsed);
      if (status != ModelStatus::OK) {
        if (cancel_observed)
          cancel_return_us = call(MK61_SERVICE_MICROS) - cancel_observed;
        cancel = true;
        break;
      }
      if (mode == 2 && i >= PREFILL - 1 && next != model.config().eos) {
        char piece[2049];
        unsigned n = 0;
        valid_prefix =
            valid_prefix &&
            model.decode(next, piece, sizeof(piece), n) == ModelStatus::OK &&
            policy.grammar.accept(piece, n);
        if (!valid_prefix) {
          cancel = true;
          break;
        }
      }
      if (i < PREFILL) {
        r.prefill += elapsed;
        ++r.prefill_count;
        if (i == PREFILL - 1 && !mode)
          trajectory[0] = next;
      } else {
        const auto j = i - PREFILL;
        r.decode += elapsed;
        ++r.decode_count;
        r.next[j] = next;
        if (!mode && j + 1 < DECODE)
          trajectory[j + 1] = next;
      }
    }
  }
  sample_memory();
  bool same = true;
  for (unsigned j = 0; j < DECODE; ++j)
    same = same && result[0].next[j] == result[1].next[j];
  // Exercise the largest session and the real transactional copy/codec
  // paths while the model, KV and UI are resident. Only a diagnostic file
  // is written; no user session ID or calculator state is changed.
  auto fill = [](char *p, unsigned n) {
    std::memset(p, 'a', n - 1);
    p[n - 1] = 0;
  };
  s.id = 1;
  s.test_count = TEST_COUNT;
  s.form_kind = 0;
  s.state = RunState::DRAFT;
  fill(s.task, sizeof(s.task));
  fill(s.draft, sizeof(s.draft));
  fill(s.form, sizeof(s.form));
  fill(s.reply, sizeof(s.reply));
  fill(s.plan, sizeof(s.plan));
  fill(s.feedback, sizeof(s.feedback));
  fill(s.model, sizeof(s.model));
  for (auto &e : s.tests) {
    fill(e.name, sizeof(e.name));
    e.inputs = e.expected_mask = e.preserve = (1U << INPUT_COUNT) - 1;
    e.has_expected = true;
    e.scenario_count = SCENARIO_STEPS;
    for (auto &a : e.scenario) {
      a.input_index = a.output_index = 15;
    }
  }
  Store scratch{
      state_path,
      [](void *p, const char *, void *out, unsigned cap, unsigned &n) {
        return store_read(nullptr, static_cast<const char *>(p), out, cap, n);
      },
      [](void *p, const char *, const void *bytes, unsigned n) {
        return store_write(nullptr, static_cast<const char *>(p), bytes, n);
      },
      [](void *, const char *) { return false; },
      [](void *p, const char *, unsigned &n) {
        return store_size(nullptr, static_cast<const char *>(p), n);
      }};
  std::uint8_t maximum_code[PROGRAM_SIZE]{};
  const bool roundtrip =
      accept_program(scratch, s, maximum_code, PROGRAM_SIZE) &&
      load_session(scratch, 1, s) && s.test_count == TEST_COUNT &&
      s.tests[7].scenario_count == SCENARIO_STEPS &&
      std::strlen(s.form) == sizeof(s.form) - 1;
  files::remove(state_path);
  sample_memory();
  char json[1536];
  const auto &a = result[0];
  const auto &b = result[1];
  const auto &c = result[2];
  const int n = std::snprintf(
      json, sizeof(json),
      "{\"schema\":2,\"device\":%s,\"context_at_decode\":8,\"model\":\"%s\","
      "\"cancelled\":%s,\"matching_greedy_tokens\":%s,\"max_session_"
      "roundtrip\":%s,\"reference\":{\"prefill_tokens\":%u,\"prefill_us\":%lu,"
      "\"decode_tokens\":%u,\"decode_us\":%lu,\"max_step_us\":%lu},\"lut_"
      "fp32\":{\"prefill_tokens\":%u,\"prefill_us\":%lu,\"decode_tokens\":%u,"
      "\"decode_us\":%lu,\"max_step_us\":%lu},\"constrained_lut\":{\"prefill_"
      "tokens\":%u,\"prefill_us\":%lu,\"decode_tokens\":%u,\"decode_us\":%lu},"
      "\"valid_tool_prefix\":%s,\"cancel_return_us\":%lu,\"heap_capacity\":%lu,"
      "\"sampled_"
      "heap_peak\":%lu,\"stack_high_water\":%lu,\"service_gap_us\":%lu,\"model_"
      "load_us\":%lu}\n",
      heap_capacity ? "true" : "false", model_tag, cancel ? "true" : "false",
      same ? "true" : "false", roundtrip ? "true" : "false", a.prefill_count,
      (unsigned long)a.prefill, a.decode_count, (unsigned long)a.decode,
      (unsigned long)a.max_step, b.prefill_count, (unsigned long)b.prefill,
      b.decode_count, (unsigned long)b.decode, (unsigned long)b.max_step,
      c.prefill_count, (unsigned long)c.prefill, c.decode_count,
      (unsigned long)c.decode, valid_prefix ? "true" : "false",
      (unsigned long)cancel_return_us, (unsigned long)heap_capacity,
      (unsigned long)heap_peak, (unsigned long)stack_peak,
      (unsigned long)service_gap, (unsigned long)model_load_us);
  const bool ok =
      n > 0 && unsigned(n) < sizeof(json) &&
      files::write(json_path, reinterpret_cast<const u8 *>(json), unsigned(n));
  return ok && !cancel && same && roundtrip && valid_prefix ? 0 : 3;
}
AI_COLD_CODE unsigned UI::long_perf(const char *directory) {
  using namespace mk61ai::long_bench;
  auto plan=model.execution();plan.tile_rows=28;model.execution(plan);
  if(!ensure_model() || model.config().context<contexts[cases-1]+decode) return 3;
  std::uint16_t ids[64]{};unsigned count=0;
  if(model.encode(prompt,ids,64,count)!=ModelStatus::OK || count<2) return 3;
  std::uint8_t expected[reference_bytes]{};unsigned size=0;
  char path[128];std::snprintf(path,sizeof(path),"%s/LONG.REF",directory);
  std::uint32_t model_crc=0;
  if(!package.read(124,&model_crc,4) ||
      !files::read(path,expected,sizeof(expected),size) || size!=sizeof(expected) ||
      word(expected,0)!=magic || word(expected,4)!=model.config().vocab ||
      word(expected,8)!=cases || word(expected,12)!=decode || word(expected,16)!=model_crc) return 3;
  for(unsigned i=0;i<cases;++i) if(word(expected,20+i*32)!=contexts[i]) return 3;
  struct Result {
    std::uint64_t prefill_us=0,decode_us[decode]{},layers_us=0,classifier_us=0;
    std::uint64_t attention_bytes=0;
    std::uint32_t next[decode]{},checksums[decode]{},kv=0;
    std::uint32_t preparations=0,reuses=0;
  } result[cases];
  arithmetic=Arithmetic::INT8;dual_core=true;freeze_screen=true;double_buffer=true;
  filter_head=false;m3_core=false;linear_kernel=LinearKernel::SRAM;
  configure_execution();cancel=false;
  ai_clock::State frequency;
  bool ok=ai_clock::begin(270,frequency),matching=true,host_tokens=true;
  unsigned verified_steps=0;
  const auto actual_hz=ai_clock::hz();
  ModelStatus status=ModelStatus::OK;
  auto marker=[&](unsigned context,unsigned position) {
    char text[96];const int n=std::snprintf(text,sizeof(text),
        "AI_PERF long_context=%u prefill=%u hz=%lu\r\n",context,position,(unsigned long)ai_clock::hz());
    call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,text);
  };
  auto row_hash=[&](unsigned position) AI_COLD_CODE {
    const auto &c=model.config();const unsigned bytes=c.kv_heads*c.head_dim*8;
    std::uint32_t value=2166136261U;std::uint8_t block[256];
    for(unsigned layer=0;layer<c.layers;++layer) for(unsigned at=0;at<bytes;) {
      const unsigned take=std::min<unsigned>(sizeof(block),bytes-at);
      if(!cache.read(layer*c.context*bytes+position*bytes+at,block,take)) { ok=false;return value; }
      value=hash(value,block,take);at+=take;
    }
    return value;
  };
  // The host and MCU libm can round transcendental functions differently.
  // Compare the old INT8 path on the same MCU at selected positions. Rewind
  // only the current position; both passes read the identical prior KV prefix.
  auto step=[&](std::uint16_t token,bool output,std::uint16_t &next,bool verify,std::uint64_t &elapsed) AI_COLD_CODE {
    const auto execution=model.execution();const unsigned position=model.position();
    std::uint16_t reference_next=0;std::uint32_t reference_hash=0,reference_kv=0;
    if(verify) {
      auto reference=execution;reference.reuse_activations=false;reference.share_kv=false;
      model.execution(reference);
      status=model.forward(token,output,reference_next,service,this,arithmetic);
      reference_hash=model.compute_metrics().checksum;reference_kv=row_hash(position);
      model.execution(execution);
      if(status!=ModelStatus::OK || !ok || !model.rewind(position))return false;
    }
    const auto before=call(MK61_SERVICE_MICROS);
    status=model.forward(token,output,next,service,this,arithmetic);
    elapsed=call(MK61_SERVICE_MICROS)-before;
    if(status!=ModelStatus::OK)return false;
    if(verify) {
      ++verified_steps;
      matching=matching && next==reference_next && model.compute_metrics().checksum==reference_hash &&
          row_hash(position)==reference_kv;
    }
    return ok && matching;
  };
  for(unsigned which=0;ok && which<cases;++which) {
    const unsigned context=contexts[which],at=20+which*32;
    auto &r=result[which];model.reset();std::uint16_t next=0;
    for(unsigned pos=0;ok && pos<context;++pos) {
      if((pos&15U)==0) {
        marker(context,pos);
        std::snprintf(s.feedback,sizeof(s.feedback),"Context %u: %u/%u; Esc: stop",context,pos,context);
        dirty=true;sample_memory();
      }
      std::uint64_t elapsed=0;
      ok=step(input(ids,count,pos),pos+1==context,next,pos+1==context,elapsed);
      r.prefill_us+=elapsed;
    }
    if(!ok) break;
    host_tokens=host_tokens && next==word(expected,at+4);
    for(unsigned i=0;ok && i<decode;++i) {
      ok=step(next,true,next,true,r.decode_us[i]);
      r.next[i]=next;const auto &m=model.compute_metrics();r.checksums[i]=m.checksum;
      r.layers_us+=m.layers_us;r.classifier_us+=m.classifier_us;
      r.attention_bytes+=m.attention_read_bytes;
      r.preparations+=m.activation_preparations;r.reuses+=m.activation_reuses;
      host_tokens=host_tokens && next==word(expected,at+12+i*8);
    }
    r.kv=2166136261U;std::uint8_t block[512];
    const auto &c=model.config();const unsigned row=c.kv_heads*c.head_dim*8;
    for(unsigned layer=0;ok && layer<c.layers;++layer) {
      for(unsigned offset=0;ok && offset<(context+decode)*row;) {
        const unsigned take=std::min<unsigned>(sizeof(block),(context+decode)*row-offset);
        ok=cache.read(layer*c.context*row+offset,block,take);
        if(ok) r.kv=hash(r.kv,block,take);
        offset+=take;
      }
    }
    ok=ok && matching;sample_memory();
  }
  const bool restored=ai_clock::restore(frequency);
  ok=ok && restored && matching && !cancel && !freeze_violations && freeze_count==thaw_count;
  sample_memory();
  std::unique_ptr<char[]> json(new(std::nothrow) char[8192]);if(!json) return 3;
  unsigned used=0;bool fits=true;
  auto append=[&](const char *format,auto...args) {
    if(!fits)return;const int n=std::snprintf(json.get()+used,8192-used,format,args...);
    if(n<0 || unsigned(n)>=8192-used)fits=false;else used+=unsigned(n);
  };
  append("{\"schema\":1,\"ok\":%s,\"matching_reference\":%s,\"model\":\"%s\","
      "\"actual_hz\":%lu,\"restored_hz\":%lu,\"clocks_restored\":%s,\"arithmetic\":1,"
      "\"model_load_us\":%lu,\"model_status\":%u,\"results\":[",
      ok?"true":"false",matching?"true":"false",model_tag,(unsigned long)actual_hz,
      (unsigned long)ai_clock::hz(),restored?"true":"false",(unsigned long)model_load_us,unsigned(status));
  for(unsigned i=0;i<cases;++i) {
    const auto &r=result[i];
    append("%s{\"context_tokens\":%u,\"prefill_us\":%llu,\"time_to_first_token_us\":%llu,"
        "\"decode_us\":[%llu,%llu],\"next\":[%lu,%lu],\"checksums\":[\"%08lx\",\"%08lx\"],"
        "\"kv_checksum\":\"%08lx\",\"decode_layers_us\":%llu,\"decode_classifier_us\":%llu,"
        "\"attention_read_bytes\":%llu,\"activation_preparations\":%lu,\"activation_reuses\":%lu}",
        i?",":"",contexts[i],(unsigned long long)r.prefill_us,(unsigned long long)r.prefill_us,
        (unsigned long long)r.decode_us[0],(unsigned long long)r.decode_us[1],
        (unsigned long)r.next[0],(unsigned long)r.next[1],(unsigned long)r.checksums[0],(unsigned long)r.checksums[1],
        (unsigned long)r.kv,(unsigned long long)r.layers_us,(unsigned long long)r.classifier_us,
        (unsigned long long)r.attention_bytes,(unsigned long)r.preparations,(unsigned long)r.reuses);
  }
  append("],\"verified_device_steps\":%u,\"matching_host_tokens\":%s,\"freeze_violations\":%u,\"freeze_count\":%u,\"thaw_count\":%u,"
      "\"heap_capacity\":%lu,\"heap_peak\":%lu,\"stack_peak\":%lu}",verified_steps,host_tokens?"true":"false",freeze_violations,freeze_count,thaw_count,
      (unsigned long)heap_capacity,(unsigned long)heap_peak,(unsigned long)stack_peak);
  std::snprintf(path,sizeof(path),"%s/LONG.JSON",directory);
  return fits && files::write(path,reinterpret_cast<const u8*>(json.get()),used) && ok?0:3;
}
AI_COLD_CODE unsigned UI::perf(const char *directory,const PerfConfig &config) {
  // Reserve the larger tiles only for this diagnostic, before workspace bind.
  auto memory_plan=model.execution();memory_plan.tile_rows=config.cores==3?64:28;
  model.execution(memory_plan);
  if(!ensure_model()) return 3;
  cancel=false;cancel_observed=cancel_return_us=0;
  std::uint16_t ids[64]{};unsigned count=0;
  if(model.encode("Задача: вычисли выражение в регистрах. Проверь результат и заверши программу.",
                  ids,64,count)!=ModelStatus::OK || count<config.prefill) return 3;
  if(config.cores==3) {
    const int n=std::snprintf(m3_module_path,sizeof(m3_module_path),"%s/M3LINE.S3M",directory);
    if(n<0 || unsigned(n)>=sizeof(m3_module_path)) return 3;
  }
  struct Result {
    std::uint64_t prefill_us=0,decode_us=0;
    std::uint32_t max_step_us=0,rows=0,skipped=0,jobs=0,worker_rows=0,prefetches=0,prefetched_bytes=0;
    std::uint64_t read_us=0,matmul_us=0,wait_us=0;
    std::uint64_t decode_layers_us=0,decode_classifier_us=0;
    std::uint64_t decode_presentation_us=0,decode_service_us=0;
    std::uint32_t decode_service_calls=0,decode_kv_reads=0,decode_kv_batches=0;
    std::uint32_t remote_jobs=0,remote_rows=0,remote_fallbacks=0;
    std::uint64_t remote_prepare_us=0,remote_submit_us=0,remote_wait_us=0;
    ai_m3::Statistics m3{};
    std::uint32_t kv_checksum=0;
    unsigned completed=0,prefill=0,decode=0;
    std::uint16_t next[24]{};
    std::uint32_t checksum[24]{};
  };
  std::unique_ptr<Result[]> results(new(std::nothrow) Result[5]);
  if(!results) return 3;
  const bool archived = config.control == 2;
  if(archived) {
    char path[128];std::snprintf(path,sizeof(path),"%s/PERF.REF",directory);
    std::uint8_t bytes[20+24*8];unsigned used=0;
    const unsigned steps=config.prefill+config.decode;
    files::Entry entry{};
    const auto word=[&](unsigned at) { return unsigned(bytes[at]) | unsigned(bytes[at+1])<<8 |
        unsigned(bytes[at+2])<<16 | unsigned(bytes[at+3])<<24; };
    if(!files::stat(path,entry) || entry.directory || entry.size!=20+steps*8 ||
        !files::read_range(path,0,bytes,entry.size,used) || used!=entry.size ||
        word(0)!=0x31524941U || word(4)!=steps || word(8)!=config.prefill ||
        word(12)!=config.decode || word(16)!=model.config().vocab) return 3;
    for(unsigned i=0;i<steps;++i) {
      if(word(20+i*8)>=model.config().vocab) return 3;
      results[0].next[i]=std::uint16_t(word(20+i*8));
      results[0].checksum[i]=word(24+i*8);
    }
  }
  bool matching_tokens=true,matching_checksums=true,matching_kv=true,valid_prefix=true;
  ModelStatus status=ModelStatus::OK;
  struct Policy { UI *ui;ToolGrammar grammar; } policy{this,{}};
  auto allowed=[](void *raw,std::uint16_t id) {
    auto &p=*static_cast<Policy*>(raw);
    if(id==p.ui->model.config().eos) return p.grammar.complete();
    if(!id || id==p.ui->model.config().bos) return false;
    char piece[2049];unsigned n=0;
    if(p.ui->model.decode(id,piece,sizeof(piece),n)!=ModelStatus::OK || !n || std::memchr(piece,0,n)) return false;
    auto next=p.grammar;return next.accept(piece,n) && next.minimum_tail()<128;
  };
  const unsigned steps=config.prefill+config.decode;
  auto run=[&](unsigned pass) {
    auto &result=results[pass];
    const bool original=pass==0 && !config.control;
    linear_kernel=original?LinearKernel::REFERENCE:LinearKernel(config.kernel);
    dual_core=!original && config.cores>=2;
    m3_core=pass>0 && config.cores==3;
    arithmetic=Arithmetic(config.arithmetic);
    freeze_screen=!original && config.freeze;
    filter_head=!original && config.filter;
    // M3 compares identical two-core settings, including prefetch. Older DMA
    // experiments retain their synchronous control and target-only prefetch.
    double_buffer=(pass>0 || config.cores==3) && config.prefetch;
    configure_execution();model.reset();policy.grammar.reset(false,false,false);
    const auto transport_before=ai_m3::statistics();
    struct TransportEnd {
      bool enabled;
      Result &result;
      ai_m3::Statistics before;
      ~TransportEnd() {
        if(!enabled) return;
        result.m3=ai_m3::statistics();
        result.m3.sent-=before.sent;result.m3.received-=before.received;
        result.m3.requests-=before.requests;
        ai_m3::close();
        const auto closed=ai_m3::statistics();
        result.m3.unload_failures=closed.unload_failures;
        result.m3.uart_errors=closed.uart_errors;result.m3.error=closed.error;
      }
    } transport_end{m3_core,result,transport_before};
    if(m3_core && !transport_before.active) return false;
    for(unsigned i=0;i<steps;++i) {
      std::snprintf(s.feedback,sizeof(s.feedback),"Perf pass %u step %u/%u; Esc: stop",pass,i+1,steps);
      dirty=true;
      char marker[96];const int n=std::snprintf(marker,sizeof(marker),"AI_PERF pass=%u step=%u begin hz=%lu\r\n",
          pass,i,(unsigned long)ai_clock::hz());
      call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,marker);
      const auto token=i<config.prefill?ids[i]:pass?results[0].next[i-1]:result.next[i-1];
      const auto before=call(MK61_SERVICE_MICROS);
      std::uint16_t next=0;
      status=model.forward(token,i+1>=config.prefill,next,service,this,
          Arithmetic(config.arithmetic),nullptr,config.constrained?+allowed:nullptr,&policy);
      const auto elapsed=call(MK61_SERVICE_MICROS)-before;
      if(m3_core && ai_m3::statistics().error) return false;
      result.max_step_us=std::max(result.max_step_us,elapsed);
      if(status!=ModelStatus::OK) {
        if(cancel_observed) cancel_return_us=call(MK61_SERVICE_MICROS)-cancel_observed;
        if(status==ModelStatus::CANCELLED) cancel=true;
        return false;
      }
      result.next[i]=next;result.checksum[i]=model.compute_metrics().checksum;
      result.rows+=model.compute_metrics().rows;
      result.skipped+=model.compute_metrics().skipped_rows;
      result.jobs+=model.compute_metrics().worker_jobs;
      result.worker_rows+=model.compute_metrics().worker_rows;
      result.prefetches+=model.compute_metrics().prefetches;
      result.prefetched_bytes+=model.compute_metrics().prefetched_bytes;
      result.read_us+=model.compute_metrics().read_us;
      result.matmul_us+=model.compute_metrics().matmul_us;
      result.wait_us+=model.compute_metrics().wait_us;
      const auto &metrics=model.compute_metrics();
      result.remote_jobs+=metrics.remote_jobs;
      result.remote_rows+=metrics.remote_rows;
      result.remote_fallbacks+=metrics.remote_fallbacks;
      result.remote_prepare_us+=metrics.remote_prepare_us;
      result.remote_submit_us+=metrics.remote_submit_us;
      result.remote_wait_us+=metrics.remote_wait_us;
      ++result.completed;
      if(i<config.prefill) { result.prefill_us+=elapsed;++result.prefill; }
      else {
        result.decode_us+=elapsed;++result.decode;
        result.decode_layers_us+=metrics.layers_us;
        result.decode_classifier_us+=metrics.classifier_us;
        result.decode_presentation_us+=metrics.presentation_us;
        result.decode_service_us+=metrics.service_us;
        result.decode_service_calls+=metrics.service_calls;
        result.decode_kv_reads+=metrics.attention_read_transactions;
        result.decode_kv_batches+=metrics.attention_batches;
      }
      if(pass) {
        matching_tokens=matching_tokens && next==results[0].next[i];
        // A legacy control evaluates masked-out logits too. Sparse output
        // filtering intentionally omits them from the all-linear-rows hash.
        if(!config.filter || config.control || i+1<config.prefill)
          matching_checksums=matching_checksums && result.checksum[i]==results[0].checksum[i];
      }
      if(config.constrained && i+1>=config.prefill && next!=model.config().eos) {
        char piece[2049];unsigned n=0;
        valid_prefix=valid_prefix && model.decode(next,piece,sizeof(piece),n)==ModelStatus::OK &&
            policy.grammar.accept(piece,n);
      }
      sample_memory();
      if(!matching_tokens || !matching_checksums || !valid_prefix) return false;
    }
    if(config.cores==3) {
      // Outside forward timing, after every worker/DMA job is joined. The
      // unwritten KV bytes remain unchanged between passes; compare the whole
      // allocation too, so accidental writes outside valid positions count.
      std::uint8_t block[256];std::uint32_t hash=2166136261U;
      for(unsigned at=0;at<model.cache_bytes();) {
        const unsigned take=std::min(unsigned(sizeof(block)),unsigned(model.cache_bytes()-at));
        if(!cache.read(at,block,take)) { status=ModelStatus::IO;return false; }
        for(unsigned j=0;j<take;++j) hash=(hash^block[j])*16777619U;
        at+=take;
        if((at&16383U)==0 && !pump()) { cancel=true;return false; }
      }
      result.kv_checksum=hash;
      if(pass && !archived) matching_kv=matching_kv && hash==results[0].kv_checksum;
    }
    if(m3_core) {
      const auto state=ai_m3::statistics();
      if(!result.remote_jobs || result.remote_fallbacks || state.error || state.uart_errors) return false;
    }
    return true;
  };
  bool ok=archived || run(0);
  // Stress only an owned external allocation. Never run the device-wide
  // PSRAM self-test while the model/KV or another cache is resident.
  shared_memory::Buffer scratch;
  if(ok && config.stress_ms)
    ok=scratch.acquire(shared_memory::Owner::APPLICATION,65536,
                       shared_memory::BufferAccess::EXTERNAL_ONLY);
  float stress_input[32],stress_lookup[128],stress_sum=0,stress_output[4]{},stress_reference[4]{};
  std::uint8_t stress_weights[64],stress_scales[8];
  for(unsigned j=0;j<32;++j) stress_input[j]=(float(j)-16.0f)*0.0625f;
  for(unsigned q=0;q<8;++q) {
    float *t=stress_lookup+q*16;t[0]=0;
    for(unsigned lane=0;lane<4;++lane)
      for(unsigned mask=0;mask<(1U<<lane);++mask)
        t[mask+(1U<<lane)]=t[mask]+stress_input[q*4+lane];
    stress_sum+=t[15];
  }
  for(unsigned row=0;row<4;++row) {
    std::uint8_t packed[16];
    for(unsigned j=0;j<16;++j) packed[j]=std::uint8_t(((j+row*3)&15)|(((j*7+row)&15)<<4));
    mk61ai_pack_q4_planes32(packed,stress_weights+16*row);
    stress_scales[2*row]=0;stress_scales[2*row+1]=0x3c;
  }
  LinearBatch stress{};stress.columns=32;stress.rows=4;stress.input=stress_input;
  stress.lookup=stress_lookup;stress.input_sums=&stress_sum;
  stress.weights=stress_weights;stress.scales=stress_scales;stress.output=stress_reference;
  linear_batch_flash(&stress);
  stress.output=stress_output;
  ai_clock::State frequency;
  unsigned passes=0,stress_iterations=0,control_probe_calls=0;std::uint32_t actual_hz=ai_clock::hz();
  const auto reads_before=psram_reads,writes_before=psram_writes;
#if defined(PICO_ON_DEVICE)
  const auto worker_before=io_worker::statistics();
#endif
  if(ok) {
    // The host plan explicitly expects USB re-enumeration for an OC rate.
    char marker[96];const int n=std::snprintf(marker,sizeof(marker),"AI_CLOCK requested=%u begin\r\n",config.mhz);
    call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,marker);
    ok=ai_clock::begin(config.mhz,frequency);actual_hz=ai_clock::hz();
  }
  for(unsigned pass=1;ok && pass<=config.repeat;++pass) {
    ok=run(pass);++passes;
    if(!ok || !config.stress_ms || pass>1) continue;
    // Direct diagnostic matmuls use the same presentation boundary as a
    // model forward, retaining input service throughout the stress loop.
    const auto stress_execution=model.execution();
    if(stress_execution.busy) stress_execution.busy(stress_execution.context,true);
#if defined(PICO_ON_DEVICE)
    // Exercise the same core-1 control path used by the key-click timer,
    // without playing a sound. It must remain callable while LCD is held.
    bool invoked=false;
    io_worker::invoke(&invoked,[](void *p) { *static_cast<bool*>(p)=true; });
    ok=ok && invoked;if(invoked) ++control_probe_calls;
#endif
    const auto started=host.api->millis_ms();
    std::uint8_t expected[256],actual[256];
    while(ok && host.api->millis_ms()-started<config.stress_ms) {
      if(!pump()) { cancel=true;ok=false;break; }
      LinearBatch local=stress,remote=stress;
      bool submitted=false;
#if defined(PICO_ON_DEVICE)
      if(config.cores>=2) {
        local.rows=remote.rows=2;remote.weights+=32;remote.scales+=4;remote.output+=2;
        submitted=io_worker::submit_compute(&remote,linear_batch_sram);
        if(!submitted) local.rows=4;
      }
#endif
      linear_batch_sram(&local);
#if defined(PICO_ON_DEVICE)
      if(submitted) io_worker::join_compute();
#else
      (void)submitted;
#endif
      ok=local.status==ModelStatus::OK && (!submitted || remote.status==ModelStatus::OK) &&
          !std::memcmp(stress_reference,stress_output,sizeof(stress_output));
      for(unsigned j=0;j<sizeof(expected);++j)
        expected[j]=std::uint8_t((j*37U)^(stress_iterations*13U)^(j>>3));
      const unsigned address=(stress_iterations*4093U)&(65536-256);
      ok=ok && scratch.write(address,expected,sizeof(expected)) &&
          scratch.read(address,actual,sizeof(actual)) && !std::memcmp(expected,actual,sizeof(expected));
      ++stress_iterations;
    }
    if(stress_execution.busy) stress_execution.busy(stress_execution.context,false);
  }
#if defined(PICO_ON_DEVICE)
  const unsigned psram_read_div=psram::diagnostic_clock_divider256();
#else
  const unsigned psram_read_div=0;
#endif
  const bool clocks_restored=ai_clock::restore(frequency);
  ai_m3::close();
  const auto restored_hz=ai_clock::hz();
  // All exits after begin converge here, before SD writes, teardown or return.
  // A failed stability check does not start the next requested frequency.
  sample_memory();
#if defined(PICO_ON_DEVICE)
  const auto worker_after=io_worker::statistics();
  const unsigned worker_jobs=unsigned(worker_after.compute_jobs-worker_before.compute_jobs);
  const unsigned worker_max_us=unsigned(worker_after.compute_max_us);
  const unsigned i2c_errors=unsigned(worker_after.i2c_timeouts-worker_before.i2c_timeouts+
                                   worker_after.i2c_aborts-worker_before.i2c_aborts);
  const bool device=true;
#else
  const unsigned worker_jobs=0,worker_max_us=0,i2c_errors=0;const bool device=false;
#endif
  bool used_worker=!device || config.cores==1;
  for(unsigned i=1;i<=passes;++i) used_worker=used_worker || results[i].jobs>0;
  if(config.cores==3) for(unsigned i=1;i<=passes;++i)
    ok=ok && results[i].remote_jobs && !results[i].remote_fallbacks &&
       !results[i].m3.error && !results[i].m3.uart_errors && !results[i].m3.unload_failures;
  ok=ok && !cancel && matching_tokens && matching_checksums && matching_kv && valid_prefix && clocks_restored &&
      !freeze_violations && freeze_count==thaw_count && used_worker && !i2c_errors;
  std::unique_ptr<char[]> json(new(std::nothrow) char[8192]);
  if(!json) return 3;
  sample_memory();
  unsigned used=0;bool fits=true;
  auto append=[&](const char *format,auto... args) {
    if(!fits) return;
    int n;
    if constexpr(sizeof...(args)==0) n=std::snprintf(json.get()+used,8192-used,"%s",format);
    else n=std::snprintf(json.get()+used,8192-used,format,args...);
    if(n<0 || unsigned(n)>=8192-used) fits=false;else used+=unsigned(n);
  };
  append("{\"schema\":3,\"device\":%s,\"ok\":%s,\"cancelled\":%s,\"model\":\"%s\",\"vocab\":%u,"
      "\"config\":{\"kernel\":%u,\"arithmetic\":%u,\"cores\":%u,\"freeze\":%u,\"filter\":%u,\"mhz\":%u,"
      "\"prefill\":%u,\"decode\":%u,\"repeat\":%u,\"stress_ms\":%u,\"control\":%u,\"constrained\":%u",
      device?"true":"false",ok?"true":"false",cancel?"true":"false",model_tag,unsigned(model.config().vocab),
      config.kernel,config.arithmetic,config.cores,config.freeze,config.filter,config.mhz,config.prefill,
      config.decode,config.repeat,config.stress_ms,config.control,config.constrained);
  if(config.version==2) append(",\"prefetch\":%u",config.prefetch);
  append("},\"reference_external\":%s,\"tile_rows\":%u,",archived?"true":"false",config.cores==3?64:28);
  append("\"psram_read_divider256\":%u,",psram_read_div);
  append(
      "\"actual_hz\":%lu,\"restored_hz\":%lu,\"clocks_restored\":%s,\"matching_tokens\":%s,"
      "\"matching_checksums\":%s,\"matching_kv\":%s,\"valid_tool_prefix\":%s,\"model_status\":%u,\"results\":[",
      (unsigned long)actual_hz,
      (unsigned long)restored_hz,clocks_restored?"true":"false",matching_tokens?"true":"false",
      matching_checksums?"true":"false",archived?"null":matching_kv?"true":"false",valid_prefix?"true":"false",unsigned(status));
  for(unsigned i=archived?1U:0U;i<=passes;++i) {
    const auto &r=results[i];
    append("%s{\"pass\":%u,\"prefill_tokens\":%u,\"prefill_us\":%llu,\"decode_tokens\":%u,\"decode_us\":%llu,"
        "\"max_step_us\":%lu,\"rows\":%lu,\"skipped_rows\":%lu,\"worker_jobs\":%lu,\"worker_rows\":%lu,"
        "\"prefetches\":%lu,\"prefetched_bytes\":%lu,\"read_us\":%llu,\"matmul_us\":%llu,\"wait_us\":%llu,"
        "\"decode_layers_us\":%llu,\"decode_classifier_us\":%llu,"
        "\"decode_presentation_us\":%llu,\"decode_service_us\":%llu,\"decode_service_calls\":%lu,\"decode_kv_reads\":%lu,\"decode_kv_batches\":%lu,\"next\":[",
        i>(archived?1U:0U)?",":"",i,r.prefill,(unsigned long long)r.prefill_us,r.decode,(unsigned long long)r.decode_us,
        (unsigned long)r.max_step_us,(unsigned long)r.rows,(unsigned long)r.skipped,(unsigned long)r.jobs,
        (unsigned long)r.worker_rows,(unsigned long)r.prefetches,(unsigned long)r.prefetched_bytes,
        (unsigned long long)r.read_us,(unsigned long long)r.matmul_us,(unsigned long long)r.wait_us,
        (unsigned long long)r.decode_layers_us,(unsigned long long)r.decode_classifier_us,
        (unsigned long long)r.decode_presentation_us,(unsigned long long)r.decode_service_us,
        (unsigned long)r.decode_service_calls,(unsigned long)r.decode_kv_reads,(unsigned long)r.decode_kv_batches);
    for(unsigned j=0;j<r.completed;++j) append("%s%u",j?",":"",unsigned(r.next[j]));
    append("],\"checksums\":[");
    for(unsigned j=0;j<r.completed;++j) append("%s\"%08lx\"",j?",":"",(unsigned long)r.checksum[j]);
    append("],\"kv_checksum\":\"%08lx\",\"remote_jobs\":%lu,\"remote_rows\":%lu,\"remote_fallbacks\":%lu,"
        "\"remote_prepare_us\":%llu,\"remote_submit_us\":%llu,\"remote_wait_us\":%llu,"
        "\"m3\":{\"error\":%d,\"setup_us\":%lu,\"sent\":%lu,\"received\":%lu,\"requests\":%lu,"
        "\"jobs\":%lu,\"rows\":%lu,\"vectors\":%lu,\"max_slice_us\":%lu,\"context_bytes\":%lu,"
        "\"uart_errors\":%lu,\"unload_failures\":%lu}}",
        (unsigned long)r.kv_checksum,(unsigned long)r.remote_jobs,(unsigned long)r.remote_rows,(unsigned long)r.remote_fallbacks,
        (unsigned long long)r.remote_prepare_us,(unsigned long long)r.remote_submit_us,(unsigned long long)r.remote_wait_us,
        r.m3.error,(unsigned long)r.m3.setup_us,(unsigned long)r.m3.sent,(unsigned long)r.m3.received,(unsigned long)r.m3.requests,
        (unsigned long)r.m3.jobs,(unsigned long)r.m3.rows,(unsigned long)r.m3.vectors,(unsigned long)r.m3.max_slice_us,
        (unsigned long)r.m3.context_bytes,(unsigned long)r.m3.uart_errors,(unsigned long)r.m3.unload_failures);
  }
  append("],\"freeze_count\":%u,\"thaw_count\":%u,\"freeze_violations\":%u,\"worker_jobs\":%u,\"worker_max_us\":%u,"
      "\"i2c_errors\":%u,\"stress_iterations\":%u,\"control_probe_calls\":%u,\"heap_capacity\":%lu,\"sampled_heap_peak\":%lu,"
      "\"stack_high_water\":%lu,\"service_gap_us\":%lu,\"cancel_return_us\":%lu,\"model_load_us\":%lu,"
      "\"psram_read_bytes\":%llu,\"psram_write_bytes\":%llu}",freeze_count,thaw_count,freeze_violations,
      worker_jobs,worker_max_us,i2c_errors,stress_iterations,control_probe_calls,(unsigned long)heap_capacity,(unsigned long)heap_peak,
      (unsigned long)stack_peak,(unsigned long)service_gap,(unsigned long)cancel_return_us,(unsigned long)model_load_us,
      (unsigned long long)(psram_reads-reads_before),(unsigned long long)(psram_writes-writes_before));
  char path[128];std::snprintf(path,sizeof(path),"%s/PERF.JSON",directory);
  const bool saved=fits && files::write(path,reinterpret_cast<const u8*>(json.get()),used);
  return ok && saved?0:3;
}
AI_COLD_CODE unsigned UI::run() {
  bool directories = files::ready();
  for (const char *path : {"/AI", "/AI/SESSIONS", "/AI/Exports"}) {
    files::Entry e{};
    if (directories)
      directories = files::exists(path) ? files::stat(path, e) && e.directory
                                        : files::mkdir(path);
  }
  if (!directories) {
    row(0, M8("Нужна доступная SD-карта."));
    host.api->key_wait();
    return 3;
  }
  display(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT);
  rows = host.api->display_rows();
  width = display(MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH);
  if (host.api->graphics_width() != 320 || host.api->graphics_height() != 320 ||
      rows < 8) {
    row(0, M8("Нужен PicoCalc и шрифт до 32 px."));
    host.api->key_wait();
    return 1;
  }
  mk61_service_text_event event{};
  event.layout = 1;
  if (!call(MK61_SERVICE_TEXT_INPUT, MK61_TEXT_BEGIN, 0, sizeof(event), &event))
    return 3;
  begin_measurements();
  if (benchmarking) {
    const auto result = bench();
    call(MK61_SERVICE_TEXT_INPUT, MK61_TEXT_END);
    display(MK61_SERVICE_DISPLAY_END_UI_TEXT);
    return result;
  }
  if (host.initial_file) {
    unsigned n = 0;
    std::unique_ptr<u8[]> buffer(new (std::nothrow) u8[SESSION_BYTES]);
    if (buffer &&
        store_read(nullptr, host.initial_file, buffer.get(), SESSION_BYTES,
                   n) &&
        decode_session(buffer.get(), n, s)) {
      char canonical[96];
      std::snprintf(canonical, sizeof(canonical), "/AI/SESSIONS/%08lu.AIS",
                    (unsigned long)s.id);
      bool ok = true;
      if (std::strcmp(host.initial_file, canonical)) {
        s.id = unused_id();
        s.event = 0;
        s.last_version = s.program.size ? 1 : 0;
        s.program.version = s.last_version;
        invalidate(s);
        ok = s.id && (!s.program.size || archive_program(store, s)) &&
             save_session(store, s);
        if (ok)
          message(M8("Импортирована задача с текущей версией."));
      }
      if (ok) {
        screen = s.form_kind ? Screen::FORM : Screen::SESSION;
        typing = s.form_kind || s.view == 0;
        cursor = unsigned(std::strlen(s.form_kind ? s.form : s.draft));
        follow_cursor = true;
      } else {
        s.id = 0;
        message(M8("Не удалось импортировать задачу на SD."));
      }
    } else
      message(M8("Файл задачи повреждён или несовместим."));
  }
  scan_sessions();
  while (!quit) {
    pump();
    tick();
    if (dirty && draw_due(host.api->millis_ms()))
      draw();
    if (!agent.active() && !loading) {
      const auto now = host.api->millis_ms();
      while (host.api->millis_ms() - now < 4) {
        if (!pump() || agent.active() || dirty)
          break;
      }
    }
  }
  call(MK61_SERVICE_TEXT_INPUT, MK61_TEXT_END);
  end_chat_graphics();
  display(MK61_SERVICE_DISPLAY_END_UI_TEXT);
  return 0;
}
} // namespace
unsigned run(const Host &host) {
  if (!host.api || !host.services || !host.key)
    return 1;
  std::unique_ptr<UI> app(new (std::nothrow) UI(host));
  if (!app) {
    host.api->display_clear();
    host.api->display_write_m8(0, 0, "AI: not enough RAM", 18);
    host.api->key_wait();
    return 3;
  }
  const auto result = app->run();
  allocation_observer(nullptr, nullptr);
  return result;
}
unsigned benchmark(const Host &host) {
  if (!host.api || !host.services || !host.key)
    return 1;
  std::unique_ptr<UI> app(new (std::nothrow) UI(host));
  if (!app)
    return 3;
  app->benchmarking = true;
  const auto result = app->run();
  allocation_observer(nullptr, nullptr);
  return result;
}
} // namespace picocalc::ai
