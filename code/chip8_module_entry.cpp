#if defined(MK61_BUILD_CHIP8_MODULE)

#include "chip8_runner.hpp"
#include "loadable_module_abi.hpp"
#include "program_store.hpp"

extern "C" u32 mk61_app_initialize(const mk61_app_api* api,
                                    u32 image_crc, u32 kind) {
  return portable_system::bind(api, image_crc, kind)
      ? 0 : (u32) loadable_module::FileOpenResult::RUNTIME_ERROR;
}

extern "C" u32 mk61_app_command(u32 raw_command, u32 argument0,
                                 u32 argument1, u32 argument2, u32) {
  (void) argument0; (void) argument1; (void) argument2;
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::FILE_OPEN: {
      program_store::Entry entry = {};
      if(argument1 > 0xFFFFU ||
         !program_store::entry_by_id((u16) argument1, entry)) {
        return (u32) loadable_module::FileOpenResult::INVALID_FILE;
      }
      return (u32) chip8_runner::run_entry(entry);
    }
    default:
      return (u32) loadable_module::FileOpenResult::INVALID_FILE;
  }
}

#endif
