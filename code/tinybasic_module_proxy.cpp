#include "config.h"

#if MK61_TINYBASIC_IS_LOADABLE

#include "loadable_module_runtime.hpp"
#include "tinybasic.hpp"

namespace {

static u32 pointer_argument(const void* value) {
  return (u32) (usize) value;
}

static bool call_bool(loadable_module::Command command,
                      u32 argument0 = 0) {
  u32 result = 0;
  return loadable_module::invoke(loadable_module::Kind::TINYBASIC, command,
                                 argument0, 0, 0, 0, result) ==
           loadable_module::RuntimeStatus::OK && result != 0;
}

static void call_void(loadable_module::Command command, u32 argument0 = 0) {
  u32 result = 0;
  (void) loadable_module::invoke(loadable_module::Kind::TINYBASIC, command,
                                 argument0, 0, 0, 0, result);
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
  call_void(loadable_module::Command::INITIALIZE);
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

void EditTinyBasic(void) {
  call_void(loadable_module::Command::TINYBASIC_EDIT);
}

bool EditTinyBasicProgram(const char* name) {
  return call_bool(loadable_module::Command::TINYBASIC_EDIT_NAME,
                   pointer_argument(name));
}

bool EditTinyBasicProgram(u16 id) {
  return call_bool(loadable_module::Command::TINYBASIC_EDIT_ID, id);
}

#endif
