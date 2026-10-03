#ifndef MK61_UI_DISPLAY_TEST_ARDUINO_H
#define MK61_UI_DISPLAY_TEST_ARDUINO_H
#include <stddef.h>
#include <stdint.h>
#ifndef HEX
#define HEX 16
#endif
namespace ui_display_test { inline uint32_t now = 0; }
inline uint32_t millis() { return ui_display_test::now; }
#endif
