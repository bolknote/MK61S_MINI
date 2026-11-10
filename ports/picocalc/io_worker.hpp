#ifndef MK61_PICOCALC_IO_WORKER_HPP
#define MK61_PICOCALC_IO_WORKER_HPP
#include "rust_types.h"
#include "worker_deadline_trace.hpp"

namespace picocalc::io_worker {
struct Statistics { bool running;u32 transactions,uart_bytes,uart_wait_us,uart_flush_us,uart_flushes,idle_us;bool uart_dma;u32 uart_event_waits,uart_sleep_holds,uart_baud;
    u32 i2c_irqs,i2c_timeouts,i2c_aborts,i2c_busy_us,i2c_sleep_holds;
    u32 compute_jobs,compute_us,compute_max_us,display_frames,display_refused; };
void start();
bool request_i2c(bool read,const u8* bytes,unsigned length);
bool take_i2c(int& result,u8* bytes=nullptr);
int blocking_i2c(bool read,u8* bytes,unsigned length);
bool frame_pending();
bool input_ready();
bool submit_frame(void* context,void (*transfer)(void*));
// Presentation only: invoke(), keyboard/UART IRQs and compute jobs stay live.
// Suspension drains the last accepted frame before closing the LCD queue.
void suspend_frames(bool suspended);
bool frames_suspended();
// Core 1 calls this between LCD scanlines; keyboard and UART do not wait
// for a complete 320x320 RGB565 transfer.
// I2C transfers finish through IRQs; no LCD strip waits for bus clocks.
void service(bool allow_i2c=true);
// LCD DMA waits must retain the audio transport's short polling interval.
// RX uses DMA without per-byte IRQs, and TX may still have FIFO work pending.
void wait_for_progress();
// Core 0 drains outstanding peripheral work before reset/sleep/clock changes.
void drain();
// Core1 only: give back an entirely idle console TX DMA channel. UART
// output can reclaim it on demand or keep using its existing FIFO fallback.
// True also means no console DMA channel was reserved in the first place.
bool release_idle_uart_dma();
// Synchronous bounded setup/teardown on core 1, serialized with LCD work.
// Used to bind timer IRQ ownership; callbacks must not wait for core 0.
void invoke(void* context,void (*function)(void*));
// Core 0 only. One bounded SRAM-only calculation, never PSRAM/SD/LCD or
// foreground APIs. Interrupts stay enabled and I/O is serviced between jobs.
// The producer must join before changing/freeing any referenced memory.
bool submit_compute(void* context,void (*function)(void*));
void join_compute();
Statistics statistics();
// Nested core1 frame diagnostics. These are IRQ-enabled wall-clock scopes,
// never measurements of interrupt masking. Core0 calls leave the trace alone.
class FrameDeadlineScope {
    u32 previous_=0;
    WorkerDeadlineTrace::Step site_;
public:
    explicit FrameDeadlineScope(WorkerDeadlineTrace::Step site);
    ~FrameDeadlineScope();
    FrameDeadlineScope(const FrameDeadlineScope&)=delete;
    FrameDeadlineScope& operator=(const FrameDeadlineScope&)=delete;
};
struct DeadlineStatistics {u32 resets,fault_site,fault_age_us;};
// Arm/fire diagnostics retain the nonblocking current/fault publication;
// the older boot-lifetime maxima are intentionally omitted to save60B.
DeadlineStatistics deadline_statistics();
void note_audio_deadline();
}
#endif
