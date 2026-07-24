#include "config.h"

// See mk61_ide_focal_app.cpp.  The normal resident link discards this object;
// the MK61s board hook relinks it at the exact SRAM overlay address.
#if defined(MK61_ARDUINO_IDE_SYSTEM_APPS) && MK61_WBMP_VIEWER_IS_LOADABLE

#define MK61_BUILD_WBMP_MODULE 1
#define mk61_module_entry mk61_ide_wbmp_module_entry
#define view mk61_ide_wbmp_view
#define view_entry mk61_ide_wbmp_view_entry
#define result_text mk61_ide_wbmp_result_text

#include "wbmp.cpp"
#include "a00_image_multiplex.cpp"
#include "image1_viewer.cpp"
#include "image1_viewer_module_entry.cpp"

#endif
