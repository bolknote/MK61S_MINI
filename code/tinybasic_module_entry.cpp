#if defined(MK61_BUILD_TINYBASIC_MODULE)

#define TinyBASIC_library_select mk61_module_tinybasic_library_select
#define TinyBASIC_menu_select mk61_module_tinybasic_menu_select
#define CompileTinyBasic mk61_module_compile_tinybasic
#define InitTinyBasic mk61_module_init_tinybasic
#define TinyBasicIsReady mk61_module_tinybasic_is_ready
#define RunTinyBasic mk61_module_run_tinybasic
#define RunTinyBasicProgram mk61_module_run_tinybasic_program
#define EditTinyBasic mk61_module_edit_tinybasic
#define EditTinyBasicProgram mk61_module_edit_tinybasic_program

#include "loadable_module_abi.hpp"
#include "tinybasic.hpp"

extern "C" __attribute__((used, section(".mk61_module_entry")))
u32 mk61_module_entry(u32 raw_command, u32 argument0, u32, u32, u32) {
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::INITIALIZE:
      InitTinyBasic(); return 0;
    case loadable_module::Command::TINYBASIC_LIBRARY_SELECT:
      return TinyBASIC_library_select();
    case loadable_module::Command::TINYBASIC_MENU_SELECT:
      return TinyBASIC_menu_select();
    case loadable_module::Command::TINYBASIC_COMPILE:
      return CompileTinyBasic((char*) argument0);
    case loadable_module::Command::TINYBASIC_IS_READY:
      return TinyBasicIsReady();
    case loadable_module::Command::TINYBASIC_RUN_INDEX:
      RunTinyBasic((int) argument0); return 0;
    case loadable_module::Command::TINYBASIC_RUN_NAME:
      return RunTinyBasicProgram((const char*) argument0);
    case loadable_module::Command::TINYBASIC_RUN_ID:
      return RunTinyBasicProgram((u16) argument0);
    case loadable_module::Command::TINYBASIC_EDIT:
      EditTinyBasic(); return 0;
    case loadable_module::Command::TINYBASIC_EDIT_NAME:
      return EditTinyBasicProgram((const char*) argument0);
    case loadable_module::Command::TINYBASIC_EDIT_ID:
      return EditTinyBasicProgram((u16) argument0);
    default:
      return 0;
  }
}

#endif
