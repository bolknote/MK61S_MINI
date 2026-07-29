#include "config.h"

// Arduino IDE post-build relinks this discarded object into the SRAM overlay.
#if defined(MK61_ARDUINO_IDE_SYSTEM_APPS) && \
    MK61_MARKDOWN_VIEWER_IS_LOADABLE

#define MK61_BUILD_MARKDOWN_MODULE 1
#define mk61_module_entry mk61_ide_markdown_module_entry
#define view_entry mk61_ide_markdown_view_entry
#define result_text mk61_ide_markdown_result_text

#if MK61_HAS_COMPILED_GRAPHICS

  #include "markdown_document.cpp"

// Keep the private decoder names distinct from resident symbols before the
// post-link extraction of MARKDOWN.APP.
#define viewport_bytes mk61_ide_markdown_wbmp_viewport_bytes
#define inspect mk61_ide_markdown_wbmp_inspect
#define dark_pixel mk61_ide_markdown_wbmp_dark_pixel
#define decode_viewport mk61_ide_markdown_wbmp_decode_viewport
#define status_text mk61_ide_markdown_wbmp_status_text

  #include "wbmp.cpp"
  #include "image1_viewer.cpp"

#else

  #include "markdown_plain.cpp"

#endif

#include "markdown_viewer.cpp"
#include "markdown_viewer_module_entry.cpp"

#endif
