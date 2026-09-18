#ifndef TINYBASIC_COMPILER
#define TINYBASIC_COMPILER

#include "rust_types.h"

#ifndef TINYBASIC_HOST_TEST
#include "config.h"
#endif

#ifndef MK61_ENABLE_TINYBASIC
  #define MK61_ENABLE_TINYBASIC 1
#endif

// A TinyBASIC program can be launched interactively or as one synchronous
// step of an M61 scenario.  In the latter case ESC belongs to the outer
// scenario: the interpreter must return it as STOPPED without drawing its own
// message or waiting for another acknowledgement key.
enum class TinyBasicRunMode : u32 {
  INTERACTIVE = 0,
  M61_SCENARIO = 1
};

// Keep zero reserved for an unavailable/old loadable module.  This makes an
// unknown command in an older BASIC.APP fail closed instead of being mistaken
// for successful completion.
enum class TinyBasicRunStatus : u32 {
  UNAVAILABLE = 0,
  COMPLETED = 1,
  STOPPED = 2,
  COMPILE_ERROR = 3,
  RUNTIME_ERROR = 4,
  NOT_FOUND = 5
};

inline bool TinyBasicRunSucceeded(TinyBasicRunStatus status) {
  return status == TinyBasicRunStatus::COMPLETED;
}

#if MK61_ENABLE_TINYBASIC
extern bool TinyBASIC_library_select(void);
extern bool TinyBASIC_menu_select(void);
extern bool CompileTinyBasic(char* program);
extern void InitTinyBasic(void);
extern bool TinyBasicIsReady(void);
extern void RunTinyBasic(int program_index);
extern bool RunTinyBasicProgram(const char* name);
extern bool RunTinyBasicProgram(u16 id);
extern TinyBasicRunStatus RunTinyBasicProgramStatus(
    u16 id, TinyBasicRunMode mode);
extern void EditTinyBasic(void);
extern bool EditTinyBasicProgram(const char* name);
extern bool EditTinyBasicProgram(u16 id);
#else
inline bool TinyBASIC_library_select(void) { return false; }
inline bool TinyBASIC_menu_select(void) { return false; }
inline bool CompileTinyBasic(char*) { return false; }
inline void InitTinyBasic(void) {}
inline bool TinyBasicIsReady(void) { return false; }
inline void RunTinyBasic(int) {}
inline bool RunTinyBasicProgram(const char*) { return false; }
inline bool RunTinyBasicProgram(u16) { return false; }
inline TinyBasicRunStatus RunTinyBasicProgramStatus(u16, TinyBasicRunMode) {
  return TinyBasicRunStatus::UNAVAILABLE;
}
inline void EditTinyBasic(void) {}
inline bool EditTinyBasicProgram(const char*) { return false; }
inline bool EditTinyBasicProgram(u16) { return false; }
#endif

#endif
