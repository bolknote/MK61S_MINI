#ifndef FOCAL_COMPILER
#define FOCAL_COMPILER

#include "rust_types.h"

#ifndef FOCAL_HOST_TEST
#include "config.h"
#endif

#ifndef MK61_ENABLE_FOCAL
  #define MK61_ENABLE_FOCAL 1
#endif

enum class FocalRunStatus {
  COMPLETED,
  STOPPED,
  COMPILE_ERROR,
  RUNTIME_ERROR,
  NOT_FOUND,
  UNAVAILABLE
};

inline bool FocalRunSucceeded(FocalRunStatus status) {
  return status == FocalRunStatus::COMPLETED;
}

#if MK61_ENABLE_FOCAL
extern bool FOCAL_library_select(void);
extern bool FOCAL_menu_select(void);
extern bool CompileFocal(const char* program);
extern void InitFocal(void);
extern bool FocalIsReady(void);
extern FocalRunStatus RunFocal(int FocalN);
extern FocalRunStatus RunFocalProgram(const char* name);
extern FocalRunStatus RunFocalProgram(u16 id);
extern void EditFocal(void);
extern bool EditFocalProgram(const char* name);
extern bool EditFocalProgram(u16 id);
#else
inline bool FOCAL_library_select(void) { return false; }
inline bool FOCAL_menu_select(void) { return false; }
inline bool CompileFocal(const char*) { return false; }
inline void InitFocal(void) {}
inline bool FocalIsReady(void) { return false; }
inline FocalRunStatus RunFocal(int) { return FocalRunStatus::UNAVAILABLE; }
inline FocalRunStatus RunFocalProgram(const char*) { return FocalRunStatus::UNAVAILABLE; }
inline FocalRunStatus RunFocalProgram(u16) { return FocalRunStatus::UNAVAILABLE; }
inline void EditFocal(void) {}
inline bool EditFocalProgram(const char*) { return false; }
inline bool EditFocalProgram(u16) { return false; }
#endif

#endif
