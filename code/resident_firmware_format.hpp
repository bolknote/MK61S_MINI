#ifndef MK61_RESIDENT_FIRMWARE_FORMAT_HPP
#define MK61_RESIDENT_FIRMWARE_FORMAT_HPP

#include "rust_types.h"

#include <stddef.h>

namespace resident_firmware_format {

static constexpr u8 MAGIC[8] = {
  'M', 'K', '6', '1', 'F', 'W', 'C', 0
};
static constexpr u16 VERSION = 1;
static constexpr u32 IMAGE_START = 0x08000000UL;
static constexpr u32 FLAG_CRC_REQUIRED = 1UL << 0;
static constexpr u32 KNOWN_FLAGS = FLAG_CRC_REQUIRED;

struct alignas(4) Footer {
  u8 magic[8];
  u16 version;
  u16 size;
  u32 image_start;
  u32 image_size;
  u32 expected_crc32;
  u32 build_id;
  u32 profile_id;
  u32 flags;
  u32 reserved;
};

static_assert(sizeof(Footer) == 40,
              "resident firmware footer format must remain stable");
static_assert(offsetof(Footer, image_size) == 16,
              "post-link image-size offset changed");
static_assert(offsetof(Footer, expected_crc32) == 20,
              "post-link CRC offset changed");

static constexpr usize IMAGE_SIZE_OFFSET = offsetof(Footer, image_size);
static constexpr usize CRC32_OFFSET = offsetof(Footer, expected_crc32);
static constexpr usize BUILD_ID_OFFSET = offsetof(Footer, build_id);

enum class Status : u8 {
  VALID,
  UNSEALED,
  BAD_MAGIC,
  BAD_VERSION,
  BAD_SIZE,
  BAD_RANGE,
  BAD_BUILD,
  BAD_PROFILE,
  BAD_FLAGS,
  CRC_MISMATCH
};

inline bool magic_valid(const Footer& footer) {
  for(usize index = 0; index < sizeof(MAGIC); index++) {
    if(footer.magic[index] != MAGIC[index]) return false;
  }
  return true;
}

inline bool unsealed(const Footer& footer) {
  return footer.image_size == 0 && footer.expected_crc32 == 0;
}

inline bool required(const Footer& footer) {
  return (footer.flags & FLAG_CRC_REQUIRED) != 0;
}

inline const char* status_name(Status status) {
  switch(status) {
    case Status::VALID:        return "valid";
    case Status::UNSEALED:     return "unsealed";
    case Status::BAD_MAGIC:    return "bad-magic";
    case Status::BAD_VERSION:  return "bad-version";
    case Status::BAD_SIZE:     return "bad-size";
    case Status::BAD_RANGE:    return "bad-range";
    case Status::BAD_BUILD:    return "bad-build";
    case Status::BAD_PROFILE:  return "bad-profile";
    case Status::BAD_FLAGS:    return "bad-flags";
    case Status::CRC_MISMATCH: return "crc-mismatch";
  }
  return "unknown";
}

inline Status validate_metadata(const Footer& footer, u32 linked_image_size,
                                u32 footer_offset, u32 expected_profile_id,
                                u32 flash_capacity) {
  if(!magic_valid(footer)) return Status::BAD_MAGIC;
  if(footer.version != VERSION) return Status::BAD_VERSION;
  if(footer.size != sizeof(Footer)) return Status::BAD_SIZE;
  if((footer.flags & ~KNOWN_FLAGS) != 0 || footer.reserved != 0)
    return Status::BAD_FLAGS;
  if(footer.profile_id != expected_profile_id) return Status::BAD_PROFILE;
  if(unsealed(footer)) return Status::UNSEALED;
  // The sealer writes one content-derived value to both fields. The
  // canonical checksum treats both words as zero, avoiding a circular CRC.
  if(footer.build_id == 0 || footer.build_id != footer.expected_crc32)
    return Status::BAD_BUILD;
  if(footer.image_start != IMAGE_START || footer.image_size == 0 ||
     footer.image_size != linked_image_size ||
     footer.image_size > flash_capacity ||
     footer_offset > footer.image_size ||
     sizeof(Footer) > footer.image_size - footer_offset)
    return Status::BAD_RANGE;
  return Status::VALID;
}

} // namespace resident_firmware_format

#endif
