#ifndef MK61_ZX0_HPP
#define MK61_ZX0_HPP

#include "rust_types.h"

namespace zx0 {

struct Input {
  void* context;
  bool (*next)(void* context, u8& value);
};

struct Output {
  void* context;
  bool (*next)(void* context, u8 value);
};

enum class EncodeMode : u8 {
  GREEDY = 0,
  BOUNDED_OPTIMAL = 1
};

struct EncodeResult {
  u32 output_size;
  EncodeMode mode;
};

// Ссылается на input и workspace, переданные prepare(). Оба буфера должны
// оставаться неизменными до последнего emit(). Поля являются внутренним
// описанием подготовленного потока; вызывающему нужны output_size и mode.
struct Prepared {
  const u8* input;
  const u8* workspace;
  u32 output_size;
  u16 input_size;
  u16 token_count;
  u16 control_offset;
  u16 control_count;
  EncodeMode mode;
};

// Ограниченный упаковщик использует обычный формат ZX0 v2 и окно 256 байт.
// При workspace_size >= 4 * (input_size + 1) он делает bounded-optimal поиск:
// новые offset оптимизируются точно в пределах окна, а дешёвый last-offset
// дополнительно выбирается при восстановлении пути. Если памяти меньше,
// применяется детерминированный greedy-разбор. Heap не используется.
//
// Пересечение workspace с input отвергается. Упаковщик может вернуть false,
// когда рабочего буфера недостаточно даже для greedy-плана.
bool prepare(const u8* input, u32 input_size,
             u8* workspace, usize workspace_size,
             Prepared& prepared);

// Повторно выдаёт уже подготовленный побитно идентичный поток, не перестраивая
// DP/greedy-план и не изменяя input или workspace.
bool emit(const Prepared& prepared, const Output& output);

// Удобная однопроходная обёртка prepare() + emit().
bool encode(const u8* input, u32 input_size,
            u8* workspace, usize workspace_size,
            const Output& output, EncodeResult& result);

// Распаковывает прямой поток ZX0 v2 непосредственно в output. Уже записанная
// часть output служит словарём, поэтому отдельное окно в SRAM не требуется.
bool decode(const Input& input, u32 source_size,
            u8* output, u32 capacity, u32& written);

// Проверяет и распаковывает весь логический поток, сохраняя только заданный
// диапазон. window служит кольцевым словарём; для потоков C5 достаточно
// 256 байт, так как встроенный упаковщик не создаёт больших offset.
bool decode_range(const Input& input, u32 source_size, u32 logical_size,
                  u32 range_offset, u8* output, u32 range_size,
                  u8* window, u32 window_size);

} // namespace zx0

#endif
