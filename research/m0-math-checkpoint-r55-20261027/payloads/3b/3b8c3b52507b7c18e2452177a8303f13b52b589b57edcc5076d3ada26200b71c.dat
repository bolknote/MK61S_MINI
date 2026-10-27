#ifndef MK61_IDLE_SLEEP_HPP
#define MK61_IDLE_SLEEP_HPP

#include "idle_sleep_policy.hpp"

#ifndef MK61_ENABLE_IDLE_WFI
  #define MK61_ENABLE_IDLE_WFI 1
#endif
#if MK61_ENABLE_IDLE_WFI != 0 && MK61_ENABLE_IDLE_WFI != 1
  #error "MK61_ENABLE_IDLE_WFI must be 0 or 1"
#endif

#if MK61_ENABLE_IDLE_WFI && defined(ARDUINO_ARCH_STM32) && \
    defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_IDLE_WFI_SUPPORTED 1
#else
  #define MK61_IDLE_WFI_SUPPORTED 0
#endif

namespace idle_sleep {

// Executes only shallow Cortex-M Sleep. STOP/STANDBY and clock-tree changes
// are intentionally outside this API.
bool attempt(const idle_sleep_policy::Conditions& conditions);
void reset_statistics(void);
idle_sleep_policy::Snapshot statistics(void);
const char* backend_name(void);
bool enabled(void);

} // namespace idle_sleep

#endif
