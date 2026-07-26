#ifndef MK61_HARDWARE_INFO_HPP
#define MK61_HARDWARE_INFO_HPP

#include <stdio.h>

#include "rust_types.h"

namespace hardware_info {

static constexpr u8 LINE_COUNT = 4;
static constexpr u16 ADC_FULL_SCALE = 4095;
static constexpr u16 VREF_CALIBRATION_MV = 3300;
static constexpr u8 VBAT_DIVIDER = 4;

struct VbatReading {
  bool valid;
  u16 millivolts;
};

inline VbatReading calculate_vbat_millivolts(
    u16 raw_vbat, u16 raw_vref, u16 calibrated_vref) {
  if(raw_vbat > ADC_FULL_SCALE || raw_vref == 0 ||
     raw_vref > ADC_FULL_SCALE || calibrated_vref == 0 ||
     calibrated_vref > ADC_FULL_SCALE) {
    return {false, 0};
  }

  const u32 vdda_numerator =
    (u32) calibrated_vref * VREF_CALIBRATION_MV;
  const u32 vdda_mv =
    (vdda_numerator + raw_vref / 2U) / raw_vref;
  if(vdda_mv < 1700U || vdda_mv > 3700U) return {false, 0};

  // STM32F401/F411 подают на ADC1_IN18 напряжение VBAT / 4.
  const u32 vbat_numerator =
    (u32) raw_vbat * vdda_mv * VBAT_DIVIDER;
  const u32 millivolts =
    (vbat_numerator + ADC_FULL_SCALE / 2U) / ADC_FULL_SCALE;
  if(millivolts > 0xFFFFU) return {false, 0};
  return {true, (u16) millivolts};
}

inline bool format_vbat_line(
    char* out, usize size, bool russian, VbatReading reading) {
  if(out == NULL || size == 0) return false;

  int written;
  if(!reading.valid) {
    written = snprintf(
      out, size, russian ? "VBAT:--,-- В" : "VBAT:--.-- V");
  } else {
    const u16 centivolts = (u16) ((reading.millivolts + 5U) / 10U);
    written = snprintf(
      out, size, russian ? "VBAT:%u,%02u В" : "VBAT:%u.%02u V",
      (unsigned) (centivolts / 100U),
      (unsigned) (centivolts % 100U));
  }
  return written >= 0 && (usize) written < size;
}

inline bool format_display_line(
    char* out, usize size, bool russian, const char* display_type) {
  if(out == NULL || size == 0 || display_type == NULL) return false;
  const int written = snprintf(
    out, size, russian ? "ЭКРАН:%s" : "Disp:%s", display_type);
  return written >= 0 && (usize) written < size;
}

inline u8 max_scroll_offset(u8 rows) {
  if(rows >= LINE_COUNT) return 0;
  if(rows == 0) return LINE_COUNT - 1;
  return LINE_COUNT - rows;
}

inline u8 clamp_scroll_offset(u8 offset, u8 rows) {
  const u8 maximum = max_scroll_offset(rows);
  return offset > maximum ? maximum : offset;
}

inline u8 step_scroll_offset(u8 offset, u8 rows, i8 delta) {
  offset = clamp_scroll_offset(offset, rows);
  const u8 maximum = max_scroll_offset(rows);
  if(delta < 0 && offset > 0) return offset - 1;
  if(delta > 0 && offset < maximum) return offset + 1;
  return offset;
}

VbatReading read_vbat(void);
const char* display_type(void);

} // пространство имён hardware_info

#endif
