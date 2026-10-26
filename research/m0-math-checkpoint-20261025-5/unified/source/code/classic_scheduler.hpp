#ifndef MK61_CLASSIC_SCHEDULER_HPP
#define MK61_CLASSIC_SCHEDULER_HPP

#include "rust_types.h"

namespace classic_scheduler {

// Два ожидающих шага позволяют пережить короткий занятый участок переднего
// плана, но не дают программе затем долго догонять реальное время рывком.
static constexpr u8 MAX_PENDING_STEPS = 2;

struct Snapshot {
  bool active;
  u8 pending;
  u8 maximum_pending;
  u32 ticks;
  u32 steps;
  u32 missed_ticks;
};

class Scheduler {
  public:
    constexpr Scheduler(void)
      : active_(false), pending_(0), maximum_pending_(0), ticks_(0),
        steps_(0), missed_ticks_(0) {}

    bool active(void) const { return active_; }

    void set_active(bool active) {
      if(active_ == active) return;
      active_ = active;
      pending_ = 0;
    }

    void on_tick(void) {
      on_ticks(1);
    }

    void on_ticks(u32 count) {
      if(!active_ || count == 0) return;

      saturating_add(ticks_, count);
      const u8 room = (u8) (MAX_PENDING_STEPS - pending_);
      const u8 accepted = count < (u32) room ? (u8) count : room;
      pending_ = (u8) (pending_ + accepted);
      if(pending_ > maximum_pending_) maximum_pending_ = pending_;
      saturating_add(missed_ticks_, count - accepted);
    }

    bool take_step(void) {
      if(!active_ || pending_ == 0) return false;
      pending_--;
      saturating_add(steps_, 1);
      return true;
    }

    void reset_statistics(void) {
      ticks_ = 0;
      steps_ = 0;
      missed_ticks_ = 0;
      maximum_pending_ = pending_;
    }

    Snapshot snapshot(void) const {
      const Snapshot result = {
        active_, pending_, maximum_pending_, ticks_, steps_, missed_ticks_
      };
      return result;
    }

  private:
    static void saturating_add(volatile u32& value, u32 increment) {
      const u32 current = value;
      const u32 room = 0xFFFFFFFFUL - current;
      value = increment > room ? 0xFFFFFFFFUL : current + increment;
    }

    volatile bool active_;
    volatile u8 pending_;
    volatile u8 maximum_pending_;
    volatile u32 ticks_;
    volatile u32 steps_;
    volatile u32 missed_ticks_;
};

} // namespace classic_scheduler

#endif
