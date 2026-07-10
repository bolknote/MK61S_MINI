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

/* BSPDependencies
- "stm32xxxxx_{eval}{discovery}{nucleo_144}.c"
- "stm32xxxxx_{eval}{discovery}_io.c"
- "stm32xxxxx_{eval}{discovery}{adafruit}_sd.c"
EndBSPDependencies */

/* Includes ------------------------------------------------------------------*/
#include "usbd_msc_bot.h"
#include "usbd_msc.h"
#include "usbd_msc_scsi.h"
#include "usbd_ioreq.h"
#include "msc_scsi_safety.h"

/** @addtogroup STM32_USB_DEVICE_LIBRARY
  * @{
  */


/** @defgroup MSC_BOT
  * @brief BOT protocol module
  * @{
  */

/** @defgroup MSC_BOT_Private_TypesDefinitions
  * @{
  */
/**
  * @}
  */


/** @defgroup MSC_BOT_Private_Defines
  * @{
  */

/**
  * @}
  */


/** @defgroup MSC_BOT_Private_Macros
  * @{
  */
/**
  * @}
  */


/** @defgroup MSC_BOT_Private_Variables
  * @{
  */
extern uint8_t MSCInEpAdd;
extern uint8_t MSCOutEpAdd;
/**
  * @}
  */


/** @defgroup MSC_BOT_Private_FunctionPrototypes
  * @{
  */
static void MSC_BOT_SendData(USBD_HandleTypeDef *pdev, uint8_t *pbuf, uint32_t len);
static void MSC_BOT_CBW_Decode(USBD_HandleTypeDef *pdev);
static void MSC_BOT_Abort(USBD_HandleTypeDef *pdev);

static USBD_MSC_BOT_HandleTypeDef *MSC_BOT_GetHandle(USBD_HandleTypeDef *pdev)
{
  if ((pdev == NULL) || (pdev->classId >= USBD_MAX_SUPPORTED_CLASS))
  {
    return NULL;
  }
  return (USBD_MSC_BOT_HandleTypeDef *)pdev->pClassDataCmsit[pdev->classId];
}

static USBD_StorageTypeDef *MSC_BOT_GetStorage(USBD_HandleTypeDef *pdev)
{
  if ((pdev == NULL) || (pdev->classId >= USBD_MAX_SUPPORTED_CLASS))
  {
    return NULL;
  }
  return (USBD_StorageTypeDef *)pdev->pUserData[pdev->classId];
}
/**
  * @}
  */


/** @defgroup MSC_BOT_Private_Functions
  * @{
  */


/**
  * @brief  MSC_BOT_Init
  *         Initialize the BOT Process
  * @param  pdev: device instance
  * @retval None
  */
uint8_t MSC_BOT_Init(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);
  USBD_StorageTypeDef *storage = MSC_BOT_GetStorage(pdev);

  if ((hmsc == NULL) || (storage == NULL) || (storage->Init == NULL))
  {
    return (uint8_t)USBD_FAIL;
  }

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  hmsc->bot_state = USBD_BOT_IDLE;
  hmsc->bot_status = USBD_BOT_STATUS_NORMAL;

  hmsc->scsi_sense_tail = 0U;
  hmsc->scsi_sense_head = 0U;
  hmsc->scsi_medium_state = SCSI_MEDIUM_UNLOCKED;

  if (storage->Init(0U) != USBD_MSC_STORAGE_OK)
  {
    hmsc->bot_status = USBD_BOT_STATUS_ERROR;
    return (uint8_t)USBD_FAIL;
  }

  (void)USBD_LL_FlushEP(pdev, MSCOutEpAdd);
  (void)USBD_LL_FlushEP(pdev, MSCInEpAdd);

  /* Prepare EP to Receive First BOT Cmd */
  return (uint8_t)USBD_LL_PrepareReceive(pdev, MSCOutEpAdd, (uint8_t *)&hmsc->cbw,
                                         USBD_BOT_CBW_LENGTH);
}

/**
  * @brief  MSC_BOT_Reset
  *         Reset the BOT Machine
  * @param  pdev: device instance
  * @retval  None
  */
