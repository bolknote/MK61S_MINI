#include "ai_m3.hpp"
#include "m3_audio.hpp"
#include "io_worker.hpp"
#include "storage.hpp"
#include "sleep_clock_lease.hpp"
#include "stm3_module.h"
#include "stm3_client.h"
#include "pico_uart1.h"
#include "../../examples/portable-apps/MK61AI/m3_linear_protocol.h"
#include "hardware/clocks.h"
#include "hardware/structs/clocks.h"
#include "hardware/sync.h"
#include "hardware/irq.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <new>
#include <optional>

namespace picocalc::ai_m3 {
namespace {
struct Clocks {
  static uint32_t read0() { return clocks_hw->sleep_en0; }
  static uint32_t read1() { return clocks_hw->sleep_en1; }
  static void set0(uint32_t v) { hw_set_bits(&clocks_hw->sleep_en0, v); }
  static void set1(uint32_t v) { hw_set_bits(&clocks_hw->sleep_en1, v); }
  static void clear0(uint32_t v) { hw_clear_bits(&clocks_hw->sleep_en0, v); }
  static void clear1(uint32_t v) { hw_clear_bits(&clocks_hw->sleep_en1, v); }
};
struct Context {
  stm3_client client{};
  stm3_pico_uart1 uart{};
  std::optional<SleepClockLease<Clocks>> clocks;
  alignas(4) uint8_t packet[512]{}, reply[252]{};
  Statistics stats{};
  mk61ai::LinearBatch *batch = nullptr;
  uint32_t module = 0, job = 0;
  unsigned columns = 0, capacity = 0;
  uint32_t magic = AI_M3_MAGIC;
  bool owned = false, failed = false, running = false, start_pending = false;
  bool start_result = false, async_result = false;
  uint8_t rx[512]{};
  volatile uint32_t rx_head = 0, rx_tail = 0, rx_errors = 0;
  uint32_t rx_error_seen = 0;
  unsigned irq_priority = 0;
  bool irq_owned = false;
};
Context *context = nullptr;
Statistics last{};
uint16_t last_sequence = 0;
uint32_t micros(void *) { return time_us_32(); }
// A STATUS reply exceeds the hardware FIFO. Drain it even while a USB/timer
// interrupt or the other compute worker delays the foreground receiver.
void uart_rx_irq() {
  auto *c = context;
  if (!c || !c->irq_owned) return;
  while (uart_is_readable(uart1)) {
    const int value = stm3_pico_uart1_read(&c->uart, 1);
    if (value < 0) { ++c->rx_errors; continue; }
    const uint32_t head = c->rx_head;
    if (head - c->rx_tail == sizeof(c->rx)) { ++c->rx_errors; continue; }
    c->rx[head & (sizeof(c->rx)-1)] = uint8_t(value);
    __dmb(); c->rx_head = head + 1;
  }
}
int buffered_send(void *raw,const uint8_t *bytes,unsigned n,uint32_t timeout) {
  auto &c = *static_cast<Context *>(raw);
  return stm3_pico_uart1_send(&c.uart,bytes,n,timeout);
}
int buffered_read(void *raw,uint32_t timeout) {
  auto &c = *static_cast<Context *>(raw);
  const auto started = time_us_32();
  while(c.rx_head == c.rx_tail) {
    if(c.rx_errors != c.rx_error_seen) { c.rx_error_seen = c.rx_errors; return -2; }
    if(time_us_32()-started >= timeout) return -1;
  }
  if(c.rx_errors != c.rx_error_seen) { c.rx_error_seen = c.rx_errors; return -2; }
  const uint32_t tail = c.rx_tail;
  const int value = c.rx[tail & (sizeof(c.rx)-1)];
  __dmb(); c.rx_tail = tail + 1;
  return value;
}
bool fail(Context &c, int error) {
  if (!c.stats.error) c.stats.error = error;
  c.failed = true; return false;
}
bool rpc(Context &c, uint8_t command, const void *data, unsigned n, unsigned expected) {
  unsigned used = sizeof(c.reply);
  // The keyboard resident also services bounded foreground board I/O. Waiting
  // here is timed as transport; a pause must not become a lost remote job.
  int result = stm3_client_request(&c.client, command, data, n, c.reply, &used, 500000);
  // Identical cached request, including START: a lost reply must not repeat
  // module execution. A late partial frame may require one more replay.
  for(unsigned retries=0;result<0 && retries<2;++retries) {
    used=sizeof(c.reply);
    result=stm3_client_replay(&c.client,c.reply,&used,500000);
  }
  if (result || used != expected) return fail(c, result ? result : -10);
  return true;
}
bool hello(Context &c) { return rpc(c, S3_HELLO, nullptr, 0, 36); }
bool write(Context &c, uint8_t command, unsigned at, const uint8_t *p, unsigned n) {
  /* Separate reply buffer keeps packet/vector bytes intact across requests. */
  uint8_t args[256];
  stm3_put32(args, at); std::memcpy(args + 4, p, n);
  return rpc(c, command, args, n + 4, command == S3_LOAD_CHUNK ? 4 : 0);
}
bool stage(Context &c, unsigned n) {
  for (unsigned at = 0; at < n;) {
    const unsigned take = std::min(252U, n - at);
    if (!write(c, S3_WRITE, at, c.packet + at, take)) return false;
    at += take;
  }
  return true;
}
bool start(Context &c, unsigned n) {
  if(!stage(c,n)) return false;
  uint8_t args[12];
  stm3_put32(args, c.module); stm3_put32(args + 4, n); stm3_put32(args + 8, 1000);
  // Job IDs survive UNLOAD. Until the reply arrives, even the first job ID is
  // unknown; cleanup waits for its resident deadline instead of guessing it.
  c.start_pending = true;
  if (!rpc(c, S3_START, args, sizeof(args), 4)) return false;
  c.job = stm3_get32(c.reply); c.start_pending = false; c.running = true;
  return true;
}
bool read(Context &c, unsigned bytes) {
  uint8_t args[12];
  stm3_put32(args, c.job); stm3_put32(args + 4, 0); stm3_put32(args + 8, bytes);
  if (!rpc(c, S3_READ, args, sizeof(args), bytes)) return false;
  c.running = false; return true;
}
bool immediate(Context &c, unsigned bytes, unsigned received) {
  if(c.start_result) {
    if(!stage(c,bytes)) return false;
    uint8_t args[16];stm3_put32(args,c.module);stm3_put32(args+4,bytes);
    stm3_put32(args+8,1000);stm3_put32(args+12,12);
    c.start_pending=true;
    if(!rpc(c,S3_START_RESULT,args,sizeof(args),20)) return false;
    c.start_pending=false;c.job=stm3_get32(c.reply);
    c.stats.max_slice_us=std::max(c.stats.max_slice_us,stm3_get32(c.reply+4));
    return (c.job && stm3_get32(c.reply+8)==c.magic && stm3_get32(c.reply+12)==c.columns &&
            stm3_get32(c.reply+16)==received) || fail(c,-11);
  }
  if (!start(c, bytes) || !read(c, 12)) return false;
  return (stm3_get32(c.reply) == c.magic && stm3_get32(c.reply + 4) == c.columns &&
          stm3_get32(c.reply + 8) == received) || fail(c, -11);
}
bool load(Context &c, const char *path) {
  files::Entry entry{}; unsigned used = 0;
  if (!path || !files::stat(path, entry) || entry.directory || entry.size < 64 ||
      entry.size > STM3_PACKAGE_CAPACITY ||
      !files::read_range(path, 0, c.packet, 64, used) || used != 64) return fail(c, -12);
  if (stm3_get32(c.packet) != STM3_MAGIC || stm3_get32(c.packet + 4) != STM3_ABI ||
      stm3_get32(c.packet + 8) != 64 || stm3_get32(c.packet + 12) != entry.size ||
      stm3_get32(c.packet + 56) != STM3_TARGET) return fail(c, -13);
  if (!hello(c)) return false;
  const auto *h = c.reply;
  if (stm3_get32(h) != STM3_ABI || stm3_get32(h + 4) != STM3_TARGET ||
      stm3_get32(h + 8) != STM3_IMAGE_CAPACITY || stm3_get32(h + 12) != STM3_IO_CAPACITY ||
      stm3_get32(h + 16) != 0 || stm3_get32(h + 28) != 2250000 ||
      (stm3_get32(h + 32) & 3U) != 3U) return fail(c, -14);
  c.start_result=(stm3_get32(h+32)&S3_TRANSPORT_START_RESULT)!=0;
  stm3_put32(c.packet, entry.size);
  c.owned = true; // EMPTY + exclusive UART claim, including lost LOAD_BEGIN ACK.
  if (!rpc(c, S3_LOAD_BEGIN, c.packet, 4, 0)) return false;
  for (unsigned at = 0; at < entry.size;) {
    const unsigned n = std::min(252U, unsigned(entry.size - at));
    if (!files::read_range(path, at, c.packet, n, used) || used != n) return fail(c, -12);
    if (!write(c, S3_LOAD_CHUNK, at, c.packet, n)) return false;
    if (stm3_get32(c.reply) != at + n) return fail(c, -15);
    at += n;
  }
  if (!rpc(c, S3_LOAD_COMMIT, nullptr, 0, 4)) return false;
  c.module = stm3_get32(c.reply); return true;
}
void snapshot(Context &c) {
  c.stats.sent = c.client.sent; c.stats.received = c.client.received;
  c.stats.requests = c.client.requests; c.stats.uart_errors = c.uart.errors + c.rx_errors;
  last = c.stats;
}
void drain(Context &c) {
  if (!c.owned) return;
  bool empty = false;
  // Use fresh sequence numbers after a partial/late reply. HELLO is read only.
  bool known = hello(c);
  if (!known) known = hello(c);
  if (known) {
    unsigned state = stm3_get32(c.reply + 16);
    if (state == 3) {
      if(!c.start_pending && c.job) {
        uint8_t arg[4]; stm3_put32(arg, c.job);
        (void)rpc(c, S3_CANCEL, arg, sizeof(arg), 0);
      } else {
        const auto started=time_us_32();
        while(state==3 && time_us_32()-started<1100000) {
          sleep_us(500);
          if(!hello(c)) break;
          state=stm3_get32(c.reply+16);
        }
      }
    }
    if (rpc(c, S3_UNLOAD, nullptr, 0, 0) && hello(c)) empty = stm3_get32(c.reply + 16) == 0;
  }
  if (!empty) ++c.stats.unload_failures;
  c.running = false; c.batch = nullptr;
}
}
bool open(const char *path) {
  if (context) return !context->failed;
  last = {};
  if (m3_audio::transport_active()) { last.error = -16; return false; }
  if (irq_is_enabled(UART1_IRQ) || irq_get_exclusive_handler(UART1_IRQ)) {
    last.error = -23; return false;
  }
  auto *c = new(std::nothrow) Context;
  if (!c) { last.error = -17; return false; }
  const auto started = time_us_32();
  c->stats.context_bytes = sizeof(Context);
  bool ready = false;
  struct Args { Context *c; bool *ready; } args{c, &ready};
  io_worker::invoke(&args, [](void *raw) {
    auto &a = *static_cast<Args *>(raw);
    if (!stm3_pico_uart1_begin(&a.c->uart, micros, nullptr, clock_get_hz(clk_peri), 2250000)) return;
    a.c->clocks.emplace(0, CLOCKS_SLEEP_EN1_CLK_SYS_UART1_BITS | CLOCKS_SLEEP_EN1_CLK_PERI_UART1_BITS);
    *a.ready = true;
  });
  if (!ready) { delete c; last.error = -18; return false; }
  context = c;
  c->irq_priority = irq_get_priority(UART1_IRQ);
  irq_set_exclusive_handler(UART1_IRQ, uart_rx_irq);
  irq_set_priority(UART1_IRQ, 0);
  c->irq_owned = true;
  irq_set_enabled(UART1_IRQ, true);
  uart_set_irq_enables(uart1, true, false);
  stm3_client_io io{c, micros, buffered_send, buffered_read};
  stm3_client_init(&c->client, &io);
  c->client.seq = uint16_t(last_sequence + 1);
  if (!load(*c, path)) { close(); return false; }
  c->stats.setup_us = time_us_32() - started; c->stats.active = true;
  return true;
}
void close() {
  auto *c = context; if (!c) return;
  drain(*c); snapshot(*c); last.active = false;
  last_sequence = c->client.seq;
  uart_set_irq_enables(uart1, false, false);
  irq_set_enabled(UART1_IRQ, false);
  irq_remove_handler(UART1_IRQ, uart_rx_irq);
  irq_set_priority(UART1_IRQ, c->irq_priority);
  c->irq_owned = false;
  io_worker::invoke(c, [](void *raw) {
    auto &c = *static_cast<Context *>(raw);
    stm3_pico_uart1_end(&c.uart); c.clocks.reset();
  });
  context = nullptr; delete c;
}
unsigned prepare(const mk61ai::LinearBatch *b) {
  auto *c = context;
  if (!c || c->failed || c->running || !b || b->bits != 4 || !b->columns ||
      b->columns % 32 || b->columns > AI_M3_MAX_COLUMNS) return 0;
  const bool integer = b->arithmetic == mk61ai::Arithmetic::INT8 && b->grid == 0;
  const bool fp32 = b->arithmetic == mk61ai::Arithmetic::LUT_FLOAT32 && b->grid == 256;
  if ((!integer && !fp32) || (integer ? (!b->quant || !b->activation_scales) : !b->input)) return 0;
  c->magic = integer ? AI_M3_INT8_MAGIC : AI_M3_MAGIC;
  c->columns = b->columns;
  // INT8 initially gives STM32 one tail row: 4+3+1, with all UART costs timed.
  c->capacity = std::min(integer ? 1U : 2U, (512U - AI_M3_HEADER) / (b->columns / 2U + b->columns / 16U));
  stm3_put32(c->packet, c->magic); stm3_put32(c->packet + 4, AI_M3_PREPARE);
  stm3_put32(c->packet + 8, c->columns); stm3_put32(c->packet + 12, 0);
  if (!immediate(*c, AI_M3_HEADER, 0)) { drain(*c);return 0; }
  const unsigned vector_bytes = integer ? c->columns * 9U / 8U : c->columns * 4U;
  for (unsigned at = 0; at < vector_bytes;) {
    const unsigned n = std::min(512U, vector_bytes - at);
    if (!integer) std::memcpy(c->packet, reinterpret_cast<const uint8_t *>(b->input) + at, n);
    else {
      const unsigned q = at < c->columns ? std::min(n,c->columns-at) : 0U;
      if (q) std::memcpy(c->packet,b->quant+at,q);
      if (q<n) std::memcpy(c->packet+q,reinterpret_cast<const uint8_t *>(b->activation_scales)+at+q-c->columns,n-q);
    }
    if (!immediate(*c, n, at + n)) { drain(*c);return 0; }
    at += n;
  }
  ++c->stats.vectors; return c->capacity;
}
bool submit(mk61ai::LinearBatch *b) {
  auto *c = context;
  if (!c || c->failed || c->running || !b || !b->rows || b->rows > c->capacity ||
      b->bits != 4 ||
      b->columns != c->columns || !b->weights || !b->scales || !b->output) return false;
  const bool integer = c->magic == AI_M3_INT8_MAGIC;
  if (integer ? (b->arithmetic != mk61ai::Arithmetic::INT8 || b->grid != 0) :
      (b->arithmetic != mk61ai::Arithmetic::LUT_FLOAT32 || b->grid != 256)) return false;
  stm3_put32(c->packet, c->magic); stm3_put32(c->packet + 4, AI_M3_RUN);
  stm3_put32(c->packet + 8, c->columns); stm3_put32(c->packet + 12, b->rows);
  const unsigned w = c->columns / 2, s = c->columns / 16;
  for (unsigned r = 0; r < b->rows; ++r) {
    std::memcpy(c->packet + AI_M3_HEADER + r * (w + s), b->weights + r * w, w);
    std::memcpy(c->packet + AI_M3_HEADER + r * (w + s) + w, b->scales + r * s, s);
  }
  const unsigned packet_bytes=AI_M3_HEADER+b->rows*(w+s);
  if(c->start_result) {
    if(!stage(*c,packet_bytes)) { drain(*c);return false; }
    uint8_t args[16];stm3_put32(args,c->module);stm3_put32(args+4,packet_bytes);
    stm3_put32(args+8,1000);stm3_put32(args+12,b->rows*4U);
    c->start_pending=true;
    const int error=stm3_client_begin(&c->client,S3_START_RESULT,args,sizeof(args),500000);
    if(error) { fail(*c,error);drain(*c);return false; }
    c->async_result=true;c->running=true;c->batch=b;return true;
  }
  if (!start(*c,packet_bytes)) {
    // Refusal promises no live remote job; draining also invalidates backend.
    drain(*c); return false;
  }
  c->batch = b; return true;
}
bool join() {
  auto *c = context;
  if (!c || !c->batch) return false;
  auto *b = c->batch; c->batch = nullptr;
  if(c->async_result) {
    unsigned used=sizeof(c->reply);
    int error=stm3_client_finish(&c->client,c->reply,&used,500000);
    for(unsigned retries=0;error<0&&retries<2;++retries) {
      used=sizeof(c->reply);error=stm3_client_replay(&c->client,c->reply,&used,500000);
    }
    if(error || used!=8+b->rows*4U) { fail(*c,error?error:-10);drain(*c);return false; }
    c->job=stm3_get32(c->reply);c->start_pending=false;c->running=false;c->async_result=false;
    c->stats.max_slice_us=std::max(c->stats.max_slice_us,stm3_get32(c->reply+4));
    float values[2];std::memcpy(values,c->reply+8,b->rows*4U);
    for(unsigned r=0;r<b->rows;++r)
      if(!std::isfinite(values[r])) { fail(*c,-21);drain(*c);return false; }
    std::memcpy(b->output,values,b->rows*4U);
    ++c->stats.jobs;c->stats.rows+=b->rows;return true;
  }
  uint8_t arg[4]; stm3_put32(arg, c->job);
  const auto started = time_us_32();
  for (;;) {
    if (!rpc(*c, S3_STATUS, arg, sizeof(arg), 28)) break;
    if (stm3_get32(c->reply) != c->job) { fail(*c, -19); break; }
    const unsigned state = stm3_get32(c->reply + 4);
    c->stats.max_slice_us = std::max(c->stats.max_slice_us, stm3_get32(c->reply + 24));
    if (state == 4) {
      if (stm3_get32(c->reply + 8) || stm3_get32(c->reply + 16) != b->rows * 4U ||
          stm3_get32(c->reply + 12) != c->columns / 32U) { fail(*c, -20); break; }
      if (!read(*c, b->rows * 4U)) break;
      float values[2]; std::memcpy(values, c->reply, b->rows * 4U);
      for (unsigned r = 0; r < b->rows; ++r)
        if (!std::isfinite(values[r])) { fail(*c, -21); drain(*c); return false; }
      std::memcpy(b->output, values, b->rows * 4U);
      ++c->stats.jobs; c->stats.rows += b->rows; return true;
    }
    if (state != 3 || time_us_32() - started > 1000000) { fail(*c, -22); break; }
  }
  drain(*c); return false;
}
Statistics statistics() {
  if (context) snapshot(*context);
  return last;
}
}
