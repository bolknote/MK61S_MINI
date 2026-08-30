#include "usb_power.hpp"

#if MK61_USB_POWER_OBSERVER_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>

  extern "C" {
  #include <cdc_queue.h>
  #include <usbd_cdc.h>
  #include <usbd_cdc_if.h>
  #include <usbd_core.h>
  #include "usbd_msc.h"

  extern USBD_HandleTypeDef hUSBD_Device_CDC;
  extern PCD_HandleTypeDef g_hpcd;
  }
#endif

namespace usb_power {
namespace {

#if MK61_USB_POWER_OBSERVER_SUPPORTED

enum WrapperSeen : u8 {
  SEEN_SETUP = 1UL << 0,
  SEEN_RESET = 1UL << 1,
  SEEN_SUSPEND = 1UL << 2,
  SEEN_RESUME = 1UL << 3,
  SEEN_CONNECT = 1UL << 4,
  SEEN_DISCONNECT = 1UL << 5,
};

static constexpr u8 REQUIRED_RUNTIME_WRAPPERS = SEEN_SETUP | SEEN_RESET;

static volatile bool link_present;
static volatile u32 suspend_started_ms;
static volatile u8 wrappers_seen;
static volatile u16 setup_callbacks;
static volatile u16 reset_callbacks;
static volatile u16 suspend_callbacks;
static volatile u16 resume_callbacks;
static volatile u16 connect_callbacks;
static volatile u16 disconnect_callbacks;
#if MK61_USB_SUSPEND_SUPPORTED
static volatile u16 stop_arms;
static volatile u16 stop_aborts;
static volatile u16 host_wakes;
static volatile u16 local_wakes;
static volatile u8 last_stop_blockers;
static volatile u8 last_endpoint_blockers;
static volatile bool stop_armed;
#endif

static u32 load(const volatile u32& value) {
  return __atomic_load_n(&value, __ATOMIC_ACQUIRE);
}

static u16 load(const volatile u16& value) {
  return __atomic_load_n(&value, __ATOMIC_ACQUIRE);
}

static void store(volatile u32& target, u32 value) {
  __atomic_store_n(&target, value, __ATOMIC_RELEASE);
}

static void store(volatile u16& target, u16 value) {
  __atomic_store_n(&target, value, __ATOMIC_RELEASE);
}

static bool load_bool(const volatile bool& value) {
  return __atomic_load_n(&value, __ATOMIC_ACQUIRE);
}

static void store_bool(volatile bool& target, bool value) {
  __atomic_store_n(&target, value, __ATOMIC_RELEASE);
}

static u8 load_u8(const volatile u8& value) {
  return __atomic_load_n(&value, __ATOMIC_ACQUIRE);
}

#if MK61_USB_SUSPEND_SUPPORTED
static void store_u8(volatile u8& target, u8 value) {
  __atomic_store_n(&target, value, __ATOMIC_RELEASE);
}
#endif

static void increment(volatile u16& target) {
  u16 value = load(target);
  while(value != 0xFFFFU &&
        !__atomic_compare_exchange_n(&target, &value, (u16) (value + 1U), false,
                                     __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {}
}

static void note_wrapper(u8 bit, volatile u16& counter) {
  __atomic_fetch_or(&wrappers_seen, bit, __ATOMIC_ACQ_REL);
  increment(counter);
}

static USBD_HandleTypeDef* device(void) {
  return &hUSBD_Device_CDC;
}

static void observe(USBD_HandleTypeDef* value, bool present) {
  if(value != device()) return;
  store_bool(link_present, present);
}

static bool active_class_is(USBD_HandleTypeDef* value,
                            USBD_ClassTypeDef* expected) {
  return value != nullptr && expected != nullptr &&
         value->classId < USBD_MAX_SUPPORTED_CLASS &&
         value->pClass[value->classId] == expected;
}

static void* active_class_data(USBD_HandleTypeDef* value) {
  if(value == nullptr || value->classId >= USBD_MAX_SUPPORTED_CLASS) {
    return nullptr;
  }
  void* result = value->pClassDataCmsit[value->classId];
  return result != nullptr ? result : value->pClassData;
}

static u8 endpoint_blockers_now(void) {
  USBD_HandleTypeDef* const value = device();
  u8 result = 0;
  if(value->dev_state != USBD_STATE_SUSPENDED) {
    result |= ENDPOINT_BLOCK_NOT_SUSPENDED;
  }
  if(value->dev_old_state != USBD_STATE_CONFIGURED) {
    result |= ENDPOINT_BLOCK_PREVIOUS_STATE;
  }
  // Do not gate STOP on the USB middleware's logical ep0_state.  A bus
  // suspend IRQ is itself the authoritative transaction boundary, and the ST
  // low-power path enters STOP directly from that callback.  In practice the
  // final host power-management request can leave EP0 in STATUS even though
  // the status packet has completed; requiring IDLE then deadlocks suspend.

  if(active_class_is(value, USBD_CDC_CLASS)) {
    const USBD_CDC_HandleTypeDef* const cdc =
        static_cast<const USBD_CDC_HandleTypeDef*>(active_class_data(value));
    if(cdc == nullptr) {
      result |= ENDPOINT_BLOCK_CLASS_DATA;
    } else if(cdc->TxState != 0U) {
      result |= ENDPOINT_BLOCK_CDC_TX;
    }
    if(CDC_TransmitQueue_ReadSize(&TransmitQueue) != 0) {
      result |= ENDPOINT_BLOCK_CDC_QUEUE;
    }
    return result;
  }

  if(active_class_is(value, USBD_MSC_CLASS)) {
    const USBD_MSC_BOT_HandleTypeDef* const msc =
        static_cast<const USBD_MSC_BOT_HandleTypeDef*>(
            active_class_data(value));
    if(msc == nullptr) {
      result |= ENDPOINT_BLOCK_CLASS_DATA;
    } else if(msc->bot_state != USBD_BOT_IDLE ||
              msc->bot_status != USBD_BOT_STATUS_NORMAL) {
      result |= ENDPOINT_BLOCK_MSC_BOT;
    }
    return result;
  }

  return result | ENDPOINT_BLOCK_UNKNOWN_CLASS;
}

static bool endpoints_are_idle(void) {
  return endpoint_blockers_now() == 0U;
}

extern "C" USBD_StatusTypeDef __real_USBD_LL_SetupStage(
    USBD_HandleTypeDef*, u8*) __attribute__((weak));
extern "C" USBD_StatusTypeDef __real_USBD_LL_Reset(
    USBD_HandleTypeDef*) __attribute__((weak));
extern "C" USBD_StatusTypeDef __real_USBD_LL_Suspend(
    USBD_HandleTypeDef*) __attribute__((weak));
extern "C" USBD_StatusTypeDef __real_USBD_LL_Resume(
    USBD_HandleTypeDef*) __attribute__((weak));
extern "C" USBD_StatusTypeDef __real_USBD_LL_DevConnected(
    USBD_HandleTypeDef*) __attribute__((weak));
extern "C" USBD_StatusTypeDef __real_USBD_LL_DevDisconnected(
    USBD_HandleTypeDef*) __attribute__((weak));

static bool wrappers_linked(void) {
  return __real_USBD_LL_SetupStage != nullptr &&
         __real_USBD_LL_Reset != nullptr &&
         __real_USBD_LL_Suspend != nullptr &&
         __real_USBD_LL_Resume != nullptr &&
         __real_USBD_LL_DevConnected != nullptr &&
         __real_USBD_LL_DevDisconnected != nullptr;
}

static bool callbacks_ready(void) {
  return wrappers_linked() &&
      (load_u8(wrappers_seen) & REQUIRED_RUNTIME_WRAPPERS) ==
          REQUIRED_RUNTIME_WRAPPERS;
}

#if MK61_USB_SUSPEND_SUPPORTED
static usb_power_policy::Conditions conditions(bool application_idle,
                                                u32 now_ms,
                                                u8 endpoint_blockers) {
  USBD_HandleTypeDef* const value = device();
  const bool present = load_bool(link_present);
  const u8 state = value->dev_state;
  const u32 started = load(suspend_started_ms);
  const bool is_suspended = present && state == USBD_STATE_SUSPENDED;
  return {
    MK61_USB_SUSPEND_SUPPORTED != 0,
    callbacks_ready(),
    is_suspended,
    is_suspended && value->dev_old_state == USBD_STATE_CONFIGURED,
    endpoint_blockers == 0U,
    application_idle,
    is_suspended ? now_ms - started : 0U,
  };
}
#endif

[[maybe_unused]] static void enable_usb_wakeup_irq(void) {
#if MK61_USB_SUSPEND_SUPPORTED && defined(USB_OTG_FS) && \
    defined(OTG_FS_WKUP_IRQn)
  __HAL_USB_OTG_FS_WAKEUP_EXTI_ENABLE_RISING_EDGE();
  __HAL_USB_OTG_FS_WAKEUP_EXTI_ENABLE_IT();
  HAL_NVIC_SetPriority(OTG_FS_WKUP_IRQn, USBD_IRQ_PRIO, USBD_IRQ_SUBPRIO);
  HAL_NVIC_EnableIRQ(OTG_FS_WKUP_IRQn);
#endif
}

[[maybe_unused]] static void clear_usb_wakeup_flag(void) {
#if MK61_USB_SUSPEND_SUPPORTED && defined(USB_OTG_FS)
  __HAL_USB_OTG_FS_WAKEUP_EXTI_CLEAR_FLAG();
#endif
}

#endif

} // namespace

#if MK61_USB_POWER_OBSERVER_SUPPORTED

extern "C" USBD_StatusTypeDef __wrap_USBD_LL_SetupStage(
    USBD_HandleTypeDef* value, u8* setup) {
  if(__real_USBD_LL_SetupStage == nullptr) return USBD_FAIL;
  const USBD_StatusTypeDef result = __real_USBD_LL_SetupStage(value, setup);
  note_wrapper(SEEN_SETUP, setup_callbacks);
  observe(value, true);
  return result;
}

extern "C" USBD_StatusTypeDef __wrap_USBD_LL_Reset(
    USBD_HandleTypeDef* value) {
  if(__real_USBD_LL_Reset == nullptr) return USBD_FAIL;
  const USBD_StatusTypeDef result = __real_USBD_LL_Reset(value);
  note_wrapper(SEEN_RESET, reset_callbacks);
  observe(value, true);
  return result;
}

extern "C" USBD_StatusTypeDef __wrap_USBD_LL_Suspend(
    USBD_HandleTypeDef* value) {
  if(__real_USBD_LL_Suspend == nullptr) return USBD_FAIL;
  const USBD_StatusTypeDef result = __real_USBD_LL_Suspend(value);
  note_wrapper(SEEN_SUSPEND, suspend_callbacks);
  store(suspend_started_ms, HAL_GetTick());
  observe(value, true);
  return result;
}

extern "C" USBD_StatusTypeDef __wrap_USBD_LL_Resume(
    USBD_HandleTypeDef* value) {
  if(__real_USBD_LL_Resume == nullptr) return USBD_FAIL;
  const USBD_StatusTypeDef result = __real_USBD_LL_Resume(value);
  note_wrapper(SEEN_RESUME, resume_callbacks);
  store(suspend_started_ms, 0);
#if MK61_USB_SUSPEND_SUPPORTED
  g_hpcd.Init.low_power_enable = DISABLE;
  store_bool(stop_armed, false);
#endif
  observe(value, true);
  return result;
}

extern "C" USBD_StatusTypeDef __wrap_USBD_LL_DevConnected(
    USBD_HandleTypeDef* value) {
  if(__real_USBD_LL_DevConnected == nullptr) return USBD_FAIL;
  const USBD_StatusTypeDef result = __real_USBD_LL_DevConnected(value);
  note_wrapper(SEEN_CONNECT, connect_callbacks);
  observe(value, true);
  return result;
}

extern "C" USBD_StatusTypeDef __wrap_USBD_LL_DevDisconnected(
    USBD_HandleTypeDef* value) {
  if(__real_USBD_LL_DevDisconnected == nullptr) return USBD_FAIL;
  const USBD_StatusTypeDef result = __real_USBD_LL_DevDisconnected(value);
  note_wrapper(SEEN_DISCONNECT, disconnect_callbacks);
#if MK61_USB_SUSPEND_SUPPORTED
  g_hpcd.Init.low_power_enable = DISABLE;
  store_bool(stop_armed, false);
#endif
  observe(value, false);
  return result;
}

#endif

void service(u32 now_ms) {
#if MK61_USB_POWER_OBSERVER_SUPPORTED
  USBD_HandleTypeDef* const value = &hUSBD_Device_CDC;
  const u8 state = value->dev_state;
  if(value->pData == nullptr) {
    store_bool(link_present, false);
  } else if(state == USBD_STATE_ADDRESSED ||
            state == USBD_STATE_CONFIGURED ||
            state == USBD_STATE_SUSPENDED) {
    // DEFAULT alone is ambiguous before the first bus reset. Exact reset and
    // disconnect wrappers own that transition, avoiding a false "connected"
    // report merely because the USB stack was initialized without a cable.
    store_bool(link_present, true);
  }
  if(state == USBD_STATE_SUSPENDED && load(suspend_started_ms) == 0U) {
    store(suspend_started_ms, now_ms);
  } else if(state != USBD_STATE_SUSPENDED) {
    store(suspend_started_ms, 0);
  }
#else
  (void) now_ms;
#endif
}

Snapshot statistics(u32 now_ms) {
#if MK61_USB_POWER_OBSERVER_SUPPORTED
  service(now_ms);
  USBD_HandleTypeDef* const value = device();
  const bool present = load_bool(link_present);
  const u8 state = value->dev_state;
  const u8 previous_state = value->dev_old_state;
  const bool is_suspended = present && state == USBD_STATE_SUSPENDED;
  const u32 started = load(suspend_started_ms);
#if MK61_USB_SUSPEND_SUPPORTED
  const u32 arm_count = load(stop_arms);
  const u32 abort_count = load(stop_aborts);
  const u32 host_wake_count = load(host_wakes);
  const u32 local_wake_count = load(local_wakes);
  const u32 stop_blocker_bits = load_u8(last_stop_blockers);
  const u32 endpoint_blocker_bits = load_u8(last_endpoint_blockers);
#else
  constexpr u32 arm_count = 0;
  constexpr u32 abort_count = 0;
  constexpr u32 host_wake_count = 0;
  constexpr u32 local_wake_count = 0;
  constexpr u32 stop_blocker_bits = 0;
  constexpr u32 endpoint_blocker_bits = 0;
#endif
  return {
    true,
    wrappers_linked(),
    callbacks_ready(),
    MK61_USB_SUSPEND_SUPPORTED != 0,
    is_suspended && previous_state == USBD_STATE_CONFIGURED,
    value != nullptr && value->dev_remote_wakeup != 0U,
    endpoints_are_idle(),
    usb_power_policy::classify(
        state, present, USBD_STATE_DEFAULT, USBD_STATE_ADDRESSED,
        USBD_STATE_CONFIGURED, USBD_STATE_SUSPENDED),
    state,
    previous_state,
    is_suspended ? now_ms - started : 0U,
    load(setup_callbacks),
    load(reset_callbacks),
    load(suspend_callbacks),
    load(resume_callbacks),
    load(connect_callbacks),
    load(disconnect_callbacks),
    arm_count,
    abort_count,
    host_wake_count,
    local_wake_count,
    stop_blocker_bits,
    endpoint_blocker_bits,
  };
#else
  (void) now_ms;
  return {
    false, false, false, false, false, false, false,
    usb_power_policy::LinkState::LINK_DETACHED, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
  };
#endif
}

void reset_statistics(void) {
#if MK61_USB_POWER_OBSERVER_SUPPORTED
  store(setup_callbacks, 0);
  store(reset_callbacks, 0);
  store(suspend_callbacks, 0);
  store(resume_callbacks, 0);
  store(connect_callbacks, 0);
  store(disconnect_callbacks, 0);
#if MK61_USB_SUSPEND_SUPPORTED
  store(stop_arms, 0);
  store(stop_aborts, 0);
  store(host_wakes, 0);
  store(local_wakes, 0);
  store_u8(last_stop_blockers, 0);
  store_u8(last_endpoint_blockers, 0);
#endif
#endif
}

const char* backend_name(void) {
  return MK61_USB_POWER_OBSERVER_SUPPORTED ? "STM32-OTGFS-wrap" : "disabled";
}

bool suspended(void) {
#if MK61_USB_POWER_OBSERVER_SUPPORTED
  return load_bool(link_present) &&
      device()->dev_state == USBD_STATE_SUSPENDED;
#else
  return false;
#endif
}

bool endpoints_idle(void) {
#if MK61_USB_POWER_OBSERVER_SUPPORTED
  return endpoints_are_idle();
#else
  return false;
#endif
}

u32 stop_blockers(bool application_idle, u32 now_ms) {
#if MK61_USB_SUSPEND_SUPPORTED
  const u8 endpoint_blockers = endpoint_blockers_now();
  const usb_power_policy::Conditions current =
      conditions(application_idle, now_ms, endpoint_blockers);
  const u32 result = usb_power_policy::stop_blockers(current);
  // Preserve the last decision made while the bus was genuinely suspended.
  // Calls after host resume must not overwrite the useful diagnosis with the
  // expected NOT_SUSPENDED/ENDPOINT state of an active link.
  if(current.suspended) {
    store_u8(last_stop_blockers, (u8) result);
    store_u8(last_endpoint_blockers, endpoint_blockers);
  }
  return result;
#else
  (void) application_idle;
  (void) now_ms;
  return usb_power_policy::BLOCK_UNSUPPORTED;
#endif
}

bool prepare_stop(bool application_idle, u32 now_ms) {
#if MK61_USB_SUSPEND_SUPPORTED
  const u32 blockers = stop_blockers(application_idle, now_ms);
  if(blockers != 0U) return false;
  enable_usb_wakeup_irq();
  // The Core's suspend callback has already run, so enabling this here cannot
  // trigger its automatic SLEEPONEXIT path. It only lets the stock wake IRQ
  // restore clocks and ungate the PHY if the host resumes during our STOP.
  g_hpcd.Init.low_power_enable = ENABLE;
  store_bool(stop_armed, true);
  if(stop_wake_pending()) {
    cancel_stop();
    return false;
  }
  increment(stop_arms);
  return true;
#else
  (void) application_idle;
  (void) now_ms;
  return false;
#endif
}

bool stop_wake_pending(void) {
#if MK61_USB_SUSPEND_SUPPORTED && defined(USB_OTG_FS)
  const u32 pending = __HAL_USB_OTG_FS_WAKEUP_EXTI_GET_FLAG();
  return pending != 0U;
#else
  return false;
#endif
}

bool finish_stop(bool usb_host_wake, bool keyboard_wake) {
#if MK61_USB_SUSPEND_SUPPORTED
  if(!load_bool(stop_armed)) return false;
  if(usb_host_wake) increment(host_wakes);
  if(keyboard_wake) increment(local_wakes);

  if(usb_host_wake) {
    // The host owns resume.  Restore the PHY immediately and let the pending
    // USB core IRQ complete the middleware CONFIGURED transition.
    __HAL_PCD_UNGATE_PHYCLOCK(&g_hpcd);
    g_hpcd.Init.low_power_enable = DISABLE;
    clear_usb_wakeup_flag();
  }
  // For keyboard and RTC wake the host is still suspended.  Keep its PHY
  // clock gated and its wake IRQ armed while the calculator runs locally;
  // this is deliberately not USB Remote Wake.
  store_bool(stop_armed, false);
  return true;
#else
  (void) usb_host_wake;
  (void) keyboard_wake;
  return false;
#endif
}

void cancel_stop(void) {
#if MK61_USB_SUSPEND_SUPPORTED
  if(!load_bool(stop_armed)) return;
  if(!suspended()) {
    __HAL_PCD_UNGATE_PHYCLOCK(&g_hpcd);
    g_hpcd.Init.low_power_enable = DISABLE;
    clear_usb_wakeup_flag();
  }
  store_bool(stop_armed, false);
  increment(stop_aborts);
#endif
}

} // namespace usb_power
