#include "resident_firmware.hpp"

#include "config.h"
#include "crc32.hpp"
#include "early_dfu.hpp"
#include "firmware_build.hpp"

#if defined(ARDUINO_ARCH_STM32)
  #include <stm32f4xx.h>
#endif

namespace resident_firmware {
namespace {

using resident_firmware_format::Footer;
using resident_firmware_format::Status;

static constexpr u32 FAILURE_MAGIC = 0x46574321UL; // "FWC!"
static constexpr u32 DEVELOPMENT_BUILD_ID = firmware_build::fnv1a_text(
    firmware_build::PROFILE, firmware_build::fnv1a_text(FIRMWARE_VER));

struct FailureRecord {
  u32 magic;
  u32 inverse_magic;
  u32 status;
  u32 build_id;
  u32 expected_crc32;
  u32 actual_crc32;
};

static_assert(sizeof(FailureRecord) == 24,
              "firmware CRC breadcrumb must remain compact");

extern "C" {

__attribute__((used, aligned(4), section(".mk61_fw_footer")))
volatile const Footer mk61_resident_firmware_footer = {
  {
    resident_firmware_format::MAGIC[0],
    resident_firmware_format::MAGIC[1],
    resident_firmware_format::MAGIC[2],
    resident_firmware_format::MAGIC[3],
    resident_firmware_format::MAGIC[4],
    resident_firmware_format::MAGIC[5],
    resident_firmware_format::MAGIC[6],
    resident_firmware_format::MAGIC[7]
  },
  resident_firmware_format::VERSION,
  sizeof(Footer),
  resident_firmware_format::IMAGE_START,
  0, // patched image size
  0, // patched canonical CRC32
  DEVELOPMENT_BUILD_ID,
  firmware_build::PROFILE_ID,
  MK61_REQUIRE_RESIDENT_CRC
      ? resident_firmware_format::FLAG_CRC_REQUIRED : 0,
  0
};

__attribute__((used, aligned(4), section(".noinit.mk61_firmware_failure")))
volatile FailureRecord mk61_resident_firmware_failure;

#if defined(ARDUINO_ARCH_STM32)
extern u8 _sidata;
extern u8 _sdata;
extern u8 _edata;
#endif

} // extern "C"

u32 flash_capacity(void) {
#if defined(STM32F401xC)
  return 256UL * 1024UL;
#elif defined(STM32F401xE) || defined(STM32F411xE)
  return 512UL * 1024UL;
#else
  return 0;
#endif
}

u32 linked_image_size(void) {
#if defined(ARDUINO_ARCH_STM32)
  const usize data_size = (usize) &_edata - (usize) &_sdata;
  const usize data_load_end = (usize) &_sidata + data_size;
  return data_load_end >= resident_firmware_format::IMAGE_START
      ? (u32) (data_load_end - resident_firmware_format::IMAGE_START) : 0;
#else
  return 0;
#endif
}

u32 footer_offset(void) {
  const usize address = (usize) &mk61_resident_firmware_footer;
  return address >= resident_firmware_format::IMAGE_START
      ? (u32) (address - resident_firmware_format::IMAGE_START)
      : 0xFFFFFFFFUL;
}

Footer read_footer(void) {
  // The post-link sealer patches this const object after the compiler has
  // emitted the image. Volatile byte loads are deliberate: without them LTO
  // may replace image_size/expected_crc32 with their initializer zeros.
  Footer snapshot = {};
  const volatile u8* source = reinterpret_cast<const volatile u8*>(
      &mk61_resident_firmware_footer);
  u8* destination = reinterpret_cast<u8*>(&snapshot);
  for(usize index = 0; index < sizeof(snapshot); index++)
    destination[index] = source[index];
  return snapshot;
}

void publish_failure(const Result& result) {
  mk61_resident_firmware_failure.magic = 0;
  __DMB();
  mk61_resident_firmware_failure.inverse_magic = ~FAILURE_MAGIC;
  mk61_resident_firmware_failure.status = (u32) result.status;
  mk61_resident_firmware_failure.build_id = build_id();
  mk61_resident_firmware_failure.expected_crc32 = result.expected_crc32;
  mk61_resident_firmware_failure.actual_crc32 = result.actual_crc32;
  __DMB();
  mk61_resident_firmware_failure.magic = FAILURE_MAGIC;
  __DSB();
}

} // namespace

Result verify(void) {
  const Footer footer = read_footer();
  Result result = {
    Status::BAD_RANGE, 0, 0xFFFFFFFFUL,
    footer.expected_crc32, 0, 0, false
  };
#if defined(ARDUINO_ARCH_STM32)
  result.image_size = linked_image_size();
  result.footer_offset = footer_offset();
  result.status = resident_firmware_format::validate_metadata(
      footer, result.image_size,
      result.footer_offset, firmware_build::PROFILE_ID, flash_capacity());
  if(result.status != Status::VALID) return result;

  const u32 started = DWT->CYCCNT;
  mk61_crc32::Context crc;
  result.hardware_crc = crc.using_hardware();
  const u8* const image = reinterpret_cast<const u8*>(
      resident_firmware_format::IMAGE_START);
  const u32 crc_offset = result.footer_offset +
      (u32) resident_firmware_format::CRC32_OFFSET;
  const u32 build_offset = result.footer_offset +
      (u32) resident_firmware_format::BUILD_ID_OFFSET;
  static constexpr u8 ZERO_CRC[sizeof(u32)] = {};
  const bool updated =
      crc.update(image, crc_offset) &&
      crc.update(ZERO_CRC, sizeof(ZERO_CRC)) &&
      crc.update(image + crc_offset + sizeof(u32),
                 build_offset - crc_offset - sizeof(u32)) &&
      crc.update(ZERO_CRC, sizeof(ZERO_CRC)) &&
      crc.update(image + build_offset + sizeof(u32),
                 result.image_size - build_offset - sizeof(u32));
  result.actual_crc32 = updated ? crc.finish() : 0;
  result.cycles = DWT->CYCCNT - started;
  if(!updated || result.actual_crc32 != result.expected_crc32)
    result.status = Status::CRC_MISMATCH;
#endif
  return result;
}

u32 build_id(void) {
  const u32 sealed = mk61_resident_firmware_footer.build_id;
  return sealed != 0 ? sealed : DEVELOPMENT_BUILD_ID;
}

void enforce_or_dfu(void) {
  const Result result = verify();
  if(result.status == Status::VALID) return;
  if(result.status == Status::UNSEALED &&
     MK61_REQUIRE_RESIDENT_CRC == 0) return;
  publish_failure(result);
  early_dfu::request();
}

bool last_failure(Failure& output) {
  const u32 magic = mk61_resident_firmware_failure.magic;
  const u32 inverse = mk61_resident_firmware_failure.inverse_magic;
  if(magic != FAILURE_MAGIC || inverse != ~FAILURE_MAGIC) return false;
  const u32 status = mk61_resident_firmware_failure.status;
  if(status > (u32) Status::CRC_MISMATCH) return false;
  output.status = (Status) status;
  output.build_id = mk61_resident_firmware_failure.build_id;
  output.expected_crc32 = mk61_resident_firmware_failure.expected_crc32;
  output.actual_crc32 = mk61_resident_firmware_failure.actual_crc32;
  return true;
}

} // namespace resident_firmware
