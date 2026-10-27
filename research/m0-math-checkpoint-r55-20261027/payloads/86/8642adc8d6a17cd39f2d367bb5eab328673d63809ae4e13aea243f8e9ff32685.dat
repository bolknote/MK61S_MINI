#ifndef MK61_STM32F4_KEYBOARD_EXTI_HPP
#define MK61_STM32F4_KEYBOARD_EXTI_HPP
#include <Arduino.h>
#include "stm32f4_platform_resources.hpp"
#if MK61_STM32F4_RESOURCE_MAP_SUPPORTED
namespace stm32f4_keyboard_exti {
static constexpr u32 MASK = 0x1F0UL; // PB4..PB8; EXTI4 and EXTI9_5 belong to the keyboard.
inline void arm() {
  RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;
  (void)RCC->APB2ENR;
  EXTI->IMR &= ~MASK;
  SYSCFG->EXTICR[1] = (SYSCFG->EXTICR[1] & ~0xFFFFU) | 0x1111UL;
  SYSCFG->EXTICR[2] = (SYSCFG->EXTICR[2] & ~15U) | 1UL;
  EXTI->FTSR &= ~MASK;
  EXTI->RTSR |= MASK;
  EXTI->PR = MASK;
  NVIC_ClearPendingIRQ(EXTI4_IRQn);
  NVIC_ClearPendingIRQ(EXTI9_5_IRQn);
  // Preserve STM32duino's Cortex-M4 EXTI default priority.
  NVIC_SetPriority(EXTI4_IRQn, 6);
  NVIC_SetPriority(EXTI9_5_IRQn, 6);
  EXTI->IMR |= MASK;
  NVIC_EnableIRQ(EXTI4_IRQn);
  NVIC_EnableIRQ(EXTI9_5_IRQn);
}
inline u32 take_pending() {
  const u32 pending = EXTI->PR & EXTI->IMR & MASK;
  EXTI->PR = pending; // W1C only the observed rows; preserve a concurrent different row.
  __DSB();
  return pending;
}
inline void disarm() {
  EXTI->IMR &= ~MASK;
  NVIC_DisableIRQ(EXTI4_IRQn);
  NVIC_DisableIRQ(EXTI9_5_IRQn);
  EXTI->PR = MASK;
  NVIC_ClearPendingIRQ(EXTI4_IRQn);
  NVIC_ClearPendingIRQ(EXTI9_5_IRQn);
}
} // namespace stm32f4_keyboard_exti
#endif
#endif
