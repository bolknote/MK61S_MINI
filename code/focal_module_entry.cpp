#if defined(MK61_BUILD_FOCAL_MODULE)

#define FOCAL_library_select mk61_module_focal_library_select
#define FOCAL_menu_select mk61_module_focal_menu_select
#define CompileFocal mk61_module_compile_focal
#define InitFocal mk61_module_init_focal
#define FocalIsReady mk61_module_focal_is_ready
#define RunFocal mk61_module_run_focal
#define RunFocalProgram mk61_module_run_focal_program
#define EditFocal mk61_module_edit_focal
#define EditFocalProgram mk61_module_edit_focal_program

#include "focal.hpp"
#include "loadable_module_abi.hpp"

extern "C" __attribute__((used, section(".mk61_module_entry")))
u32 mk61_module_entry(u32 raw_command, u32 argument0, u32 argument1, u32 argument2, u32) {
  (void) argument0; (void) argument1; (void) argument2;
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::INITIALIZE:
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
      if(argument0 != 0) return portable_system::bind(argument0, argument1, argument2)
          ? 0 : (u32) loadable_module::FileOpenResult::RUNTIME_ERROR;
#endif
      InitFocal(); return 0;
    case loadable_module::Command::FOCAL_LIBRARY_SELECT:
      return FOCAL_library_select();
    case loadable_module::Command::FOCAL_MENU_SELECT:
      return FOCAL_menu_select();
    case loadable_module::Command::FOCAL_COMPILE:
      return CompileFocal((const char*) argument0);
    case loadable_module::Command::FOCAL_IS_READY:
      return FocalIsReady();
    case loadable_module::Command::FOCAL_RUN_INDEX:
      return (u32) RunFocal((int) argument0);
    case loadable_module::Command::FOCAL_RUN_NAME:
      return (u32) RunFocalProgram((const char*) argument0);
    case loadable_module::Command::FOCAL_RUN_ID:
      return (u32) RunFocalProgram((u16) argument0);
    case loadable_module::Command::FOCAL_EDIT:
      EditFocal(); return 0;
    case loadable_module::Command::FOCAL_EDIT_NAME:
      return EditFocalProgram((const char*) argument0);
    case loadable_module::Command::FOCAL_EDIT_ID:
      return EditFocalProgram((u16) argument0);
    default:
      return 0;
  }
}

#endif
