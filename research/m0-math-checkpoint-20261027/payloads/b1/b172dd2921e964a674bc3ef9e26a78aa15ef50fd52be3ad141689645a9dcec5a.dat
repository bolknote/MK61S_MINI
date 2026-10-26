#ifndef MK61_STM32F4_BUZZER_HPP
#define MK61_STM32F4_BUZZER_HPP
#include <Arduino.h>
#include "config.h"
#include "stm32f4_platform_resources.hpp"
#if MK61_STM32F4_RESOURCE_MAP_SUPPORTED
namespace stm32f4_buzzer {
static_assert(PIN_BUZZER == PA0 || PIN_BUZZER == PB9 || PIN_BUZZER == PB10,
              "qualify a fixed timer/channel/AF route for this buzzer pin");
static constexpr u8 BIT = PIN_BUZZER == PA0 ? 0 : (PIN_BUZZER == PB9 ? 9 : 10);
static constexpr u8 CHANNEL = PIN_BUZZER == PB9 ? 4 : (PIN_BUZZER == PB10 ? 3 : 1);
static constexpr u8 AF = PIN_BUZZER == PB9 ? 2 : 1;
inline TIM_TypeDef* timer() { return PIN_BUZZER == PB9 ? TIM4 : TIM2; }
inline void enable_timer_clock() {
  RCC->APB1ENR |= PIN_BUZZER == PB9 ? RCC_APB1ENR_TIM4EN : RCC_APB1ENR_TIM2EN;
  (void)RCC->APB1ENR;
}
inline void alternate_function() {
  GPIO_TypeDef* const port = PIN_BUZZER == PA0 ? GPIOA : GPIOB;
  RCC->AHB1ENR |= PIN_BUZZER == PA0 ? RCC_AHB1ENR_GPIOAEN : RCC_AHB1ENR_GPIOBEN;
  (void)RCC->AHB1ENR;
  constexpr u32 pair = 3U << (BIT * 2U);
  constexpr u32 af_shift = (BIT & 7U) * 4U;
  port->OTYPER &= ~(1U << BIT);
  port->OSPEEDR |= pair;
  port->PUPDR &= ~pair;
  port->AFR[BIT >> 3] = (port->AFR[BIT >> 3] & ~(15U << af_shift)) | ((u32)AF << af_shift);
  port->MODER = (port->MODER & ~pair) | (2U << (BIT * 2U));
}
} // namespace stm32f4_buzzer
#endif
#endif
