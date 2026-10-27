#ifndef MK61_STM32F4_USB_DEVICE_HPP
#define MK61_STM32F4_USB_DEVICE_HPP
#include <Arduino.h>
#if defined(ARDUINO_ARCH_STM32) && defined(USBCON) && defined(USBD_USE_CDC) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
#define MK61_USB_DIRECT_SUPPORTED 1
namespace stm32f4_usb_device {
void set_low_power(bool enabled);
void gate_phy();
void ungate_phy();
}
#else
#define MK61_USB_DIRECT_SUPPORTED 0
#endif
#endif
