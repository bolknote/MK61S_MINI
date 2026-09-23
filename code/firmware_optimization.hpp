#ifndef MK61_FIRMWARE_OPTIMIZATION_HPP
#define MK61_FIRMWARE_OPTIMIZATION_HPP

// Public F401 artifacts are intentionally lean: service-only profilers and
// verbose storage diagnostics belong in qualification images. Keep the flag
// here because the core header must choose the same product policy even when
// it is included before config.h.
#ifndef MK61_F401_PRODUCT_BUILD
  #define MK61_F401_PRODUCT_BUILD 0
#endif
#if MK61_F401_PRODUCT_BUILD != 0 && MK61_F401_PRODUCT_BUILD != 1
  #error "MK61_F401_PRODUCT_BUILD must be 0 or 1"
#endif

// Applying -O2/-O3 to the entire firmware makes GCC clone and unroll cold
// parsers, menus and diagnostic formatters.  Those copies cannot accelerate
// calculator execution and can overflow even the 512-KiB F411 Flash.  Keep
// cold firmware size-optimised for such experimental F411 builds; measured
// hot translation units restore the optimization selected by the toolchain.
// Canonical -Os builds are unchanged.
#ifndef MK61_MIXED_OPTIMIZATION
  #if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE) && \
      defined(__GNUC__) && !defined(__clang__) && \
      defined(__OPTIMIZE__) && !defined(__OPTIMIZE_SIZE__)
    #define MK61_MIXED_OPTIMIZATION 1
  #else
    #define MK61_MIXED_OPTIMIZATION 0
  #endif
#endif

#if MK61_MIXED_OPTIMIZATION != 0 && MK61_MIXED_OPTIMIZATION != 1
  #error "MK61_MIXED_OPTIMIZATION must be 0 or 1"
#endif

#ifndef MK61_REQUIRE_MIXED_OPTIMIZATION
  #define MK61_REQUIRE_MIXED_OPTIMIZATION 0
#endif
#if MK61_REQUIRE_MIXED_OPTIMIZATION != 0 && \
    MK61_REQUIRE_MIXED_OPTIMIZATION != 1
  #error "MK61_REQUIRE_MIXED_OPTIMIZATION must be 0 or 1"
#endif
#if MK61_REQUIRE_MIXED_OPTIMIZATION && !MK61_MIXED_OPTIMIZATION
  #error "this build requires the F411 mixed optimization policy"
#endif

#if MK61_MIXED_OPTIMIZATION
  #pragma GCC optimize ("Os")
#endif

// F401 has only 256 KiB of internal Flash.  A global -O3 build does not fit,
// while applying -O3 to the complete emulator translation unit leaves too
// little release reserve.  Its production profile therefore stays at
// -Os+LTO and promotes only explicitly marked execution-loop functions.
#ifndef MK61_F401_SELECTIVE_O3
  #if (defined(STM32F401xC) || defined(STM32F401xE)) && \
      defined(__GNUC__) && !defined(__clang__) && \
      defined(__OPTIMIZE__) && defined(__OPTIMIZE_SIZE__)
    #define MK61_F401_SELECTIVE_O3 1
  #else
    #define MK61_F401_SELECTIVE_O3 0
  #endif
#endif

#if MK61_F401_SELECTIVE_O3 != 0 && MK61_F401_SELECTIVE_O3 != 1
  #error "MK61_F401_SELECTIVE_O3 must be 0 or 1"
#endif

#ifndef MK61_REQUIRE_F401_SELECTIVE_O3
  #define MK61_REQUIRE_F401_SELECTIVE_O3 0
#endif
#if MK61_REQUIRE_F401_SELECTIVE_O3 != 0 && \
    MK61_REQUIRE_F401_SELECTIVE_O3 != 1
  #error "MK61_REQUIRE_F401_SELECTIVE_O3 must be 0 or 1"
