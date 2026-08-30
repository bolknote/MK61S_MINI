#ifndef MK61_USB_POWER_POLICY_HPP
#define MK61_USB_POWER_POLICY_HPP

#include "rust_types.h"

namespace usb_power_policy {

// A short settle guard prevents a suspend IRQ immediately followed by host
// resume from racing the STOP entry critical section.  The calculator never
// initiates USB resume signalling; keyboard wake is local-only.
static constexpr u32 MIN_SUSPEND_AGE_MS = 5U;

enum class LinkState : u8 {
  LINK_DETACHED,
  LINK_DEFAULT,
  LINK_ADDRESSED,
  LINK_CONFIGURED,
  LINK_SUSPENDED,
  LINK_UNKNOWN,
};

enum StopBlocker : u32 {
  BLOCK_UNSUPPORTED = 1UL << 0,
  BLOCK_WRAPPERS = 1UL << 1,
  BLOCK_NOT_SUSPENDED = 1UL << 2,
  BLOCK_NOT_CONFIGURED = 1UL << 3,
  BLOCK_SUSPEND_SETTLE = 1UL << 4,
  BLOCK_ENDPOINTS = 1UL << 5,
  BLOCK_APPLICATION = 1UL << 6,
};

struct Conditions {
  bool supported;
  bool wrappers_ready;
  bool suspended;
  bool configured_before_suspend;
  bool endpoints_idle;
  bool application_idle;
  u32 suspend_age_ms;
};

constexpr u32 blocker_if(bool condition, StopBlocker blocker) {
  return condition ? static_cast<u32>(blocker) : 0U;
}

constexpr u32 stop_blockers(const Conditions& value) {
  return blocker_if(!value.supported, BLOCK_UNSUPPORTED) |
         blocker_if(!value.wrappers_ready, BLOCK_WRAPPERS) |
         blocker_if(!value.suspended, BLOCK_NOT_SUSPENDED) |
         blocker_if(!value.configured_before_suspend, BLOCK_NOT_CONFIGURED) |
         blocker_if(value.suspend_age_ms < MIN_SUSPEND_AGE_MS,
                    BLOCK_SUSPEND_SETTLE) |
         blocker_if(!value.endpoints_idle, BLOCK_ENDPOINTS) |
         blocker_if(!value.application_idle, BLOCK_APPLICATION);
}

constexpr bool stop_ready(const Conditions& value) {
  return stop_blockers(value) == 0;
}

constexpr LinkState classify(u8 state, bool present,
                             u8 state_default, u8 state_addressed,
                             u8 state_configured, u8 state_suspended) {
  if(!present) return LinkState::LINK_DETACHED;
  return state == state_default ? LinkState::LINK_DEFAULT :
         state == state_addressed ? LinkState::LINK_ADDRESSED :
         state == state_configured ? LinkState::LINK_CONFIGURED :
         state == state_suspended ? LinkState::LINK_SUSPENDED :
         LinkState::LINK_UNKNOWN;
}

inline const char* state_name(LinkState state) {
  switch(state) {
    case LinkState::LINK_DETACHED: return "detached";
    case LinkState::LINK_DEFAULT: return "default";
    case LinkState::LINK_ADDRESSED: return "addressed";
    case LinkState::LINK_CONFIGURED: return "configured";
    case LinkState::LINK_SUSPENDED: return "suspended";
    case LinkState::LINK_UNKNOWN: return "unknown";
  }
  return "unknown";
}

} // namespace usb_power_policy

#endif
