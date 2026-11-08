#ifndef MK61_USB_CRC_PROBE_HPP
#define MK61_USB_CRC_PROBE_HPP
#include <stdint.h>
// Diagnostic source-copy only. All paths coexist in one ELF for matched tests.
namespace usb_crc_probe {
extern volatile uint32_t mode;
uint32_t control(uint32_t operation, uint32_t index, uint32_t value=0);
}
#endif