void MSC_BOT_Reset(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);
  USBD_StorageTypeDef *storage = MSC_BOT_GetStorage(pdev);

  if ((hmsc == NULL) || (storage == NULL) || (storage->Init == NULL))
  {
    return;
  }

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  hmsc->bot_state  = USBD_BOT_IDLE;
  hmsc->bot_status = USBD_BOT_STATUS_RECOVERY;

  /* Cancel any deferred storage callback owned by the aborted BOT command. */
  if (storage->Init(0U) != USBD_MSC_STORAGE_OK)
  {
    hmsc->bot_status = USBD_BOT_STATUS_ERROR;
    MSC_BOT_Abort(pdev);
    return;
  }

  (void)USBD_LL_ClearStallEP(pdev, MSCInEpAdd);
  (void)USBD_LL_ClearStallEP(pdev, MSCOutEpAdd);

  /* Prepare EP to Receive First BOT Cmd */
  (void)USBD_LL_PrepareReceive(pdev, MSCOutEpAdd, (uint8_t *)&hmsc->cbw,
                               USBD_BOT_CBW_LENGTH);
}

/**
  * @brief  MSC_BOT_DeInit
  *         DeInitialize the BOT Machine
  * @param  pdev: device instance
  * @retval None
  */
void MSC_BOT_DeInit(USBD_HandleTypeDef  *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

  if (hmsc != NULL)
  {
    hmsc->bot_state = USBD_BOT_IDLE;
  }
}

/**
  * @brief  MSC_BOT_DataIn
  *         Handle BOT IN data stage
  * @param  pdev: device instance
  * @param  epnum: endpoint index
  * @retval None
  */
void MSC_BOT_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  UNUSED(epnum);

  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

  if (hmsc == NULL)
  {
    return;
  }

  switch (hmsc->bot_state)
  {
    case USBD_BOT_DATA_IN:
      if (SCSI_ProcessCmd(pdev, hmsc->cbw.bLUN, &hmsc->cbw.CB[0]) < 0)
      {
        MSC_BOT_SendCSW(pdev, USBD_CSW_CMD_FAILED);
      }
      break;

    case USBD_BOT_SEND_DATA:
    case USBD_BOT_LAST_DATA_IN:
      MSC_BOT_SendCSW(pdev, USBD_CSW_CMD_PASSED);
      break;

    default:
      break;
  }
}
/**
  * @brief  MSC_BOT_DataOut
  *         Process MSC OUT data
  * @param  pdev: device instance
  * @param  epnum: endpoint index
  * @retval None
  */
void MSC_BOT_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  UNUSED(epnum);

  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

  if (hmsc == NULL)
  {
    return;
  }

  switch (hmsc->bot_state)
  {
    case USBD_BOT_IDLE:
      MSC_BOT_CBW_Decode(pdev);
      break;

    case USBD_BOT_DATA_OUT:
      if (SCSI_ProcessCmd(pdev, hmsc->cbw.bLUN, &hmsc->cbw.CB[0]) < 0)
      {
        MSC_BOT_SendCSW(pdev, USBD_CSW_CMD_FAILED);
      }
      break;

    default:
      break;
  }
}

/**
  * @brief  MSC_BOT_CBW_Decode
  *         Decode the CBW command and set the BOT state machine accordingly
  * @param  pdev: device instance
  * @retval None
  */
static void  MSC_BOT_CBW_Decode(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if (hmsc == NULL)
  {
    return;
  }

  hmsc->csw.dTag = hmsc->cbw.dTag;
  hmsc->csw.dDataResidue = hmsc->cbw.dDataLength;

  if (!msc_bot_cbw_is_valid(USBD_LL_GetRxDataSize(pdev, MSCOutEpAdd),
                            USBD_BOT_CBW_LENGTH, hmsc->cbw.dSignature,
                            USBD_BOT_CBW_SIGNATURE, hmsc->cbw.bmFlags,
                            hmsc->cbw.bLUN, (uint8_t)hmsc->max_lun,
                            hmsc->cbw.bCBLength))
  {
    SCSI_SenseCode(pdev, hmsc->cbw.bLUN, ILLEGAL_REQUEST, INVALID_CDB);

    hmsc->bot_status = USBD_BOT_STATUS_ERROR;
    MSC_BOT_Abort(pdev);
  }
  else
  {
    if (SCSI_ProcessCmd(pdev, hmsc->cbw.bLUN, &hmsc->cbw.CB[0]) < 0)
    {
      if (hmsc->bot_state == USBD_BOT_NO_DATA)
      {
        MSC_BOT_SendCSW(pdev, USBD_CSW_CMD_FAILED);
      }
      else
      {
        MSC_BOT_Abort(pdev);
      }
    }
    /* Burst xfer handled internally */
    else if ((hmsc->bot_state != USBD_BOT_DATA_IN) &&
             (hmsc->bot_state != USBD_BOT_DATA_OUT) &&
             (hmsc->bot_state != USBD_BOT_LAST_DATA_IN) &&
             (hmsc->bot_state != USBD_BOT_DEFERRED))
    {
      if (hmsc->bot_data_length > 0U)
      {
        MSC_BOT_SendData(pdev, hmsc->bot_data, hmsc->bot_data_length);
      }
      else if (hmsc->bot_data_length == 0U)
      {
        MSC_BOT_SendCSW(pdev, USBD_CSW_CMD_PASSED);
      }
      else
      {
        MSC_BOT_Abort(pdev);
      }
    }
    else
    {
      return;
    }
  }
}

