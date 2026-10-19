#include "io_worker.hpp"
#include "io_queue.hpp"
#include "hardware/i2c.h"
#include "hardware/uart.h"
#include "pico/flash.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include <atomic>
#include <cstring>
#if LIB_PICO_STDIO_UART
#include "pico/stdio/driver.h"
#include "pico/stdio_uart.h"
#endif

namespace picocalc::io_worker {
namespace {
enum Stage : unsigned { IDLE,QUEUED,WORKING,DONE };
struct I2cJob {
    std::atomic<unsigned> stage{IDLE};
    bool read=false;unsigned length=0;u8 bytes[2]{};int result=0;
} i2c;
std::atomic<bool> ready{false},frame{false};
std::atomic<bool> uart_active{false};
std::atomic<u32> transactions{0},uart_bytes{0};
std::atomic<u32> uart_wait_us{0},uart_flush_us{0},uart_flushes{0};
void* frame_context=nullptr;
void (*frame_transfer)(void*)=nullptr;
IoQueue<char,1024> uart_queue;

void drain_uart() {
#if LIB_PICO_STDIO_UART
    uart_active.store(true,std::memory_order_relaxed);
    char byte;
    while(uart_is_writable(uart_default) && uart_queue.pop(byte)) {
        uart_putc_raw(uart_default,byte);
        uart_bytes.fetch_add(1,std::memory_order_relaxed);
    }
    uart_active.store(false,std::memory_order_release);
#endif
}
void uart_output(const char* bytes,int count) {
    for(int i=0;i<count;++i) {
        if(!uart_queue.push(bytes[i])) {
            const u64 start=time_us_64();
            while(!uart_queue.push(bytes[i])) { __sev();tight_loop_contents(); }
            uart_wait_us.fetch_add((u32)(time_us_64()-start),std::memory_order_relaxed);
        }
        __sev();
    }
}
void uart_flush() {
    const u64 start=time_us_64();
    while(!uart_queue.empty() || uart_active.load(std::memory_order_acquire)) { __sev();tight_loop_contents(); }
#if LIB_PICO_STDIO_UART
    uart_tx_wait_blocking(uart_default);
#endif
    uart_flush_us.fetch_add((u32)(time_us_64()-start),std::memory_order_relaxed);
    uart_flushes.fetch_add(1,std::memory_order_relaxed);
}
void worker() {
    flash_safe_execute_core_init();
    ready.store(true,std::memory_order_release);__sev();
    for(;;) {
        service();
        if(frame.load(std::memory_order_acquire)) {
            frame_transfer(frame_context);
            frame.store(false,std::memory_order_release);__sev();
        }
        if(!frame.load(std::memory_order_acquire) && uart_queue.empty() &&
           i2c.stage.load(std::memory_order_acquire)!=QUEUED) __wfe();
    }
}
}
void start() {
    if(ready.load(std::memory_order_acquire)) return;
    flash_safe_execute_core_init();
    multicore_launch_core1(worker);
    while(!ready.load(std::memory_order_acquire)) __wfe();
#if LIB_PICO_STDIO_UART
    // Preserve the SDK's pins, baud rate, CRLF handling, RX IRQ and input
    // callbacks. Only its blocking TX callback becomes a lossless queue.
    stdio_uart.out_chars=uart_output;
    stdio_uart.out_flush=uart_flush;
#endif
}
bool request_i2c(bool read,const u8* bytes,unsigned length) {
    if(!ready.load(std::memory_order_acquire) || !length || length>sizeof(i2c.bytes) ||
       (!read && !bytes) || i2c.stage.load(std::memory_order_acquire)!=IDLE) return false;
    i2c.read=read;i2c.length=length;
    if(!read) std::memcpy(i2c.bytes,bytes,length);
    i2c.stage.store(QUEUED,std::memory_order_release);__sev();return true;
}
bool take_i2c(int& result,u8* bytes) {
    if(i2c.stage.load(std::memory_order_acquire)!=DONE) return false;
    result=i2c.result;
    if(bytes && result>0) std::memcpy(bytes,i2c.bytes,(unsigned)result);
    i2c.stage.store(IDLE,std::memory_order_release);return true;
}
int blocking_i2c(bool read,u8* bytes,unsigned length) {
    if(!request_i2c(read,bytes,length)) return -1;
    int result;
    while(!take_i2c(result,read?bytes:nullptr)) __wfe();
    return result;
}
bool frame_pending() { return frame.load(std::memory_order_acquire); }
bool submit_frame(void* context,void (*transfer)(void*)) {
    if(!ready.load(std::memory_order_acquire) || frame_pending()) return false;
    frame_context=context;frame_transfer=transfer;
    frame.store(true,std::memory_order_release);__sev();return true;
}
void service() {
    drain_uart();
    if(i2c.stage.load(std::memory_order_acquire)!=QUEUED) return;
    i2c.stage.store(WORKING,std::memory_order_release);
    i2c.result=i2c.read?
        i2c_read_timeout_us(i2c1,0x1F,i2c.bytes,i2c.length,false,10000):
        i2c_write_timeout_us(i2c1,0x1F,i2c.bytes,i2c.length,false,10000);
    transactions.fetch_add(1,std::memory_order_relaxed);
    i2c.stage.store(DONE,std::memory_order_release);__sev();
    drain_uart();
}
void drain() {
    if(!ready.load(std::memory_order_acquire)) return;
    while(frame_pending() || i2c.stage.load(std::memory_order_acquire)==QUEUED ||
          i2c.stage.load(std::memory_order_acquire)==WORKING) { __sev();tight_loop_contents(); }
    uart_flush();
}
Statistics statistics() {
    return {ready.load(std::memory_order_acquire),transactions.load(std::memory_order_relaxed),
        uart_bytes.load(std::memory_order_relaxed),uart_wait_us.load(std::memory_order_relaxed),
        uart_flush_us.load(std::memory_order_relaxed),uart_flushes.load(std::memory_order_relaxed)};
}
}
