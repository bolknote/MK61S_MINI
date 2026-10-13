#include "stm32f4_adc.hpp"
#if MK61_STM32F4_ADC_SUPPORTED
#include <Arduino.h>
#include "stm32f4_platform_resources.hpp"
namespace stm32f4_adc {
namespace {
static bool conversion(u16 &out) {
  ADC1->SR = 0;
  ADC1->CR2 |= ADC_CR2_SWSTART;
  const u32 started = micros();
  while ((ADC1->SR & ADC_SR_EOC) == 0) {
    if ((u32)(micros() - started) >= 1000U)
      return false;
  }
  out = (u16)ADC1->DR;
  return true;
}
static bool channel(u8 number, u16 &out) {
  // Temperature/VREF and VBAT share the internal input mux. Keep the battery
  // divider off while reading temperature, and turn it off after sampling.
  ADC->CCR = (ADC->CCR & ~(ADC_CCR_TSVREFE | ADC_CCR_VBATE)) |
             (number == 18 ? ADC_CCR_VBATE : ADC_CCR_TSVREFE);
  ADC1->SQR3 = number;
  delayMicroseconds(10); // F4 internal temperature sensor startup minimum.
  u16 discarded;
  if (!conversion(discarded))
    return false;
  u16 samples[5];
  for (u8 i = 0; i < 5; i++) {
    u16 value;
    if (!conversion(value))
      return false;
    u8 j = i;
    while (j && samples[j - 1] > value) {
      samples[j] = samples[j - 1];
      --j;
    }
    samples[j] = value;
  }
  out = samples[2];
  return true;
}
} // namespace
namespace {
class Session {
  u32 common_;
  bool clock_enabled_;

public:
  Session() : common_(0), clock_enabled_((RCC->APB2ENR & RCC_APB2ENR_ADC1EN) != 0) {
    RCC->APB2ENR |= RCC_APB2ENR_ADC1EN;
    (void)RCC->APB2ENR;
    common_ = ADC->CCR;
    ADC->CCR = (common_ &
                ~(ADC_CCR_ADCPRE | ADC_CCR_MULTI | ADC_CCR_TSVREFE | ADC_CCR_VBATE)) |
               ADC_CCR_ADCPRE_0;
    ADC1->CR1 = 0;
    ADC1->CR2 = 0;
    ADC1->SQR1 = 0;
    ADC1->SQR2 = 0;
    ADC1->SMPR1 = (7UL << 18) | (7UL << 21) | (7UL << 24);
    ADC1->CR2 = ADC_CR2_ADON;
    delayMicroseconds(3);
  }
  ~Session() {
    ADC1->CR2 = 0;
    ADC->CCR = common_;
    if (!clock_enabled_)
      RCC->APB2ENR &= ~RCC_APB2ENR_ADC1EN;
  }
};
} // namespace
bool read_vbat(u16 &value) {
  Session session;
  ADC->CCR = (ADC->CCR & ~ADC_CCR_TSVREFE) | ADC_CCR_VBATE;
  ADC1->SQR3 = 18;
  delayMicroseconds(10);
  return conversion(value); // Raw noise: never use the diagnostic median here.
}
bool read_internal(u16 &vref, u16 &temperature, u16 &vbat) {
  Session session;
  u16 raw_vref = 0, raw_temperature = 0, raw_vbat = 0;
  const bool ok =
      channel(17, raw_vref) && channel(16, raw_temperature) && channel(18, raw_vbat);
  if (ok) {
    vref = raw_vref;
    temperature = raw_temperature;
    vbat = raw_vbat;
  }
  return ok;
}
} // namespace stm32f4_adc
#endif
