#ifndef BASIC_COMPILER
#define BASIC_COMPILER

#ifndef BASIC_HOST_TEST
#include "config.h"
#endif

#ifndef MK61_ENABLE_BASIC
  #define MK61_ENABLE_BASIC 1
#endif

static constexpr int BASIC_MAXIMUM_STRING = 14;

enum class BASIC_WORD {_PRINT=1, _INPUT, _IF, _THEN, _ELSE, _STOP, _BEGIN, _END};

#if MK61_ENABLE_BASIC
extern bool BASIC_library_select(void);
extern bool BASIC_menu_select(void);
extern bool CompileBasic(char* program);
extern void InitBasic(void);
extern int  AssignBasic(void);
extern bool BasicIsReady(void);
extern void RunBasic(int BasicN);
extern void EditBasic(void);
extern bool EditBasicProgram(const char* name);
extern bool BasicRunAssignedForStep(int mk61_step);
extern bool BasicHasAssignedStep(int mk61_step);
#else
inline bool BASIC_library_select(void) { return false; }
inline bool BASIC_menu_select(void) { return false; }
inline bool CompileBasic(char*) { return false; }
inline void InitBasic(void) {}
inline int AssignBasic(void) { return -1; }
inline bool BasicIsReady(void) { return false; }
inline void RunBasic(int) {}
inline void EditBasic(void) {}
inline bool EditBasicProgram(const char*) { return false; }
inline bool BasicRunAssignedForStep(int) { return false; }
inline bool BasicHasAssignedStep(int) { return false; }
#endif

#endif
