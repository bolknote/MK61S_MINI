#ifndef MK61_PICOCALC_CALCULATOR_HPP
#define MK61_PICOCALC_CALCULATOR_HPP

#include "mk61emu_core.h"

namespace picocalc {

struct Key {
    u8 x = 0;
    u8 y = 0;
    AngleUnit angle = NONE;
    const char* label = "";
    bool valid() const { return x != 0 || angle != NONE; }
};

// BIOS FIFO state 1 is an initial press. States 2/3 are hold/release.
// Momentary emulated presses are scheduled separately from the I2C poller.
struct KeyEvent {
    u8 state;
    u8 code;
    // USB Screen carries a calculator scan; the BIOS carries QWERTY text.
    u8 native_scan = 0xFF;
    bool pressed() const { return state == 1 && code != 0; }
};

Key map_key(u8 code);

struct Snapshot {
    char indicator[INDICATOR_STRING_LENGTH] = {};
    char face_indicator[INDICATOR_STRING_LENGTH] = {};
    char stack_values[3][INDICATOR_STRING_LENGTH] = {};
    u8 segments[12] = {};
    bool segmented = false;
    const char* last_key = "READY";
    AngleUnit angle = DEGREE;
    u8 ip = 0;
    bool running = false;
    bool programming = false;
    bool idle = true;
    u32 dropped_keys = 0;
};

class Calculator {
public:
    void init(bool expanded = false);
    void set_memory_mode(u8 mode);
    bool input(u8 code);
    void tick(bool script_owns_display = false);
    bool idle() const { return count_ == 0 && press_steps_ == 0 && !releasing_; }
    Snapshot snapshot() const;

private:
    static constexpr u8 QUEUE_SIZE = 32;
    Key queue_[QUEUE_SIZE] = {};
    Key active_;
    const char* last_key_ = "READY";
    u8 read_ = 0, count_ = 0, press_steps_ = 0;
    u16 release_steps_ = 0;
    u32 dropped_keys_ = 0;
    bool releasing_ = false, f_pending_ = false;
};

} // namespace picocalc
#endif
