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
  #ifndef HAL_TIM_MODULE_ONLY
    #define HAL_TIM_MODULE_ONLY
  #endif
#endif

#endif
