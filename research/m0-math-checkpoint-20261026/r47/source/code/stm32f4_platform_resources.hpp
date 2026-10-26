#ifndef MK61_STM32F4_PLATFORM_RESOURCES_HPP
#define MK61_STM32F4_PLATFORM_RESOURCES_HPP

#include "rust_types.h"

// Этот заголовок подключается после Arduino/CMSIS, поэтому TIMx_BASE и TIMx
// уже известны. Здесь хранится единая карта ресурсов, общая для штатных
// STM32F401/F411; последующие DMA-этапы должны использовать те же значения.
#if defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_STM32F4_RESOURCE_MAP_SUPPORTED 1

  #define MK61_CLASSIC_TIMER_INSTANCE TIM9
  #define MK61_SPI1_RX_DMA_INSTANCE DMA2_Stream2
  #define MK61_SPI1_TX_DMA_INSTANCE DMA2_Stream3
  #define MK61_SPI1_RX_DMA_IRQ DMA2_Stream2_IRQn
  #define MK61_SPI1_TX_DMA_IRQ DMA2_Stream3_IRQn

namespace stm32f4_platform_resources {

static constexpr u8 SPI1_DMA_CONTROLLER = 2;
static constexpr u8 SPI1_RX_DMA_STREAM = 2;
static constexpr u8 SPI1_RX_DMA_CHANNEL = 3;
static constexpr u8 SPI1_TX_DMA_STREAM = 3;
static constexpr u8 SPI1_TX_DMA_CHANNEL = 3;

static constexpr u8 ADC1_DMA_CONTROLLER = 2;
static constexpr u8 ADC1_DMA_STREAM = 0;
static constexpr u8 ADC1_DMA_CHANNEL = 0;

// Штатные buzzer pin используют TIM2, TIM4 либо TIM5. Отсечка звука
// обслуживается общим SysTick, TIM10 остаётся свободным, TIM11 зарезервирован
// STM32duino под Servo.
static_assert(TIM9_BASE != TIM2_BASE && TIM9_BASE != TIM4_BASE &&
              TIM9_BASE != TIM5_BASE,
              "CLASSIC timer conflicts with a supported buzzer PWM timer");
static_assert(TIM9_BASE != TIM11_BASE,
              "CLASSIC timer conflicts with STM32duino Servo timer");
static_assert(SPI1_RX_DMA_STREAM != SPI1_TX_DMA_STREAM,
              "SPI1 RX and TX require different DMA streams");
static_assert(SPI1_RX_DMA_STREAM != ADC1_DMA_STREAM &&
              SPI1_TX_DMA_STREAM != ADC1_DMA_STREAM,
              "SPI1 and ADC1 resource plans require different DMA streams");

inline u32 timer_clock_hz(bool apb2) {
  const u32 prescaler = RCC->CFGR &
    (apb2 ? RCC_CFGR_PPRE2 : RCC_CFGR_PPRE1);
  const u32 div1 = apb2 ? RCC_CFGR_PPRE2_DIV1 : RCC_CFGR_PPRE1_DIV1;
  const u32 div2 = apb2 ? RCC_CFGR_PPRE2_DIV2 : RCC_CFGR_PPRE1_DIV2;
  const u32 div4 = apb2 ? RCC_CFGR_PPRE2_DIV4 : RCC_CFGR_PPRE1_DIV4;
  const u32 pclk = apb2 ? HAL_RCC_GetPCLK2Freq() : HAL_RCC_GetPCLK1Freq();

#if defined(RCC_DCKCFGR_TIMPRE)
  if((RCC->DCKCFGR & RCC_DCKCFGR_TIMPRE) != 0) {
    if(prescaler == div1 || prescaler == div2 || prescaler == div4) {
      return HAL_RCC_GetHCLKFreq();
    }
    return pclk * 4UL;
  }
#endif

  return prescaler == div1 ? pclk : pclk * 2UL;
}

inline u32 apb1_timer_clock_hz(void) {
  return timer_clock_hz(false);
}

inline u32 apb2_timer_clock_hz(void) {
  return timer_clock_hz(true);
}

} // namespace stm32f4_platform_resources

#else
  #define MK61_STM32F4_RESOURCE_MAP_SUPPORTED 0
#endif

#endif
