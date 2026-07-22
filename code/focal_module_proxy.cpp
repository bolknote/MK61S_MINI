#include "config.h"

#if MK61_FOCAL_IS_LOADABLE

#include "focal.hpp"
#include "loadable_module_runtime.hpp"

namespace {

static u32 pointer_argument(const void* value) {
  return (u32) (usize) value;
}

static bool call_bool(loadable_module::Command command,
                      u32 argument0 = 0) {
  u32 result = 0;
  return loadable_module::invoke(loadable_module::Kind::FOCAL, command,
                                 argument0, 0, 0, 0, result) ==
           loadable_module::RuntimeStatus::OK && result != 0;
}

static FocalRunStatus call_status(loadable_module::Command command,
                                  u32 argument0) {
  u32 result = 0;
  return loadable_module::invoke(loadable_module::Kind::FOCAL, command,
                                 argument0, 0, 0, 0, result) ==
           loadable_module::RuntimeStatus::OK
      ? (FocalRunStatus) result : FocalRunStatus::UNAVAILABLE;
}

} // namespace

bool FOCAL_library_select(void) {
  return call_bool(loadable_module::Command::FOCAL_LIBRARY_SELECT);
}

bool FOCAL_menu_select(void) {
  return call_bool(loadable_module::Command::FOCAL_MENU_SELECT);
}

bool CompileFocal(const char* program) {
  return call_bool(loadable_module::Command::FOCAL_COMPILE,
                   pointer_argument(program));
}

void InitFocal(void) {
  u32 result = 0;
  (void) loadable_module::invoke(loadable_module::Kind::FOCAL,
      loadable_module::Command::INITIALIZE, result);
}

bool FocalIsReady(void) {
  return call_bool(loadable_module::Command::FOCAL_IS_READY);
}

FocalRunStatus RunFocal(int index) {
  return call_status(loadable_module::Command::FOCAL_RUN_INDEX, (u32) index);
}

FocalRunStatus RunFocalProgram(const char* name) {
  return call_status(loadable_module::Command::FOCAL_RUN_NAME,
                     pointer_argument(name));
}

FocalRunStatus RunFocalProgram(u16 id) {
  return call_status(loadable_module::Command::FOCAL_RUN_ID, id);
}

void EditFocal(void) {
  u32 result = 0;
  (void) loadable_module::invoke(loadable_module::Kind::FOCAL,
      loadable_module::Command::FOCAL_EDIT, result);
}

bool EditFocalProgram(const char* name) {
  return call_bool(loadable_module::Command::FOCAL_EDIT_NAME,
                   pointer_argument(name));
}

bool EditFocalProgram(u16 id) {
  return call_bool(loadable_module::Command::FOCAL_EDIT_ID, id);
}

#endif
