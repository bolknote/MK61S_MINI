#ifndef MK61_EARLY_DFU_HPP
#define MK61_EARLY_DFU_HPP

#include "early_dfu_protocol.hpp"

#if defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_EARLY_DFU_SUPPORTED 1
#else
  #define MK61_EARLY_DFU_SUPPORTED 0
#endif

namespace early_dfu {

using Diagnostic = early_dfu_protocol::Diagnostic;

// Штатный вход из меню сохраняет заставку на уже инициализированном дисплее,
// публикует одноразовый запрос и делает reset. Ранний preinit-пролог принимает
// запрос до STM32duino, HAL и всех C++-конструкторов, затем передаёт
// управление ROM DFU.
[[noreturn]] void request(void);

// Runtime USB must be visibly detached before reset when changing from the
// application descriptor to ROM DFU.  Splitting publication from reset lets
// the caller hold that disconnect interval without weakening the early boot
// protocol.  reset_prepared() is valid only after prepare_request().
void prepare_request(void);
[[noreturn]] void reset_prepared(void);

// Резерв для платформ, где ранний STM32F401/F411-пролог недоступен: setup()
// принимает тот же одноразовый запрос и использует прежний путь.
bool consume_request(void);

// Last retained transition stage.  It is diagnostic only: the DFU decision
// continues to require a valid torn-safe request or a physical ESC press.
Diagnostic diagnostic(void);
const char* diagnostic_stage_name(early_dfu_protocol::Stage stage);

} // namespace early_dfu

#endif
