#ifndef MK61_EXPLORER_VIEW_CONFIG_HPP
#define MK61_EXPLORER_VIEW_CONFIG_HPP

// System EXPLORER.APP retains its text browser within the 8000-byte file /
// 10000-byte module RAM budgets. Graphical residents keep the native icon view.
// An explicit numeric override remains available for larger custom modules.
#ifndef MK61_EXPLORER_GRAPHICS
  #if defined(MK61_BUILD_EXPLORER_MODULE)
    #define MK61_EXPLORER_GRAPHICS 0
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
