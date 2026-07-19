#ifndef MK61_MSC_SCSI_SAFETY_H
#define MK61_MSC_SCSI_SAFETY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MSC_SCSI_READ_CAPACITY16_RESPONSE_SIZE 32U
#define MSC_BOT_MAX_LUN_VALUE 15U
#define MSC_SCSI_CACHING_PAGE 0x08U
#define MSC_SCSI_REMOVABLE_BLOCK_ACCESS_PAGE 0x1BU
#define MSC_SCSI_ALL_PAGES 0x3FU
#define MSC_SCSI_START_STOP_UNIT 0x1BU

#define MSC_SCSI_MODE_PAGE_NONE 0x00U
#define MSC_SCSI_MODE_PAGE_CACHING 0x01U
#define MSC_SCSI_MODE_PAGE_REMOVABLE 0x02U
#define MSC_SCSI_MODE_PAGE_INVALID 0xFFU

#define MSC_SCSI_CACHING_PAGE_LENGTH 20U
#define MSC_SCSI_REMOVABLE_PAGE_LENGTH 12U
#define MSC_SCSI_MODE_SENSE6_HEADER_LENGTH 4U
#define MSC_SCSI_MODE_SENSE10_HEADER_LENGTH 8U

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

static inline uint8_t msc_scsi_mode_page_mask(uint8_t page_code,
                                               uint8_t subpage_code)
{
  page_code &= 0x3FU;
  if (subpage_code != 0U &&
      !(page_code == MSC_SCSI_ALL_PAGES && subpage_code == 0xFFU))
  {
    return MSC_SCSI_MODE_PAGE_INVALID;
  }
  if (page_code == 0U)
  {
    return MSC_SCSI_MODE_PAGE_NONE;
  }
  if (page_code == MSC_SCSI_CACHING_PAGE)
  {
    return MSC_SCSI_MODE_PAGE_CACHING;
  }
  if (page_code == MSC_SCSI_REMOVABLE_BLOCK_ACCESS_PAGE)
  {
    return MSC_SCSI_MODE_PAGE_REMOVABLE;
  }
  if (page_code == MSC_SCSI_ALL_PAGES)
  {
    return MSC_SCSI_MODE_PAGE_CACHING | MSC_SCSI_MODE_PAGE_REMOVABLE;
  }
  return MSC_SCSI_MODE_PAGE_INVALID;
}

static inline uint16_t msc_scsi_mode_sense_length(uint8_t page_code,
                                                   uint8_t subpage_code,
                                                   uint16_t header_length,
                                                   uint16_t caching_page_length,
                                                   uint16_t removable_page_length)
{
  const uint8_t pages = msc_scsi_mode_page_mask(page_code, subpage_code);
  uint32_t length = header_length;
  if (pages == MSC_SCSI_MODE_PAGE_INVALID)
  {
    return 0U;
  }
  if ((pages & MSC_SCSI_MODE_PAGE_CACHING) != 0U)
  {
    length += caching_page_length;
  }
  if ((pages & MSC_SCSI_MODE_PAGE_REMOVABLE) != 0U)
  {
    length += removable_page_length;
  }
  return length <= 0xFFFFU ? (uint16_t)length : 0U;
}

static inline uint16_t msc_scsi_build_mode_sense(uint8_t *buffer,
                                                  uint16_t buffer_capacity,
                                                  uint8_t page_code,
                                                  uint8_t subpage_code,
                                                  uint8_t ten_byte_command,
                                                  uint8_t write_protected)
{
  const uint16_t header_length = ten_byte_command != 0U
      ? MSC_SCSI_MODE_SENSE10_HEADER_LENGTH
      : MSC_SCSI_MODE_SENSE6_HEADER_LENGTH;
  const uint8_t pages = msc_scsi_mode_page_mask(page_code, subpage_code);
  const uint16_t response_length = msc_scsi_mode_sense_length(
      page_code, subpage_code, header_length,
      MSC_SCSI_CACHING_PAGE_LENGTH, MSC_SCSI_REMOVABLE_PAGE_LENGTH);
  const uint8_t changeable_values = (uint8_t)((page_code & 0xC0U) == 0x40U);
  uint16_t offset;
  uint16_t index;

  if (buffer == 0 || response_length == 0U ||
      response_length > buffer_capacity ||
      pages == MSC_SCSI_MODE_PAGE_INVALID)
  {
    return 0U;
  }

  for (index = 0U; index < response_length; index++)
  {
    buffer[index] = 0U;
  }

  if (ten_byte_command != 0U)
  {
    buffer[0] = (uint8_t)((response_length - 2U) >> 8);
    buffer[1] = (uint8_t)(response_length - 2U);
    buffer[3] = write_protected != 0U ? 0x80U : 0U;
  }
  else
  {
    buffer[0] = (uint8_t)(response_length - 1U);
    buffer[2] = write_protected != 0U ? 0x80U : 0U;
  }

  offset = header_length;
  if ((pages & MSC_SCSI_MODE_PAGE_CACHING) != 0U)
  {
    buffer[offset] = MSC_SCSI_CACHING_PAGE;
    buffer[offset + 1U] = MSC_SCSI_CACHING_PAGE_LENGTH - 2U;
    /* WCE is enabled but read-only. A changeable-values response therefore
       reports zero even though current/default values report WCE=1. */
    buffer[offset + 2U] = changeable_values != 0U ? 0U : 0x04U;
    offset += MSC_SCSI_CACHING_PAGE_LENGTH;
  }
  if ((pages & MSC_SCSI_MODE_PAGE_REMOVABLE) != 0U)
  {
    buffer[offset] = MSC_SCSI_REMOVABLE_BLOCK_ACCESS_PAGE;
    buffer[offset + 1U] = MSC_SCSI_REMOVABLE_PAGE_LENGTH - 2U;
    /* SFLP=SRFP=NCD=SML=0. TLUN is a count, so current/default values report
       one LUN; no fields are MODE SELECT-changeable. */
    buffer[offset + 3U] = changeable_values != 0U ? 0U : 1U;
  }

  return response_length;
}

static inline uint8_t msc_scsi_is_eject(uint8_t opcode,
                                         uint8_t start_stop_flags)
{
  return (uint8_t)((opcode == MSC_SCSI_START_STOP_UNIT) &&
                   ((start_stop_flags & 0x03U) == 0x02U));
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
