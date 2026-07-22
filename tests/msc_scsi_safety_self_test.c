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

static void test_bot_contract(void)
{
  assert(msc_bot_max_lun_is_valid(0));
  assert(msc_bot_max_lun_is_valid(15));
  assert(!msc_bot_max_lun_is_valid(-1));
  assert(!msc_bot_max_lun_is_valid(16));

  assert(msc_bot_cbw_is_valid(31U, 31U, 0x43425355U, 0x43425355U,
                              0x80U, 0U, 0U, 10U));
  assert(!msc_bot_cbw_is_valid(30U, 31U, 0x43425355U, 0x43425355U,
                               0x80U, 0U, 0U, 10U));
  assert(!msc_bot_cbw_is_valid(31U, 31U, 0U, 0x43425355U,
                               0x80U, 0U, 0U, 10U));
  assert(!msc_bot_cbw_is_valid(31U, 31U, 0x43425355U, 0x43425355U,
                               0x81U, 0U, 0U, 10U));
  assert(!msc_bot_cbw_is_valid(31U, 31U, 0x43425355U, 0x43425355U,
                               0x80U, 1U, 0U, 10U));
  assert(!msc_bot_cbw_is_valid(31U, 31U, 0x43425355U, 0x43425355U,
                               0x80U, 0U, 0U, 0U));
  assert(!msc_bot_cbw_is_valid(31U, 31U, 0x43425355U, 0x43425355U,
                               0x80U, 0U, 0U, 17U));

  assert(msc_bot_transfer_length(8U, 32U) == 8U);
  assert(msc_bot_transfer_length(64U, 32U) == 32U);
  assert(msc_bot_residue_after_transfer(64U, 32U) == 32U);
  assert(msc_bot_residue_after_transfer(8U, 32U) == 0U);
  assert(msc_scsi_copy_length(1024U, 512U) == 512U);
  assert(msc_scsi_ring_next(0U, 4U) == 1U);
  assert(msc_scsi_ring_next(3U, 4U) == 0U);
  assert(msc_scsi_ring_next(4U, 4U) == 0U);
  assert(msc_scsi_ring_next(0U, 0U) == 0U);
}

static void test_mode_sense_page_selection(void)
{
  assert(msc_scsi_mode_page_mask(0x00U, 0x00U) == MSC_SCSI_MODE_PAGE_NONE);
  assert(msc_scsi_mode_page_mask(0x08U, 0x00U) == MSC_SCSI_MODE_PAGE_CACHING);
  assert(msc_scsi_mode_page_mask(0x1BU, 0x00U) == MSC_SCSI_MODE_PAGE_REMOVABLE);
  assert(msc_scsi_mode_page_mask(0x3FU, 0x00U) ==
         (MSC_SCSI_MODE_PAGE_CACHING | MSC_SCSI_MODE_PAGE_REMOVABLE));
  assert(msc_scsi_mode_page_mask(0x3FU, 0xFFU) ==
         (MSC_SCSI_MODE_PAGE_CACHING | MSC_SCSI_MODE_PAGE_REMOVABLE));
  assert(msc_scsi_mode_page_mask(0x09U, 0x00U) == MSC_SCSI_MODE_PAGE_INVALID);
  assert(msc_scsi_mode_page_mask(0x08U, 0x01U) == MSC_SCSI_MODE_PAGE_INVALID);

  assert(msc_scsi_mode_sense_length(0x00U, 0x00U, 4U, 20U, 12U) == 4U);
  assert(msc_scsi_mode_sense_length(0x08U, 0x00U, 4U, 20U, 12U) == 24U);
  assert(msc_scsi_mode_sense_length(0x1BU, 0x00U, 4U, 20U, 12U) == 16U);
  assert(msc_scsi_mode_sense_length(0x3FU, 0x00U, 8U, 20U, 12U) == 40U);
  assert(msc_scsi_mode_sense_length(0x3FU, 0xFFU, 8U, 20U, 12U) == 40U);
  assert(msc_scsi_mode_sense_length(0x09U, 0x00U, 4U, 20U, 12U) == 0U);
  assert(msc_scsi_mode_sense_length(0x08U, 0x01U, 4U, 20U, 12U) == 0U);
  assert(msc_scsi_mode_sense_length(0x3FU, 0x00U, 0xFFF0U,
                                    20U, 12U) == 0U);
}

static void test_mode_sense_response_encoding(void)
{
  uint8_t data[40];
  uint16_t length;

  length = msc_scsi_build_mode_sense(data, sizeof(data),
                                      0x1BU, 0x00U, 0U, 0U);
  assert(length == 16U);
  assert(data[0] == 15U);
  assert(data[1] == 0U && data[2] == 0U && data[3] == 0U);
  assert(data[4] == 0x1BU && data[5] == 0x0AU);
  assert(data[6] == 0U && data[7] == 1U);
  for(uint16_t i = 8U; i < length; i++) assert(data[i] == 0U);

  length = msc_scsi_build_mode_sense(data, sizeof(data),
                                      0x3FU, 0x00U, 1U, 1U);
  assert(length == 40U);
  assert(data[0] == 0U && data[1] == 38U);
  assert(data[2] == 0U && data[3] == 0x80U);
  assert(data[8] == 0x08U && data[9] == 0x12U && data[10] == 0x04U);
  assert(data[28] == 0x1BU && data[29] == 0x0AU);
  assert(data[30] == 0U && data[31] == 1U);

  length = msc_scsi_build_mode_sense(data, sizeof(data),
                                      0x7FU, 0x00U, 1U, 0U);
  assert(length == 40U);
  assert(data[10] == 0U); /* WCE нельзя изменить через MODE SELECT. */
  assert(data[31] == 0U); /* TLUN также нельзя изменить. */

  data[0] = 0xA5U;
  assert(msc_scsi_build_mode_sense(data, 15U,
                                   0x1BU, 0x00U, 0U, 0U) == 0U);
  assert(data[0] == 0xA5U);
  assert(msc_scsi_build_mode_sense(data, sizeof(data),
                                   0x09U, 0x00U, 0U, 0U) == 0U);
}

static void test_explicit_eject_detection(void)
{
  assert(msc_scsi_is_eject(0x1BU, 0x02U) != 0U);
  assert(msc_scsi_is_eject(0x1BU, 0x12U) != 0U);
  assert(msc_scsi_is_eject(0x1BU, 0x00U) == 0U);
  assert(msc_scsi_is_eject(0x1BU, 0x01U) == 0U);
  assert(msc_scsi_is_eject(0x1BU, 0x03U) == 0U);
  assert(msc_scsi_is_eject(0x35U, 0x02U) == 0U);
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
  test_bot_contract();
  test_mode_sense_page_selection();
  test_mode_sense_response_encoding();
  test_explicit_eject_detection();
  test_arithmetic_matches_64_bit_reference();
  puts("msc_scsi_safety_self_test: ok");
  return 0;
}
