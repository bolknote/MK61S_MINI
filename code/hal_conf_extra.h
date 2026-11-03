#ifndef MK61_HAL_CONF_EXTRA_H
#define MK61_HAL_CONF_EXTRA_H

// F401/F411 sound PWM and the classic TIM9 clock are owned by the project's
// direct LL drivers. Retain the HAL TIM module, but omit Arduino's unrelated
// HardwareTimer callbacks and IRQ wrappers. Other STM32 targets keep their
// existing Arduino timer backend.
#if defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
  // Project handlers own keyboard EXTI4/EXTI9_5; omit the 16-line Arduino callback table.
  #define HAL_EXTI_MODULE_DISABLED
  // crc32.hpp owns the F4 CRC registers and clock. Core's eager HAL CRC
  // initialization adds a redundant handle and must not reset that engine.
  #define HAL_CRC_MODULE_DISABLED
  #ifndef HAL_TIM_MODULE_ONLY
    #define HAL_TIM_MODULE_ONLY
  #endif
  // The terminal uses the owned USB CDC transport. STM32duino's UART IRQ
  // wrappers otherwise stay live through the vector table even with no UART
  // instance in the firmware. Keep HAL declarations, omit that unused adapter.
  #ifndef HAL_UART_MODULE_ONLY
    #define HAL_UART_MODULE_ONLY
  #endif
#endif

#endif
