#include "io_worker.hpp"
#include "io_queue.hpp"
#include "dma_support.hpp"
#include "event_wait.hpp"
#include "sleep_clock_lease.hpp"
#include "hardware/clocks.h"
#include "hardware/dma.h"
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
std::atomic<u32> idle_us{0},uart_event_waits{0};
std::atomic<u32> uart_sleep_holds{0};
std::atomic<int> uart_dma_channel{-1};
u8 uart_buffer[64]{};
unsigned uart_inflight=0;
void* frame_context=nullptr;
void (*frame_transfer)(void*)=nullptr;
IoQueue<char,1024> uart_queue;
#if LIB_PICO_STDIO_UART
struct UartClockRegisters {
    static u32 read0() { return clocks_hw->sleep_en0; }
    static u32 read1() { return clocks_hw->sleep_en1; }
    static void set0(u32 bits) { hw_set_bits(&clocks_hw->sleep_en0,bits); }
    static void set1(u32 bits) { hw_set_bits(&clocks_hw->sleep_en1,bits); }
    static void clear0(u32 bits) { hw_clear_bits(&clocks_hw->sleep_en0,bits); }
    static void clear1(u32 bits) { hw_clear_bits(&clocks_hw->sleep_en1,bits); }
};
auto uart_clocks() {
    // WFE can gate UART before the final stop bit, and DMA can wait for its
    // DREQ. Keep the transport and its striped SRAM source alive only while
    // sending a diagnostic in clock-gated sleep. Clock transitions drain it.
    constexpr u32 memory=CLOCKS_SLEEP_EN0_CLK_SYS_DMA_BITS |
        CLOCKS_SLEEP_EN0_CLK_SYS_BUSFABRIC_BITS |
        CLOCKS_SLEEP_EN0_CLK_SYS_SRAM0_BITS | CLOCKS_SLEEP_EN0_CLK_SYS_SRAM1_BITS |
        CLOCKS_SLEEP_EN0_CLK_SYS_SRAM2_BITS | CLOCKS_SLEEP_EN0_CLK_SYS_SRAM3_BITS;
    const u32 uart=uart_default==uart0?
        CLOCKS_SLEEP_EN1_CLK_SYS_UART0_BITS | CLOCKS_SLEEP_EN1_CLK_PERI_UART0_BITS:
        CLOCKS_SLEEP_EN1_CLK_SYS_UART1_BITS | CLOCKS_SLEEP_EN1_CLK_PERI_UART1_BITS;
    return SleepClockLease<UartClockRegisters>(memory,uart);
}
#endif

