#ifndef MK61_IDLE_SLEEP_POLICY_HPP
#define MK61_IDLE_SLEEP_POLICY_HPP

#include "rust_types.h"

namespace idle_sleep_policy {

enum Blocker : u32 {
  BLOCK_FOREGROUND_CONTEXT = 1UL << 0,
  BLOCK_CALCULATOR_BUSY     = 1UL << 1,
  BLOCK_USB_MASS_STORAGE    = 1UL << 2,
  BLOCK_USB_SCREEN          = 1UL << 3,
  BLOCK_TERMINAL            = 1UL << 4,
  BLOCK_SOUND               = 1UL << 5,
  BLOCK_KEYBOARD            = 1UL << 6,
  BLOCK_CLASSIC             = 1UL << 7,
  BLOCK_SCHEDULED_WORK      = 1UL << 8,
  BLOCK_PERIODIC_WAKE       = 1UL << 9,
  BLOCK_IRQ_CONTEXT         = 1UL << 10,
};

static constexpr usize BLOCKER_COUNT = 11;

struct Conditions {
  bool foreground_context;
  bool calculator_idle;
  bool usb_mass_storage_active;
  bool usb_screen_work_pending;
  bool terminal_work_pending;
  bool sound_active;
  bool keyboard_active;
  bool classic_active;
  bool scheduled_work;
  bool periodic_wake_ready;
};

constexpr u32 blockers(const Conditions& value) {
  return (!value.foreground_context ? BLOCK_FOREGROUND_CONTEXT : 0) |
         (!value.calculator_idle ? BLOCK_CALCULATOR_BUSY : 0) |
         (value.usb_mass_storage_active ? BLOCK_USB_MASS_STORAGE : 0) |
         (value.usb_screen_work_pending ? BLOCK_USB_SCREEN : 0) |
         (value.terminal_work_pending ? BLOCK_TERMINAL : 0) |
         (value.sound_active ? BLOCK_SOUND : 0) |
         (value.keyboard_active ? BLOCK_KEYBOARD : 0) |
         (value.classic_active ? BLOCK_CLASSIC : 0) |
         (value.scheduled_work ? BLOCK_SCHEDULED_WORK : 0) |
         (!value.periodic_wake_ready ? BLOCK_PERIODIC_WAKE : 0);
}

constexpr u32 saturating_increment(u32 value) {
  return value == 0xFFFFFFFFUL ? value : value + 1U;
}

constexpr u64 saturating_add(u64 left, u64 right) {
  return left > ~((u64) 0) - right ? ~((u64) 0) : left + right;
}

struct Snapshot {
  u32 attempts;
  u32 entries;
  u64 total_sleep_us;
  u32 minimum_sleep_us;
  u32 maximum_sleep_us;
  u32 last_blockers;
  u32 rejected[BLOCKER_COUNT];

  u32 average_sleep_us(void) const {
    return entries == 0 ? 0 : (u32) (total_sleep_us / entries);
  }
};

// Pure accounting state used by the target WFI wrapper and host tests. No
// counter participates in eligibility, so saturation can never disable sleep.
class Tracker {
  public:
    constexpr Tracker(void)
      : attempts_(0), entries_(0), total_sleep_us_(0),
        minimum_sleep_us_(0xFFFFFFFFUL), maximum_sleep_us_(0),
        last_blockers_(0), rejected_{} {}

    void reset(void) {
      attempts_ = 0;
      entries_ = 0;
      total_sleep_us_ = 0;
      minimum_sleep_us_ = 0xFFFFFFFFUL;
      maximum_sleep_us_ = 0;
      last_blockers_ = 0;
      for(usize index = 0; index < BLOCKER_COUNT; index++) {
        rejected_[index] = 0;
      }
    }

    bool note_attempt(u32 mask) {
      attempts_ = saturating_increment(attempts_);
      last_blockers_ = mask;
      if(mask == 0) return true;
      for(usize index = 0; index < BLOCKER_COUNT; index++) {
        if((mask & ((u32) 1U << index)) != 0) {
          rejected_[index] = saturating_increment(rejected_[index]);
        }
      }
      return false;
    }

    void note_entry(u32 elapsed_us) {
      entries_ = saturating_increment(entries_);
      total_sleep_us_ = saturating_add(total_sleep_us_, elapsed_us);
      if(elapsed_us < minimum_sleep_us_) minimum_sleep_us_ = elapsed_us;
      if(elapsed_us > maximum_sleep_us_) maximum_sleep_us_ = elapsed_us;
    }

    Snapshot snapshot(void) const {
      Snapshot result = {
        attempts_, entries_, total_sleep_us_,
        entries_ == 0 ? 0 : minimum_sleep_us_, maximum_sleep_us_,
        last_blockers_, {}
      };
      for(usize index = 0; index < BLOCKER_COUNT; index++) {
        result.rejected[index] = rejected_[index];
      }
      return result;
    }

  private:
    u32 attempts_;
    u32 entries_;
    u64 total_sleep_us_;
    u32 minimum_sleep_us_;
    u32 maximum_sleep_us_;
    u32 last_blockers_;
    u32 rejected_[BLOCKER_COUNT];
};

inline const char* blocker_name(usize index) {
  switch(index) {
    case 0: return "foreground";
    case 1: return "calculator";
    case 2: return "msc";
    case 3: return "uscreen";
    case 4: return "terminal";
    case 5: return "sound";
    case 6: return "keyboard";
    case 7: return "classic";
    case 8: return "scheduled";
    case 9: return "wake";
    case 10: return "irq";
    default: return "unknown";
  }
}

} // namespace idle_sleep_policy

#endif
