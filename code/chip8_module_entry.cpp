#if defined(MK61_BUILD_CHIP8_MODULE)

#include "chip8_runner.hpp"
#include "loadable_module_abi.hpp"
#include "program_store.hpp"

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
      return (u32) chip8_runner::run_entry(entry);
    }
    default:
      return (u32) loadable_module::FileOpenResult::INVALID_FILE;
  }
}

#endif
