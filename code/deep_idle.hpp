#ifndef MK61_DEEP_IDLE_HPP
#define MK61_DEEP_IDLE_HPP

#include "config.h"
#include "deep_idle_auto_policy.hpp"
#include "deep_idle_policy.hpp"

#if MK61_DEEP_IDLE_ENABLED && \
    defined(MK61_KEYBOARD_MINI) && defined(MK61_OLED1602_WS0010) && \
    defined(ARDUINO_ARCH_STM32) && defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_DEEP_IDLE_SUPPORTED 1
#else
  #define MK61_DEEP_IDLE_SUPPORTED 0
#endif

namespace deep_idle {

bool request(u8 seconds, u16 cycles, u32 now_ms);
bool cancel(void);
bool pending(void);
bool service_needed(void);
bool service(const deep_idle_policy::Conditions& conditions, u32 now_ms);
void reset_statistics(void);
deep_idle_policy::Snapshot statistics(void);
deep_idle_auto_policy::Snapshot automatic_statistics(u32 now_ms);
const char* backend_name(void);
bool enabled(void);
bool automatic_enabled(void);

} // namespace deep_idle

#endif
