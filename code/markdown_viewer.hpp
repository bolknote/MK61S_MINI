#ifndef MK61_MARKDOWN_VIEWER_HPP
#define MK61_MARKDOWN_VIEWER_HPP

#include "display.hpp"
#include "program_store.hpp"

namespace markdown_viewer {

enum class Result : u8 {
  OK = 0,
  BUSY,
  READ_ERROR,
  INVALID_DOCUMENT,
  DISPLAY_ERROR
};

Result view_entry(MK61Display& display,
                  const program_store::Entry& entry);
const char* result_text(Result result);

} // namespace markdown_viewer

#endif
