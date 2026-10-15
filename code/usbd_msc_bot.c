/**
  ******************************************************************************
  * @file    usbd_msc_bot.c
  * @author  MCD Application Team
  * @brief   This file provides all the BOT protocol core functions.
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

/* One fixed Full Speed BOT interface. The wire contracts remain independent
 * of our disk geometry: malformed wrappers require reset recovery, and
 * host/device direction/length disagreements retain their BOT phase status. */
#include "usbd_msc.h"
#include "msc_scsi_safety.h"
#include <stddef.h>

_Static_assert(offsetof(USBD_MSC_BOT_CBWTypeDef, CB) == 15U,
               "CBW wire layout changed");
_Static_assert(offsetof(USBD_MSC_BOT_CSWTypeDef, bStatus) == 12U,
               "CSW wire layout changed");

static void receive_cbw(USBD_HandleTypeDef *pdev, USBD_MSC_BOT_HandleTypeDef *h)
{
  (void)USBD_LL_PrepareReceive(pdev, MSC_EPOUT_ADDR, (uint8_t *)&h->cbw, USBD_BOT_CBW_LENGTH);
}
static void stall_both(USBD_HandleTypeDef *pdev)
{
  (void)USBD_LL_StallEP(pdev, MSC_EPIN_ADDR);
  (void)USBD_LL_StallEP(pdev, MSC_EPOUT_ADDR);
}
uint8_t MSC_BOT_Init(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL || MK61_MSC_DiskInit() != USBD_MSC_STORAGE_OK) return USBD_FAIL;
  h->bot_state = USBD_BOT_IDLE;
  h->bot_status = USBD_BOT_STATUS_NORMAL;
  h->scsi_sense_head = h->scsi_sense_tail = 0U;
  h->scsi_medium_state = SCSI_MEDIUM_UNLOCKED;
  h->host_eject_latched = 0U;
  (void)USBD_LL_FlushEP(pdev, MSC_EPIN_ADDR);
  (void)USBD_LL_FlushEP(pdev, MSC_EPOUT_ADDR);
  return USBD_LL_PrepareReceive(pdev, MSC_EPOUT_ADDR, (uint8_t *)&h->cbw, USBD_BOT_CBW_LENGTH);
}
void MSC_BOT_Reset(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL) return;
  h->bot_state = USBD_BOT_IDLE;
  h->bot_status = USBD_BOT_STATUS_RECOVERY;
  /* Cancel deferred work before reusing its buffer. BOT reset preserves halt
   * and data-toggle state; the host must subsequently clear IN and OUT. */
  if (MK61_MSC_DiskInit() != USBD_MSC_STORAGE_OK) {
    h->bot_status = USBD_BOT_STATUS_ERROR;
    stall_both(pdev);
  }
  (void)USBD_LL_FlushEP(pdev, MSC_EPIN_ADDR);
  (void)USBD_LL_FlushEP(pdev, MSC_EPOUT_ADDR);
}
void MSC_BOT_DeInit(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h != NULL) {
    (void)MK61_MSC_DiskInit();
    h->bot_state = USBD_BOT_IDLE;
  }
}
void MSC_BOT_SendCSW(USBD_HandleTypeDef *pdev, uint8_t status)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL) return;
  h->csw.dSignature = USBD_BOT_CSW_SIGNATURE;
  h->csw.bStatus = status;
  h->bot_state = USBD_BOT_IDLE;
  if (status == USBD_CSW_PHASE_ERROR) h->bot_status = USBD_BOT_STATUS_ERROR;
  (void)USBD_LL_Transmit(pdev, MSC_EPIN_ADDR, (uint8_t *)&h->csw, USBD_BOT_CSW_LENGTH);
  /* A phase error requires reset recovery, not another command. */
  if (h->bot_status == USBD_BOT_STATUS_NORMAL) receive_cbw(pdev, h);
}
static void wait_clear(USBD_HandleTypeDef *pdev, USBD_MSC_BOT_HandleTypeDef *h)
{
  h->bot_state = USBD_BOT_WAIT_CLEAR;
  (void)USBD_LL_StallEP(pdev, MSC_EPIN_ADDR);
}
void MSC_BOT_Complete(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL) return;
  if (h->csw.dDataResidue != 0U) {
    if ((h->cbw.bmFlags & 0x80U) != 0U) { wait_clear(pdev, h); return; }
    (void)USBD_LL_StallEP(pdev, MSC_EPOUT_ADDR);
  }
  MSC_BOT_SendCSW(pdev, h->csw.bStatus);
}
void MSC_BOT_Fail(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL) return;
  if (h->csw.bStatus != USBD_CSW_PHASE_ERROR) h->csw.bStatus = USBD_CSW_CMD_FAILED;
  MSC_BOT_Complete(pdev);
}
static void decode_cbw(USBD_HandleTypeDef *pdev, USBD_MSC_BOT_HandleTypeDef *h)
{
  if (!msc_bot_cbw_is_valid(USBD_LL_GetRxDataSize(pdev, MSC_EPOUT_ADDR),
      USBD_BOT_CBW_LENGTH, h->cbw.dSignature, USBD_BOT_CBW_SIGNATURE,
      h->cbw.bmFlags, h->cbw.bLUN, 0U, h->cbw.bCBLength)) {
    SCSI_SenseCode(pdev, ILLEGAL_REQUEST, INVALID_CDB);
    h->bot_status = USBD_BOT_STATUS_ERROR;
    stall_both(pdev);
    return;
  }
  h->csw.dTag = h->cbw.dTag;
  h->csw.dDataResidue = h->cbw.dDataLength;
  h->csw.bStatus = USBD_CSW_CMD_PASSED;
  if (SCSI_ProcessCmd(pdev) < 0) { MSC_BOT_Fail(pdev); return; }
  if (h->bot_state != USBD_BOT_IDLE) return; /* streaming or foreground I/O */
  if (h->bot_data_length == 0U) { MSC_BOT_Complete(pdev); return; }
  h->csw.dDataResidue -= h->bot_data_length;
  h->bot_state = USBD_BOT_SEND_DATA;
  (void)USBD_LL_Transmit(pdev, MSC_EPIN_ADDR, h->bot_data, h->bot_data_length);
}
void MSC_BOT_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  (void)epnum;
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL) return;
  if (h->bot_status == USBD_BOT_STATUS_ERROR) { stall_both(pdev); return; }
  if (h->bot_status != USBD_BOT_STATUS_NORMAL) return;
  switch (h->bot_state) {
    case USBD_BOT_DATA_IN: (void)SCSI_ContinueRead(pdev); break;
    case USBD_BOT_SEND_DATA:
      /* Immediate replies are shorter than one FS packet. Their short packet
       * already terminates data IN, so the CSW can follow without a halt. */
      MSC_BOT_SendCSW(pdev, h->csw.bStatus); break;
    case USBD_BOT_LAST_DATA_IN: MSC_BOT_Complete(pdev); break;
    default: break;
  }
}
void MSC_BOT_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  (void)epnum;
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL || h->bot_status != USBD_BOT_STATUS_NORMAL) return;
  if (h->bot_state == USBD_BOT_IDLE) decode_cbw(pdev, h);
  else if (h->bot_state == USBD_BOT_DATA_OUT) (void)SCSI_ContinueWrite(pdev);
}
void MSC_BOT_CplClrFeature(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  USBD_MSC_BOT_HandleTypeDef *h = MK61_MSC_Handle(pdev);
  if (h == NULL) return;
  if (h->bot_status == USBD_BOT_STATUS_ERROR) { stall_both(pdev); return; }
  if (h->bot_status != USBD_BOT_STATUS_NORMAL) {
    h->bot_status &= (uint8_t)~(epnum == MSC_EPIN_ADDR ? 1U : 2U);
    if (h->bot_status == USBD_BOT_STATUS_NORMAL) receive_cbw(pdev, h);
  } else if (epnum == MSC_EPIN_ADDR && h->bot_state == USBD_BOT_WAIT_CLEAR) {
    MSC_BOT_SendCSW(pdev, h->csw.bStatus);
  }
}
