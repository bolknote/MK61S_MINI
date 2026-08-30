#ifndef MK61_RESIDENT_FIRMWARE_HPP
#define MK61_RESIDENT_FIRMWARE_HPP

#include "resident_firmware_format.hpp"

namespace resident_firmware {

struct Result {
  resident_firmware_format::Status status;
  u32 image_size;
  u32 footer_offset;
  u32 expected_crc32;
  u32 actual_crc32;
  u32 cycles;
  bool hardware_crc;
};

struct Failure {
  resident_firmware_format::Status status;
  u32 build_id;
  u32 expected_crc32;
  u32 actual_crc32;
};

// Recomputes the canonical resident checksum directly from internal Flash.
// The expected_crc32 and content-derived build_id fields are treated as zero,
// exactly as by the post-link sealer.
Result verify(void);

// Returns the single image identity used by footer diagnostics, terminal
// handshake and crash dumps. Sealed releases use their content-derived CRC;
// an unsealed developer image uses a local compile fallback.
u32 build_id(void);

// Release builds call this before display/storage construction. A required
// image that is malformed or has a CRC mismatch records a tiny .noinit
// breadcrumb, requests a reset and enters ROM DFU through the existing
// preinit path. An unsealed generic Arduino developer build remains bootable.
void enforce_or_dfu(void);

bool last_failure(Failure& output);

} // namespace resident_firmware

#endif
