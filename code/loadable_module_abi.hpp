#ifndef MK61_LOADABLE_MODULE_ABI_HPP
#define MK61_LOADABLE_MODULE_ABI_HPP

#include "rust_types.h"

namespace loadable_module {

// Единственная C ABI-функция каждого образа. Пять 32-битных регистровых
// аргументов не требуют общей структуры данных и сохраняют границу модулей
// независимой от C++ name mangling.
using Entry = u32 (*)(u32 command, u32 argument0, u32 argument1,
                      u32 argument2, u32 argument3);

enum class Command : u32 {
  INITIALIZE = 0,
  APPLICATION_RUN = 1,

  FOCAL_LIBRARY_SELECT = 0x100,
  FOCAL_MENU_SELECT,
  FOCAL_COMPILE,
  FOCAL_IS_READY,
  FOCAL_RUN_INDEX,
  FOCAL_RUN_NAME,
  FOCAL_RUN_ID,
  FOCAL_EDIT,
  FOCAL_EDIT_NAME,
  FOCAL_EDIT_ID,

  TINYBASIC_LIBRARY_SELECT = 0x200,
  TINYBASIC_MENU_SELECT,
  TINYBASIC_COMPILE,
  TINYBASIC_IS_READY,
  TINYBASIC_RUN_INDEX,
  TINYBASIC_RUN_NAME,
  TINYBASIC_RUN_ID,
  TINYBASIC_EDIT,
  TINYBASIC_EDIT_NAME,
  TINYBASIC_EDIT_ID,

  WBMP_VIEW = 0x300,
  WBMP_VIEW_ENTRY
};

} // namespace loadable_module

#endif
