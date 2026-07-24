#include "config.h"

// See mk61_ide_focal_app.cpp.  Keeping the System APP implementation in one
// dedicated object lets Arduino IDE build resident and BASIC.APP in one pass.
#if defined(MK61_ARDUINO_IDE_SYSTEM_APPS) && MK61_TINYBASIC_IS_LOADABLE

#define MK61_BUILD_TINYBASIC_MODULE 1
#define mk61_module_entry mk61_ide_basic_module_entry

#include "tinybasic.cpp"
#include "tinybasic_module_entry.cpp"

#endif
