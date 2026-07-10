#ifndef MK61_MSC_SCSI_SAFETY_H
#define MK61_MSC_SCSI_SAFETY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MSC_SCSI_READ_CAPACITY16_RESPONSE_SIZE 32U

static inline uint32_t msc_scsi_min_u32(uint32_t lhs, uint32_t rhs)
{
  return lhs < rhs ? lhs : rhs;
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

#ifdef __cplusplus
}
#endif

#endif