void drain_uart() {
#if LIB_PICO_STDIO_UART
    static bool attempted=false;
    if(!attempted) {
        attempted=true;
        const int channel=dma_claim_unused_channel(false);
        if(channel>=0) dma_support::enable_irq((unsigned)channel);
        uart_dma_channel.store(channel,std::memory_order_release);
    }
    const int channel=uart_dma_channel.load(std::memory_order_relaxed);
    if(channel>=0) {
        if(dma_channel_is_busy((unsigned)channel)) return;
        const bool completed=uart_inflight!=0;
        if(uart_inflight) {
            uart_bytes.fetch_add(uart_inflight,std::memory_order_relaxed);
            uart_inflight=0;
        }
        uart_active.store(true,std::memory_order_release);
        char byte;
        while(uart_inflight<sizeof(uart_buffer) && uart_queue.pop(byte))
            uart_buffer[uart_inflight++]=(u8)byte;
        uart_active.store(uart_inflight!=0,std::memory_order_release);
        // Publish freed space even if the previous DMA IRQ happened before
        // the producer observed the full queue.
        if(completed || uart_inflight) __sev();
        if(!uart_inflight) return;
        auto config=dma_channel_get_default_config((unsigned)channel);
        channel_config_set_transfer_data_size(&config,DMA_SIZE_8);
        channel_config_set_read_increment(&config,true);
        channel_config_set_write_increment(&config,false);
        channel_config_set_dreq(&config,uart_get_dreq(uart_default,true));
        dma_channel_configure((unsigned)channel,&config,&uart_get_hw(uart_default)->dr,
            uart_buffer,uart_inflight,true);
        return;
    }
    uart_active.store(true,std::memory_order_relaxed);
    bool progress=false;
    char byte;
    while(uart_is_writable(uart_default) && uart_queue.pop(byte)) {
        uart_putc_raw(uart_default,byte);
        uart_bytes.fetch_add(1,std::memory_order_relaxed);
        progress=true;
    }
    uart_active.store(false,std::memory_order_release);
    if(progress) __sev();
#endif
}
template<class Pending> void wait_uart(Pending pending) {
    const auto waits=event_wait(pending,[] { __sev();__wfe(); },[] {
        best_effort_wfe_or_timeout(make_timeout_time_us(1000));
    });
    uart_event_waits.fetch_add(waits,std::memory_order_relaxed);
}
void uart_flush();
void uart_output(const char* bytes,int count) {
#if LIB_PICO_STDIO_UART
    auto clocks=uart_clocks();
    if(clocks.temporary()) uart_sleep_holds.fetch_add(1,std::memory_order_relaxed);
#endif
    for(int i=0;i<count;++i) {
        if(!uart_queue.push(bytes[i])) {
            const u64 start=time_us_64();
            wait_uart([&] { return !uart_queue.push(bytes[i]); });
            uart_wait_us.fetch_add((u32)(time_us_64()-start),std::memory_order_relaxed);
        }
        __sev();
    }
#if LIB_PICO_STDIO_UART
    // putchar/raw writes need not call stdio_flush. Finish their wire data
    // before returning the temporary clocks to the sleep policy as well.
    if(clocks.temporary()) uart_flush();
#endif
}
void uart_flush() {
#if LIB_PICO_STDIO_UART
    auto clocks=uart_clocks();
#endif
    const u64 start=time_us_64();
    __sev();
    wait_uart([] { return !uart_queue.empty() || uart_active.load(std::memory_order_acquire); });
#if LIB_PICO_STDIO_UART
    // BUSY includes the final stop bit, unlike DMA/FIFO completion.
    // A timer bounds the wait without replacing the SDK RX IRQ handler.
    wait_uart([] { return (uart_get_hw(uart_default)->fr&UART_UARTFR_BUSY_BITS)!=0; });
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
        if(!frame.load(std::memory_order_acquire) &&
           (uart_queue.empty() || uart_active.load(std::memory_order_acquire)) &&
           i2c.stage.load(std::memory_order_acquire)!=QUEUED) {
            const u64 started=time_us_64();__wfe();
            idle_us.fetch_add((u32)(time_us_64()-started),std::memory_order_relaxed);
        } else if(!frame.load(std::memory_order_acquire) &&
                  uart_dma_channel.load(std::memory_order_relaxed)<0 &&
                  i2c.stage.load(std::memory_order_acquire)!=QUEUED) {
            // If DMA allocation failed, the UART FIFO still drains in
            // hardware. Poll it from a bounded sleep instead of spinning.
            const u64 started=time_us_64();
            best_effort_wfe_or_timeout(make_timeout_time_us(100));
            idle_us.fetch_add((u32)(time_us_64()-started),std::memory_order_relaxed);
        }
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
bool input_ready() { return i2c.stage.load(std::memory_order_acquire)==DONE; }
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
    u32 baud=0;
#if LIB_PICO_STDIO_UART
    const auto* uart=uart_get_hw(uart_default);
    const u32 divisor=uart->ibrd*64+uart->fbrd;
    if(divisor) baud=clock_get_hz(clk_peri)*4/divisor;
#endif
    return {ready.load(std::memory_order_acquire),transactions.load(std::memory_order_relaxed),
        uart_bytes.load(std::memory_order_relaxed),uart_wait_us.load(std::memory_order_relaxed),
        uart_flush_us.load(std::memory_order_relaxed),uart_flushes.load(std::memory_order_relaxed),
        idle_us.load(std::memory_order_relaxed),uart_dma_channel.load(std::memory_order_relaxed)>=0,
        uart_event_waits.load(std::memory_order_relaxed),uart_sleep_holds.load(std::memory_order_relaxed),baud};
}
}
