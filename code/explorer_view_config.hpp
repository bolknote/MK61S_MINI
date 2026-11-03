#ifndef MK61_EXPLORER_VIEW_CONFIG_HPP
#define MK61_EXPLORER_VIEW_CONFIG_HPP

// Character-only modules omit graphics; graphical residents and System APPs
// keep the native icon view. An explicit numeric override remains available.
#ifndef MK61_EXPLORER_GRAPHICS
  #if defined(MK61_BUILD_EXPLORER_MODULE)
    #define MK61_EXPLORER_GRAPHICS (!MK61_PORTABLE_TEXT_ONLY)
  #elif defined(MK61_DISPLAY_UC1609)
    #define MK61_EXPLORER_GRAPHICS 1
  #else
    #define MK61_EXPLORER_GRAPHICS 0
  #endif
#endif
#if MK61_EXPLORER_GRAPHICS != 0 && MK61_EXPLORER_GRAPHICS != 1
  #error "MK61_EXPLORER_GRAPHICS must be 0 or 1"
#endif
#endif
