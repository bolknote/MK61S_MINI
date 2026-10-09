#ifndef MK61_FOCAL_HPP
#define MK61_FOCAL_HPP
#include "rust_types.h"
#ifndef FOCAL_HOST_TEST
#include "config.h"
#endif
#ifndef MK61_ENABLE_FOCAL
#define MK61_ENABLE_FOCAL 1
#endif
enum class FocalRunStatus : u32 {
  COMPLETED = 0,
  STOPPED = 1,
  COMPILE_ERROR = 2,
  RUNTIME_ERROR = 3,
  NOT_FOUND = 4,
  UNAVAILABLE = 5
};
inline bool FocalRunSucceeded(FocalRunStatus s) {
  return s == FocalRunStatus::COMPLETED;
}
#if MK61_ENABLE_FOCAL
bool FOCAL_library_select();
bool FOCAL_menu_select();
bool CompileFocal(const char *);
void InitFocal();
bool FocalIsReady();
FocalRunStatus RunFocal(int);
FocalRunStatus RunFocalProgram(const char *);
FocalRunStatus RunFocalProgram(u16);
void EditFocal();
bool EditFocalProgram(const char *);
bool EditFocalProgram(u16);
#else
inline bool FOCAL_library_select() { return false; }
inline bool FOCAL_menu_select() { return false; }
inline bool CompileFocal(const char *) { return false; }
inline void InitFocal() {}
inline bool FocalIsReady() { return false; }
inline FocalRunStatus RunFocal(int) { return FocalRunStatus::UNAVAILABLE; }
inline FocalRunStatus RunFocalProgram(const char *) {
  return FocalRunStatus::UNAVAILABLE;
}
inline FocalRunStatus RunFocalProgram(u16) {
  return FocalRunStatus::UNAVAILABLE;
}
inline void EditFocal() {}
inline bool EditFocalProgram(const char *) { return false; }
inline bool EditFocalProgram(u16) { return false; }
#endif
#endif
