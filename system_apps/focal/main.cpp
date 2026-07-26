// Standalone FOCAL System APP translation unit.
//
// The resident firmware owns Arduino/Core/library implementations.  This
// object contains only the FOCAL implementation and its module entry point;
// unresolved calls are bound to the exact resident ELF during the APP link.

#define MK61_BUILD_FOCAL_MODULE 1

#include "../../code/focal.cpp"
#include "../../code/focal_module_entry.cpp"
