#ifndef MK61_ENTROPY_POOL_HPP
#define MK61_ENTROPY_POOL_HPP

#include "rust_types.h"

namespace entropy_pool {

enum class Domain : u8 {
  CALCULATOR = 0,
  FOCAL = 1,
  TINYBASIC = 2,
  CHIP8 = 3,
  M61_INIT = 4,
  COUNT
};

// Начинает сбор внутреннего шума АЦП AVBAT. poll_startup() достаточно дёшев,
// чтобы вызывать его один раз за цикл ожидания заставки; finish_startup()
// добирает недостающие биты фон Неймана, если заставка пропущена, и восстанавливает
// обычную разрядность АЦП.
void begin(void);
void poll_startup(void);
void finish_startup(void);

// Подмешивает согласованный отсчёт календаря и фазы RTC в начальное состояние.
// RTC добавляет различия между запусками, но намеренно не учитывается в
// startup_entropy_bits(): эта функция по-прежнему возвращает число выходных
// битов фон Неймана от AVBAT.
void note_rtc_snapshot(u8 snapshot_index, u64 calendar_material, u64 phase_material);

// Подмешивает в пул время каждого физического перехода клавиши и при активном
// расширенном режиме меняет ключ потока калькулятора.
void note_key(u8 keycode, u32 timestamp_us);

// Независимые, разделённые по доменам потоки для калькулятора, M61, FOCAL,
// TinyBASIC и CHIP-8. Настройка совместимости управляет только тем, использует
// ли ROM-команда К СЧ поток CALCULATOR.
u32 next_u32(Domain domain);
// Равномерное ненулевое семизначное слово 1..9 999 999. Отдельный домен
// M61_INIT позволяет R<r>= random не расходовать поток команды К СЧ.
u32 next_decimal7(Domain domain);
void configure_calculator(bool enhanced);

u16 startup_raw_samples(void);
u8 startup_entropy_bits(void);

} // пространство имён entropy_pool

#endif
