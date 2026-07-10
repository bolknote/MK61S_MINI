#ifndef MK61_MSC_SCSI_SAFETY_H
#define MK61_MSC_SCSI_SAFETY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MSC_SCSI_READ_CAPACITY16_RESPONSE_SIZE 32U
#define MSC_BOT_MAX_LUN_VALUE 15U

static inline uint32_t msc_scsi_min_u32(uint32_t lhs, uint32_t rhs)
{
  return lhs < rhs ? lhs : rhs;
}

static inline uint8_t msc_bot_max_lun_is_valid(int32_t max_lun)
{
  return (uint8_t)(max_lun >= 0 && max_lun <= (int32_t)MSC_BOT_MAX_LUN_VALUE);
}

static inline uint8_t msc_bot_cbw_is_valid(uint32_t received_length,
                                            uint32_t expected_length,
                                            uint32_t signature,
                                            uint32_t expected_signature,
                                            uint8_t flags,
                                            uint8_t lun,
                                            uint8_t max_lun,
                                            uint8_t cdb_length)
{
  return (uint8_t)(received_length == expected_length &&
                   signature == expected_signature &&
                   (flags & 0x7FU) == 0U && lun <= max_lun &&
                   cdb_length >= 1U && cdb_length <= 16U);
}

static inline uint32_t msc_bot_transfer_length(uint32_t host_length,
                                                uint32_t payload_length)
{
  return msc_scsi_min_u32(host_length, payload_length);
}

static inline uint32_t msc_bot_residue_after_transfer(uint32_t residue,
                                                       uint32_t transferred)
{
  return transferred >= residue ? 0U : residue - transferred;
}

static inline uint32_t msc_scsi_read_be32(const uint8_t *value)
{
  return ((uint32_t)value[0] << 24) |
         ((uint32_t)value[1] << 16) |
         ((uint32_t)value[2] << 8) |
         (uint32_t)value[3];
}

static inline uint8_t msc_scsi_range_is_valid(uint32_t total_blocks,
                                               uint32_t first_block,
                                               uint32_t block_count)
{
  return (uint8_t)(first_block <= total_blocks &&
                   block_count <= (total_blocks - first_block));
}

static inline uint8_t msc_scsi_transfer_bytes(uint32_t block_count,
                                               uint32_t block_size,
                                               uint32_t *byte_count)
{
  if (byte_count == 0 || block_size == 0U ||
      (block_count != 0U && block_size > (0xFFFFFFFFU / block_count)))
  {
    return 0U;
  }

  *byte_count = block_count * block_size;
  return 1U;
}

static inline uint32_t msc_scsi_capacity16_response_length(uint32_t allocation_length,
                                                            uint32_t transport_length,
                                                            uint32_t buffer_capacity)
{
  uint32_t length = msc_scsi_min_u32(allocation_length,
                                     MSC_SCSI_READ_CAPACITY16_RESPONSE_SIZE);
  length = msc_scsi_min_u32(length, transport_length);
  return msc_scsi_min_u32(length, buffer_capacity);
}

static inline uint32_t msc_scsi_copy_length(uint32_t requested_length,
                                             uint32_t buffer_capacity)
{
  return msc_scsi_min_u32(requested_length, buffer_capacity);
}

static inline uint8_t msc_scsi_ring_next(uint8_t index, uint8_t depth)
{
  if (depth == 0U || index >= depth)
  {
    return 0U;
  }
  index++;
  return index == depth ? 0U : index;
}

#ifdef __cplusplus
}
#endif

#endif
