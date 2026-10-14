#include "config.h"
#if MK61_NARROW_USB_SERIAL_SUPPORTED
extern "C" {
#include <usbd_cdc_if.h>
}
namespace mk61_io {
UsbSerial serial;
void UsbSerial::begin(uint32_t) { CDC_init(); }
void UsbSerial::end() { CDC_deInit(); }
int UsbSerial::available() { return CDC_ReceiveQueue_ReadSize(&ReceiveQueue); }
int UsbSerial::availableForWrite() { return CDC_TransmitQueue_WriteSize(&TransmitQueue); }
int UsbSerial::peek() { return CDC_ReceiveQueue_Peek(&ReceiveQueue); }
int UsbSerial::read() {
  const int byte = CDC_ReceiveQueue_Dequeue(&ReceiveQueue);
  CDC_resume_receive();
  return byte;
}
size_t UsbSerial::write(uint8_t byte) { return write(&byte, 1); }
size_t UsbSerial::write(const uint8_t* bytes, size_t count) {
  size_t remaining = count;
  while(remaining && CDC_connected()) {
    size_t portion = static_cast<size_t>(CDC_TransmitQueue_WriteSize(&TransmitQueue));
    if(portion > remaining) portion = remaining;
    if(portion) {
      CDC_TransmitQueue_Enqueue(&TransmitQueue, bytes, static_cast<uint32_t>(portion));
      bytes += portion;
      remaining -= portion;
      CDC_continue_transmit();
    }
  }
  return count - remaining;
}
void UsbSerial::flush() {
  while(CDC_TransmitQueue_ReadSize(&TransmitQueue) > 0 && CDC_connected()) {}
}
UsbSerial::operator bool() { return CDC_connected(); }
}
// The calculator polls its terminal explicitly; there are no Arduino serial hooks.
void serialEventRun(void) {}
#endif
