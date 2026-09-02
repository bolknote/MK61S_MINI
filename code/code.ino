// Arduino IDE requires the primary .ino file to have the same name as its
// directory.  The actual MK61s sketch remains in mk61s-M.ino; Arduino joins
// both .ino tabs before compiling them.

#include "rust_types.h"
#include "deep_idle_policy.hpp"
#include "idle_sleep_policy.hpp"

// Keep Arduino's generated prototypes after every non-built-in type used by
// an .ino function signature.  The implementation lives in the second tab,
// but Arduino IDE preprocesses this file first because it matches the sketch
// directory name.
[[maybe_unused]] static void mk61_arduino_sketch_anchor(void) {}
