#ifndef MK61_COMPUTE_GAP_PROBE_HPP
#define MK61_COMPUTE_GAP_PROBE_HPP
#include <stdint.h>
// Diagnostic source-copy instrumentation; never linked in a release build.
namespace compute_gap_probe {
enum class Service : uint8_t {
  KEYBOARD_POLL, KEYBOARD_SAMPLE, KEYBOARD_ROW0, KEYBOARD_ROW1,
  KEYBOARD_ROW2, KEYBOARD_ROW3, KEYBOARD_ROW4, USB_SCREEN
};
void note(Service);
void row(uint8_t);
uint32_t service(uint32_t operation, uint32_t index);
}
#endif
