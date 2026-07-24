// Arduino IDE requires the primary .ino file to have the same name as its
// directory.  The actual MK61s sketch remains in mk61s-M.ino; Arduino joins
// both .ino tabs before compiling them.

#include "rust_types.h"

// Keep Arduino's generated prototypes after the type definitions above even
// though the implementation lives in the second .ino tab.
static void mk61_arduino_sketch_anchor(void) {}
