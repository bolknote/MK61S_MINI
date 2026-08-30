#include "hardware_info.hpp"

#include <Arduino.h>

#include "config.h"
#include "stm32f4xx_ll_adc.h"

namespace hardware_info {
namespace {

static constexpr char configured_pin_count_code(void) {
#if defined(ARDUINO_BLACKPILL_F411CE) || \
    defined(ARDUINO_BLACKPILL_F401CE) || \
    defined(ARDUINO_BLACKPILL_F401CC) || \
    defined(ARDUINO_GENERIC_F401CDUX) || \
    defined(ARDUINO_GENERIC_F411CCUX) || \
    defined(ARDUINO_GENERIC_F401CBYX)
  // Все эти target-ы выбирают 48/49-pin вариант STM32, код "C".
  return 'C';
#else
  return 'x';
#endif
}

static u16 filtered_adc(u32 pin) {
  u16 samples[ADC_FILTER_SAMPLES];
  for(u8 sample = 0; sample < ADC_FILTER_SAMPLES; sample++) {
    const u16 value = (u16) analogRead(pin);
    u8 position = sample;
    while(position > 0 && samples[position - 1] > value) {
      samples[position] = samples[position - 1];
      position--;
    }
    samples[position] = value;
  }
  return samples[ADC_FILTER_SAMPLES / 2U];
}

static u16 elapsed_u16(u32 started_at) {
  const u32 elapsed = micros() - started_at;
  return (u16) (elapsed > 0xFFFFU ? 0xFFFFU : elapsed);
}

} // анонимное пространство имён

DeviceIdentity read_device_identity(void) {
  u32 idcode = 0;
  u16 flash_kb = 0;

#if defined(DBGMCU)
  // DEV_ID занимает только младшие 12 бит; в старшей половине
  // DBGMCU_IDCODE находится REV_ID.
  idcode = DBGMCU->IDCODE;
#endif
#if defined(FLASHSIZE_BASE)
  // Заводская electronic signature хранит размер Flash в КиБ.
  flash_kb = *((const volatile u16*) FLASHSIZE_BASE);
#endif

  return decode_device_identity(
    idcode, flash_kb, configured_pin_count_code());
}

AnalogSnapshot read_analog_snapshot(void) {
  AnalogSnapshot result = {};
  result.vdda = {false, 0};
  result.mcu_temperature = {false, 0};
  result.battery = unqualified_battery_status({false, 0});

#if defined(AVREF) && defined(ATEMP) && defined(AVBAT) && \
    defined(VREFINT_CAL_ADDR) && defined(TEMPSENSOR_CAL1_ADDR) && \
    defined(TEMPSENSOR_CAL2_ADDR)
  const u32 started_at = micros();
  analogReadResolution(12);

  // STM32duino selects the maximum (480-cycle on F4) internal-channel sample
  // time and HAL waits the specified 10 us temperature-sensor startup time.
  // Discard one conversion after every mux change and use a median-of-five:
  // 18 conversions total, the same count as the previous VBAT-only average.
  (void) analogRead(AVREF);
  result.raw_vref = filtered_adc(AVREF);
  (void) analogRead(ATEMP);
  result.raw_temperature = filtered_adc(ATEMP);
  (void) analogRead(AVBAT);
  result.raw_vbat = filtered_adc(AVBAT);

  const u16 calibrated_vref = *VREFINT_CAL_ADDR;
  const u16 calibrated_temperature_30 = *TEMPSENSOR_CAL1_ADDR;
  const u16 calibrated_temperature_110 = *TEMPSENSOR_CAL2_ADDR;
  result.conversion_count = 3U * (ADC_FILTER_SAMPLES + 1U);

  analogReadResolution(ADC_RESOLUTION);

  result.vdda = calculate_vdda_millivolts(
    result.raw_vref, calibrated_vref);
  if(result.vdda.valid) {
    result.mcu_temperature = calculate_temperature_decicelsius(
      result.raw_temperature,
      result.vdda.millivolts,
      calibrated_temperature_30,
      calibrated_temperature_110);
  }
  result.battery = unqualified_battery_status(
    calculate_vbat_millivolts(
      result.raw_vbat, result.raw_vref, calibrated_vref));
  result.elapsed_us = elapsed_u16(started_at);
#endif

  return result;
}

const char* display_type(void) {
#if defined(MK61_DISPLAY_UC1609)
  return "UC1609";
#elif defined(MK61_OLED1602_WS0010)
  return "WS0010";
#elif defined(MK61_LCD1602_A02)
  return "LCD1602A02";
#else
  return "LCD1602A00";
#endif
}

} // пространство имён hardware_info
