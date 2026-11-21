#ifndef MK61_PICOCALC_HARDWARE_HPP
#define MK61_PICOCALC_HARDWARE_HPP

#include "screen.hpp"
#include "battery.hpp"
#include "lcd_update.hpp"
#include "lcd_chain.hpp"
#include "lcd_color.hpp"
#include "lcd_index4_pairs.hpp"
#include "bios_sleep.hpp"
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
    void idle(bool enabled) { idle_ = enabled;bios_sleep_.idle(enabled); }
    const BiosSleep& bios_sleep() const { return bios_sleep_; }
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
    BiosSleep bios_sleep_;
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
    struct ColorHistory {
        static constexpr unsigned CAPACITY=16;
        u32 frames=0,crc[CAPACITY]={};
    };
    struct ColorChainTiming {u32 bytes,setup_us,dma_us,pauses;};
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
    bool color_history(ColorHistory& out) const;
    u32 last_bytes() const { return last_bytes_.load(std::memory_order_relaxed); }
    u32 last_rectangles() const { return last_rectangles_.load(std::memory_order_relaxed); }
    u32 last_us() const { return last_us_.load(std::memory_order_relaxed); }
    u32 full_frames() const { return full_frames_.load(std::memory_order_relaxed); }
    u32 errors() const { return errors_.load(std::memory_order_relaxed); }
    bool dma() const { return dma_tx_>=0 && dma_rx_>=0; }
    bool chained_dma() const { return dma() && dma_control_>=0; }
    u32 strips() const { return last_strips_.load(std::memory_order_relaxed); }
    u32 chain_pauses() const { return last_pauses_.load(std::memory_order_relaxed); }
    u32 queued_strips() const { return queued_strips_; }
    ColorChainTiming color_chain_timing() const;
    u32 scrolls() const { return scrolls_.load(std::memory_order_relaxed); }
    u32 scrolled_rows() const { return scrolled_rows_.load(std::memory_order_relaxed); }
    unsigned scroll_offset() const { return scroll_.offset; }
private:
    static constexpr unsigned GRAM_ROWS=480;
    static constexpr unsigned COLOR_SLOT_BYTES=Screen::WIDTH*32/2;
    alignas(4) u16 previous_[Screen::BYTES/sizeof(u16)] = {};
    u8* previous_bytes() { return reinterpret_cast<u8*>(previous_); }
    lcd::ShellTheme previous_theme_{};
    bool valid_ = false;
    u32 spi_hz_ = 0;
    u32 color_spi_request_ = 0;
    u32 applied_spi_request_ = 0,clock_fallbacks_=0;
    bool external_power_=false,auto_fast_failed_=false;
    u64 input_at_=0,frame_input_at_=0;
    std::atomic<u32> responses_{0},response_us_{0},response_max_us_{0};
    std::atomic<u32> frames_{0},frame_crc_{0};
    ColorHistory color_history_;
    std::atomic<u32> last_bytes_{0},last_rectangles_{0},last_us_{0},full_frames_{0};
    std::atomic<u32> errors_{0};
    std::atomic<bool> failed_{false};
    bool dma_irq_ready_=false,dma_chain_configured_=false;
    bool color_active_=false,color_clear_=false,color_inverted_=false;
    bool pages_active_=false,pages_configured_=false,pages_selected_=false,pages_display_on_=false;
    u8 pages_write_=0,pages_transfer_=0,pages_snapshot_=0,pages_written_=0,pages_origin_=0,pages_first_=0;
    u16 pages_top_=0,pages_height_=0;
    u32 pages_scan_changed_at_=0;
    mk61_service_color_frame color_frames_[2]{};
    u8 color_slot_=0;
    u32 queued_strips_=0;
    lcd::Index4Pairs index4_pairs_;
    u16 color_palette_[64]{};
    bool palette_dirty_=false;
    lcd::Update update_;
    lcd::Scroll scroll_;
    lcd::ColorScroll color_scroll_;
    lcd::Region configured_region_;
    bool scroll_configured_=false;
    unsigned configured_start_=0,pending_scroll_rows_=0;
    std::atomic<u32> scrolls_{0},scrolled_rows_{0};
    u16 discard_=0;
    int dma_tx_=-1,dma_rx_=-1,dma_control_=-1;
    std::atomic<u32> last_strips_{0},last_pauses_{0};
    std::atomic<u32> color_chain_bytes_{0},color_chain_setup_us_{0},color_chain_dma_us_{0},color_chain_pauses_{0};
    void configure_dma(bool chain=true);
    u32 color_clock(u32 hz);
    void apply_clock();
    u32 clock_request() const;
    bool clock_pending() const;
    bool take_failure();
    bool color_pages_settled() const;
    unsigned color_page_offset(unsigned page) const { return page==pages_first_?0:pages_height_; }
    void set_color_page_origin(unsigned page);
    void prepare_color_pages();
    void end_color_pages();
    void completed_input(u64 now);
    lcd::Stream stream_;
    bool transfer_chain(const lcd::Rect& rect,u32& pauses,const mk61_service_color_frame* frame=nullptr);
    bool transfer_fill(u16 color,unsigned width,unsigned height);
    void abort_dma();
    void start_scanline(const u16* pixels,unsigned count);
    bool finish_scanline(bool service_io=false);
    void transfer();
    bool queue_color(const mk61_service_color_frame& frame);
    void transfer_queued_color(unsigned slot);
    void transfer_color(const mk61_service_color_frame& frame);
    void transfer_color_scroll();
    bool transfer_color_rect(const mk61_service_color_frame& frame,const lcd::Rect& rect,bool background,
                             u32& strips,u32& pauses,u32& windows);
    bool transfer_color_window(const mk61_service_color_frame& frame,const lcd::Rect& rect,unsigned physical_y,
                               bool background,u32& strips,u32& pauses);
};

} // namespace picocalc
#endif
