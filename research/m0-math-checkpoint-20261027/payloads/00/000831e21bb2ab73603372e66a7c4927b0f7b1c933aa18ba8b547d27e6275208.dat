#ifndef MK61_WATCHDOG_GATE_HPP
#define MK61_WATCHDOG_GATE_HPP

#include "rust_types.h"

namespace watchdog_gate {

static constexpr u32 MINIMUM_RELOAD_INTERVAL_MS = 250;

struct Snapshot {
  bool started;
  bool inhibited;
  u32 epochs;
  u32 reloads;
  u32 last_epoch_ms;
  u32 last_reload_ms;
  u32 maximum_reload_gap_ms;
};

// Gate не знает о IWDG и пригоден для host-тестов. Reload разрешается только
// после нового полностью завершённого foreground epoch и не чаще заданного
// интервала; ISR не имеет входа в этот интерфейс.
class Gate {
  public:
    constexpr Gate(void)
      : started_(false), inhibited_(false), epoch_pending_(false), epochs_(0),
        reloads_(0), last_epoch_ms_(0), last_reload_ms_(0),
        maximum_reload_gap_ms_(0) {}

    void start(u32 now_ms) {
      started_ = true;
      inhibited_ = false;
      epoch_pending_ = false;
      epochs_ = 0;
      reloads_ = 1; // initialize() выполняет первую аппаратную reload.
      last_epoch_ms_ = now_ms;
      last_reload_ms_ = now_ms;
      maximum_reload_gap_ms_ = 0;
    }

    void note_epoch(u32 now_ms) {
      if(!started_) return;
      if(epochs_ != 0xFFFFFFFFUL) epochs_++;
      // Feed eligibility must not depend on the diagnostic counter. At the
      // observed foreground rate that counter can saturate in roughly a day;
      // a separate edge flag keeps the watchdog healthy indefinitely.
      epoch_pending_ = true;
      last_epoch_ms_ = now_ms;
    }

    bool take_reload(u32 now_ms) {
      if(!started_ || inhibited_ || !epoch_pending_ ||
         (u32) (now_ms - last_reload_ms_) < MINIMUM_RELOAD_INTERVAL_MS) {
        return false;
      }
      epoch_pending_ = false;
      const u32 gap = now_ms - last_reload_ms_;
      if(gap > maximum_reload_gap_ms_) maximum_reload_gap_ms_ = gap;
      last_reload_ms_ = now_ms;
      if(reloads_ != 0xFFFFFFFFUL) reloads_++;
      return true;
    }

    void inhibit(void) { inhibited_ = true; }

    Snapshot snapshot(void) const {
      const Snapshot result = {
        started_, inhibited_, epochs_, reloads_, last_epoch_ms_,
        last_reload_ms_, maximum_reload_gap_ms_
      };
      return result;
    }

  private:
    bool started_;
    bool inhibited_;
    bool epoch_pending_;
    u32 epochs_;
    u32 reloads_;
    u32 last_epoch_ms_;
    u32 last_reload_ms_;
    u32 maximum_reload_gap_ms_;
};

} // namespace watchdog_gate

#endif
