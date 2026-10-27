#ifndef MK61_STM32F4_ADC_HPP
#define MK61_STM32F4_ADC_HPP
#include "rust_types.h"
#if defined(ARDUINO_ARCH_STM32)
#include <Arduino.h>
#endif
#if defined(ARDUINO_ARCH_STM32) &&                                                     \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
#define MK61_STM32F4_ADC_SUPPORTED 1
#else
#define MK61_STM32F4_ADC_SUPPORTED 0
#endif
namespace stm32f4_adc {
// ADC1 is reserved by stm32f4_platform_resources. No external pin map or
// runtime resolution is needed for the three fixed internal channels.
bool read_vbat(u16 &value);
bool read_internal(u16 &vref, u16 &temperature, u16 &vbat);
} // namespace stm32f4_adc
#endif
