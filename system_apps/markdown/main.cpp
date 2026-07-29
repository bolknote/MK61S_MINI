// Standalone T2 Markdown viewer System APP translation unit.

#define MK61_BUILD_MARKDOWN_MODULE 1
#define view_entry mk61_standalone_markdown_view_entry
#define result_text mk61_standalone_markdown_result_text

#include "../../code/config.h"

#if MK61_HAS_COMPILED_GRAPHICS
  #include "../../code/markdown_document.cpp"
  #include "../../code/wbmp.cpp"
  #include "../../code/image1_viewer.cpp"
#else
  #include "../../code/markdown_plain.cpp"
#endif
#include "../../code/markdown_viewer.cpp"
#include "../../code/markdown_viewer_module_entry.cpp"
