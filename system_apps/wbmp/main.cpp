// Standalone WBMP viewer System APP translation unit.
//
// All viewer sources are compiled as one module object.  Calls shared with the
// firmware are resolved from the exact resident ELF during the APP link.

#define MK61_BUILD_WBMP_MODULE 1
#define view mk61_standalone_wbmp_view
#define view_entry mk61_standalone_wbmp_view_entry
#define result_text mk61_standalone_wbmp_result_text

#include "../../code/wbmp.cpp"
#include "../../code/image1_viewer.cpp"
#include "../../code/image1_viewer_module_entry.cpp"
