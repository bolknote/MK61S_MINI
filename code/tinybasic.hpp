#ifndef TINYBASIC_COMPILER
#define TINYBASIC_COMPILER

#include "rust_types.h"

#ifndef TINYBASIC_HOST_TEST
#include "config.h"
#endif

#ifndef MK61_ENABLE_TINYBASIC
  #define MK61_ENABLE_TINYBASIC 1
#endif

#if MK61_ENABLE_TINYBASIC
extern bool TinyBASIC_library_select(void);
extern bool TinyBASIC_menu_select(void);
extern bool CompileTinyBasic(char* program);
extern void InitTinyBasic(void);
extern bool TinyBasicIsReady(void);
extern void RunTinyBasic(int program_index);
extern bool RunTinyBasicProgram(const char* name);
extern bool RunTinyBasicProgram(u16 id);
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
inline void EditTinyBasic(void) {}
inline bool EditTinyBasicProgram(const char*) { return false; }
inline bool EditTinyBasicProgram(u16) { return false; }
#endif

#endif
