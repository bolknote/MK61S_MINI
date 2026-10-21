#include "hardware.hpp"
#include "diagnostics.hpp"
#include "io_worker.hpp"
#include "crc32.hpp"
#include "dma_support.hpp"
#include "hardware/i2c.h"
#include "hardware/spi.h"
#include "hardware/dma.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"
#include <cstring>

namespace picocalc {
namespace {
constexpr unsigned DC = MK61_PICOCALC_LCD_DC_PIN;
constexpr unsigned RESET = MK61_PICOCALC_LCD_RESET_PIN;
constexpr unsigned CS = PICO_DEFAULT_SPI_CSN_PIN;
// The core 1 stack uses the upper 2 KiB of scratch X. Its otherwise unused
// lower half holds both DMA rows, preserving the main heap for viewers/APPs.
// NOLOAD scratch storage: every byte handed to DMA is filled by scanline().
alignas(4) u16 scanlines[lcd::STRIP_ROWS*Screen::WIDTH] __attribute__((section(".lcd_dma.scanlines")));
// Three rows fit below the core 1 stack in scratch X; the other strip
// occupies 1920 bytes of ordinary SRAM. No RGB565 frame is allocated.
alignas(4) u16 chained_scanlines[lcd::STRIP_ROWS*Screen::WIDTH];

void command(u8 op, const u8* data = nullptr, unsigned size = 0) {
    gpio_put(DC, 0);
    gpio_put(CS, 0);
    busy_wait_us(1);
    spi_write_blocking(spi1, &op, 1);
    if(size) {
        busy_wait_us(1);
        gpio_put(DC, 1);
        busy_wait_us(1);
        spi_write_blocking(spi1, data, size);
    }
    busy_wait_us(1);
    gpio_put(CS, 1);
    busy_wait_us(1);
}

struct InitCommand { u8 op, count, data[1]; };
// ST7365P native setup. Leave power, VCOM, gamma and scan timing at the
// panel's reset/NVM values: ILI9488 parameters at the same addresses differ.
// RGB565/MADCTL/INVON/entry mode match the working PicOS PicoCalc driver.
constexpr InitCommand PANEL_INIT[] = {
    {0x3A, 1, {0x55}}, {0x36, 1, {0x48}}, {0x21, 0, {}},
    {0xB7, 1, {0xC6}}, {0x55, 1, {0x00}}, // Content-adaptive brightness off.
    {0x38, 0, {}}, {0x13, 0, {}} // Idle off, normal display mode.
};

int write_backlight(u8 reg, u8 value) {
    u8 message[] = {(u8)(reg | 0x80U), value};
    if(io_worker::blocking_i2c(false,message,2) != 2) return -1;
    sleep_ms(16);
    u8 response[2] = {};
    if(io_worker::blocking_i2c(true,response,2) != 2 ||
       response[0] != reg) return -1;
    return response[1];
}
} // namespace

void Keyboard::init() {
    i2c_init(i2c1, 10000);
    gpio_set_function(PICO_DEFAULT_I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(PICO_DEFAULT_I2C_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(PICO_DEFAULT_I2C_SDA_PIN);
    gpio_pull_up(PICO_DEFAULT_I2C_SCL_PIN);
    online_ = pending_ = false;io_phase_=0;
    due_ = 0;
    io_worker::start();
}

bool Keyboard::poll(KeyEvent& event) {
    const u64 now = time_us_64();
    if(io_phase_) {
        int count;u8 response[2]{};
        if(!io_worker::take_i2c(count,response)) return false;
        const u8 phase=io_phase_;io_phase_=0;
        if(phase==1) {
            if(count==1) { pending_=true;due_=now+16000; }
            else { online_=false;++errors_;due_=now+100000; }
            return false;
        }
        pending_=false;online_=count==2;
        if(!online_) { ++errors_;due_=now+100000;return false; }
        event={response[0],response[1]};
        if(idle_ && !event.state) due_=now+64000;
        return event.state!=0;
    }
    if(now < due_) return false;
    diagnostics::Scope measure(diagnostics::Point::KEYBOARD);
    if(!pending_) {
        const u8 reg = 0x09;
        if(io_worker::request_i2c(false,&reg,1)) io_phase_=1;
        return false;
    }
    if(io_worker::request_i2c(true,nullptr,2)) io_phase_=2;
    return false;
}

void Keyboard::clock_changed() { io_worker::drain();i2c_set_baudrate(i2c1, 10000); }

void Keyboard::backlight(u8 lcd, u8 keys) {
    // Do not touch PMU shutdown, reset, SD or PSRAM registers.
    // The stock BIOS quantizes LCD PWM in steps of 16 and caps it at 240.
    lcd_backlight_ = write_backlight(0x05, lcd);
    key_backlight_ = write_backlight(0x0A, keys);
}

void Panel::init() {
    io_worker::drain();
    static_assert(Screen::WIDTH==lcd::WIDTH && Screen::HEIGHT==lcd::HEIGHT && Screen::BYTES==lcd::BYTES);
    if(!dma()) {
        dma_tx_=dma_claim_unused_channel(false);
        dma_rx_=dma_claim_unused_channel(false);
        if(!dma()) {
            if(dma_tx_>=0) dma_channel_unclaim((unsigned)dma_tx_);
            if(dma_rx_>=0) dma_channel_unclaim((unsigned)dma_rx_);
            dma_tx_=dma_rx_=-1;
        }
    }
    if(dma() && dma_control_<0) dma_control_=dma_claim_unused_channel(false);
    // ST7365P specifies >=66 ns per write clock (<=15.15 MHz).
    // 12.5 MHz has an 80 ns cycle at the stock 125 MHz system clock.
    spi_hz_ = spi_init(spi1, MK61_PICOCALC_LCD_SPI_HZ);
    gpio_set_function(PICO_DEFAULT_SPI_SCK_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_TX_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_RX_PIN, GPIO_FUNC_SPI);
    const unsigned control_pins[] = {CS, DC, RESET};
    for(unsigned pin : control_pins) {
        gpio_init(pin);
        gpio_set_dir(pin, GPIO_OUT);
        gpio_put(pin, 1);
    }
    gpio_put(RESET, 0);
    sleep_ms(10);
    gpio_put(RESET, 1);
    sleep_ms(200);
    command(0x01);
    sleep_ms(150);
    for(const auto& c : PANEL_INIT) command(c.op, c.data, c.count);
    command(0x11);
    sleep_ms(120);
    command(0x29);
    sleep_ms(120);
    valid_ = false;
    frames_ = 0;
    full_frames_=0;
}

void Panel::sleep(bool enabled) {
    io_worker::drain();
    if(enabled) { command(0x28);command(0x10); }
    else { command(0x11);sleep_ms(120);command(0x29);valid_=false; }
}
void Panel::flush(const Screen& screen) {
    if(io_worker::frame_pending()) return;
    if(failed_.exchange(false,std::memory_order_acquire)) valid_=false;
    // The retained BASIC/APP image is usually identical. Avoid walking all
    // dirty tiles at every UI poll while a chess search is computing.
    if(valid_ && std::memcmp(previous_,screen.data(),Screen::BYTES)==0) return;
    diagnostics::Scope measure(diagnostics::Point::LCD);
    update_.plan(previous_,screen.data(),!valid_);
    if(!update_.count) return;
    std::memcpy(previous_,screen.data(),Screen::BYTES);
    valid_=io_worker::submit_frame(this,[](void* context) { ((Panel*)context)->transfer(); });
}
void Panel::configure_dma() {
    if(!dma_irq_ready_) {
        // Transfer runs on core 1, independently of the core which claimed
        // the channels during panel initialization.
        dma_support::enable_irq((unsigned)dma_tx_);dma_support::enable_irq((unsigned)dma_rx_);
        auto tx=dma_channel_get_default_config((unsigned)dma_tx_);
        channel_config_set_transfer_data_size(&tx,DMA_SIZE_16);
        channel_config_set_dreq(&tx,spi_get_dreq(spi1,true));
        channel_config_set_read_increment(&tx,true);
        channel_config_set_write_increment(&tx,false);
        if(chained_dma()) {
            channel_config_set_chain_to(&tx,(unsigned)dma_control_);
            channel_config_set_irq_quiet(&tx,true);
        }
        auto rx=dma_channel_get_default_config((unsigned)dma_rx_);
        channel_config_set_transfer_data_size(&rx,DMA_SIZE_16);
        channel_config_set_dreq(&rx,spi_get_dreq(spi1,false));
        channel_config_set_read_increment(&rx,false);
        channel_config_set_write_increment(&rx,false);
        // SPI is full duplex. Drain every received word too, so RX cannot
        // retain data between DMA windows and ordinary controller commands.
        dma_channel_configure((unsigned)dma_rx_,&rx,&discard_,&spi_get_hw(spi1)->dr,0,false);
        dma_channel_configure((unsigned)dma_tx_,&tx,&spi_get_hw(spi1)->dr,nullptr,0,false);
        dma_irq_ready_=true;
    }
}
void Panel::start_scanline(const u16* pixels,unsigned count) {
    if(!dma()) { spi_write16_blocking(spi1,pixels,count);return; }
    configure_dma();
    dma_channel_set_read_addr((unsigned)dma_tx_,pixels,false);
    dma_channel_set_trans_count((unsigned)dma_rx_,count,false);
    dma_channel_set_trans_count((unsigned)dma_tx_,count,false);
    dma_start_channel_mask((1U<<dma_tx_) | (1U<<dma_rx_));
}
void Panel::abort_dma() {
    // Stop the control channel first: an in-flight chain must not restart a
    // data channel after its abort. Disable both before draining transactions.
    if(dma_control_>=0) {
        hw_clear_bits(&dma_hw->ch[dma_control_].ctrl_trig,DMA_CH0_CTRL_TRIG_EN_BITS);
        hw_clear_bits(&dma_hw->ch[dma_tx_].ctrl_trig,DMA_CH0_CTRL_TRIG_EN_BITS);
        dma_channel_abort((unsigned)dma_control_);
    }
    dma_channel_abort((unsigned)dma_tx_);dma_channel_abort((unsigned)dma_rx_);
    dma_irq_ready_=false;
}
bool Panel::transfer_chain(const lcd::Rect& rect,u32& pauses,u64& next_i2c) {
    static_assert(sizeof(lcd::Segment)==2*sizeof(u32));
    configure_dma();stream_.reset(rect);
    const auto descriptor=[&](unsigned index) {
        const auto next=lcd::Stream::prepare(previous_,rect,index,
            index&1?chained_scanlines:scanlines);
        // Count first, trigger address last; a DMA race can only cause a
        // harmless null/zero-count stop, subsequently resumed at the wire cursor.
        stream_.segments[index].count=next.count;__dmb();
        stream_.segments[index].source=next.source;__dmb();
    };
    unsigned prepared=stream_.count<2?stream_.count:2;
    for(unsigned i=0;i<prepared;++i) descriptor(i);
    auto control=dma_channel_get_default_config((unsigned)dma_control_);
    channel_config_set_transfer_data_size(&control,DMA_SIZE_32);
    channel_config_set_read_increment(&control,true);
    channel_config_set_write_increment(&control,true);
    channel_config_set_ring(&control,true,3); // AL3 count, then read-address trigger.
    dma_support::enable_irq((unsigned)dma_control_);
    // Control completion signals that the previous strip is free. Pixel DMA
    // uses quiet IRQs: its null trigger still wakes a producer after a stall.
    dma_channel_configure((unsigned)dma_control_,&control,
        &dma_hw->ch[dma_tx_].al3_transfer_count,stream_.segments,2,false);
    const unsigned total=rect.width*rect.height;
    dma_channel_set_trans_count((unsigned)dma_rx_,total,false);__dmb();
    dma_start_channel_mask((1U<<dma_rx_) | (1U<<dma_control_));
    const u64 limit=time_us_64()+1000000;
    const auto service=[&] {
        const bool i2c=time_us_64()>=next_i2c;
        io_worker::service(i2c);
        if(i2c) next_i2c=time_us_64()+2000;
    };
    const auto loaded=[&] {
        return (dma_hw->ch[dma_control_].read_addr-(uintptr_t)stream_.segments)/sizeof(lcd::Segment);
    };
    const auto resume=[&] {
        if(dma_channel_is_busy((unsigned)dma_control_) || dma_channel_is_busy((unsigned)dma_tx_) ||
           spi_is_busy(spi1) || spi_is_readable(spi1)) return;
        __dmb();
        const unsigned pixels=total-dma_hw->ch[dma_rx_].transfer_count;
        const unsigned next=lcd::Stream::next(pixels,rect.width);
        if(next<prepared && loaded()>=next+1) {
            // A null trigger has stopped this descriptor. Rewind only after
            // the previous SPI/RX data is drained, so no strip is duplicated.
            dma_channel_set_read_addr((unsigned)dma_control_,stream_.segments+next,true);++pauses;
        }
    };
    while(prepared<stream_.count) {
        // Loading descriptor N means N-1 finished: strip N-2 is now reusable.
        if(loaded()>=prepared) {
            descriptor(prepared++);resume();
        } else {
            resume();
            if(time_us_64()>=limit) { abort_dma();return false; }
            best_effort_wfe_or_timeout(make_timeout_time_us(1000));
        }
        // Convert future pixels while the chain shifts the prepared strips;
        // I2C/UART likewise overlap the transfer. A late producer pauses safely.
        service();
    }
    while(dma_channel_is_busy((unsigned)dma_rx_) || dma_channel_is_busy((unsigned)dma_tx_) ||
          dma_channel_is_busy((unsigned)dma_control_) || loaded()!=stream_.count+1) {
        resume();
        if(time_us_64()>=limit) { abort_dma();return false; }
        service();best_effort_wfe_or_timeout(make_timeout_time_us(1000));
    }
    while(spi_is_busy(spi1)) tight_loop_contents();
    return true;
}
bool Panel::finish_scanline() {
    if(!dma()) return true;
    if(!dma_support::wait((unsigned)dma_tx_,dma_rx_)) return false;
    while(spi_is_busy(spi1)) tight_loop_contents();
    return true;
}
void Panel::transfer() {
    const u64 start=time_us_64();
    u64 next_i2c=start+2000;
    u32 strips=0,pauses=0;
    for(unsigned index=0;index<update_.count;++index) {
        const auto& rect=update_.rectangles[index];
        const unsigned right=rect.x+rect.width-1,bottom=rect.y+rect.height-1;
        const u8 columns[]={(u8)(rect.x>>8),(u8)rect.x,(u8)(right>>8),(u8)right};
        const u8 rows[]={(u8)(rect.y>>8),(u8)rect.y,(u8)(bottom>>8),(u8)bottom};
        command(0x2A,columns,sizeof(columns));
        command(0x2B,rows,sizeof(rows));
        // Keep RAMWR and all of its pixels in one CS transaction. Window
        // writes use the same ST7365P initialization, with CABC disabled.
        gpio_put(DC,0);gpio_put(CS,0);busy_wait_us(1);
        const u8 ram_write=0x2C;
        spi_write_blocking(spi1,&ram_write,1);
        busy_wait_us(1);gpio_put(DC,1);busy_wait_us(1);
        // Controller commands remain 8-bit; pixels are native RGB565 words.
        // This halves DMA bus transactions without an extra SRAM buffer.
        spi_set_format(spi1,16,SPI_CPOL_0,SPI_CPHA_0,SPI_MSB_FIRST);
        bool ok=true;
        if(chained_dma()) {
            ok=transfer_chain(rect,pauses,next_i2c);strips+=stream_.count;
        } else {
          lcd::scanline(previous_,rect,0,(u8*)scanlines);
          start_scanline(scanlines,rect.width);
          for(unsigned row=1;row<=rect.height;++row) {
            // Convert the next row while DMA sends the other buffer. Neither
            // the snapshot nor an in-flight scanline is modified by core 0.
            if(row<rect.height) lcd::scanline(previous_,rect,row,(u8*)(scanlines+(row&1)*Screen::WIDTH));
            if(!finish_scanline()) { ok=false;break; }
            if(row<rect.height) start_scanline(scanlines+(row&1)*Screen::WIDTH,rect.width);
            io_worker::service();
          }
        }
        if(!ok) {
            gpio_put(CS,1);errors_.fetch_add(1);
            spi_set_format(spi1,8,SPI_CPOL_0,SPI_CPHA_0,SPI_MSB_FIRST);
            failed_.store(true,std::memory_order_release);return;
        }
        busy_wait_us(1);gpio_put(CS,1);busy_wait_us(1);
        spi_set_format(spi1,8,SPI_CPOL_0,SPI_CPHA_0,SPI_MSB_FIRST);
    }
    last_us_.store((u32)(time_us_64()-start),std::memory_order_relaxed);
    last_strips_.store(strips,std::memory_order_relaxed);
    last_pauses_.store(pauses,std::memory_order_relaxed);
    last_bytes_.store(update_.bytes,std::memory_order_relaxed);
    last_rectangles_.store(update_.count,std::memory_order_relaxed);
    if(update_.bytes==Screen::WIDTH*Screen::HEIGHT*2) full_frames_.fetch_add(1,std::memory_order_relaxed);
    frame_crc_.store(dma_support::crc32(previous_,sizeof(previous_)),std::memory_order_relaxed);
    frames_.fetch_add(1,std::memory_order_relaxed);
}

} // namespace picocalc
