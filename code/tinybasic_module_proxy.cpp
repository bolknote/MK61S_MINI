#include "config.h"

#if MK61_TINYBASIC_IS_LOADABLE

#include "loadable_module_runtime.hpp"
#include "tinybasic.hpp"
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
#include "language_vm_resident.hpp"
#endif

namespace {

static loadable_module::RuntimeStatus invoke(loadable_module::Command command,
    u32 a,u32 b,u32& result) {
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
  return language_vm::invoke_resident(language_vm::Language::BASIC,command,a,b,result);
#else
  return loadable_module::invoke(loadable_module::Kind::TINYBASIC,command,a,b,0,0,result);
#endif
}

static u32 pointer_argument(const void* value) {
  return (u32) (usize) value;
}

static bool call_bool(loadable_module::Command command,
                      u32 argument0 = 0) {
  u32 result = 0;
  return invoke(command,argument0,0,result) ==
           loadable_module::RuntimeStatus::OK && result != 0;
}

static void call_void(loadable_module::Command command, u32 argument0 = 0) {
  u32 result = 0;
  (void) invoke(command,argument0,0,result);
}

static TinyBasicRunStatus call_status(loadable_module::Command command,
                                      u32 argument0, u32 argument1) {
  u32 result = 0;
  if(invoke(command,argument0,argument1,result) !=
     loadable_module::RuntimeStatus::OK) {
    return TinyBasicRunStatus::UNAVAILABLE;
  }
  if(result > (u32) TinyBasicRunStatus::NOT_FOUND) {
    return TinyBasicRunStatus::UNAVAILABLE;
  }
  return (TinyBasicRunStatus) result;
}

} // namespace

bool TinyBASIC_library_select(void) {
  return call_bool(loadable_module::Command::TINYBASIC_LIBRARY_SELECT);
}

bool TinyBASIC_menu_select(void) {
  return call_bool(loadable_module::Command::TINYBASIC_MENU_SELECT);
}

bool CompileTinyBasic(char* program) {
  return call_bool(loadable_module::Command::TINYBASIC_COMPILE,
                   pointer_argument(program));
}

void InitTinyBasic(void) {
  // INITIALIZE belongs to the loader lifecycle and is issued exactly once
  // after a decode. Merely ensure that the cached BASIC image is active.
  (void) loadable_module::status(loadable_module::Kind::TINYBASIC);
}

bool TinyBasicIsReady(void) {
  return call_bool(loadable_module::Command::TINYBASIC_IS_READY);
}

void RunTinyBasic(int index) {
  call_void(loadable_module::Command::TINYBASIC_RUN_INDEX, (u32) index);
}

bool RunTinyBasicProgram(const char* name) {
  return call_bool(loadable_module::Command::TINYBASIC_RUN_NAME,
                   pointer_argument(name));
}

bool RunTinyBasicProgram(u16 id) {
  return call_bool(loadable_module::Command::TINYBASIC_RUN_ID, id);
}

TinyBasicRunStatus RunTinyBasicProgramStatus(u16 id,
                                              TinyBasicRunMode mode) {
  return call_status(loadable_module::Command::TINYBASIC_RUN_ID_STATUS,
                     id, (u32) mode);
}

void EditTinyBasic(void) {
  call_void(loadable_module::Command::TINYBASIC_EDIT);
}

bool EditTinyBasicProgram(const char* name) {
  return call_bool(loadable_module::Command::TINYBASIC_EDIT_NAME,
                   pointer_argument(name));
}

bool EditTinyBasicProgramAt(u16 id, u16 line, u16 column) {
  u32 result = 0;
  return invoke(loadable_module::Command::TINYBASIC_EDIT_ID, id, ((u32)line << 16) | column,
                result) == loadable_module::RuntimeStatus::OK &&
         result != 0;
}

bool EditTinyBasicProgram(u16 id) {
  return call_bool(loadable_module::Command::TINYBASIC_EDIT_ID, id);
}

#endif
