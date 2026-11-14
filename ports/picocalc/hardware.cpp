#include "hardware.hpp"
#include "lcd_shell_update.hpp"
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
#ifndef MK61_PICOCALC_LCD_COLOR_CHAIN
#define MK61_PICOCALC_LCD_COLOR_CHAIN 1
#endif

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
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_CONTROL);
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
    due_ = battery_due_ = power_due_ = 0;battery_={};battery_errors_=0;
    selected_at_=0;selected_reg_=0;selection_restarts_=battery_unknown_reads_=0;battery_fault_={};
    io_worker::start();
}

bool Keyboard::request_register(u8 reg,u8 phase,u64 now) {
    if(!io_worker::request_i2c(false,&reg,1)) return false;
    selected_reg_=reg;selected_at_=now;io_phase_=phase;return true;
}
void Keyboard::record_battery_fault(u8 phase,int count,const u8* reply,u64 now) {
    if(battery_fault_.phase) return;
    const u64 elapsed=now-selected_at_;
    battery_fault_={(u32)now,(u32)(elapsed>UINT32_MAX?UINT32_MAX:elapsed),count,phase,reply[0],reply[1],selected_reg_};
}
bool Keyboard::poll(KeyEvent& event) {
    const u64 now = time_us_64();
    if(io_phase_) {
        if((io_phase_==4 || io_phase_==6 || io_phase_==8) && pending_ && now>=due_) {
            // Southbridge discards an unconsumed register selection after1s.
            // An SD operation may keep feeding the watchdog while core0's
            // keyboard poll is delayed. Renew before reading a stale0,0.
            if(now-selected_at_>=900000) {
                if(request_register(selected_reg_,io_phase_-1,now)) {pending_=false;++selection_restarts_;}
            } else if(io_worker::request_i2c(true,nullptr,2)) pending_=false;
            return false;
        }
        if((io_phase_==4 || io_phase_==6 || io_phase_==8) && pending_) return false;
        int count;u8 response[2]{};
        if(!io_worker::take_i2c(count,response)) return false;
        const u8 phase=io_phase_;io_phase_=0;
        if(phase==1) {
            if(count==1) { pending_=true;due_=now+16000; }
            else { online_=false;battery_.power_status=0;++errors_;due_=now+100000; }
            return false;
        }
        if(phase==3 || phase==5 || phase==7) {
            if(count==1) { pending_=true;io_phase_=phase+1;due_=now+16000; }
            else { record_battery_fault(phase,count,response,now);++battery_errors_;if(phase==3) battery_.clear_reading();else battery_.clear_power(); }
            return false;
        }
        if(phase==4) {
            pending_=false;
            if(count!=2 || !battery_.decode(response[0],response[1])) {record_battery_fault(phase,count,response,now);++battery_errors_;battery_.clear_reading();}
            else if((response[1]&127)==127) ++battery_unknown_reads_;
            battery_due_=now+20000000;return false;
        }
        if(phase==6) {
            pending_=false;
            if(count!=2) {record_battery_fault(phase,count,response,now);++battery_errors_;battery_.clear_power();}
            else battery_.decode_power(response[0],response[1]); // Old BIOS: unsupported, not an I2C error.
            power_due_=now+(battery_.power_supported()?1000000:20000000);return false;
        }
        if(phase==8) {
            pending_=false;
            // Older Southbridge echoes its previous payload for an unknown
            // register. Seed that payload with a version byte outside the
            // power tag range before discovering the optional register.
            if(count==2 && response[0]<=1 && (response[1]&BIOS_POWER_TAG_MASK)!=BIOS_POWER_TAG) {
                const u8 reg=BIOS_POWER_REG;
                if(!request_register(reg,5,now)) power_due_=now;
            } else {if(count!=2) {record_battery_fault(phase,count,response,now);++battery_errors_;}battery_.clear_power();}
            return false;
        }
        pending_=false;online_=count==2;
        if(!online_) { battery_.power_status=0;++errors_;due_=now+100000;return false; }
        event={response[0],response[1]};
        if(idle_ && !event.state) due_=now+64000;
        return event.state!=0;
    }
    if(!idle_ && online_ && !pending_ && now>=battery_due_) {
        const u8 reg=0x0B;
        if(request_register(reg,3,now)) battery_due_=now+20000000;
        return false;
    }
    if(!idle_ && online_ && !pending_ && now>=power_due_) {
        const bool known=battery_.power_supported();const u8 reg=known?BIOS_POWER_REG:0x01;
        if(request_register(reg,known?5:7,now)) power_due_=now+20000000;
        return false;
    }
    if(now < due_) return false;
    diagnostics::Scope measure(diagnostics::Point::KEYBOARD);
    if(!pending_) {
        const u8 reg = 0x09;
        (void)request_register(reg,1,now);
        return false;
    }
    if(now-selected_at_>=900000) {
        if(request_register(selected_reg_,1,now)) {pending_=false;++selection_restarts_;}
    } else if(io_worker::request_i2c(true,nullptr,2)) io_phase_=2;
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
    applied_spi_request_=MK61_PICOCALC_LCD_SPI_HZ;
    spi_hz_ = spi_init(spi1, applied_spi_request_);
    color_spi_request_ = 0;
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
    valid_ = false;scroll_={};scroll_configured_=false;pending_scroll_rows_=0;
    frames_ = 0;
    full_frames_=0;
}

