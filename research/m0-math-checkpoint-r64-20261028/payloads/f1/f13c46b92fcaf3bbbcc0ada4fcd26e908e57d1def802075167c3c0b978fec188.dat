#ifndef MK61_USB_CDC_RX_GUARD_HPP
#define MK61_USB_CDC_RX_GUARD_HPP

#include "rust_types.h"

#if defined(MK61_BUILD_FOCAL_MODULE) || \
    defined(MK61_BUILD_TINYBASIC_MODULE) || \
    defined(MK61_BUILD_WBMP_MODULE) || \
    defined(MK61_BUILD_MARKDOWN_MODULE) || \
    defined(MK61_BUILD_CHIP8_MODULE)
  #define MK61_USB_CDC_RX_GUARD_MODULE_BUILD 1
#else
  #define MK61_USB_CDC_RX_GUARD_MODULE_BUILD 0
#endif

#if defined(ARDUINO_ARCH_STM32) && defined(USBCON) && \
    !MK61_USB_CDC_RX_GUARD_MODULE_BUILD && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_USB_CDC_RX_GUARD_SUPPORTED 1
#else
  #define MK61_USB_CDC_RX_GUARD_SUPPORTED 0
#endif

namespace usb_cdc_rx_guard {

struct Snapshot {
  bool supported;
  bool linked;
  u32 throttles;
};

Snapshot statistics(void);
void reset_statistics(void);
const char* backend_name(void);

} // namespace usb_cdc_rx_guard

#endif
