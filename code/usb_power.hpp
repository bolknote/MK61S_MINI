#ifndef MK61_USB_POWER_HPP
#define MK61_USB_POWER_HPP

#include "config.h"
#include "usb_power_policy.hpp"

#if defined(MK61_BUILD_FOCAL_MODULE) || \
    defined(MK61_BUILD_TINYBASIC_MODULE) || \
    defined(MK61_BUILD_WBMP_MODULE) || \
    defined(MK61_BUILD_MARKDOWN_MODULE) || \
    defined(MK61_BUILD_CHIP8_MODULE)
  #define MK61_USB_POWER_MODULE_BUILD 1
#else
  #define MK61_USB_POWER_MODULE_BUILD 0
#endif

#if MK61_ENABLE_USB_POWER_OBSERVER && defined(ARDUINO_ARCH_STM32) && \
    defined(USBCON) && !MK61_USB_POWER_MODULE_BUILD && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_USB_POWER_OBSERVER_SUPPORTED 1
#else
  #define MK61_USB_POWER_OBSERVER_SUPPORTED 0
#endif

#if MK61_USB_POWER_OBSERVER_SUPPORTED && \
    MK61_ENABLE_USB_SUSPEND_QUALIFICATION && \
    MK61_ENABLE_DEEP_IDLE_QUALIFICATION
  #define MK61_USB_SUSPEND_SUPPORTED 1
#else
  #define MK61_USB_SUSPEND_SUPPORTED 0
#endif

namespace usb_power {

enum EndpointBlocker : u32 {
  ENDPOINT_BLOCK_NOT_SUSPENDED = 1UL << 0,
  ENDPOINT_BLOCK_PREVIOUS_STATE = 1UL << 1,
  ENDPOINT_BLOCK_CLASS_DATA = 1UL << 2,
  ENDPOINT_BLOCK_CDC_TX = 1UL << 3,
  ENDPOINT_BLOCK_CDC_QUEUE = 1UL << 4,
  ENDPOINT_BLOCK_MSC_BOT = 1UL << 5,
  ENDPOINT_BLOCK_UNKNOWN_CLASS = 1UL << 6,
};

struct Snapshot {
  bool supported;
  bool wrappers_linked;
  bool callbacks_ready;
  bool qualification_enabled;
  bool configured_before_suspend;
  bool host_remote_wakeup_enabled;
  bool endpoints_idle;
  usb_power_policy::LinkState state;
  u8 raw_state;
  u8 old_state;
  u32 suspend_age_ms;
  u32 setup_callbacks;
  u32 reset_callbacks;
  u32 suspend_callbacks;
  u32 resume_callbacks;
  u32 connect_callbacks;
  u32 disconnect_callbacks;
  u32 stop_arms;
  u32 stop_aborts;
  u32 host_wakes;
  u32 local_wakes;
  u32 last_stop_blockers;
  u32 last_endpoint_blockers;
};

// Refreshes the main-context snapshot in addition to the exact IRQ wrappers.
void service(u32 now_ms);
Snapshot statistics(u32 now_ms);
void reset_statistics(void);
const char* backend_name(void);

bool suspended(void);
bool endpoints_idle(void);
u32 stop_blockers(bool application_idle, u32 now_ms);

// These calls bracket only a confirmed USB-suspended STOP interval. They do
// not stop, deinitialize or re-enumerate the USB device.
bool prepare_stop(bool application_idle, u32 now_ms);
bool stop_wake_pending(void);
bool finish_stop(bool usb_host_wake, bool keyboard_wake);
void cancel_stop(void);

} // namespace usb_power

#endif
