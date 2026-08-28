#if defined(MK61_BUILD_MARKDOWN_MODULE)

#include "config.h"
#if MK61_MARKDOWN_USES_WBMP
  #include "image1_viewer.hpp"
#endif
#include "loadable_module_abi.hpp"
#include "markdown_viewer.hpp"
#include "program_store.hpp"

namespace {

static loadable_module::FileOpenResult markdown_result(
    markdown_viewer::Result result) {
  using loadable_module::FileOpenResult;
  switch(result) {
    case markdown_viewer::Result::OK:
      return FileOpenResult::OK;
    case markdown_viewer::Result::BUSY:
      return FileOpenResult::BUSY;
    case markdown_viewer::Result::READ_ERROR:
      return FileOpenResult::IO_ERROR;
    case markdown_viewer::Result::INVALID_DOCUMENT:
      return FileOpenResult::INVALID_FILE;
    case markdown_viewer::Result::DISPLAY_ERROR:
      return FileOpenResult::RUNTIME_ERROR;
  }
  return FileOpenResult::RUNTIME_ERROR;
}

#if MK61_MARKDOWN_USES_WBMP
static loadable_module::FileOpenResult image_result(
    image1_viewer::Result result) {
  using loadable_module::FileOpenResult;
  switch(result) {
    case image1_viewer::Result::OK:
      return FileOpenResult::OK;
    case image1_viewer::Result::BUSY:
      return FileOpenResult::BUSY;
    case image1_viewer::Result::READ_ERROR:
      return FileOpenResult::IO_ERROR;
    case image1_viewer::Result::INVALID_IMAGE:
    case image1_viewer::Result::DECODE_ERROR:
      return FileOpenResult::INVALID_FILE;
    case image1_viewer::Result::UNSUPPORTED_DISPLAY:
      return FileOpenResult::UNSUPPORTED_DISPLAY;
    case image1_viewer::Result::DISPLAY_ERROR:
      return FileOpenResult::RUNTIME_ERROR;
  }
  return FileOpenResult::RUNTIME_ERROR;
}
#endif

} // namespace

extern "C" __attribute__((used, section(".mk61_module_entry")))
u32 mk61_module_entry(u32 raw_command, u32, u32 argument1, u32, u32) {
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::INITIALIZE:
      return 0;
    case loadable_module::Command::FILE_OPEN: {
      program_store::Entry entry = {};
      if(argument1 > 0xFFFFU ||
         !program_store::entry_by_id((u16) argument1, entry)) {
        return (u32) loadable_module::FileOpenResult::INVALID_FILE;
      }
      if(entry.type == program_store::ProgramType::MARKDOWN) {
        return (u32) markdown_result(
            markdown_viewer::view_entry(main_lcd(), entry));
      }
#if MK61_MARKDOWN_USES_WBMP
      if(entry.type == program_store::ProgramType::IMAGE1) {
        return (u32) image_result(
            image1_viewer::view_entry(main_lcd(), entry));
      }
#endif
      return (u32) loadable_module::FileOpenResult::INVALID_FILE;
    }
    default:
      return (u32) loadable_module::FileOpenResult::INVALID_FILE;
  }
}

#endif
