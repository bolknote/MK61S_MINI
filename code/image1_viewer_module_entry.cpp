#if defined(MK61_BUILD_WBMP_MODULE)

#include "image1_viewer.hpp"
#include "loadable_module_abi.hpp"
#include "menu.hpp"

namespace {

static loadable_module::FileOpenResult file_open_result(
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

} // namespace

extern "C" u32 mk61_app_initialize(const mk61_app_api* api,
                                    u32 image_crc, u32 kind) {
  return portable_system::bind(api, image_crc, kind)
      ? 0 : (u32) loadable_module::FileOpenResult::RUNTIME_ERROR;
}

extern "C" u32 mk61_app_command(u32 raw_command, u32 argument0,
                                 u32 argument1, u32 argument2,
                                 u32 argument3) {
  (void) argument0; (void) argument1; (void) argument2;
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::WBMP_VIEW:
      return (u32) image1_viewer::view(
          main_lcd(), (const u8*) argument1
          , (u16) argument2,
          (wbmp::Status*) argument3);
    case loadable_module::Command::WBMP_VIEW_ENTRY:
    {
      program_store::Entry entry = {};
      if(argument1 > 0xFFFFU || !program_store::entry_by_id((u16) argument1, entry))
        return (u32) image1_viewer::Result::READ_ERROR;
      return (u32) image1_viewer::view_entry(main_lcd(), entry, (wbmp::Status*) argument2);
    }
    case loadable_module::Command::FILE_OPEN: {
      program_store::Entry entry = {};
      if(argument1 > 0xFFFFU ||
         !program_store::entry_by_id((u16) argument1, entry)) {
        return (u32) loadable_module::FileOpenResult::INVALID_FILE;
      }
      return (u32) file_open_result(
          image1_viewer::view_entry(main_lcd(), entry));
    }
    default:
      return (u32) loadable_module::FileOpenResult::INVALID_FILE;
  }
}

#endif
