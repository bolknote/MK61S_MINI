#if defined(MK61_BUILD_WBMP_MODULE)

#include "image1_viewer.hpp"
#include "loadable_module_abi.hpp"

extern "C" __attribute__((used, section(".mk61_module_entry")))
u32 mk61_module_entry(u32 raw_command, u32 argument0, u32 argument1,
                      u32 argument2, u32 argument3) {
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::INITIALIZE:
      return 0;
    case loadable_module::Command::WBMP_VIEW:
      return (u32) image1_viewer::view(
          *(MK61Display*) argument0, (const u8*) argument1, (u16) argument2,
          (wbmp::Status*) argument3);
    case loadable_module::Command::WBMP_VIEW_ENTRY:
      return (u32) image1_viewer::view_entry(
          *(MK61Display*) argument0,
          *(const program_store::Entry*) argument1,
          (wbmp::Status*) argument2);
    default:
      return 0;
  }
}

#endif
