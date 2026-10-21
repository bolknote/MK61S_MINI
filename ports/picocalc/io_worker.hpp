#ifndef MK61_PICOCALC_IO_WORKER_HPP
#define MK61_PICOCALC_IO_WORKER_HPP
#include "rust_types.h"

namespace picocalc::io_worker {
struct Statistics { bool running;u32 transactions,uart_bytes,uart_wait_us,uart_flush_us,uart_flushes,idle_us;bool uart_dma;u32 uart_event_waits,uart_sleep_holds,uart_baud; };
void start();
bool request_i2c(bool read,const u8* bytes,unsigned length);
bool take_i2c(int& result,u8* bytes=nullptr);
int blocking_i2c(bool read,u8* bytes,unsigned length);
bool frame_pending();
bool input_ready();
bool submit_frame(void* context,void (*transfer)(void*));
// Core 1 calls this between LCD scanlines; keyboard and UART do not wait
// for a complete 320x320 RGB565 transfer.
// UART remains serviced when short LCD windows defer blocking I2C briefly.
void service(bool allow_i2c=true);
// Core 0 drains outstanding peripheral work before reset/sleep/clock changes.
void drain();
Statistics statistics();
}
#endif
