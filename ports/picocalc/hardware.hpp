#ifndef MK61_PICOCALC_HARDWARE_HPP
#define MK61_PICOCALC_HARDWARE_HPP

#include "screen.hpp"

namespace picocalc {

class Keyboard {
public:
    void init();
    bool poll(KeyEvent& event);
    void backlight(u8 lcd = 240, u8 keys = 40);
    void idle(bool enabled) { idle_ = enabled; }
    void clock_changed();
    bool transaction_pending() const { return pending_; }
    bool online() const { return online_; }
    u32 errors() const { return errors_; }
    int lcd_backlight() const { return lcd_backlight_; }
    int key_backlight() const { return key_backlight_; }
private:
    bool online_ = false, pending_ = false, idle_ = false;
    u64 due_ = 0;
    u32 errors_ = 0;
    int lcd_backlight_ = -1, key_backlight_ = -1;
};

class Panel {
public:
    void init();
    void flush(const Screen& screen);
    void sleep(bool enabled);
    u32 spi_hz() const { return spi_hz_; }
    u32 frames() const { return frames_; }
private:
    u8 previous_[Screen::BYTES] = {};
    bool valid_ = false;
    u32 spi_hz_ = 0, frames_ = 0;
};

} // namespace picocalc
#endif
