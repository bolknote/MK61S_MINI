#include "usb_cdc_rx_guard.hpp"

#if MK61_USB_CDC_RX_GUARD_SUPPORTED
  #include <usbd_def.h>
#endif

namespace usb_cdc_rx_guard {

#if MK61_USB_CDC_RX_GUARD_SUPPORTED
namespace {

static volatile u32 throttle_count;

} // namespace

// STM32 Arduino Core 2.12.0 and 3.0.0 try to suspend a full CDC OUT queue by
// preparing a zero-length transfer with a null destination.  OTG FS interprets
// that as one enabled max-packet transfer and USB_ReadPacket then stores through
// address zero.  The build links this wrapper with
// --wrap=USBD_CDC_ClearBuffer.  Leaving the completed OUT endpoint unarmed makes
// the peripheral NAK correctly; USBSerial::read() rearms it through
// CDC_resume_receive() as soon as a queue block becomes free.
extern "C" u8 __wrap_USBD_CDC_ClearBuffer(USBD_HandleTypeDef* device) {
  if(device == nullptr ||
     device->pClassDataCmsit[device->classId] == nullptr) {
    return (u8) USBD_FAIL;
  }
  if(throttle_count != 0xFFFFFFFFUL) throttle_count++;
  return (u8) USBD_OK;
}

// GNU ld defines __real_* only when --wrap is active.  A weak reference lets
// diagnostics distinguish an official protected build from a direct Arduino
// build that omitted the required linker property.
extern "C" u8 __real_USBD_CDC_ClearBuffer(USBD_HandleTypeDef*)
    __attribute__((weak));

static bool wrapper_linked(void) {
  return __real_USBD_CDC_ClearBuffer != nullptr;
}

#else

static bool wrapper_linked(void) { return false; }

#endif

Snapshot statistics(void) {
  const Snapshot result = {
    MK61_USB_CDC_RX_GUARD_SUPPORTED != 0,
    wrapper_linked(),
#if MK61_USB_CDC_RX_GUARD_SUPPORTED
    throttle_count
#else
    0
#endif
  };
  return result;
}

void reset_statistics(void) {
#if MK61_USB_CDC_RX_GUARD_SUPPORTED
  throttle_count = 0;
#endif
}

const char* backend_name(void) {
  return MK61_USB_CDC_RX_GUARD_SUPPORTED ? "NAK-wrap" : "disabled";
}

} // namespace usb_cdc_rx_guard
