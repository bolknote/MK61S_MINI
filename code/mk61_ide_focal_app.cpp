#include "config.h"

// The MK61s Arduino board compiles this translation unit together with the
// resident sketch.  It is deliberately unreferenced by the resident linker;
// the board's post-build hook links the resulting object into FOCAL.APP.
#if defined(MK61_ARDUINO_IDE_SYSTEM_APPS) && MK61_FOCAL_IS_LOADABLE

#define MK61_BUILD_FOCAL_MODULE 1
#define mk61_module_entry mk61_ide_focal_module_entry

#include "focal.cpp"
#include "focal_module_entry.cpp"

#endif
