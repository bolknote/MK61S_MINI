#ifndef FOCAL_COMPILER
#define FOCAL_COMPILER

#ifndef FOCAL_HOST_TEST
#include "config.h"
#endif

#ifndef MK61_ENABLE_FOCAL
  #define MK61_ENABLE_FOCAL 1
#endif

#if MK61_ENABLE_FOCAL
extern bool FOCAL_library_select(void);
extern bool FOCAL_menu_select(void);
extern bool CompileFocal(char* program);
extern void InitFocal(void);
extern bool FocalIsReady(void);
extern void RunFocal(int FocalN);
extern void EditFocal(void);
extern bool EditFocalProgram(const char* name);
#else
inline bool FOCAL_library_select(void) { return false; }
inline bool FOCAL_menu_select(void) { return false; }
inline bool CompileFocal(char*) { return false; }
inline void InitFocal(void) {}
inline bool FocalIsReady(void) { return false; }
inline void RunFocal(int) {}
inline void EditFocal(void) {}
inline bool EditFocalProgram(const char*) { return false; }
#endif

#endif
