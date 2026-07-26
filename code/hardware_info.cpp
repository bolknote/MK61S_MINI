#include "hardware_info.hpp"

#include "config.h"
#include "stm32f4xx_ll_adc.h"

namespace hardware_info {
namespace {

static constexpr u8 ADC_SAMPLE_COUNT = 8;

static u16 average_adc(u32 pin) {
  u32 sum = 0;
  for(u8 sample = 0; sample < ADC_SAMPLE_COUNT; sample++) {
    sum += analogRead(pin);
  }
  return (u16) ((sum + ADC_SAMPLE_COUNT / 2U) / ADC_SAMPLE_COUNT);
}

} // анонимное пространство имён

VbatReading read_vbat(void) {
#if defined(AVREF) && defined(AVBAT) && defined(VREFINT_CAL_ADDR)
  analogReadResolution(12);

  // Первые отсчёты оставляем вне среднего после переключения внутреннего канала.
  (void) analogRead(AVREF);
  const u16 raw_vref = average_adc(AVREF);
  (void) analogRead(AVBAT);
  const u16 raw_vbat = average_adc(AVBAT);
  const u16 calibrated_vref = *VREFINT_CAL_ADDR;

  analogReadResolution(ADC_RESOLUTION);
  return calculate_vbat_millivolts(
    raw_vbat, raw_vref, calibrated_vref);
#else
  return {false, 0};
#endif
}

const char* display_type(void) {
#if defined(MK61_DISPLAY_UC1609)
  return "UC1609";
#elif defined(MK61_LCD1602_A02)
  return "LCD1602A02";
#else
  return "LCD1602A00";
#endif
}

} // пространство имён hardware_info
