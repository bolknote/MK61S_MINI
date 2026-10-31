#ifndef MK61_PICOCALC_POWER_HPP
#define MK61_PICOCALC_POWER_HPP
#include "rust_types.h"
namespace picocalc {
struct IdleStatistics { u32 waits;u64 wait_us; };
void idle_until(u64 deadline,bool watch_input=true);
IdleStatistics idle_statistics();
// RP2040 SLEEP keeps the XOSC/RTC and polls the stock I2C keyboard. The
// USB sleep retains the normal SYS/peripheral clocks and both PLLs for E16.
// Battery sleep runs from 12 MHz XOSC with USB stopped and both PLLs off.
class SleepClocks {
public:
  void init();
  void enter();
  void leave();
  bool refresh();
  bool active() const { return active_; }
  bool usb_available() const { return !active_ || usb_; }
  u32 entries() const { return entries_; }
  u32 battery_entries() const { return battery_entries_; }
  unsigned pll_mask() const;
private:
  bool active_ = false, usb_ = true, usb_irq_ = false;
  u32 entries_ = 0, battery_entries_ = 0;
  u32 sys_hz_ = 0, peri_hz_ = 0, sleep_en0_ = 0, sleep_en1_ = 0, scr_ = 0;
  u32 adc_ctrl_ = 0, adc_div_ = 0, adc_hz_ = 0;
  u32 usb_ctrl_ = 0, usb_div_ = 0, usb_hz_ = 0;
};
class SleepPolicy {
public:
  bool asleep() const { return asleep_; }
  void sleep() { asleep_ = true; }
  bool wake(u64 now) {
    const bool was = asleep_;
    asleep_ = false;
    activity_ = now;
    return was;
  }
  void activity(u64 now) { activity_ = now; }
  bool due(u64 now, unsigned minutes, bool busy) const {
    return !asleep_ && !busy && minutes && now >= activity_ &&
           now - activity_ >= (u64)minutes * 60000000;
  }

private:
  bool asleep_ = false;
  u64 activity_ = 0;
};
} // namespace picocalc
#endif
