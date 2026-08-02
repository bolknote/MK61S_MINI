#ifndef EXCLUSIVE_BUFFER_HPP
#define EXCLUSIVE_BUFFER_HPP

#include "shared_memory.hpp"

#define MK61_EXCLUSIVE_BUFFER_ENABLED MK61_SHARED_MEMORY_BULK_ENABLED

namespace exclusive_buffer {

enum class Owner : u8 {
  NONE,
  DISPLAY_FONT,
  USB_CACHE,
  PROGRAM_STORE_COMPRESSION
};

// Постоянное хранилище внешнего шрифта во время работы интерфейса; когда
// интерфейсом владеет USB-накопитель, буфер становится кэшем секторов. F401
// оставляет три сектора (и место для максимального .fmk), F411 — шестнадцать.
static constexpr usize SIZE = shared_memory::BULK_SIZE;

bool acquire(Owner owner, usize required);
void release(Owner owner);
u8* data(Owner owner);
Owner current_owner(void);

} // пространство имён exclusive_buffer

#endif
