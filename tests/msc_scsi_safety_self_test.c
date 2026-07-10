#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "msc_scsi_safety.h"

static void test_capacity16_response_is_bounded(void)
{
  assert(msc_scsi_capacity16_response_length(0xFFFFFFFFU, 0xFFFFFFFFU, 512U) == 32U);
  assert(msc_scsi_capacity16_response_length(12U, 64U, 512U) == 12U);
  assert(msc_scsi_capacity16_response_length(32U, 8U, 512U) == 8U);
  assert(msc_scsi_capacity16_response_length(32U, 32U, 7U) == 7U);
}

static void test_address_range_rejects_wraparound(void)
{
  assert(msc_scsi_range_is_valid(800U, 0U, 800U));
  assert(msc_scsi_range_is_valid(800U, 800U, 0U));
  assert(!msc_scsi_range_is_valid(800U, 801U, 0U));
  assert(!msc_scsi_range_is_valid(800U, 799U, 2U));
  assert(!msc_scsi_range_is_valid(0xFFFFFFFFU, 0xFFFFFFF0U, 0x30U));
}

static void test_transfer_size_rejects_overflow(void)
{
  uint32_t bytes = 0U;
  assert(msc_scsi_transfer_bytes(3U, 512U, &bytes));
  assert(bytes == 1536U);
  assert(msc_scsi_transfer_bytes(0U, 512U, &bytes));
  assert(bytes == 0U);
  assert(!msc_scsi_transfer_bytes(0x01000000U, 512U, &bytes));
  assert(!msc_scsi_transfer_bytes(1U, 0U, &bytes));
}

static void test_big_endian_decode(void)
{
  const uint8_t bytes[4] = {0xDEU, 0xADU, 0xBEU, 0xEFU};
  assert(msc_scsi_read_be32(bytes) == 0xDEADBEEFU);
}

static uint32_t random_state = 0x61F4A7C3U;

static uint32_t next_random(void)
{
  random_state ^= random_state << 13;
  random_state ^= random_state >> 17;
  random_state ^= random_state << 5;
  return random_state;
}

static void test_arithmetic_matches_64_bit_reference(void)
{
  for(uint32_t i = 0; i < 100000U; i++) {
    const uint32_t total = next_random();
    const uint32_t first = next_random();
    const uint32_t count = next_random();
    const uint8_t expected_range =
        first <= total && (uint64_t)first + count <= total;
    assert(msc_scsi_range_is_valid(total, first, count) == expected_range);

    const uint32_t block_size = next_random();
    uint32_t bytes = 0U;
    const uint64_t wide = (uint64_t)count * block_size;
    const uint8_t expected_transfer = block_size != 0U && wide <= 0xFFFFFFFFULL;
    assert(msc_scsi_transfer_bytes(count, block_size, &bytes) == expected_transfer);
    if(expected_transfer) assert(bytes == (uint32_t)wide);
  }
}

int main(void)
{
  test_capacity16_response_is_bounded();
  test_address_range_rejects_wraparound();
  test_transfer_size_rejects_overflow();
  test_big_endian_decode();
  test_arithmetic_matches_64_bit_reference();
  puts("msc_scsi_safety_self_test: ok");
  return 0;
}