void Panel::sleep(bool enabled) {
    io_worker::drain();
    if(enabled) { command(0x28);command(0x10); }
    else { command(0x11);sleep_ms(120);command(0x29);valid_=false; }
}
bool Panel::flush(const Screen& screen) {
    if(io_worker::frames_suspended()) return false;
    if(color_active_) return false;
    if(io_worker::frame_pending()) return false;
    if(take_failure()) valid_=false;
    apply_clock();
    // The retained BASIC/APP image is usually identical. Avoid walking all
    // dirty tiles at every UI poll while a chess search is computing.
    const auto& theme=screen.color_theme();
    if(valid_ && previous_theme_.same(theme) && std::memcmp(previous_,screen.data(),Screen::BYTES)==0) return true;
    diagnostics::Scope measure(diagnostics::Point::LCD);
    const auto region=screen.scroll_region();
    bool force=!valid_;
    if(force || scroll_.region!=region) {
        force|=scroll_.offset!=0;scroll_={region,0};
    }
    const bool scroll_safe=region.valid() && theme.scroll_safe(region.top,region.height) &&
        previous_theme_.scroll_safe(region.top,region.height);
    if(!scroll_safe && scroll_.offset) {scroll_={region,0};force=true;}
    const int delta=force || !scroll_safe?0:lcd::Scroll::find(previous_,screen.data(),region);
    pending_scroll_rows_=delta<0?-delta:delta;
    if(delta) scroll_.rotate(previous_,delta);
    lcd::plan_shell(update_,previous_,screen.data(),previous_theme_,theme,force);
    if(!update_.count && !delta) {previous_theme_=theme;return true;}
    std::memcpy(previous_,screen.data(),Screen::BYTES);
    previous_theme_=theme;
    if(input_at_ && (!frame_input_at_ || input_at_<frame_input_at_)) frame_input_at_=input_at_;
    input_at_=0;
    valid_=io_worker::submit_frame(this,[](void* context) { ((Panel*)context)->transfer(); });
    return valid_;
}
u32 Panel::clock_request() const {
    return color_spi_request_?color_spi_request_:
        external_power_ && !auto_fast_failed_?24000000:MK61_PICOCALC_LCD_SPI_HZ;
}
bool Panel::clock_pending() const { return clock_request()!=applied_spi_request_; }
void Panel::apply_clock() {
    const u32 request=clock_request();
    if(request!=applied_spi_request_ && !io_worker::frame_pending()) {
        spi_hz_=spi_set_baudrate(spi1,request);applied_spi_request_=request;
    }
}
bool Panel::take_failure() {
    const bool failed=failed_.exchange(false,std::memory_order_acquire);
    if(failed && !color_spi_request_ && applied_spi_request_==24000000 && !auto_fast_failed_) {
        auto_fast_failed_=true;++clock_fallbacks_;
    }
    return failed;
}
void Panel::completed_input(u64 now) {
    if(!frame_input_at_) return;
    const u64 elapsed=now-frame_input_at_;
    if(elapsed<=UINT32_MAX) {
        response_us_.store((u32)elapsed,std::memory_order_relaxed);
        if(elapsed>response_max_us_.load(std::memory_order_relaxed))
            response_max_us_.store((u32)elapsed,std::memory_order_relaxed);
        responses_.fetch_add(1,std::memory_order_relaxed);
    }
    frame_input_at_=0;
}
u32 Panel::color_palette(const u16* colors) {
    if(!colors) return 0;
    if(io_worker::frame_pending()) return 2;
    if(std::memcmp(colors,color_palette_,sizeof(color_palette_))) {
        std::memcpy(color_palette_,colors,sizeof(color_palette_));palette_dirty_=true;
    }
    return 1;
}
u32 Panel::color_clock(u32 hz) {
    if(hz && hz!=12000000 && hz!=24000000) return 0;
    if(hz==color_spi_request_) { apply_clock();return spi_hz_; }
    // The previous frame belongs to core 1. Finish it before changing SPI;
    // the request never changes the shared peripheral or CPU clock.
    io_worker::drain();
    color_spi_request_=hz;
    apply_clock();
    return spi_hz_;
}
u32 Panel::color(u32 operation,const void* payload) {
    if(operation==MK61_COLOR_SPI_HZ) {
        if(!payload) return 0;
        u32 hz;std::memcpy(&hz,payload,sizeof(hz));
        return color_clock(hz);
    }
    if(operation==MK61_COLOR_PALETTE64) return color_palette((const u16*)payload);
    if(operation==MK61_COLOR_AVAILABLE) return 1;
    if(operation==MK61_COLOR_END) {
        if(color_active_) {
            io_worker::drain();color_active_=false;valid_=false;color_frame_={};
        }
        if(color_spi_request_) (void)color_clock(0);
        else apply_clock();
        return 1;
    }
    if(operation!=MK61_COLOR_PRESENT || !payload) return 0;
    const auto* frame=(const mk61_service_color_frame*)payload;
    if(!lcd::valid_color(*frame)) return 0;
    if(io_worker::frames_suspended()) return 2;
    if(io_worker::frame_pending()) return 2;
    const bool failed=take_failure();
    apply_clock();
    const bool geometry=!color_active_ || failed || !lcd::same_color_view(color_frame_,*frame);
    const bool force=geometry || ((frame->format&~MK61_COLOR_PRESERVE_OUTSIDE)==MK61_COLOR_TILE8 && palette_dirty_);
    color_clear_=!(frame->format&MK61_COLOR_PRESERVE_OUTSIDE) && (geometry || color_frame_.background!=frame->background);
    lcd::plan_color(update_,color_frame_,*frame,force);
    if(!update_.count && !color_clear_) return 1;
    lcd::copy_color(color_frame_,*frame,previous_);
    palette_dirty_=false;
    color_active_=true;valid_=false;
    if(!io_worker::submit_frame(this,[](void* context) { ((Panel*)context)->transfer_color(); })) {
        failed_.store(true,std::memory_order_release);return 2;
    }
    return 1;
}
void Panel::configure_dma(bool chain) {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_CONTROL);
    const bool use_chain=chain && chained_dma();
    if(!dma_irq_ready_ || dma_chain_configured_!=use_chain) {
        // Transfer runs on core 1, independently of the core which claimed
        // the channels during panel initialization.
        dma_support::enable_irq((unsigned)dma_tx_);dma_support::enable_irq((unsigned)dma_rx_);
        auto tx=dma_channel_get_default_config((unsigned)dma_tx_);
        channel_config_set_transfer_data_size(&tx,DMA_SIZE_16);
        channel_config_set_dreq(&tx,spi_get_dreq(spi1,true));
        channel_config_set_read_increment(&tx,true);
        channel_config_set_write_increment(&tx,false);
        if(use_chain) {
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
        dma_chain_configured_=use_chain;
    }
}
void Panel::start_scanline(const u16* pixels,unsigned count) {
    if(!dma()) { spi_write16_blocking(spi1,pixels,count);return; }
    configure_dma(false);
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
bool Panel::transfer_chain(const lcd::Rect& rect,u32& pauses,bool color) {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_WAIT);
    static_assert(sizeof(lcd::Segment)==2*sizeof(u32));
    configure_dma();stream_.reset(rect);
    const auto descriptor=[&](unsigned index) {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_PREPARE);
        const auto next=lcd::Stream::prepare(rect,index,index&1?chained_scanlines:scanlines,
            [&](unsigned row,u16* out) {
                if(color) {
                    lcd::color_scanline(color_frame_,rect,row,out,color_palette_,[] {io_worker::service();});
                    // Pixel expansion is CPU work too: keep M3 transport
                    // serviced between rows, not only between 3-row strips.
                    io_worker::service();
                }
                else lcd::shell_scanline(previous_,rect,row,previous_theme_,out);
            });
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
    const auto service=[] { io_worker::service(); };
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
            io_worker::wait_for_progress();
        }
        // Convert future pixels while the chain shifts the prepared strips;
        // I2C/UART likewise overlap the transfer. A late producer pauses safely.
        service();
    }
    while(dma_channel_is_busy((unsigned)dma_rx_) || dma_channel_is_busy((unsigned)dma_tx_) ||
          dma_channel_is_busy((unsigned)dma_control_) || loaded()!=stream_.count+1) {
        resume();
        if(time_us_64()>=limit) { abort_dma();return false; }
        io_worker::wait_for_progress();
    }
    while(spi_is_busy(spi1)) tight_loop_contents();
    return true;
}
bool Panel::finish_scanline() {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_WAIT);
    if(!dma()) return true;
    if(!dma_support::wait((unsigned)dma_tx_,dma_rx_)) return false;
    while(spi_is_busy(spi1)) tight_loop_contents();
    return true;
}
bool Panel::transfer_fill(u16 color,unsigned width,unsigned height) {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_WAIT);
    if(!dma()) {
        for(unsigned x=0;x<width;++x) scanlines[x]=color;
        for(unsigned row=0;row<height;++row) {
            start_scanline(scanlines,width);io_worker::service();
        }
        return true;
    }
    configure_dma(false);
    auto tx=dma_channel_get_default_config((unsigned)dma_tx_);
    channel_config_set_transfer_data_size(&tx,DMA_SIZE_16);
    channel_config_set_dreq(&tx,spi_get_dreq(spi1,true));
    channel_config_set_read_increment(&tx,false);
    channel_config_set_write_increment(&tx,false);
    // The constant remains alive until both DMA channels and SPI drain.
    // Invalidate cached configuration: the next image must increment reads.
    dma_channel_configure((unsigned)dma_tx_,&tx,&spi_get_hw(spi1)->dr,&color,width*height,false);
    dma_irq_ready_=false;
    dma_channel_set_trans_count((unsigned)dma_rx_,width*height,false);
    dma_start_channel_mask((1U<<dma_tx_) | (1U<<dma_rx_));
    const u64 limit=time_us_64()+1000000;
    while(dma_channel_is_busy((unsigned)dma_tx_) || dma_channel_is_busy((unsigned)dma_rx_)) {
        if(time_us_64()>=limit) { abort_dma();return false; }
        io_worker::wait_for_progress();
    }
    return finish_scanline();
}
void Panel::transfer() {
    const u64 start=time_us_64();
    u32 strips=0,pauses=0,windows=0;
    const bool manage_scroll=scroll_configured_ || pending_scroll_rows_;
    const lcd::Region physical=scroll_.region.valid()?scroll_.region:lcd::Region{0,lcd::HEIGHT};
    const unsigned start_row=physical.top+(scroll_.region.valid()?scroll_.offset:0);
    const bool redefine=manage_scroll && (!scroll_configured_ || configured_region_!=physical);
    if(redefine) {
        const unsigned bottom=lcd::HEIGHT-physical.top-physical.height;
        const u8 definition[]={(u8)(physical.top>>8),(u8)physical.top,(u8)(physical.height>>8),(u8)physical.height,(u8)(bottom>>8),(u8)bottom};
        command(0x33,definition,sizeof(definition));
        // A failed transfer may retry after the UI changes the scroll region.
        // Cache the definition already sent; the origin awaits VSCSAD below.
        scroll_configured_=true;
        configured_region_=physical;configured_start_=lcd::HEIGHT;
    }
    for(unsigned index=0;index<update_.count;++index) {
      const auto& area=update_.rectangles[index];
      for(unsigned first=0;first<area.height;) {
        const unsigned count=scroll_.run(area.y+first,area.height-first);
        const lcd::Rect rect{area.x,(u16)(area.y+first),area.width,(u16)count};
        const unsigned physical_y=scroll_.map(rect.y);
        const unsigned right=rect.x+rect.width-1,bottom=physical_y+rect.height-1;
        ++windows;first+=count;
        const u8 columns[]={(u8)(rect.x>>8),(u8)rect.x,(u8)(right>>8),(u8)right};
        const u8 rows[]={(u8)(physical_y>>8),(u8)physical_y,(u8)(bottom>>8),(u8)bottom};
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
            ok=transfer_chain(rect,pauses);strips+=stream_.count;
        } else {
          lcd::shell_scanline(previous_,rect,0,previous_theme_,scanlines);
          start_scanline(scanlines,rect.width);
          for(unsigned row=1;row<=rect.height;++row) {
            // Convert the next row while DMA sends the other buffer. Neither
            // the snapshot nor an in-flight scanline is modified by core 0.
            if(row<rect.height) lcd::shell_scanline(previous_,rect,row,previous_theme_,scanlines+(row&1)*Screen::WIDTH);
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
      }
    // Publish the new scan origin after writing its exposed rows (VSCSAD).
    if(manage_scroll && (redefine || configured_start_!=start_row)) {
        const u8 origin[]={(u8)(start_row>>8),(u8)start_row};command(0x37,origin,sizeof(origin));
        configured_region_=physical;configured_start_=start_row;scroll_configured_=true;
    }
    if(pending_scroll_rows_) { scrolls_.fetch_add(1);scrolled_rows_.fetch_add(pending_scroll_rows_); }
    io_worker::FrameDeadlineScope publish_trace(WorkerDeadlineTrace::LCD_PUBLISH);
    last_us_.store((u32)(time_us_64()-start),std::memory_order_relaxed);
    last_strips_.store(strips,std::memory_order_relaxed);
    last_pauses_.store(pauses,std::memory_order_relaxed);
    last_bytes_.store(update_.bytes,std::memory_order_relaxed);
    last_rectangles_.store(windows,std::memory_order_relaxed);
    completed_input(time_us_64());
    if(update_.bytes==Screen::WIDTH*Screen::HEIGHT*2) full_frames_.fetch_add(1,std::memory_order_relaxed);
    { io_worker::FrameDeadlineScope crc_trace(WorkerDeadlineTrace::LCD_CRC);
    frame_crc_.store(dma_support::crc32(previous_,sizeof(previous_),[] {io_worker::service();}),std::memory_order_relaxed);
    }
    frames_.fetch_add(1,std::memory_order_relaxed);
}

bool Panel::transfer_color_rect(const lcd::Rect& rect,bool background,u32& strips,u32& pauses) {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_CONTROL);
    const unsigned right=rect.x+rect.width-1,bottom=rect.y+rect.height-1;
    const u8 columns[]={(u8)(rect.x>>8),(u8)rect.x,(u8)(right>>8),(u8)right};
    const u8 rows[]={(u8)(rect.y>>8),(u8)rect.y,(u8)(bottom>>8),(u8)bottom};
    command(0x2A,columns,sizeof(columns));command(0x2B,rows,sizeof(rows));
    gpio_put(DC,0);gpio_put(CS,0);busy_wait_us(1);
    const u8 ram_write=0x2C;spi_write_blocking(spi1,&ram_write,1);
    busy_wait_us(1);gpio_put(DC,1);busy_wait_us(1);
    spi_set_format(spi1,16,SPI_CPOL_0,SPI_CPHA_0,SPI_MSB_FIRST);
    const auto prepare=[&](unsigned row) {
    io_worker::FrameDeadlineScope frame_trace(WorkerDeadlineTrace::LCD_PREPARE);
        u16* out=scanlines+(row&1U)*Screen::WIDTH;
        if(background) for(unsigned x=0;x<rect.width;++x) out[x]=color_frame_.background;
        else lcd::color_scanline(color_frame_,rect,row,out,color_palette_);
    };
    bool ok=true;
    if(MK61_PICOCALC_LCD_COLOR_CHAIN && background) {
        ok=transfer_fill(color_frame_.background,rect.width,rect.height);
        strips+=dma()?1:rect.height;
    } else if(MK61_PICOCALC_LCD_COLOR_CHAIN && chained_dma()) {
        ok=transfer_chain(rect,pauses,true);strips+=stream_.count;
    } else {
        prepare(0);start_scanline(scanlines,rect.width);
        for(unsigned row=1;row<=rect.height;++row) {
            if(row<rect.height) prepare(row);
            if(!finish_scanline()) { ok=false;break; }
            if(row<rect.height) start_scanline(scanlines+(row&1U)*Screen::WIDTH,rect.width);
            io_worker::service();
        }
        strips+=rect.height;
    }
    busy_wait_us(1);gpio_put(CS,1);busy_wait_us(1);
    spi_set_format(spi1,8,SPI_CPOL_0,SPI_CPHA_0,SPI_MSB_FIRST);
    return ok;
}
void Panel::transfer_color() {
    const u64 start=time_us_64();
    // A color image uses ordinary, unscrolled LCD coordinates. The next
    // monochrome frame likewise starts from a fresh snapshot after END.
    if(scroll_configured_) {
        const u8 definition[]={0,0,1,64,0,0},origin[]={0,0};
        command(0x33,definition,sizeof(definition));command(0x37,origin,sizeof(origin));
        scroll_configured_=false;
    }
    scroll_={};pending_scroll_rows_=0;
    bool ok=true;unsigned border_bytes=0,border_windows=0;u32 strips=0,pauses=0;
    if(color_clear_) {
        const auto& f=color_frame_;
        const lcd::Rect borders[]={
            {0,0,Screen::WIDTH,f.y},
            {0,(u16)(f.y+f.height),Screen::WIDTH,(u16)(Screen::HEIGHT-f.y-f.height)},
            {0,f.y,f.x,f.height},
            {(u16)(f.x+f.width),f.y,(u16)(Screen::WIDTH-f.x-f.width),f.height}};
        for(const auto& r:borders) if(r.width && r.height && ok) {
            ok=transfer_color_rect(r,true,strips,pauses);border_bytes+=r.width*r.height*2;++border_windows;
        }
    }
    for(unsigned i=0;i<update_.count && ok;++i) ok=transfer_color_rect(update_.rectangles[i],false,strips,pauses);
    if(!ok) { errors_.fetch_add(1);failed_.store(true,std::memory_order_release);return; }
    io_worker::FrameDeadlineScope publish_trace(WorkerDeadlineTrace::LCD_PUBLISH);
    last_us_.store((u32)(time_us_64()-start),std::memory_order_relaxed);
    last_bytes_.store(update_.bytes+border_bytes,std::memory_order_relaxed);
    last_rectangles_.store(update_.count+border_windows,std::memory_order_relaxed);
    last_strips_.store(strips,std::memory_order_relaxed);last_pauses_.store(pauses,std::memory_order_relaxed);
    { io_worker::FrameDeadlineScope crc_trace(WorkerDeadlineTrace::LCD_CRC);
    frame_crc_.store(dma_support::crc32(previous_,color_frame_.pixel_bytes+color_frame_.tile_bytes,[] {io_worker::service();}),std::memory_order_relaxed);
    }
    frames_.fetch_add(1,std::memory_order_relaxed);
}

} // namespace picocalc
