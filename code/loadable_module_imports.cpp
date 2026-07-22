#include "config.h"

#if MK61_ANY_LOADABLE_MODULE

#include "display.hpp"
#include "language_workspace.hpp"
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
  #include "mk_math.hpp"
#endif
#include "program_store.hpp"

#include <string.h>
#if (MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE) && \
    MK61_MATH_BACKEND == MK61_MATH_BACKEND_LIBM
  #include <math.h>
#endif

namespace {

using Import = void (*)(void);

// Отдельная линковка может обратиться только к символам, уже оставшимся в
// resident ELF. Эти адреса удерживают общие части libc/libm и C5, которые
// нужны модулям, но основная прошивка сама могла бы удалить --gc-sections.
static const Import imports[] = {
  (Import) language_workspace::data,
  (Import) program_store::count,
  (Import) (bool (*)(program_store::ProgramType, int,
                     program_store::Entry&)) program_store::entry,
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
  #if MK61_MATH_BACKEND == MK61_MATH_BACKEND_LIBM
  (Import) (double (*)(double)) acos,
  (Import) (double (*)(double)) asin,
  (Import) (double (*)(double)) atan,
  (Import) (double (*)(double)) cos,
  (Import) (double (*)(double)) exp,
  (Import) (double (*)(double)) log,
  (Import) (double (*)(double)) log10,
  (Import) (double (*)(double, double)) pow,
  (Import) (double (*)(double)) sin,
  (Import) (double (*)(double)) sqrt,
  (Import) (double (*)(double)) tan,
  #else
  (Import) (double (*)(double)) mk_math::acos,
  (Import) (double (*)(double)) mk_math::asin,
  (Import) (double (*)(double)) mk_math::atan,
  (Import) (double (*)(double)) mk_math::cos,
  (Import) (double (*)(double)) mk_math::exp,
  (Import) (double (*)(double)) mk_math::ln,
  (Import) (double (*)(double)) mk_math::log10,
  (Import) (double (*)(double, double)) mk_math::pow,
  (Import) (double (*)(double)) mk_math::sin,
  (Import) (double (*)(double)) mk_math::sqrt,
  (Import) (double (*)(double)) mk_math::tan,
  #endif
  (Import) strncat
#endif
};

#if MK61_WBMP_VIEWER_IS_LOADABLE
using DisplayBegin = bool (MK61Display::*)(void);
using DisplayWrite = bool (MK61Display::*)(const u8 (*)[8], const u8*, usize);
using DisplayEnd = void (MK61Display::*)(void);
static const DisplayBegin display_begin_import =
    &MK61Display::beginCellAnimation;
static const DisplayWrite display_write_import =
    &MK61Display::writeCellAnimationPaletteFrame;
static const DisplayEnd display_end_import = &MK61Display::endCellAnimation;
#endif

} // namespace

extern "C" __attribute__((noinline, used))
void mk61_module_keep_imports(void) {
  __asm volatile("" : : "r" (imports) : "memory");
#if MK61_WBMP_VIEWER_IS_LOADABLE
  __asm volatile("" : : "r" (&display_begin_import),
                          "r" (&display_write_import),
                          "r" (&display_end_import) : "memory");
#endif
}

#endif
