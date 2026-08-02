#include <Arduino.h>
#include "classic_timer.hpp"
#include "sound_driver.hpp"
#include "stm32f4_platform_resources.hpp"

#if defined(ARDUINO_ARCH_STM32) && MK61_STM32F4_RESOURCE_MAP_SUPPORTED

// STM32duino вызывает слабый osSystickHandler() после обновления HAL tick.
// Один сильный диспетчер позволяет нескольким подсистемам использовать уже
// существующий 1-kHz такт без отдельных объектов HardwareTimer и IRQ-векторов.
extern "C" void osSystickHandler(void) {
  classic_timer::on_systick_isr();
  sound_driver_on_systick_isr();
}

#endif
