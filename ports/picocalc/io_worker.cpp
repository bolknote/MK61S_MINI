#include "io_worker.hpp"
#include "io_queue.hpp"
#include "dma_support.hpp"
#include "event_wait.hpp"
#include "sleep_clock_lease.hpp"
#include "console_route.hpp"
#include "i2c_transfer.hpp"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/i2c.h"
#include "hardware/irq.h"
#include "hardware/timer.h"
#include "hardware/uart.h"
#include "pico/flash.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include <atomic>
#include <cstring>
#include <optional>
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
std::atomic<u32> i2c_irqs{0},i2c_timeouts{0},i2c_aborts{0},i2c_busy_us{0};
std::atomic<u32> i2c_sleep_holds{0};
struct WorkerClockRegisters {
    static u32 read0() { return clocks_hw->sleep_en0; }
    static u32 read1() { return clocks_hw->sleep_en1; }
    static void set0(u32 bits) { hw_set_bits(&clocks_hw->sleep_en0,bits); }
    static void set1(u32 bits) { hw_set_bits(&clocks_hw->sleep_en1,bits); }
    static void clear0(u32 bits) { hw_clear_bits(&clocks_hw->sleep_en0,bits); }
    static void clear1(u32 bits) { hw_clear_bits(&clocks_hw->sleep_en1,bits); }
};
std::optional<SleepClockLease<WorkerClockRegisters>> i2c_sleep_clocks;
I2cTransfer i2c_transfer;
int i2c_alarm=-1;
struct I2cBus {
    void prepare(bool read) {
        auto* hw=i2c_get_hw(i2c1);
        hw->intr_mask=0;hw->enable=0;hw->tar=0x1F;
        (void)hw->clr_intr;
        while(hw->rxflr) (void)hw->data_cmd;
        hw->rx_tl=0;hw->enable=1;
        hw->intr_mask=I2C_IC_INTR_MASK_M_STOP_DET_BITS|I2C_IC_INTR_MASK_M_TX_ABRT_BITS|
            I2C_IC_INTR_MASK_M_RX_OVER_BITS|(read?I2C_IC_INTR_MASK_M_RX_FULL_BITS:0);
    }
    void put(unsigned command) { i2c_get_hw(i2c1)->data_cmd=command; }
    unsigned flags() {
        const auto flags=i2c_get_hw(i2c1)->raw_intr_stat;
        return ((flags&I2C_IC_RAW_INTR_STAT_STOP_DET_BITS)?I2cTransfer::STOP:0)|
            ((flags&I2C_IC_RAW_INTR_STAT_TX_ABRT_BITS)?I2cTransfer::ABORT:0)|
            ((flags&I2C_IC_RAW_INTR_STAT_RX_OVER_BITS)?I2cTransfer::RX_OVERFLOW:0);
    }
    bool available() { return i2c_get_hw(i2c1)->rxflr!=0; }
    u8 get() { return (u8)i2c_get_hw(i2c1)->data_cmd; }
    void finish(bool failed) {
        auto* hw=i2c_get_hw(i2c1);hw->intr_mask=0;(void)hw->clr_intr;
        // A timed-out/stretched bus must not hold a job alive or leave FIFO
        // bytes for the next one. Reset only this dedicated master instance.
        if(failed) {
            i2c_init(i2c1,10000);
            // Reset restores TX_EMPTY's interrupt mask too. Keep the idle
            // master silent until prepare() enables this job's sources.
            i2c_get_hw(i2c1)->intr_mask=0;
        }
    }
} i2c_bus;
void finish_i2c() {
    if(i2c.stage.load(std::memory_order_acquire)!=WORKING ||
       !i2c_transfer.step(i2c_bus,time_us_64())) return;
    if(i2c_alarm>=0) hardware_alarm_cancel((unsigned)i2c_alarm);
    i2c.result=i2c_transfer.result();
    if(i2c.read && i2c.result>0) std::memcpy(i2c.bytes,i2c_transfer.bytes(),(unsigned)i2c.result);
    transactions.fetch_add(1,std::memory_order_relaxed);
    i2c_busy_us.fetch_add(i2c_transfer.elapsed(),std::memory_order_relaxed);
    if(i2c_transfer.timed_out()) i2c_timeouts.fetch_add(1,std::memory_order_relaxed);
    if(i2c_transfer.aborted()) i2c_aborts.fetch_add(1,std::memory_order_relaxed);
    i2c_sleep_clocks.reset();
    i2c.stage.store(DONE,std::memory_order_release);__sev();
}
void i2c_irq() { i2c_irqs.fetch_add(1,std::memory_order_relaxed);finish_i2c(); }
void i2c_timeout(unsigned) { finish_i2c(); }
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
    return SleepClockLease<WorkerClockRegisters>(memory,uart);
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
// SDK stdio_flush visits every driver even when stdio_filter_driver selects
// USB. Its implicit printf flush must not wait for a separate UART stream.
// drain() still calls uart_flush directly at clock/sleep/reset boundaries.
void uart_stdio_flush() { if(console::routing.uart_output_enabled()) uart_flush(); }
void worker() {
    flash_safe_execute_core_init();
    i2c_alarm=hardware_alarm_claim_unused(false);
    if(i2c_alarm>=0) hardware_alarm_set_callback((unsigned)i2c_alarm,i2c_timeout);
    // SDK i2c_init leaves the reset interrupt mask (including TX_EMPTY).
    // An empty FIFO would otherwise interrupt forever before ready=true.
    i2c_get_hw(i2c1)->intr_mask=0;
    irq_set_exclusive_handler(I2C1_IRQ,i2c_irq);irq_set_enabled(I2C1_IRQ,true);
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
            const u64 started=time_us_64();
            if(i2c.stage.load(std::memory_order_acquire)==WORKING && i2c_alarm<0)
                best_effort_wfe_or_timeout(make_timeout_time_us(1000));
            else __wfe();
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
    stdio_uart.out_flush=uart_stdio_flush;
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
void service(bool allow_i2c) {
    drain_uart();
    (void)allow_i2c; // Starting the FIFO is bounded even for tiny LCD windows.
    const u32 interrupts=save_and_disable_interrupts();
    finish_i2c();
    if(i2c.stage.load(std::memory_order_acquire)==QUEUED) {
        i2c.stage.store(WORKING,std::memory_order_release);
        // Both cores may WFE while the FIFO shifts. Retain I2C1's clock
        // until STOP/error cleanup, before publishing DONE to clock changes.
        i2c_sleep_clocks.emplace(CLOCKS_SLEEP_EN0_CLK_SYS_I2C1_BITS,0);
        if(i2c_sleep_clocks->temporary()) i2c_sleep_holds.fetch_add(1,std::memory_order_relaxed);
        i2c_transfer.begin(i2c_bus,i2c.read,i2c.bytes,i2c.length,time_us_64());
        if(i2c_alarm>=0) hardware_alarm_set_target((unsigned)i2c_alarm,from_us_since_boot(i2c_transfer.deadline()));
    }
    restore_interrupts(interrupts);
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
        uart_event_waits.load(std::memory_order_relaxed),uart_sleep_holds.load(std::memory_order_relaxed),baud,
        i2c_irqs.load(std::memory_order_relaxed),i2c_timeouts.load(std::memory_order_relaxed),
        i2c_aborts.load(std::memory_order_relaxed),i2c_busy_us.load(std::memory_order_relaxed),
        i2c_sleep_holds.load(std::memory_order_relaxed)};
}
}
