#if defined(MK61_BUILD_TINYBASIC_MODULE)

#define TinyBASIC_library_select mk61_module_tinybasic_library_select
#define TinyBASIC_menu_select mk61_module_tinybasic_menu_select
#define CompileTinyBasic mk61_module_compile_tinybasic
#define InitTinyBasic mk61_module_init_tinybasic
#define TinyBasicIsReady mk61_module_tinybasic_is_ready
#define RunTinyBasic mk61_module_run_tinybasic
#define RunTinyBasicProgram mk61_module_run_tinybasic_program
#define RunTinyBasicProgramStatus mk61_module_run_tinybasic_program_status
#define EditTinyBasic mk61_module_edit_tinybasic
#define EditTinyBasicProgram mk61_module_edit_tinybasic_program
#define EditTinyBasicProgramAt mk61_module_edit_tinybasic_program_at

#include "loadable_module_abi.hpp"
#include "tinybasic.hpp"
#if defined(MK61_LANGUAGE_VM_COMPILER)
#include "language_vm_abi.hpp"
#endif

extern "C" u32 mk61_app_initialize(const mk61_app_api* api,
                                    u32 image_crc, u32 kind) {
  if(!portable_system::bind(api, image_crc, kind))
    return (u32) loadable_module::FileOpenResult::RUNTIME_ERROR;
  InitTinyBasic();
  return 0;
}

extern "C" u32 mk61_app_command(u32 raw_command, u32 argument0,
                                 u32 argument1, u32 argument2, u32) {
  (void) argument2;
#if defined(MK61_LANGUAGE_VM_COMPILER)
  struct Binding {
    ~Binding() {
      if(language_vm::frontend_request)
        language_vm::frontend_request->source_id=language_vm::frontend_source_id();
      language_vm::frontend_request = nullptr;
    }
  } binding;
  auto* request = (language_vm::Request*)(usize)argument2;
  language_vm::frontend_request = language_vm::compatible(request) ? request : nullptr;
#endif
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
#if defined(MK61_LANGUAGE_VM_COMPILER)
    case loadable_module::Command::LANGUAGE_COMPILER_INFO:
      return language_vm::COMPILER_MAGIC;
    case loadable_module::Command::LANGUAGE_COMPILER_EMIT:
      return language_vm::frontend_emit();
#endif
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
      return argument1
                 ? EditTinyBasicProgramAt((u16)argument0, (u16)(argument1 >> 16), (u16)argument1)
                 : EditTinyBasicProgram((u16)argument0);
    case loadable_module::Command::TINYBASIC_RUN_ID_STATUS:
      return (u32) RunTinyBasicProgramStatus(
          (u16) argument0, (TinyBasicRunMode) argument1);
    default:
      return 0;
  }
}

#endif
