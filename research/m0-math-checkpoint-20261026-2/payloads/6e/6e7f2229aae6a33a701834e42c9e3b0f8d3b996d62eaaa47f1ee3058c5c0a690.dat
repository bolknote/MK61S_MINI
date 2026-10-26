#ifndef MK61_USBDISK_BACKEND_HPP
#define MK61_USBDISK_BACKEND_HPP

#include "rust_types.h"

namespace usbdisk_backend {

// Resident half of USBDISK.APP. This function contains no FAT or text codec;
// it only dispatches bounded C6 storage primitives.
u32 call(u32 operation, u32 a, u32 b, u32 c, void* payload);

} // namespace usbdisk_backend

#endif
