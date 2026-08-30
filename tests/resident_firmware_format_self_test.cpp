#include "../code/resident_firmware_format.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

using resident_firmware_format::Footer;
using resident_firmware_format::Status;

static Footer valid_footer(void) {
  Footer footer = {};
  memcpy(footer.magic, resident_firmware_format::MAGIC,
         sizeof(footer.magic));
  footer.version = resident_firmware_format::VERSION;
  footer.size = sizeof(Footer);
  footer.image_start = resident_firmware_format::IMAGE_START;
  footer.image_size = 200000;
  footer.expected_crc32 = 0x12345678UL;
  footer.build_id = footer.expected_crc32;
  footer.profile_id = 0x10203040UL;
  footer.flags = resident_firmware_format::FLAG_CRC_REQUIRED;
  return footer;
}

static Status validate(const Footer& footer, u32 image_size = 200000,
                       u32 footer_offset = 180000) {
  return resident_firmware_format::validate_metadata(
      footer, image_size, footer_offset, 0x10203040UL,
      512UL * 1024UL);
}

int main(void) {
  static_assert(resident_firmware_format::IMAGE_SIZE_OFFSET == 16, "");
  static_assert(resident_firmware_format::CRC32_OFFSET == 20, "");
  static_assert(resident_firmware_format::BUILD_ID_OFFSET == 24, "");

  Footer footer = valid_footer();
  assert(validate(footer) == Status::VALID);
  assert(resident_firmware_format::required(footer));
  assert(strcmp(resident_firmware_format::status_name(Status::VALID),
                "valid") == 0);

  footer = valid_footer();
  footer.image_size = 0;
  footer.expected_crc32 = 0;
  assert(validate(footer) == Status::UNSEALED);
  assert(resident_firmware_format::unsealed(footer));

  footer = valid_footer();
  footer.magic[3] ^= 1;
  assert(validate(footer) == Status::BAD_MAGIC);
  footer = valid_footer();
  footer.version++;
  assert(validate(footer) == Status::BAD_VERSION);
  footer = valid_footer();
  footer.size--;
  assert(validate(footer) == Status::BAD_SIZE);
  footer = valid_footer();
  footer.build_id++;
  assert(validate(footer) == Status::BAD_BUILD);
  footer = valid_footer();
  footer.profile_id++;
  assert(validate(footer) == Status::BAD_PROFILE);
  footer = valid_footer();
  footer.flags |= 0x80000000UL;
  assert(validate(footer) == Status::BAD_FLAGS);
  footer = valid_footer();
  footer.reserved = 1;
  assert(validate(footer) == Status::BAD_FLAGS);

  footer = valid_footer();
  assert(validate(footer, 199999) == Status::BAD_RANGE);
  assert(validate(footer, 200000, 199980) == Status::BAD_RANGE);
  assert(resident_firmware_format::validate_metadata(
             footer, 200000, 180000, 0x10203040UL,
             128UL * 1024UL) == Status::BAD_RANGE);

  puts("resident_firmware_format_self_test: ok");
  return 0;
}