#endif
#if MK61_REQUIRE_F401_SELECTIVE_O3 && !MK61_F401_SELECTIVE_O3
  #error "this build requires the F401 -Os plus selective -O3 policy"
#endif

// F411 release images have enough Flash to optimise the measured execution
// loops for speed while leaving the rest of the firmware at -Os. Global
// -O2/-O3 builds already restore their command-line optimisation for the whole
// emulator translation unit through MK61_MIXED_OPTIMIZATION.
#ifndef MK61_F411_SELECTIVE_O3
  #if defined(STM32F411xE) && defined(__GNUC__) && !defined(__clang__) && \
      defined(__OPTIMIZE__) && defined(__OPTIMIZE_SIZE__)
    #define MK61_F411_SELECTIVE_O3 1
  #else
    #define MK61_F411_SELECTIVE_O3 0
  #endif
#endif
#if MK61_F411_SELECTIVE_O3 != 0 && MK61_F411_SELECTIVE_O3 != 1
  #error "MK61_F411_SELECTIVE_O3 must be 0 or 1"
#endif

#ifndef MK61_REQUIRE_F411_SELECTIVE_O3
  #define MK61_REQUIRE_F411_SELECTIVE_O3 0
#endif
#if MK61_REQUIRE_F411_SELECTIVE_O3 != 0 && \
    MK61_REQUIRE_F411_SELECTIVE_O3 != 1
  #error "MK61_REQUIRE_F411_SELECTIVE_O3 must be 0 or 1"
#endif
#if MK61_REQUIRE_F411_SELECTIVE_O3 && !MK61_F411_SELECTIVE_O3
  #error "this build requires the F411 -Os plus selective -O3 policy"
#endif

#if MK61_F401_SELECTIVE_O3 || MK61_F411_SELECTIVE_O3
  #define MK61_CORE_HOT_O3 __attribute__((optimize("O3")))
#else
  #define MK61_CORE_HOT_O3
#endif

// Closed-form IK1306 paths are qualified on F411. Keep them in both the
// canonical -Os release and the mixed global -O2/-O3 compatibility build.
// F401 product images now have enough Flash for the same path; capability
// images retain the compact decoder because their worst case is nearly full.
#ifndef MK61_CORE_NATIVE_HOT_PATHS
  #if (defined(STM32F411xE) && \
       (defined(__OPTIMIZE_SIZE__) || MK61_MIXED_OPTIMIZATION)) || \
      ((defined(STM32F401xC) || defined(STM32F401xE)) && \
       defined(__OPTIMIZE_SIZE__) && MK61_F401_PRODUCT_BUILD)
    #define MK61_CORE_NATIVE_HOT_PATHS 1
  #else
    #define MK61_CORE_NATIVE_HOT_PATHS 0
  #endif
#endif
#if MK61_CORE_NATIVE_HOT_PATHS != 0 && MK61_CORE_NATIVE_HOT_PATHS != 1
  #error "MK61_CORE_NATIVE_HOT_PATHS must be 0 or 1"
#endif

// Partially evaluate the fixed ROM decoder at compile time. Qualify the
// larger dispatchers on F411; smaller targets keep the compact decoder.
// Host tests run both paths from the same state through the native switch.
#ifndef MK61_CORE_PREDECODED_ROM
  #if MK61_CORE_NATIVE_HOT_PATHS && \
      (defined(STM32F411xE) || !defined(ARDUINO))
    #define MK61_CORE_PREDECODED_ROM 1
  #else
    #define MK61_CORE_PREDECODED_ROM 0
  #endif
#endif
#if MK61_CORE_PREDECODED_ROM != 0 && MK61_CORE_PREDECODED_ROM != 1
  #error "MK61_CORE_PREDECODED_ROM must be 0 or 1"
#endif
#if MK61_CORE_PREDECODED_ROM && !MK61_CORE_NATIVE_HOT_PATHS
  #error "MK61_CORE_PREDECODED_ROM requires MK61_CORE_NATIVE_HOT_PATHS"
#endif

#endif