/**
  * @brief  MSC_BOT_SendData
  *         Send the requested data
  * @param  pdev: device instance
  * @param  buf: pointer to data buffer
  * @param  len: Data Length
  * @retval None
  */
static void  MSC_BOT_SendData(USBD_HandleTypeDef *pdev, uint8_t *pbuf, uint32_t len)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

  uint32_t length;

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if ((hmsc == NULL) || ((pbuf == NULL) && (len != 0U)))
  {
    return;
  }

  length = msc_bot_transfer_length(hmsc->cbw.dDataLength, len);

  hmsc->csw.dDataResidue = msc_bot_residue_after_transfer(hmsc->csw.dDataResidue,
                                                          length);
  hmsc->csw.bStatus = USBD_CSW_CMD_PASSED;
  hmsc->bot_state = USBD_BOT_SEND_DATA;

  (void)USBD_LL_Transmit(pdev, MSCInEpAdd, pbuf, length);
}

/**
  * @brief  MSC_BOT_SendCSW
  *         Send the Command Status Wrapper
  * @param  pdev: device instance
  * @param  status : CSW status
  * @retval None
  */
void  MSC_BOT_SendCSW(USBD_HandleTypeDef *pdev, uint8_t CSW_Status)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if (hmsc == NULL)
  {
    return;
  }

  hmsc->csw.dSignature = USBD_BOT_CSW_SIGNATURE;
  hmsc->csw.bStatus = CSW_Status;
  hmsc->bot_state = USBD_BOT_IDLE;

  (void)USBD_LL_Transmit(pdev, MSCInEpAdd, (uint8_t *)&hmsc->csw,
                         USBD_BOT_CSW_LENGTH);

  /* Prepare EP to Receive next Cmd */
  (void)USBD_LL_PrepareReceive(pdev, MSCOutEpAdd, (uint8_t *)&hmsc->cbw,
                               USBD_BOT_CBW_LENGTH);
}

/**
  * @brief  MSC_BOT_Abort
  *         Abort the current transfer
  * @param  pdev: device instance
  * @retval status
  */

static void  MSC_BOT_Abort(USBD_HandleTypeDef *pdev)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if (hmsc == NULL)
  {
    return;
  }

  if ((hmsc->cbw.bmFlags == 0U) &&
      (hmsc->cbw.dDataLength != 0U) &&
      (hmsc->bot_status == USBD_BOT_STATUS_NORMAL))
  {
    (void)USBD_LL_StallEP(pdev, MSCOutEpAdd);
  }

  (void)USBD_LL_StallEP(pdev, MSCInEpAdd);

  if (hmsc->bot_status == USBD_BOT_STATUS_ERROR)
  {
    (void)USBD_LL_StallEP(pdev, MSCInEpAdd);
    (void)USBD_LL_StallEP(pdev, MSCOutEpAdd);
  }
}

/**
  * @brief  MSC_BOT_CplClrFeature
  *         Complete the clear feature request
  * @param  pdev: device instance
  * @param  epnum: endpoint index
  * @retval None
  */

void  MSC_BOT_CplClrFeature(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc = MSC_BOT_GetHandle(pdev);

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if (hmsc == NULL)
  {
    return;
  }

  if (hmsc->bot_status == USBD_BOT_STATUS_ERROR) /* Bad CBW Signature */
  {
    (void)USBD_LL_StallEP(pdev, MSCInEpAdd);
    (void)USBD_LL_StallEP(pdev, MSCOutEpAdd);
  }
  else if (((epnum & 0x80U) == 0x80U) && (hmsc->bot_status != USBD_BOT_STATUS_RECOVERY))
  {
    MSC_BOT_SendCSW(pdev, USBD_CSW_CMD_FAILED);
  }
  else
  {
    return;
  }
}
/**
  * @}
  */


/**
  * @}
  */


/**
  * @}
  */
