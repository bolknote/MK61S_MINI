#pragma once
// Arduino resolves this board-private shim instead of the generic USBDevice
// library. Public headers still come from the pinned STM32 core; build_opt.h
// supplies the common owned ABI before them. Implementations live in code/.
#if !defined(MK61_ARDUINO_OWNED_USB) || !MK61_ARDUINO_OWNED_USB
#error "MK61s USBDevice requires the matching board package and firmware"
#endif
