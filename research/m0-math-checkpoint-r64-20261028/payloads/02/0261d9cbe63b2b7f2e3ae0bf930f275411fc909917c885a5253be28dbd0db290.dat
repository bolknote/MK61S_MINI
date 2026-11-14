#ifndef MK61_UI_BUILD_CONFIG_HPP
#define MK61_UI_BUILD_CONFIG_HPP

// Portable presentation sources need feature switches, not Arduino or a
// particular LCD bus. STM32 keeps the complete existing configuration.
#if defined(MK61_CORE_STANDALONE)
#define MK61_FIXED_CALCULATOR_FACE 1
#define MK61_PROPORTIONAL_UI_FONTS 1
#define MK61_HAS_COMPILED_GRAPHICS 1
#define MK61_SHARED_SCREEN_GRID 0
#define MK61_DISK_ACTIVITY_SUPPORTED 0
#else
#include "config.h"
#endif

#endif
