#include "device_identity.hpp"

#if defined(ARDUINO_ARCH_STM32)
  #include <Arduino.h>
#endif

namespace device_identity {
namespace {

static constexpr u64 PUBLIC_DOMAIN = 0x4D4B363150554231ULL; // "MK61PUB1"
static constexpr u64 VOLUME_DOMAIN = 0x4D4B3631564F4C31ULL; // "MK61VOL1"
static constexpr usize MAX_PROFILE_LENGTH = 31;

static u64 avalanche(u64 value) {
  value ^= value >> 30;
  value *= 0xBF58476D1CE4E5B9ULL;
  value ^= value >> 27;
  value *= 0x94D049BB133111EBULL;
  return value ^ (value >> 31);
}

static u64 domain_hash(const Uid96& uid, u64 domain) {
  if(!uid.available()) return 0;
  u64 state = avalanche(
      domain ^ ((u64) uid.word0 << 32) ^ uid.word1);
  state = avalanche(
      state ^ ((u64) uid.word2 << 32) ^ uid.word0 ^
      0xD6E8FEB86659FD93ULL);
  return state;
}

static char hex_digit(u8 value) {
  value &= 0x0FU;
  return value < 10 ? (char) ('0' + value)
                    : (char) ('A' + value - 10U);
}

static void format_hex(u64 value, u8 digits, char* out) {
  for(u8 index = 0; index < digits; index++) {
    const u8 shift = (u8) ((digits - 1U - index) * 4U);
    out[index] = hex_digit((u8) (value >> shift));
  }
  out[digits] = 0;
}

struct TextBuilder {
  char* output;
  usize capacity;
  usize length;
  bool valid;

  TextBuilder(char* destination, usize destination_capacity)
      : output(destination), capacity(destination_capacity), length(0),
        valid(destination != nullptr && destination_capacity != 0) {
    if(valid) output[0] = 0;
  }

  void character(char value) {
    if(!valid || length + 1 >= capacity) {
      valid = false;
      return;
    }
    output[length++] = value;
    output[length] = 0;
  }

  void text(const char* value) {
    if(value == nullptr) {
      valid = false;
      return;
    }
    while(*value != 0) character(*value++);
  }

  void hex(u64 value, u8 digits) {
    for(u8 index = 0; index < digits; index++) {
      const u8 shift = (u8) ((digits - 1U - index) * 4U);
      character(hex_digit((u8) (value >> shift)));
    }
  }
};

static bool valid_profile(const char* profile) {
  if(profile == nullptr || profile[0] == 0) return false;
  usize length = 0;
  while(profile[length] != 0) {
    const char value = profile[length];
    const bool allowed =
        (value >= 'a' && value <= 'z') ||
        (value >= 'A' && value <= 'Z') ||
        (value >= '0' && value <= '9') ||
        value == '-' || value == '_' || value == '.';
    if(!allowed || ++length > MAX_PROFILE_LENGTH) return false;
  }
  return true;
}

} // namespace

Uid96 read(void) {
#if defined(UID_BASE)
  const volatile u32* const uid =
      reinterpret_cast<const volatile u32*>(UID_BASE);
  return {uid[0], uid[1], uid[2]};
#else
  return {0, 0, 0};
#endif
}

u64 public_id(const Uid96& uid) {
  return domain_hash(uid, PUBLIC_DOMAIN);
}

u32 fat_volume_serial(const Uid96& uid, u32 fallback) {
  if(!uid.available()) return fallback;
  const u64 value = domain_hash(uid, VOLUME_DOMAIN);
  return (u32) value ^ (u32) (value >> 32);
}

bool format_public_id(const Uid96& uid,
                      char out[PUBLIC_ID_TEXT_SIZE]) {
  if(out == nullptr) return false;
  if(!uid.available()) {
    out[0] = 0;
    return false;
  }
  format_hex(public_id(uid), 16, out);
  return true;
}

bool format_short_id(const Uid96& uid,
                     char out[SHORT_ID_TEXT_SIZE]) {
  if(out == nullptr) return false;
  if(!uid.available()) {
    out[0] = 0;
    return false;
  }
  format_hex(public_id(uid), 8, out);
  return true;
}

bool format_fat_volume_serial(const Uid96& uid, u32 fallback,
                              char out[VOLUME_ID_TEXT_SIZE]) {
  if(out == nullptr) return false;
  format_hex(fat_volume_serial(uid, fallback), 8, out);
  return uid.available();
}

bool format_stm32duino_usb_serial(const Uid96& uid,
                                  char out[USB_SERIAL_TEXT_SIZE]) {
  if(out == nullptr) return false;
  const u32 first = uid.word0 + uid.word2;
  if(!uid.available()) {
    out[0] = 0;
    return false;
  }
  format_hex(first, 8, out);
  for(u8 index = 0; index < 4; index++) {
    out[8U + index] = hex_digit(
        (u8) (uid.word1 >> (28U - index * 4U)));
  }
  out[12] = 0;
  return true;
}

usize format_report(const Uid96& uid, u32 volume_fallback, u32 build_id,
                    const char* build_profile, char* out, usize capacity) {
  TextBuilder report(out, capacity);
  if(!valid_profile(build_profile)) return 0;

  report.text("MK61 ID v=1 public=");
  if(uid.available()) report.hex(public_id(uid), 16);
  else report.text("unsupported");
  report.text(" short=");
  if(uid.available()) report.hex(public_id(uid), 8);
  else report.text("unsupported");
  report.text(" usb=");
  char usb_serial[USB_SERIAL_TEXT_SIZE];
  if(format_stm32duino_usb_serial(uid, usb_serial)) report.text(usb_serial);
  else report.text("unsupported");
  report.text(" volume=");
  report.hex(fat_volume_serial(uid, volume_fallback), 8);
  report.text(" build=");
  report.hex(build_id, 8);
  report.text(" profile=");
  report.text(build_profile);

  return report.valid ? report.length : 0;
}

} // namespace device_identity
