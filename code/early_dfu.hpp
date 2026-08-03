#ifndef MK61_EARLY_DFU_HPP
#define MK61_EARLY_DFU_HPP

#if defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_EARLY_DFU_SUPPORTED 1
#else
  #define MK61_EARLY_DFU_SUPPORTED 0
#endif

namespace early_dfu {

// Штатный вход из меню сохраняет заставку на уже инициализированном дисплее,
// публикует одноразовый запрос и делает reset. Ранний preinit-пролог принимает
// запрос до STM32duino, HAL и всех C++-конструкторов, затем передаёт
// управление ROM DFU.
[[noreturn]] void request(void);

// Резерв для платформ, где ранний STM32F401/F411-пролог недоступен: setup()
// принимает тот же одноразовый запрос и использует прежний путь.
bool consume_request(void);

} // namespace early_dfu

#endif
