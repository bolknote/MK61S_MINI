#ifndef MK61_ZX0_HPP
#define MK61_ZX0_HPP

#include "rust_types.h"

namespace zx0 {

struct Input {
  void* context;
  bool (*next)(void* context, u8& value);
};

// Распаковывает прямой поток ZX0 v2 непосредственно в output. Уже записанная
// часть output служит словарём, поэтому отдельное окно в SRAM не требуется.
bool decode(const Input& input, u32 source_size,
            u8* output, u32 capacity, u32& written);

} // namespace zx0

#endif
