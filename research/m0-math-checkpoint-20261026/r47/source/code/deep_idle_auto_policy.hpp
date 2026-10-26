#ifndef MK61_DEEP_IDLE_AUTO_POLICY_HPP
#define MK61_DEEP_IDLE_AUTO_POLICY_HPP

#include "rust_types.h"

namespace deep_idle_auto_policy {

// A newly suspended, already-idle device may sleep promptly.  After any local
// activity it remains awake long enough for normal calculator interaction,
// then re-enters the same STOP backend if the host is still suspended.
static constexpr u32 INITIAL_IDLE_DELAY_MS = 1000U;
static constexpr u32 ACTIVITY_IDLE_DELAY_MS = 10000U;

enum class Phase : u8 {
  DISABLED,
  HOST_AWAKE,
  WAIT_USB,
  WAIT_INITIAL_IDLE,
  WAIT_ACTIVITY_IDLE,
  MANUAL_HOLDOFF,
  CONTROLLER_BUSY,
  READY,
};

struct Conditions {
  bool enabled;
  bool usb_suspended;
  bool controller_busy;
  bool local_idle;
  bool usb_ready;
};

struct Snapshot {
  Phase phase;
  bool manual_holdoff;
  u32 automatic_requests;
  u32 automatic_reentries;
  u32 wait_remaining_ms;
};

constexpr bool time_reached(u32 now, u32 target) {
  return (i32) (now - target) >= 0;
}

class Controller {
  public:
    constexpr Controller(void)
      : phase_(Phase::HOST_AWAKE), manual_holdoff_(false),
        suspend_observed_(false), requested_this_suspend_(false),
        deadline_valid_(false), activity_deadline_(false), deadline_ms_(0),
        automatic_requests_(0), automatic_reentries_(0) {}

    bool poll(const Conditions& conditions, u32 now_ms) {
      if(!conditions.enabled) {
        clear_session();
        phase_ = Phase::DISABLED;
        return false;
      }

      if(!conditions.usb_suspended) {
        clear_session();
        phase_ = Phase::HOST_AWAKE;
        return false;
      }

      if(!suspend_observed_) {
        suspend_observed_ = true;
        requested_this_suspend_ = false;
        deadline_valid_ = false;
        activity_deadline_ = false;
      }

      if(manual_holdoff_) {
        deadline_valid_ = false;
        phase_ = Phase::MANUAL_HOLDOFF;
        return false;
      }
      if(conditions.controller_busy) {
        phase_ = Phase::CONTROLLER_BUSY;
        return false;
      }

      // Every real local blocker restarts the interaction grace period. USB's
      // own 5 ms settle gate is handled separately and must not turn into a
      // ten-second delay on an otherwise idle initial suspend.
      if(!conditions.local_idle) {
        deadline_ms_ = now_ms + ACTIVITY_IDLE_DELAY_MS;
        deadline_valid_ = true;
        activity_deadline_ = true;
        phase_ = Phase::WAIT_ACTIVITY_IDLE;
        return false;
      }
      if(!conditions.usb_ready) {
        phase_ = Phase::WAIT_USB;
        return false;
      }

      if(!deadline_valid_) {
        deadline_ms_ = now_ms + INITIAL_IDLE_DELAY_MS;
        deadline_valid_ = true;
        activity_deadline_ = false;
      }
      if(!time_reached(now_ms, deadline_ms_)) {
        phase_ = activity_deadline_
            ? Phase::WAIT_ACTIVITY_IDLE : Phase::WAIT_INITIAL_IDLE;
        return false;
      }

      phase_ = Phase::READY;
      return true;
    }

    void note_request_accepted(void) {
      automatic_requests_ = saturating_increment(automatic_requests_);
      if(requested_this_suspend_) {
        automatic_reentries_ = saturating_increment(automatic_reentries_);
      }
      requested_this_suspend_ = true;
      deadline_valid_ = false;
      activity_deadline_ = false;
      phase_ = Phase::CONTROLLER_BUSY;
    }

    void note_request_rejected(u32 now_ms) {
      deadline_ms_ = now_ms + INITIAL_IDLE_DELAY_MS;
      deadline_valid_ = true;
      activity_deadline_ = false;
      phase_ = Phase::WAIT_INITIAL_IDLE;
    }

    // An explicit `prof deep` request owns the rest of this host-suspend
    // session. This keeps bounded HIL deterministic and prevents an automatic
    // request from starting immediately after its keyboard/RTC completion.
    void note_manual_completion(bool usb_suspended) {
      manual_holdoff_ = usb_suspended;
      if(usb_suspended) {
        suspend_observed_ = true;
        deadline_valid_ = false;
        phase_ = Phase::MANUAL_HOLDOFF;
      }
    }

    bool session_active(void) const {
      return suspend_observed_ || manual_holdoff_;
    }

    void reset_statistics(void) {
      automatic_requests_ = 0;
      automatic_reentries_ = 0;
    }

    Snapshot snapshot(u32 now_ms) const {
      u32 remaining = 0;
      if(deadline_valid_ && !time_reached(now_ms, deadline_ms_)) {
        remaining = deadline_ms_ - now_ms;
      }
      return {
        phase_, manual_holdoff_, automatic_requests_, automatic_reentries_,
        remaining
      };
    }

  private:
    static constexpr u32 saturating_increment(u32 value) {
      return value == 0xFFFFFFFFUL ? value : value + 1U;
    }

    void clear_session(void) {
      manual_holdoff_ = false;
      suspend_observed_ = false;
      requested_this_suspend_ = false;
      deadline_valid_ = false;
      activity_deadline_ = false;
      deadline_ms_ = 0;
    }

    Phase phase_;
    bool manual_holdoff_;
    bool suspend_observed_;
    bool requested_this_suspend_;
    bool deadline_valid_;
    bool activity_deadline_;
    u32 deadline_ms_;
    u32 automatic_requests_;
    u32 automatic_reentries_;
};

inline const char* phase_name(Phase phase) {
  switch(phase) {
    case Phase::DISABLED: return "disabled";
    case Phase::HOST_AWAKE: return "host-awake";
    case Phase::WAIT_USB: return "wait-usb";
    case Phase::WAIT_INITIAL_IDLE: return "wait-initial";
    case Phase::WAIT_ACTIVITY_IDLE: return "wait-activity";
    case Phase::MANUAL_HOLDOFF: return "manual-holdoff";
    case Phase::CONTROLLER_BUSY: return "busy";
    case Phase::READY: return "ready";
  }
  return "unknown";
}

} // namespace deep_idle_auto_policy

#endif
