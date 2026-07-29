#if defined(MK61_BUILD_MARKDOWN_MODULE)

#include "loadable_module_abi.hpp"
#include "markdown_viewer.hpp"
#include "program_store.hpp"

namespace {

static loadable_module::FileOpenResult file_open_result(
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
      return (u32) file_open_result(
          markdown_viewer::view_entry(main_lcd(), entry));
    }
    default:
      return (u32) loadable_module::FileOpenResult::INVALID_FILE;
  }
}

#endif
