#ifndef STM32_SRAM_BIT_BAND_HPP
#define STM32_SRAM_BIT_BAND_HPP

#include "rust_types.h"

#if defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
  #define MK61_STM32_SRAM_BIT_BAND_AVAILABLE 1
#else
  #define MK61_STM32_SRAM_BIT_BAND_AVAILABLE 0
#endif

#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
namespace stm32_sram_bit_band {

// STM32F401/F411 отображают первый мегабайт SRAM в bit-band alias region:
// каждому биту исходной памяти соответствует одно 32-битное слово alias.
static constexpr uintptr_t REGION_BASE = 0x20000000UL;
static constexpr uintptr_t ALIAS_BASE = 0x22000000UL;

inline volatile u32* alias_base(volatile void* storage) {
  const uintptr_t storage_address = reinterpret_cast<uintptr_t>(storage);
  return reinterpret_cast<volatile u32*>(
      ALIAS_BASE + ((storage_address - REGION_BASE) << 5U));
}

} // пространство имён stm32_sram_bit_band
#endif

#endif
