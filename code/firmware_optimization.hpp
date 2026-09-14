#ifndef MK61_FIRMWARE_OPTIMIZATION_HPP
#define MK61_FIRMWARE_OPTIMIZATION_HPP

// Applying -O2/-O3 to the entire firmware makes GCC clone and unroll cold
// parsers, menus and diagnostic formatters.  Those copies cannot accelerate
// calculator execution and can overflow even the 512-KiB F411 Flash.  Keep
// cold firmware size-optimised for such experimental builds; measured hot
// translation units restore the optimization selected by the toolchain.
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

#endif
