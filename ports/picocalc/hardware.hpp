#ifndef MK61_PICOCALC_HARDWARE_HPP
#define MK61_PICOCALC_HARDWARE_HPP

#include "screen.hpp"
#include "battery.hpp"
#include "lcd_update.hpp"
#include "lcd_chain.hpp"
#include "lcd_color.hpp"
#include <atomic>

namespace picocalc {

class Keyboard {
public:
    struct BatteryFault {
        u32 at_us=0,selection_us=0;
        int count=0;
        u8 phase=0,reg=0,value=0,selected=0;
    };
    void init();
    bool poll(KeyEvent& event);
    void backlight(u8 lcd = 240, u8 keys = 40);
    void idle(bool enabled) { idle_ = enabled; }
    void clock_changed();
    bool transaction_pending() const { return pending_ || io_phase_; }
    u64 next_poll() const { return due_; }
    bool online() const { return online_; }
    u32 errors() const { return errors_; }
    BatteryStatus battery() const { return battery_; }
    u32 battery_errors() const { return battery_errors_; }
    u32 battery_unknown_reads() const { return battery_unknown_reads_; }
    u32 selection_restarts() const { return selection_restarts_; }
    BatteryFault battery_fault() const { return battery_fault_; }
    int lcd_backlight() const { return lcd_backlight_; }
    int key_backlight() const { return key_backlight_; }
private:
    bool online_ = false, pending_ = false, idle_ = false;
    u8 io_phase_ = 0;
    u64 due_ = 0,battery_due_ = 0,power_due_ = 0;
    BatteryStatus battery_;
    u32 battery_errors_=0;
    u32 errors_ = 0;
    int lcd_backlight_ = -1, key_backlight_ = -1;
    u64 selected_at_=0;
    u8 selected_reg_=0;
    u32 selection_restarts_=0,battery_unknown_reads_=0;
    BatteryFault battery_fault_;
    bool request_register(u8 reg,u8 phase,u64 now);
    void record_battery_fault(u8 phase,int count,const u8* reply,u64 now);
};

class Panel {
public:
    void init();
    bool flush(const Screen& screen);
    u32 color(u32 operation,const void* payload=nullptr);
    u32 color_palette(const u16* colors);
    bool color_active() const { return color_active_; }
    // Cache power on core 0; only an idle flush/explicit APP request retunes SPI.
    void external_power(bool powered) {
        if(!powered) auto_fast_failed_=false;
        external_power_=powered;
    }
    void power_supply(const BatteryStatus& state,bool pico_vbus) {
        external_power(pico_vbus || state.external_power());
    }
    bool external_power() const { return external_power_; }
    u32 clock_fallbacks() const { return clock_fallbacks_; }
    void note_input(u64 when) { if(!input_at_) input_at_=when; }
    u32 responses() const { return responses_.load(std::memory_order_relaxed); }
    u32 response_us() const { return response_us_.load(std::memory_order_relaxed); }
    u32 response_max_us() const { return response_max_us_.load(std::memory_order_relaxed); }
    bool needs_refresh() const { return !valid_ || failed_.load(std::memory_order_acquire) || clock_pending(); }
    void sleep(bool enabled);
    u32 spi_hz() const { return spi_hz_; }
    u32 frames() const { return frames_.load(std::memory_order_relaxed); }
    u32 frame_crc() const { return frame_crc_.load(std::memory_order_relaxed); }
    u32 last_bytes() const { return last_bytes_.load(std::memory_order_relaxed); }
    u32 last_rectangles() const { return last_rectangles_.load(std::memory_order_relaxed); }
    u32 last_us() const { return last_us_.load(std::memory_order_relaxed); }
    u32 full_frames() const { return full_frames_.load(std::memory_order_relaxed); }
    u32 errors() const { return errors_.load(std::memory_order_relaxed); }
    bool dma() const { return dma_tx_>=0 && dma_rx_>=0; }
    bool chained_dma() const { return dma() && dma_control_>=0; }
    u32 strips() const { return last_strips_.load(std::memory_order_relaxed); }
    u32 chain_pauses() const { return last_pauses_.load(std::memory_order_relaxed); }
    u32 scrolls() const { return scrolls_.load(std::memory_order_relaxed); }
    u32 scrolled_rows() const { return scrolled_rows_.load(std::memory_order_relaxed); }
    unsigned scroll_offset() const { return scroll_.offset; }
private:
    u8 previous_[Screen::BYTES] = {};
    lcd::ShellTheme previous_theme_{};
    bool valid_ = false;
    u32 spi_hz_ = 0;
    u32 color_spi_request_ = 0;
    u32 applied_spi_request_ = 0,clock_fallbacks_=0;
    bool external_power_=false,auto_fast_failed_=false;
    u64 input_at_=0,frame_input_at_=0;
    std::atomic<u32> responses_{0},response_us_{0},response_max_us_{0};
    std::atomic<u32> frames_{0},frame_crc_{0};
    std::atomic<u32> last_bytes_{0},last_rectangles_{0},last_us_{0},full_frames_{0};
    std::atomic<u32> errors_{0};
    std::atomic<bool> failed_{false};
    bool dma_irq_ready_=false,dma_chain_configured_=false;
    bool color_active_=false,color_clear_=false;
    mk61_service_color_frame color_frame_{};
    u16 color_palette_[64]{};
    bool palette_dirty_=false;
    lcd::Update update_;
    lcd::Scroll scroll_;
    lcd::Region configured_region_;
    bool scroll_configured_=false;
    unsigned configured_start_=0,pending_scroll_rows_=0;
    std::atomic<u32> scrolls_{0},scrolled_rows_{0};
    u16 discard_=0;
    int dma_tx_=-1,dma_rx_=-1,dma_control_=-1;
    std::atomic<u32> last_strips_{0},last_pauses_{0};
    void configure_dma(bool chain=true);
    u32 color_clock(u32 hz);
    void apply_clock();
    u32 clock_request() const;
    bool clock_pending() const;
    bool take_failure();
    void completed_input(u64 now);
    lcd::Stream stream_;
    bool transfer_chain(const lcd::Rect& rect,u32& pauses,bool color=false);
    bool transfer_fill(u16 color,unsigned width,unsigned height);
    void abort_dma();
    void start_scanline(const u16* pixels,unsigned count);
    bool finish_scanline();
    void transfer();
    void transfer_color();
    bool transfer_color_rect(const lcd::Rect& rect,bool background,u32& strips,u32& pauses);
};

} // namespace picocalc
#endif
