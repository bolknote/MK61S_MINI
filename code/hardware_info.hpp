#ifndef MK61_HARDWARE_INFO_HPP
#define MK61_HARDWARE_INFO_HPP

#include <stdio.h>

#include "rust_types.h"

namespace hardware_info {

static constexpr u8 LINE_COUNT = 5;
static constexpr u16 ADC_FULL_SCALE = 4095;
static constexpr u16 VREF_CALIBRATION_MV = 3300;
static constexpr u8 VBAT_DIVIDER = 4;

struct VbatReading {
  bool valid;
  u16 millivolts;
};

struct DeviceIdentity {
  u16 device_id;
  u16 revision_id;
  u16 flash_kb;
  u16 ram_kb;
  const char* family;
  char pin_count_code;
  char flash_size_code;
};

inline bool valid_flash_size(u16 flash_kb) {
  return flash_kb != 0 && flash_kb != 0xFFFFU;
}

inline DeviceIdentity decode_device_identity(
    u32 idcode, u16 flash_kb, char pin_count_code = 'x') {
  const u16 device_id = (u16) (idcode & 0x0FFFU);
  const u16 revision_id = (u16) (idcode >> 16);
  const u16 detected_flash_kb = valid_flash_size(flash_kb) ? flash_kb : 0;
  if(pin_count_code == 0) pin_count_code = 'x';

  // DEV_ID и Flash signature задают семейство и плотность памяти.
  // Код числа выводов приходит от compile-time target: его в MCU нет.
  switch(device_id) {
    // RM0368: STM32F401xB/C and STM32F401xD/E have different DEV_IDs.
    case 0x423:
      return {
        device_id,
        revision_id,
        detected_flash_kb,
        64,
        "STM32F401",
        pin_count_code,
        detected_flash_kb == 128 ? 'B' :
          (detected_flash_kb == 256 ? 'C' : '?')
      };
    case 0x433:
      return {
        device_id,
        revision_id,
        detected_flash_kb,
        96,
        "STM32F401",
        pin_count_code,
        detected_flash_kb == 384 ? 'D' :
          (detected_flash_kb == 512 ? 'E' : '?')
      };
    case 0x431: // RM0383: STM32F411xC/E.
      return {
        device_id,
        revision_id,
        detected_flash_kb,
        128,
        "STM32F411",
        pin_count_code,
        detected_flash_kb == 256 ? 'C' :
          (detected_flash_kb == 512 ? 'E' : '?')
      };
    default:
      return {
        device_id,
        revision_id,
        detected_flash_kb,
        0,
        NULL,
        pin_count_code,
        '?'
      };
  }
}

inline bool format_device_line(
    char* out, usize size, bool russian, const DeviceIdentity& identity) {
  if(out == NULL || size == 0) return false;
  const int written = identity.family != NULL
    ? snprintf(out, size, russian ? "ЧИП:%s%c%c" : "Chip:%s%c%c",
        identity.family, identity.pin_count_code, identity.flash_size_code)
    : snprintf(out, size, russian ? "ЧИП:ID 0x%03X" : "Chip:ID 0x%03X",
        (unsigned) identity.device_id);
  return written >= 0 && (usize) written < size;
}

inline bool format_memory_line(
    char* out, usize size, bool russian, const DeviceIdentity& identity) {
  if(out == NULL || size == 0) return false;

  int written;
  if(identity.ram_kb != 0 && identity.flash_kb != 0) {
    written = snprintf(
      out, size, russian ? "ОЗУ:%u ПЗУ:%u" : "RAM:%u ROM:%u",
      (unsigned) identity.ram_kb, (unsigned) identity.flash_kb);
  } else if(identity.ram_kb != 0) {
    written = snprintf(
      out, size, russian ? "ОЗУ:%u ПЗУ:?" : "RAM:%u ROM:?",
      (unsigned) identity.ram_kb);
  } else if(identity.flash_kb != 0) {
    written = snprintf(
      out, size, russian ? "ОЗУ:? ПЗУ:%u" : "RAM:? ROM:%u",
      (unsigned) identity.flash_kb);
  } else {
    written = snprintf(
      out, size, russian ? "ОЗУ:? ПЗУ:?" : "RAM:? ROM:?");
  }
  return written >= 0 && (usize) written < size;
}

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

  // Это напряжение на входе VBAT МК, а не детектор установленной батареи.
  // На плате без элемента VBAT может быть штатно соединён с VDD, поэтому
  // подпись намеренно говорит "pin/вход" и не создаёт ложного статуса батареи.
  int written;
  if(!reading.valid) {
    written = snprintf(
      out, size, russian ? "VBAT вход:--,-- В" : "VBAT pin:--.-- V");
  } else {
    const u16 centivolts = (u16) ((reading.millivolts + 5U) / 10U);
    written = snprintf(
      out, size, russian ? "VBAT вход:%u,%02u В" : "VBAT pin:%u.%02u V",
      (unsigned) (centivolts / 100U),
      (unsigned) (centivolts % 100U));
  }
  return written >= 0 && (usize) written < size;
}

inline bool format_display_line(
    char* out, usize size, bool russian, const char* display_type) {
  if(out == NULL || size == 0 || display_type == NULL) return false;
  const int written = snprintf(
    out, size, russian ? "Экран:%s" : "Disp:%s", display_type);
  return written >= 0 && (usize) written < size;
}

inline bool format_generator_line(
    char* out, usize size, bool russian, const char* generator_type) {
  if(out == NULL || size == 0 || generator_type == NULL) return false;
  const int written = snprintf(
    out, size, russian ? "Генератор:%s" : "Generator:%s",
    generator_type);
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
DeviceIdentity read_device_identity(void);
const char* display_type(void);

} // пространство имён hardware_info

#endif
