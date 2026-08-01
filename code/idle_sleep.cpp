#include "idle_sleep.hpp"

#if MK61_IDLE_WFI_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>
#endif

namespace idle_sleep {
namespace {

static idle_sleep_policy::Tracker tracker;

} // namespace

bool attempt(const idle_sleep_policy::Conditions& conditions) {
  u32 mask = idle_sleep_policy::blockers(conditions);

#if MK61_IDLE_WFI_SUPPORTED
  // idle_main_process() must never sleep from an exception or from a caller
  // that deliberately masked interrupts: neither context guarantees a wake.
  const u32 primask = __get_PRIMASK();
  if(primask != 0 || __get_IPSR() != 0) {
    mask |= idle_sleep_policy::BLOCK_IRQ_CONTEXT;
  }
  if(!tracker.note_attempt(mask)) return false;

  const u32 started_us = micros();
  __disable_irq();

  // Shallow Sleep keeps the clock tree and all peripherals configured. Saving
  // SCR avoids changing another owner's SEVONPEND/SLEEPONEXIT policy.
  const u32 saved_scr = SCB->SCR;
  SCB->SCR = saved_scr & ~SCB_SCR_SLEEPDEEP_Msk;
  __DSB();
  __WFI();
  __ISB();
  SCB->SCR = saved_scr;
  __DSB();
  __set_PRIMASK(primask);

  // A pending SysTick/USB/timer exception runs as soon as PRIMASK is restored,
  // so micros() observes wall time rather than only active CPU cycles.
  tracker.note_entry((u32) (micros() - started_us));
  return true;
#else
  mask |= idle_sleep_policy::BLOCK_IRQ_CONTEXT;
  (void) tracker.note_attempt(mask);
  return false;
#endif
}

void reset_statistics(void) {
  tracker.reset();
}

idle_sleep_policy::Snapshot statistics(void) {
  return tracker.snapshot();
}

const char* backend_name(void) {
#if MK61_IDLE_WFI_SUPPORTED
  return "WFI";
#else
  return "disabled";
#endif
}

bool enabled(void) {
  return MK61_IDLE_WFI_SUPPORTED != 0;
}

} // namespace idle_sleep
