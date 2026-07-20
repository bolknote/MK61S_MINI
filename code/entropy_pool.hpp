#ifndef MK61_ENTROPY_POOL_HPP
#define MK61_ENTROPY_POOL_HPP

#include "rust_types.h"

namespace entropy_pool {

enum class Domain : u8 {
  CALCULATOR = 0,
  FOCAL = 1,
  TINYBASIC = 2
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

// Независимые, разделённые по доменам случайные потоки для калькулятора, FOCAL
// и TinyBASIC. Потоки языков никогда не зависят от настройки совместимости
// калькулятора.
u32 next_u32(Domain domain);
void configure_calculator(bool enhanced);

u16 startup_raw_samples(void);
u8 startup_entropy_bits(void);

} // пространство имён entropy_pool

#endif
