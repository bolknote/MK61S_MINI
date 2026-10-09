#include "config.h"

#if MK61_FOCAL_IS_LOADABLE

#include "focal.hpp"
#include "loadable_module_runtime.hpp"
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
#include "language_vm_resident.hpp"
#endif

namespace {

static loadable_module::RuntimeStatus invoke(loadable_module::Command command,
                                             u32 a, u32 b, u32 &result) {
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
  return language_vm::invoke_resident(language_vm::Language::FOCAL, command, a,
                                      b, result);
#else
  return loadable_module::invoke(loadable_module::Kind::FOCAL, command, a, b, 0,
                                 0, result);
#endif
}

static u32 pointer_argument(const void *value) { return (u32)(usize)value; }

static bool call_bool(loadable_module::Command command, u32 argument0 = 0) {
  u32 result = 0;
  return invoke(command, argument0, 0, result) ==
             loadable_module::RuntimeStatus::OK &&
         result != 0;
}

static void call_void(loadable_module::Command command, u32 argument0 = 0) {
  u32 result = 0;
  (void)invoke(command, argument0, 0, result);
}

static FocalRunStatus call_status(loadable_module::Command command,
                                  u32 argument0, u32 argument1) {
  u32 result = 0;
  if (invoke(command, argument0, argument1, result) !=
      loadable_module::RuntimeStatus::OK) {
    return FocalRunStatus::UNAVAILABLE;
  }
  if (result > (u32)FocalRunStatus::UNAVAILABLE) {
    return FocalRunStatus::UNAVAILABLE;
  }
  return (FocalRunStatus)result;
}

} // namespace

bool FOCAL_library_select(void) {
  return call_bool(loadable_module::Command::FOCAL_LIBRARY_SELECT);
}

bool FOCAL_menu_select(void) {
  return call_bool(loadable_module::Command::FOCAL_MENU_SELECT);
}

bool CompileFocal(const char *program) {
  return call_bool(loadable_module::Command::FOCAL_COMPILE,
                   pointer_argument(program));
}

void InitFocal(void) {
  // INITIALIZE belongs to the loader lifecycle and is issued exactly once
  // after a decode. Merely ensure that the cached FOCAL image is active.
  (void)loadable_module::status(loadable_module::Kind::FOCAL);
}

bool FocalIsReady(void) {
  return call_bool(loadable_module::Command::FOCAL_IS_READY);
}

FocalRunStatus RunFocal(int index) {
  return call_status(loadable_module::Command::FOCAL_RUN_INDEX, (u32)index, 0);
}

FocalRunStatus RunFocalProgram(const char *name) {
  return call_status(loadable_module::Command::FOCAL_RUN_NAME,
                     pointer_argument(name), 0);
}

FocalRunStatus RunFocalProgram(u16 id) {
  return call_status(loadable_module::Command::FOCAL_RUN_ID, id, 0);
}

void EditFocal(void) { call_void(loadable_module::Command::FOCAL_EDIT); }

bool EditFocalProgram(const char *name) {
  return call_bool(loadable_module::Command::FOCAL_EDIT_NAME,
                   pointer_argument(name));
}

bool EditFocalProgram(u16 id) {
  return call_bool(loadable_module::Command::FOCAL_EDIT_ID, id);
}

#endif
