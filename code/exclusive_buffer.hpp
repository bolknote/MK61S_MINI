#ifndef EXCLUSIVE_BUFFER_HPP
#define EXCLUSIVE_BUFFER_HPP

#include "rust_types.h"

namespace exclusive_buffer {

enum class Owner : u8 {
  NONE,
  DISPLAY_FONT,
  USB_CACHE
};

// Постоянное хранилище внешнего шрифта во время работы интерфейса; когда
// интерфейсом владеет USB-накопитель, весь буфер превращается в 16
// дополнительных 512-байтовых позиций отложенной записи.
static constexpr usize SIZE = 8192;

bool acquire(Owner owner, usize required);
void release(Owner owner);
u8* data(Owner owner);
Owner current_owner(void);

} // пространство имён exclusive_buffer

#endif
