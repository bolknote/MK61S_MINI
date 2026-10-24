#ifndef MK61_PICOCALC_HARDWARE_HPP
#define MK61_PICOCALC_HARDWARE_HPP

#include "screen.hpp"
#include "battery.hpp"
#include "lcd_update.hpp"
#include "lcd_chain.hpp"
#include <atomic>

namespace picocalc {

class Keyboard {
public:
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
    int lcd_backlight() const { return lcd_backlight_; }
    int key_backlight() const { return key_backlight_; }
private:
    bool online_ = false, pending_ = false, idle_ = false;
    u8 io_phase_ = 0;
    u64 due_ = 0,battery_due_ = 0;
    BatteryStatus battery_;
    u32 battery_errors_=0;
    u32 errors_ = 0;
    int lcd_backlight_ = -1, key_backlight_ = -1;
};

class Panel {
public:
    void init();
    void flush(const Screen& screen);
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
    bool valid_ = false;
    u32 spi_hz_ = 0;
    std::atomic<u32> frames_{0},frame_crc_{0};
    std::atomic<u32> last_bytes_{0},last_rectangles_{0},last_us_{0},full_frames_{0};
    std::atomic<u32> errors_{0};
    std::atomic<bool> failed_{false};
    bool dma_irq_ready_=false;
    lcd::Update update_;
    lcd::Scroll scroll_;
    lcd::Region configured_region_;
    bool scroll_configured_=false;
    unsigned configured_start_=0,pending_scroll_rows_=0;
    std::atomic<u32> scrolls_{0},scrolled_rows_{0};
    u16 discard_=0;
    int dma_tx_=-1,dma_rx_=-1,dma_control_=-1;
    std::atomic<u32> last_strips_{0},last_pauses_{0};
    void configure_dma();
    lcd::Stream stream_;
    bool transfer_chain(const lcd::Rect& rect,u32& pauses,u64& next_i2c);
    void abort_dma();
    void start_scanline(const u16* pixels,unsigned count);
    bool finish_scanline();
    void transfer();
};

} // namespace picocalc
#endif
