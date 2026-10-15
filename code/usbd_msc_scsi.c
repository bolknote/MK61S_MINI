/**
  ******************************************************************************
  * @file    usbd_msc_scsi.c
  * @author  MCD Application Team
  * @brief   This file provides all the USBD SCSI layer functions.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2015 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */

/* Fixed 512-byte-sector virtual disk. USB-facing validation is kept at the
 * command boundary; private handlers share the one validated transport. */
#include "usbd_msc.h"
#include "usbd_msc_data.h"
#include "msc_scsi_safety.h"

extern uint8_t MK61_VirtualFatSync(void);
extern uint32_t MK61_VirtualFatWriteCacheBlocks(void);

static int8_t sense(USBD_MSC_BOT_HandleTypeDef *h, uint8_t key, uint8_t asc)
{
  h->scsi_sense[h->scsi_sense_tail].Skey = key;
  h->scsi_sense[h->scsi_sense_tail].ASC = asc;
  const uint8_t next = msc_scsi_ring_next(h->scsi_sense_tail, SENSE_LIST_DEEPTH);
  if (next == h->scsi_sense_head)
    h->scsi_sense_head = msc_scsi_ring_next(h->scsi_sense_head, SENSE_LIST_DEEPTH);
  h->scsi_sense_tail = next;
  return -1;
}
void SCSI_SenseCode(USBD_HandleTypeDef *pdev, uint8_t key, uint8_t asc)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h != NULL) (void)sense(h, key, asc);
}
static int8_t medium_ready(USBD_MSC_BOT_HandleTypeDef *h)
{
  return h->scsi_medium_state != SCSI_MEDIUM_EJECTED &&
         MK61_MSC_DiskReady() == 0 ? 0 : sense(h, NOT_READY, MEDIUM_NOT_PRESENT);
}
static int8_t range(USBD_MSC_BOT_HandleTypeDef *h)
{
  return msc_scsi_range_is_valid(MK61_MSC_DiskBlocks(), h->scsi_blk_addr,
      h->scsi_blk_len) ? 0 : sense(h, ILLEGAL_REQUEST, ADDRESS_OUT_OF_RANGE);
}
static void put_be32(uint8_t *p, uint32_t n)
{
  p[0] = n >> 24; p[1] = n >> 16; p[2] = n >> 8; p[3] = n;
}
static uint16_t be16(const uint8_t *p)
{
  return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

/* Immediate responses fit the existing packet. Allocation length belongs to
 * the CDB; the independent CBW length/direction still need BOT phase checks. */
static int8_t response(USBD_MSC_BOT_HandleTypeDef *h, const uint8_t *data,
                       uint16_t length, uint32_t allocation)
{
  uint32_t n = MIN(length, allocation);
  if (n != 0U && h->cbw.dDataLength != 0U && (h->cbw.bmFlags & 0x80U) == 0U) {
    h->csw.bStatus = USBD_CSW_PHASE_ERROR;
    return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
  }
  if (h->cbw.dDataLength < n) {
    h->csw.bStatus = USBD_CSW_PHASE_ERROR;
    n = h->cbw.dDataLength;
  }
  h->bot_data_length = (uint16_t)n;
  if (data != h->bot_data) (void)USBD_memcpy(h->bot_data, data, n);
  return 0;
}
static int8_t inquiry(USBD_MSC_BOT_HandleTypeDef *h, const uint8_t *cmd)
{
  const uint8_t *data = MK61_MSC_Inquiry;
  uint16_t n = STANDARD_INQUIRY_DATA_LEN;
  if ((cmd[1] & 1U) != 0U) {
    if (cmd[2] == 0U) { data = MSC_Page00_Inquiry_Data; n = LENGTH_INQUIRY_PAGE00; }
    else if (cmd[2] == 0x80U) { data = MSC_Page80_Inquiry_Data; n = LENGTH_INQUIRY_PAGE80; }
    else return sense(h, ILLEGAL_REQUEST, INVALID_FIELED_IN_COMMAND);
  } else if (cmd[2] != 0U) return sense(h, ILLEGAL_REQUEST, INVALID_FIELED_IN_COMMAND);
  return response(h, data, n, be16(cmd + 3));
}
static int8_t request_sense(USBD_MSC_BOT_HandleTypeDef *h, const uint8_t *cmd)
{
  (void)USBD_memset(h->bot_data, 0, REQUEST_SENSE_DATA_LEN);
  h->bot_data[0] = 0x70U;
  h->bot_data[7] = REQUEST_SENSE_DATA_LEN - 8U;
  if (h->scsi_sense_head != h->scsi_sense_tail) {
    const USBD_SCSI_SenseTypeDef *s = &h->scsi_sense[h->scsi_sense_head];
    h->bot_data[2] = s->Skey; h->bot_data[12] = s->ASC;
    h->scsi_sense_head = msc_scsi_ring_next(h->scsi_sense_head, SENSE_LIST_DEEPTH);
  }
  return response(h, h->bot_data, REQUEST_SENSE_DATA_LEN, cmd[4]);
}
static int8_t capacity(USBD_MSC_BOT_HandleTypeDef *h, const uint8_t *cmd)
{
  const uint32_t blocks = MK61_MSC_DiskBlocks();
  if (medium_ready(h) < 0) return -1;
  if (blocks == 0U) return sense(h, NOT_READY, MEDIUM_NOT_PRESENT);
  if (cmd[0] == SCSI_READ_CAPACITY16) {
    if ((cmd[1] & 0x1fU) != 0x10U) return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
    (void)USBD_memset(h->bot_data, 0, 32U);
    put_be32(h->bot_data + 4, blocks - 1U);
    put_be32(h->bot_data + 8, MK61_MSC_SECTOR_SIZE);
    return response(h, h->bot_data, 32U, msc_scsi_read_be32(cmd + 10));
  }
  if (cmd[0] == SCSI_READ_FORMAT_CAPACITIES) {
    (void)USBD_memset(h->bot_data, 0, 12U);
    h->bot_data[3] = 8U;
    put_be32(h->bot_data + 4, blocks); /* block count, unlike last-LBA in CAPACITY */
    h->bot_data[8] = 2U;
    h->bot_data[10] = 2U; /* 512 as a three-byte block length */
    return response(h, h->bot_data, 12U, be16(cmd + 7));
  }
  put_be32(h->bot_data, blocks - 1U);
  put_be32(h->bot_data + 4, MK61_MSC_SECTOR_SIZE);
  return response(h, h->bot_data, 8U, 8U);
}
static int8_t mode_sense(USBD_MSC_BOT_HandleTypeDef *h, const uint8_t *cmd)
{
  if ((cmd[2] & 0xc0U) == 0xc0U)
    return sense(h, ILLEGAL_REQUEST, SAVING_PARAMETERS_NOT_SUPPORTED);
  const uint8_t ten = cmd[0] == SCSI_MODE_SENSE10;
  const uint16_t n = msc_scsi_build_mode_sense(h->bot_data, sizeof(h->bot_data),
      cmd[2], cmd[3], ten, (uint8_t)(MK61_MSC_DiskWriteProtected() != 0));
  if (n == 0U) return sense(h, ILLEGAL_REQUEST, INVALID_FIELED_IN_COMMAND);
  return response(h, h->bot_data, n, ten ? be16(cmd + 7) : cmd[4]);
}
static int8_t sync_cache(USBD_MSC_BOT_HandleTypeDef *h)
{
  const uint8_t status = MK61_VirtualFatSync();
  if (status == 2U) {
    h->bot_state = USBD_BOT_DEFERRED;
    return USBD_MSC_STORAGE_BUSY;
  }
  return status == 0U ? 0 : sense(h, HARDWARE_ERROR, WRITE_FAULT);
}
static int8_t start_stop(USBD_MSC_BOT_HandleTypeDef *h, const uint8_t *cmd)
{
  const uint8_t action = cmd[4] & 3U;
  if (action == 2U && h->scsi_medium_state == SCSI_MEDIUM_LOCKED)
    return sense(h, ILLEGAL_REQUEST, INVALID_FIELED_IN_COMMAND);
  /* Latch before deferred sync, including its failure path: the foreground
   * must leave an ejected disk and make its diagnostic observable over CDC. */
  h->host_eject_latched = msc_scsi_update_eject_latch(h->host_eject_latched,
      SCSI_START_STOP_UNIT, cmd[4], 1U);
  if ((action & 1U) != 0U) h->scsi_medium_state = SCSI_MEDIUM_UNLOCKED;
  else {
    const int8_t status = sync_cache(h);
    if (status != 0) return status;
    if (action == 2U) h->scsi_medium_state = SCSI_MEDIUM_EJECTED;
  }
  return 0;
}
static uint32_t write_packet_bytes(const USBD_MSC_BOT_HandleTypeDef *h)
{
  const uint32_t blocks = MIN(h->scsi_blk_len,
      MIN(MK61_VirtualFatWriteCacheBlocks(), MSC_MEDIA_PACKET / MK61_MSC_SECTOR_SIZE));
  return MIN(blocks * MK61_MSC_SECTOR_SIZE, h->csw.dDataResidue);
}
static int8_t process_read(USBD_HandleTypeDef *pdev, USBD_MSC_BOT_HandleTypeDef *h)
{
  const uint32_t bytes = MIN(MIN(h->scsi_blk_len * MK61_MSC_SECTOR_SIZE,
                                MSC_MEDIA_PACKET), h->csw.dDataResidue);
  const uint16_t blocks = (uint16_t)((bytes + MK61_MSC_SECTOR_SIZE - 1U) / MK61_MSC_SECTOR_SIZE);
  const int8_t status = MK61_MSC_DiskRead(h->bot_data, h->scsi_blk_addr, blocks);
  if (status == USBD_MSC_STORAGE_BUSY) return status;
  if (status < 0) return sense(h, HARDWARE_ERROR, UNRECOVERED_READ_ERROR);
  h->scsi_blk_addr += blocks; h->scsi_blk_len -= blocks;
  h->csw.dDataResidue -= bytes;
  if (h->scsi_blk_len == 0U || h->csw.dDataResidue == 0U)
    h->bot_state = USBD_BOT_LAST_DATA_IN;
  (void)USBD_LL_Transmit(pdev, MSC_EPIN_ADDR, h->bot_data, bytes);
  return 0;
}
static int8_t process_write(USBD_HandleTypeDef *pdev, USBD_MSC_BOT_HandleTypeDef *h)
{
  const uint32_t bytes = write_packet_bytes(h);
  if (USBD_LL_GetRxDataSize(pdev, MSC_EPOUT_ADDR) != bytes) {
    h->csw.bStatus = USBD_CSW_PHASE_ERROR;
    return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
  }
  /* A short host transfer (BOT case 13) is received and discarded. Never
   * persist a partial sector or any stale tail of the previous USB packet. */
  if (h->csw.bStatus != USBD_CSW_PHASE_ERROR) {
    const int8_t status = MK61_MSC_DiskWrite(h->bot_data, h->scsi_blk_addr,
        (uint16_t)(bytes / MK61_MSC_SECTOR_SIZE));
    if (status == USBD_MSC_STORAGE_BUSY) return status;
    if (status < 0) return sense(h, HARDWARE_ERROR, WRITE_FAULT);
  }
  const uint32_t blocks = bytes / MK61_MSC_SECTOR_SIZE;
  h->scsi_blk_addr += blocks; h->scsi_blk_len -= blocks;
  h->csw.dDataResidue -= bytes;
  if (h->scsi_blk_len == 0U || h->csw.dDataResidue == 0U) {
    if (h->csw.dDataResidue != 0U) (void)USBD_LL_StallEP(pdev, MSC_EPOUT_ADDR);
    MSC_BOT_SendCSW(pdev, h->csw.bStatus);
  } else {
    (void)USBD_LL_PrepareReceive(pdev, MSC_EPOUT_ADDR, h->bot_data, write_packet_bytes(h));
  }
  return 0;
}
static int8_t read_write(USBD_HandleTypeDef *pdev, USBD_MSC_BOT_HandleTypeDef *h,
                         const uint8_t *cmd)
{
  const uint8_t write = cmd[0] == SCSI_WRITE10 || cmd[0] == SCSI_WRITE12;
  if (medium_ready(h) < 0) return -1;
  if (write && MK61_MSC_DiskWriteProtected() != 0)
    return sense(h, NOT_READY, WRITE_PROTECTED);
  h->scsi_blk_addr = msc_scsi_read_be32(cmd + 2);
  h->scsi_blk_len = cmd[0] == SCSI_READ12 || cmd[0] == SCSI_WRITE12
      ? msc_scsi_read_be32(cmd + 6) : be16(cmd + 7);
  if (range(h) < 0) return -1;
  if (h->scsi_blk_len > UINT32_MAX / MK61_MSC_SECTOR_SIZE)
    return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
  const uint32_t bytes = h->scsi_blk_len * MK61_MSC_SECTOR_SIZE;
  if (bytes == 0U) return 0;
  if (h->cbw.dDataLength == 0U ||
      (((h->cbw.bmFlags & 0x80U) == 0U) != (write != 0U))) {
    h->csw.bStatus = USBD_CSW_PHASE_ERROR;
    return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
  }
  if (h->cbw.dDataLength < bytes) h->csw.bStatus = USBD_CSW_PHASE_ERROR;
  if (!write) {
    h->bot_state = USBD_BOT_DATA_IN;
    return process_read(pdev, h);
  }
  const uint32_t packet = write_packet_bytes(h);
  if (packet == 0U) return sense(h, HARDWARE_ERROR, WRITE_FAULT);
  h->bot_state = USBD_BOT_DATA_OUT;
  (void)USBD_LL_PrepareReceive(pdev, MSC_EPOUT_ADDR, h->bot_data, packet);
  return 0;
}

int8_t SCSI_ProcessCmd(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL || h->bot_state != USBD_BOT_IDLE) return -1;
  const uint8_t *cmd = h->cbw.CB;
  /* Ignore bytes beyond bCBLength, including a stale/host-controlled tail.
   * Every implemented opcode belongs to a standard 6/10/12/16-byte group. */
  static const uint8_t cdb_lengths[8] = {6, 10, 10, 0, 16, 12, 0, 0};
  const uint8_t needed = cdb_lengths[cmd[0] >> 5];
  h->bot_data_length = 0U;
  if (needed == 0U || h->cbw.bCBLength < needed)
    return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
  switch (cmd[0]) {
    case SCSI_TEST_UNIT_READY: return medium_ready(h);
    case SCSI_INQUIRY: return inquiry(h, cmd);
    case SCSI_REQUEST_SENSE: return request_sense(h, cmd);
    case SCSI_READ_CAPACITY10:
    case SCSI_READ_CAPACITY16:
    case SCSI_READ_FORMAT_CAPACITIES: return capacity(h, cmd);
    case SCSI_MODE_SENSE6:
    case SCSI_MODE_SENSE10: return mode_sense(h, cmd);
    case SCSI_START_STOP_UNIT: return start_stop(h, cmd);
    case SCSI_ALLOW_MEDIUM_REMOVAL:
      h->scsi_medium_state = cmd[4] == 0U ? SCSI_MEDIUM_UNLOCKED : SCSI_MEDIUM_LOCKED;
      return 0;
    case SCSI_SYNCHRONIZE_CACHE10:
    case SCSI_SYNCHRONIZE_CACHE16: return sync_cache(h);
    case SCSI_READ10:
    case SCSI_READ12:
    case SCSI_WRITE10:
    case SCSI_WRITE12: return read_write(pdev, h, cmd);
    case SCSI_VERIFY10:
      if ((cmd[1] & 2U) != 0U) return sense(h, ILLEGAL_REQUEST, INVALID_FIELED_IN_COMMAND);
      h->scsi_blk_addr = msc_scsi_read_be32(cmd + 2);
      h->scsi_blk_len = be16(cmd + 7);
      return medium_ready(h) < 0 ? -1 : range(h);
    default: return sense(h, ILLEGAL_REQUEST, INVALID_CDB);
  }
}
int8_t SCSI_ContinueRead(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL || h->bot_state != USBD_BOT_DATA_IN) return -1;
  const int8_t status = process_read(pdev, h);
  if (status < 0) MSC_BOT_Fail(pdev);
  return status;
}
int8_t SCSI_ContinueWrite(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL || h->bot_state != USBD_BOT_DATA_OUT) return -1;
  const int8_t status = process_write(pdev, h);
  if (status < 0) MSC_BOT_Fail(pdev);
  return status;
}
int8_t SCSI_CompleteSync(USBD_HandleTypeDef *pdev, uint8_t success)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL || h->bot_state != USBD_BOT_DEFERRED) return -1;
  if (success == 0U) {
    (void)sense(h, HARDWARE_ERROR, WRITE_FAULT);
    MSC_BOT_Fail(pdev);
    return -1;
  }
  if (msc_scsi_is_eject(h->cbw.CB[0], h->cbw.CB[4])) h->scsi_medium_state = SCSI_MEDIUM_EJECTED;
  MSC_BOT_Complete(pdev);
  return 0;
}
