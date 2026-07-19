#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../code/spi_nor_sfdp.hpp"

static void put_le32(u8* data, u32 value) {
  data[0] = (u8) value;
  data[1] = (u8) (value >> 8);
  data[2] = (u8) (value >> 16);
  data[3] = (u8) (value >> 24);
}

static void make_bfpt(u8* table, u32 capacity, u32 methods,
                      u8 page_exponent = 8) {
  memset(table, 0, 64);
  put_le32(table + 4, capacity * 8U - 1U);
  table[28] = 12;
  table[29] = 0x20;
  put_le32(table + 40, (u32) page_exponent << 4);
  put_le32(table + 60, methods);
}

int main(void) {
  static constexpr u32 MINIMUM = 128U * 1024U;
  static constexpr u32 MAXIMUM = 128U * 1024U * 1024U;
  u8 table[64];
  spi_nor_sfdp::BasicParameters parsed;

  const u32 wren = (1UL << 25) | (1UL << 15);
  make_bfpt(table, 16U * 1024U * 1024U, wren, 7);
  assert(spi_nor_sfdp::parse_basic(table, 16, MINIMUM, MAXIMUM, parsed));
  assert(parsed.capacity_bytes == 16U * 1024U * 1024U);
  assert(parsed.page_size == 128);
  assert(parsed.erase_opcode == 0x20);
  assert(parsed.erase_type_4k == 0);
  assert(parsed.address_mode == spi_nor_sfdp::WREN_EN4B_EX4B);

  const u32 plain = (1UL << 24) | (1UL << 14);
  make_bfpt(table, 512U * 1024U, plain);
  assert(spi_nor_sfdp::parse_basic(table, 16, MINIMUM, MAXIMUM, parsed));
  assert(parsed.capacity_bytes == 512U * 1024U);
  assert(parsed.page_size == 256);
  assert(parsed.address_mode == spi_nor_sfdp::EN4B_EX4B);

  make_bfpt(table, 64U * 1024U * 1024U, 0);
  assert(spi_nor_sfdp::parse_basic(table, 16, MINIMUM, MAXIMUM, parsed));
  assert(parsed.address_mode == spi_nor_sfdp::UNSUPPORTED);

  u8 four_bait[8] = {};
  put_le32(four_bait, (1UL << 0) | (1UL << 6) | (1UL << 9));
  four_bait[4] = 0x21;
  u8 erase4 = 0;
  assert(spi_nor_sfdp::parse_4bait(four_bait, 0, erase4));
  assert(erase4 == 0x21);
  four_bait[0] &= (u8) ~(1U << 6);
  assert(!spi_nor_sfdp::parse_4bait(four_bait, 0, erase4));

  make_bfpt(table, 64U * 1024U, plain);
  assert(!spi_nor_sfdp::parse_basic(table, 16, MINIMUM, MAXIMUM, parsed));
  assert(!spi_nor_sfdp::parse_basic(NULL, 16, MINIMUM, MAXIMUM, parsed));

  printf("SPI NOR SFDP tests: OK\n");
  return 0;
}
