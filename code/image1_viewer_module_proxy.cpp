#include "config.h"

#if MK61_WBMP_VIEWER_IS_LOADABLE && !defined(MK61_BUILD_WBMP_MODULE)

#include "image1_viewer.hpp"
#include "loadable_module_runtime.hpp"

namespace image1_viewer {
namespace {

static u32 pointer_argument(const void* value) {
  return (u32) (usize) value;
}

} // namespace

Result view(MK61Display& display, const u8* data, u16 size,
            wbmp::Status* image_status) {
  u32 result = (u32) Result::READ_ERROR;
  const loadable_module::RuntimeStatus status = loadable_module::invoke(
      loadable_module::Kind::WBMP_VIEWER,
      loadable_module::Command::WBMP_VIEW,
      pointer_argument(&display), pointer_argument(data), size,
      pointer_argument(image_status), result);
  return status == loadable_module::RuntimeStatus::OK
      ? (Result) result : Result::READ_ERROR;
}

Result view_entry(MK61Display& display, const program_store::Entry& entry,
                  wbmp::Status* image_status) {
  u32 result = (u32) Result::READ_ERROR;
  const loadable_module::RuntimeStatus status = loadable_module::invoke(
      loadable_module::Kind::WBMP_VIEWER,
      loadable_module::Command::WBMP_VIEW_ENTRY,
      pointer_argument(&display), pointer_argument(&entry),
      pointer_argument(image_status), 0, result);
  return status == loadable_module::RuntimeStatus::OK
      ? (Result) result : Result::READ_ERROR;
}

const char* result_text(Result result) {
  switch(result) {
    case Result::OK: return "ok";
    case Result::BUSY: return "workspace busy";
    case Result::READ_ERROR: return "read/module error";
    case Result::INVALID_IMAGE: return "invalid WBMP";
    case Result::DECODE_ERROR: return "decode error";
    case Result::DISPLAY_ERROR: return "display error";
  }
  return "unknown image viewer error";
}

} // namespace image1_viewer

#endif
