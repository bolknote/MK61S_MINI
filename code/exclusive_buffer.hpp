#ifndef EXCLUSIVE_BUFFER_HPP
#define EXCLUSIVE_BUFFER_HPP

#include "rust_types.h"

#if defined(MK61_DISPLAY_UC1609) || defined(DISPLAY_UC1609) || \
    defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_CLASSIC_V3) || \
    defined(MK61_BOARD_40TH) || \
    (defined(MK61_ENABLE_USB_SCREEN) && MK61_ENABLE_USB_SCREEN)
  #define MK61_EXCLUSIVE_BUFFER_ENABLED 1
#else
  #define MK61_EXCLUSIVE_BUFFER_ENABLED 0
#endif

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
#if defined(STM32F401xC) || defined(STM32F401xE)
static constexpr usize SIZE = 1536;
#else
static constexpr usize SIZE = 8192;
#endif

bool acquire(Owner owner, usize required);
void release(Owner owner);
u8* data(Owner owner);
Owner current_owner(void);

} // пространство имён exclusive_buffer

#endif
