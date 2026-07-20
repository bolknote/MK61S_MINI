#ifndef FLASH_CAPACITY_PROBE_HPP
#define FLASH_CAPACITY_PROBE_HPP

#include "rust_types.h"

namespace flash_capacity_probe {

static constexpr u32 SECTOR_SIZE = 4096;
static constexpr u32 MIN_CAPACITY = 128U * 1024U;
static constexpr u32 MAX_CAPACITY = 128U * 1024U * 1024U;
static constexpr u32 THREE_BYTE_LIMIT = 16U * 1024U * 1024U;

// complete=false сообщает кандидата до любого разрушающего доступа;
// complete=true сообщает, оказалась ли эта граница физически отдельной.
using ProbeProgress = void (*)(u32 candidate, bool complete, bool distinct);

static bool power_of_two(u32 value) {
  return value != 0 && (value & (value - 1)) == 0;
}

// Большинство последовательных NOR кодируют байтовую ёмкость как 2^N. Семейство
// Winbond W25Q512/W25Q01 использует продолжающие значения 0x20/0x21 вместо
// 0x1A/0x1B; принимать обе формы безопасно, поскольку detect() всё равно
// проверяет физическую границу, прежде чем C5 доверится результату.
inline u32 jedec_capacity_bytes(u8 capacity_code) {
  if(capacity_code >= 0x10 && capacity_code <= 0x1B) {
    return (u32) 1UL << capacity_code;
  }
  if(capacity_code == 0x20) return 64U * 1024U * 1024U;
  if(capacity_code == 0x21) return 128U * 1024U * 1024U;
  return 0;
}

static void make_marker(u8* out, u32 candidate, u8 role) {
  // Взаимодополняющие данные заставляют вторую запись при наложении адресов
  // потребовать запрещённых переходов 0->1. Даже драйвер без проверки чтением
  // обнаруживается итоговым сравнением обеих областей.
  const u8 salt = role == 0 ? 0xA5 : 0x5A;
  for(u8 i = 0; i < 32; i++) {
    const u8 size_byte = (u8) (candidate >> ((i & 3) * 8));
    out[i] = (u8) (salt ^ size_byte ^ (u8) (i * 29));
  }
  out[0] = 'C';
  out[1] = '5';
  out[2] = role;
  out[3] = (u8) ~role;
}

template<typename RawFlash>
static bool marker_matches(RawFlash& flash, u32 address,
                           const u8* expected) {
  u8 recovered[32];
  if(!flash.rawRead(address, recovered, sizeof(recovered))) return false;
  for(u8 i = 0; i < sizeof(recovered); i++) {
    if(recovered[i] != expected[i]) return false;
  }
  return true;
}

template<typename RawFlash>
static bool prepare_address_width_guards(RawFlash& flash, u32 candidate,
                                         u32 lower_address,
                                         u32 upper_address,
                                         u32& lower_guard_address,
                                         u32& upper_guard_address,
                                         u8* lower_guard,
                                         u8* upper_guard) {
  if(candidate <= THREE_BYTE_LIMIT) return flash.rawPrepare(candidate);

  // Подделка только с 3-байтовой адресацией может игнорировать EN4B. Тогда она
  // принимает A31..A8 за адрес, а A7..A0 — за первый байт данных. Перед любой
  // 4-байтовой командой защищаем эти два нижних «теневых» сектора. Настоящий
  // 4-байтовый доступ не меняет защитные данные, а игнорирование EN4B стирает их.
  if(!flash.rawPrepare(MIN_CAPACITY)) return false;
  const u32 lower_shadow = (lower_address >> 8) & ~(SECTOR_SIZE - 1U);
  const u32 upper_shadow = (upper_address >> 8) & ~(SECTOR_SIZE - 1U);
  lower_guard_address = lower_shadow + 64;
  upper_guard_address = upper_shadow + 64;
  make_marker(lower_guard, candidate, 2);
  make_marker(upper_guard, candidate, 3);
  if(!flash.rawEraseSector(upper_shadow) ||
     (lower_shadow != upper_shadow && !flash.rawEraseSector(lower_shadow)) ||
     !flash.rawWrite(lower_guard_address, lower_guard, 32) ||
     !flash.rawWrite(upper_guard_address, upper_guard, 32) ||
     !marker_matches(flash, lower_guard_address, lower_guard) ||
     !marker_matches(flash, upper_guard_address, upper_guard)) return false;
  return flash.rawPrepare(candidate);
}

template<typename RawFlash>
static bool boundary_is_distinct(RawFlash& flash, u32 candidate) {
  if(candidate < MIN_CAPACITY || !power_of_two(candidate)) return false;
  const u32 lower_address = candidate / 2 - SECTOR_SIZE;
  const u32 upper_address = candidate - SECTOR_SIZE;
  u32 lower_guard_address = 0;
  u32 upper_guard_address = 0;
  u8 lower_marker[32];
  u8 upper_marker[32];
  u8 lower_guard[32];
  u8 upper_guard[32];
  u8 recovered_lower[32];
  u8 recovered_upper[32];
  make_marker(lower_marker, candidate, 0);
  make_marker(upper_marker, candidate, 1);
  if(!prepare_address_width_guards(flash, candidate, lower_address,
                                   upper_address, lower_guard_address,
                                   upper_guard_address, lower_guard,
                                   upper_guard)) return false;

  // Сначала стираем возможный псевдоним, затем заведомо нижнюю область. Если
  // адреса накладываются, две последующие разные записи это обнаружат.
  if(!flash.rawEraseSector(upper_address) ||
     !flash.rawEraseSector(lower_address) ||
     !flash.rawWrite(lower_address, lower_marker, sizeof(lower_marker)) ||
     !flash.rawWrite(upper_address, upper_marker, sizeof(upper_marker)) ||
     !flash.rawRead(lower_address, recovered_lower, sizeof(recovered_lower)) ||
     !flash.rawRead(upper_address, recovered_upper, sizeof(recovered_upper))) return false;
  for(u8 i = 0; i < sizeof(lower_marker); i++) {
    if(recovered_lower[i] != lower_marker[i] ||
       recovered_upper[i] != upper_marker[i]) return false;
  }
  if(candidate > THREE_BYTE_LIMIT) {
    if(!flash.rawPrepare(MIN_CAPACITY) ||
       !marker_matches(flash, lower_guard_address, lower_guard) ||
       !marker_matches(flash, upper_guard_address, upper_guard)) return false;
  }
  return true;
}

// Разрушает данные только в двух проверочных секторах каждого кандидата.
// Вызывать лишь при отсутствии обеих действительных копий локатора C5.
// Стандартные ёмкости SPI NOR — степени двойки, поэтому двоичный поиск по
// показателям минимизирует число стираний и находит наибольший физически
// отдельный диапазон адресов.
template<typename RawFlash>
bool detect(RawFlash& flash, u32 reported_capacity, u32& capacity,
            ProbeProgress progress = nullptr) {
  // Заявленное значение намеренно не ограничивает поиск. Поддельные или
  // повреждённые идентификационные данные могут ошибаться в любую сторону, а
  // C5 должна использовать всё физически адресуемое устройство. Поддерживается
  // лишь одиннадцать размеров-степеней двойки, поэтому полный двоичный поиск
  // требует не более четырёх проверок границы.
  (void) reported_capacity;
  u8 low_exponent = 17; // 128 КиБ
  u8 high_exponent = 27; // 128 МиБ
  u32 best = 0;
  while(low_exponent <= high_exponent) {
    const u8 exponent = (u8) (low_exponent +
        (high_exponent - low_exponent) / 2);
    const u32 candidate = (u32) 1UL << exponent;
    if(progress != nullptr) progress(candidate, false, false);
    const bool distinct = boundary_is_distinct(flash, candidate);
    if(progress != nullptr) progress(candidate, true, distinct);
    if(distinct) {
      best = candidate;
      low_exponent = (u8) (exponent + 1);
    } else {
      high_exponent = (u8) (exponent - 1);
    }
  }
  capacity = best;
  return best != 0;
}

} // пространство имён flash_capacity_probe

#endif
