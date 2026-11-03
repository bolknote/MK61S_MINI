#include "USBDevice.h"
#include <Arduino.h>
#include <usbd_cdc_if.h>
#include <usbd_if.h>

// Keep STM32duino's resume clock sequence; USB pins, disconnect/reconnect and
// endpoint state are handled by the same owned bridge as the native firmware.
extern "C" void USBD_SystemClockConfigFromResume(void) {
  configIPClock();
  SystemClock_Config();
}
extern "C" void USBD_CDC_init(void) { CDC_init(); }
