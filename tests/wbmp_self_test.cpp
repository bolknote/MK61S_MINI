#include "wbmp.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

static wbmp::Info inspect_ok(const u8* data, usize size) {
  wbmp::Info info = {};
  assert(wbmp::inspect(data, size, info) == wbmp::Status::OK);
  return info;
}

static void test_type0_and_polarity(void) {
  const u8 image[] = {0x00, 0x00, 0x08, 0x01, 0x7E};
  const wbmp::Info info = inspect_ok(image, sizeof(image));
  assert(info.width == 8);
  assert(info.height == 1);
  assert(info.pixel_offset == 4);
  assert(info.row_bytes == 1);
  assert(info.pixel_bytes == 1);

  u8 output = 0;
  assert(wbmp::decode_viewport(image, sizeof(image), info, 0, 0, 8, 1,
      wbmp::Layout::ROW_MAJOR_MSB, &output, sizeof(output)) ==
      wbmp::Status::OK);
  assert(output == 0x81); // WBMP 0 — чёрный; внутренний 1 — тёмный.
}

static void test_multibyte_dimensions(void) {
  u8 image[25] = {0x00, 0x00, 0x81, 0x20, 0x01}; // ширина 160
  memset(image + 5, 0xFF, 20);
  const wbmp::Info info = inspect_ok(image, sizeof(image));
  assert(info.width == 160);
  assert(info.height == 1);
  assert(info.pixel_offset == 5);
  assert(info.row_bytes == 20);
}

static void test_header_rejections(void) {
  wbmp::Info info = {};
  const u8 truncated[] = {0x00};
  assert(wbmp::inspect(truncated, sizeof(truncated), info) ==
         wbmp::Status::TRUNCATED);

  const u8 wrong_type[] = {0x01, 0x00, 0x08, 0x01, 0xFF};
  assert(wbmp::inspect(wrong_type, sizeof(wrong_type), info) ==
         wbmp::Status::UNSUPPORTED_TYPE);

  const u8 extended[] = {0x00, 0x80, 0x08, 0x01, 0xFF};
  assert(wbmp::inspect(extended, sizeof(extended), info) ==
         wbmp::Status::INVALID_HEADER);

  const u8 allowed_type_bits[] = {0x00, 0x60, 0x08, 0x01, 0xFF};
  assert(wbmp::inspect(allowed_type_bits, sizeof(allowed_type_bits), info) ==
         wbmp::Status::OK);

  const u8 reserved_bit[] = {0x00, 0x01, 0x08, 0x01, 0xFF};
  assert(wbmp::inspect(reserved_bit, sizeof(reserved_bit), info) ==
         wbmp::Status::INVALID_HEADER);

  const u8 redundant_width_group[] = {
    0x00, 0x00, 0x80, 0x08, 0x01, 0xFF
  };
  assert(wbmp::inspect(redundant_width_group,
                       sizeof(redundant_width_group), info) ==
         wbmp::Status::OK);

  const u8 zero_width[] = {0x00, 0x00, 0x00, 0x01};
  assert(wbmp::inspect(zero_width, sizeof(zero_width), info) ==
         wbmp::Status::INVALID_DIMENSIONS);

  const u8 overflow[] = {
    0x00, 0x00, 0x90, 0x80, 0x80, 0x80, 0x00, 0x01
  };
  assert(wbmp::inspect(overflow, sizeof(overflow), info) ==
         wbmp::Status::SIZE_OVERFLOW);
}

static void test_size_and_padding_validation(void) {
  wbmp::Info info = {};
  const u8 truncated[] = {0x00, 0x00, 0x08, 0x01};
  assert(wbmp::inspect(truncated, sizeof(truncated), info) ==
         wbmp::Status::INVALID_DATA_SIZE);
  const u8 trailing[] = {0x00, 0x00, 0x08, 0x01, 0xFF, 0x00};
  assert(wbmp::inspect(trailing, sizeof(trailing), info) ==
         wbmp::Status::INVALID_DATA_SIZE);

  const u8 valid_padding[] = {0x00, 0x00, 0x05, 0x01, 0xF8};
  assert(wbmp::inspect(valid_padding, sizeof(valid_padding), info) ==
         wbmp::Status::OK);
  const u8 invalid_padding[] = {0x00, 0x00, 0x05, 0x01, 0xFF};
  assert(wbmp::inspect(invalid_padding, sizeof(invalid_padding), info) ==
         wbmp::Status::INVALID_PADDING);
}

static void test_row_viewport_crop_and_white_border(void) {
  // 10x3: чёрная диагональ (0,0), (1,1), (2,2).
  const u8 image[] = {
    0x00, 0x00, 0x0A, 0x03,
    0x7F, 0xC0,
    0xBF, 0xC0,
    0xDF, 0xC0,
  };
  const wbmp::Info info = inspect_ok(image, sizeof(image));
  u8 output[4] = {};
  assert(wbmp::decode_viewport(image, sizeof(image), info, 1, 1, 12, 2,
      wbmp::Layout::ROW_MAJOR_MSB, output, sizeof(output)) ==
      wbmp::Status::OK);
  assert(output[0] == 0x80); // (1,1) становится (0,0)
  assert(output[1] == 0x00);
  assert(output[2] == 0x40); // (2,2) становится (1,1)
  assert(output[3] == 0x00);
}

static void test_uc1609_page_layout(void) {
  // 2x9, белая строка = 11000000. Тёмные: (0,0), (1,7), (0,8), (1,8).
  const u8 image[] = {
    0x00, 0x00, 0x02, 0x09,
    0x40, 0xC0, 0xC0, 0xC0, 0xC0, 0xC0, 0xC0, 0x80, 0x00,
  };
  const wbmp::Info info = inspect_ok(image, sizeof(image));
  u8 output[4] = {};
  assert(wbmp::decode_viewport(image, sizeof(image), info, 0, 0, 2, 9,
      wbmp::Layout::PAGE_MAJOR_LSB, output, sizeof(output)) ==
      wbmp::Status::OK);
  assert(output[0] == 0x01);
  assert(output[1] == 0x80);
  assert(output[2] == 0x01);
  assert(output[3] == 0x01);
}

static void test_decode_guards(void) {
  const u8 image[] = {0x00, 0x00, 0x08, 0x01, 0xFF};
  wbmp::Info info = inspect_ok(image, sizeof(image));
  u8 output = 0xAA;
  assert(wbmp::decode_viewport(image, sizeof(image), info, 0, 0, 8, 1,
      wbmp::Layout::ROW_MAJOR_MSB, &output, 0) ==
      wbmp::Status::OUTPUT_TOO_SMALL);
  info.pixel_offset++;
  assert(wbmp::decode_viewport(image, sizeof(image), info, 0, 0, 8, 1,
      wbmp::Layout::ROW_MAJOR_MSB, &output, sizeof(output)) ==
      wbmp::Status::INVALID_HEADER);
  assert(wbmp::viewport_bytes(80, 14, wbmp::Layout::ROW_MAJOR_MSB) == 140);
  assert(wbmp::viewport_bytes(192, 64, wbmp::Layout::PAGE_MAJOR_LSB) == 1536);
}

} // безымянное пространство имён

int main(void) {
  test_type0_and_polarity();
  test_multibyte_dimensions();
  test_header_rejections();
  test_size_and_padding_validation();
  test_row_viewport_crop_and_white_border();
  test_uc1609_page_layout();
  test_decode_guards();
  assert(strcmp(wbmp::status_text(wbmp::Status::OK), "ok") == 0);
  printf("wbmp_self_test: ok\n");
  return 0;
}
