/**
  ******************************************************************************
  * @file    usbd_msc.c
  * @author  MCD Application Team
  * @brief   This file provides all the MSC core functions.
  *
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
  * @verbatim
  *
  *          ===================================================================
  *                                MSC Class  Description
  *          ===================================================================
  *           This module manages the MSC class V1.0 following the "Universal
  *           Serial Bus Mass Storage Class (MSC) Bulk-Only Transport (BOT) Version 1.0
  *           Sep. 31, 1999".
  *           This driver implements the following aspects of the specification:
  *             - Bulk-Only Transport protocol
  *             - Subclass : SCSI transparent command set (ref. SCSI Primary Commands - 3 (SPC-3))
  *
  *  @endverbatim
  *
  ******************************************************************************
  */

/* BSPDependencies
- "stm32xxxxx_{eval}{discovery}{nucleo_144}.c"
- "stm32xxxxx_{eval}{discovery}_io.c"
- "stm32xxxxx_{eval}{discovery}{adafruit}_sd.c"
EndBSPDependencies */

/* Includes ------------------------------------------------------------------*/
#include "usbd_msc.h"
#include "msc_scsi_safety.h"


/** @addtogroup STM32_USB_DEVICE_LIBRARY
  * @{
  */


/** @defgroup MSC_CORE
  * @brief Mass storage core module
  * @{
  */

/** @defgroup MSC_CORE_Private_TypesDefinitions
  * @{
  */
/**
  * @}
  */


/** @defgroup MSC_CORE_Private_Defines
  * @{
  */

/**
  * @}
  */


/** @defgroup MSC_CORE_Private_Macros
  * @{
  */
/**
  * @}
  */


/** @defgroup MSC_CORE_Private_FunctionPrototypes
  * @{
  */
uint8_t USBD_MSC_Init(USBD_HandleTypeDef *pdev, uint8_t cfgidx);
uint8_t USBD_MSC_DeInit(USBD_HandleTypeDef *pdev, uint8_t cfgidx);
uint8_t USBD_MSC_Setup(USBD_HandleTypeDef *pdev, USBD_SetupReqTypedef *req);
uint8_t USBD_MSC_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum);
uint8_t USBD_MSC_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum);

#ifndef USE_USBD_COMPOSITE
uint8_t *USBD_MSC_GetHSCfgDesc(uint16_t *length);
uint8_t *USBD_MSC_GetFSCfgDesc(uint16_t *length);
uint8_t *USBD_MSC_GetOtherSpeedCfgDesc(uint16_t *length);
uint8_t *USBD_MSC_GetDeviceQualifierDescriptor(uint16_t *length);
#endif /* USE_USBD_COMPOSITE */
/**
  * @}
  */


/** @defgroup MSC_CORE_Private_Variables
  * @{
  */


USBD_ClassTypeDef  USBD_MSC =
{
  USBD_MSC_Init,
  USBD_MSC_DeInit,
  USBD_MSC_Setup,
  NULL, /*EP0_TxSent*/
  NULL, /*EP0_RxReady*/
  USBD_MSC_DataIn,
  USBD_MSC_DataOut,
  NULL, /*SOF */
  NULL,
  NULL,
#ifdef USE_USBD_COMPOSITE
  NULL,
  NULL,
  NULL,
  NULL,
#else
  USBD_MSC_GetHSCfgDesc,
  USBD_MSC_GetFSCfgDesc,
  USBD_MSC_GetOtherSpeedCfgDesc,
  USBD_MSC_GetDeviceQualifierDescriptor,
#endif /* USE_USBD_COMPOSITE */
};

/* USB Mass storage device Configuration Descriptor */
#ifndef USE_USBD_COMPOSITE
/* USB Mass storage device Configuration Descriptor */
/* All Descriptors (Configuration, Interface, Endpoint, Class, Vendor */
__ALIGN_BEGIN static uint8_t USBD_MSC_CfgDesc[USB_MSC_CONFIG_DESC_SIZ]  __ALIGN_END =
{
  0x09,                                            /* bLength: Configuration Descriptor size */
  USB_DESC_TYPE_CONFIGURATION,                     /* bDescriptorType: Configuration */
  USB_MSC_CONFIG_DESC_SIZ,

  0x00,
  0x01,                                            /* bNumInterfaces: 1 interface */
  0x01,                                            /* bConfigurationValue */
  0x04,                                            /* iConfiguration */
#if (USBD_SELF_POWERED == 1U)
  0xC0,                                            /* bmAttributes: Bus Powered according to user configuration */
#else
  0x80,                                            /* bmAttributes: Bus Powered according to user configuration */
#endif /* USBD_SELF_POWERED */
  USBD_MAX_POWER,                                  /* MaxPower (mA) */

  /********************  Mass Storage interface ********************/
  0x09,                                            /* bLength: Interface Descriptor size */
  0x04,                                            /* bDescriptorType: */
  0x00,                                            /* bInterfaceNumber: Number of Interface */
  0x00,                                            /* bAlternateSetting: Alternate setting */
  0x02,                                            /* bNumEndpoints */
  0x08,                                            /* bInterfaceClass: MSC Class */
  0x06,                                            /* bInterfaceSubClass : SCSI transparent*/
  0x50,                                            /* nInterfaceProtocol */
  0x05,                                            /* iInterface: */
  /********************  Mass Storage Endpoints ********************/
  0x07,                                            /* Endpoint descriptor length = 7 */
  0x05,                                            /* Endpoint descriptor type */
  MSC_EPIN_ADDR,                                   /* Endpoint address (IN, address 1) */
  0x02,                                            /* Bulk endpoint type */
  LOBYTE(MSC_MAX_FS_PACKET),
  HIBYTE(MSC_MAX_FS_PACKET),
  0x00,                                            /* Polling interval in milliseconds */

  0x07,                                            /* Endpoint descriptor length = 7 */
  0x05,                                            /* Endpoint descriptor type */
  MSC_EPOUT_ADDR,                                  /* Endpoint address (OUT, address 1) */
  0x02,                                            /* Bulk endpoint type */
  LOBYTE(MSC_MAX_FS_PACKET),
  HIBYTE(MSC_MAX_FS_PACKET),
  0x00                                             /* Polling interval in milliseconds */
};

/* USB Standard Device Descriptor */
__ALIGN_BEGIN static uint8_t USBD_MSC_DeviceQualifierDesc[USB_LEN_DEV_QUALIFIER_DESC]  __ALIGN_END =
{
  USB_LEN_DEV_QUALIFIER_DESC,
  USB_DESC_TYPE_DEVICE_QUALIFIER,
  0x00,
  0x02,
  0x00,
  0x00,
  0x00,
  MSC_MAX_FS_PACKET,
  0x01,
  0x00,
};
#endif /* USE_USBD_COMPOSITE */

uint8_t MSCInEpAdd  = MSC_EPIN_ADDR;
uint8_t MSCOutEpAdd = MSC_EPOUT_ADDR;

static uint8_t USBD_MSC_ValidContext(const USBD_HandleTypeDef *pdev)
{
  return (uint8_t)((pdev != NULL) && (pdev->classId < USBD_MAX_SUPPORTED_CLASS));
}

static uint8_t USBD_MSC_ValidEndpoint(uint8_t address)
{
  const uint8_t index = address & 0x0FU;
  return (uint8_t)((index != 0U) && ((address & 0x70U) == 0U));
}

static uint8_t USBD_MSC_ValidInterface(uint16_t interface_index)
{
  return (uint8_t)(interface_index < USBD_MAX_NUM_INTERFACES);
}

static uint8_t USBD_MSC_ValidStorage(const USBD_StorageTypeDef *storage)
{
  return (uint8_t)((storage != NULL) && (storage->Init != NULL) &&
                   (storage->GetCapacity != NULL) && (storage->IsReady != NULL) &&
                   (storage->IsWriteProtected != NULL) && (storage->Read != NULL) &&
                   (storage->Write != NULL) && (storage->GetMaxLun != NULL) &&
                   (storage->pInquiry != NULL));
}

static void USBD_MSC_ReleaseHandle(USBD_HandleTypeDef *pdev)
{
  if (!USBD_MSC_ValidContext(pdev))
  {
    return;
  }
  if (pdev->pClassDataCmsit[pdev->classId] != NULL)
  {
    (void)USBD_free(pdev->pClassDataCmsit[pdev->classId]);
    pdev->pClassDataCmsit[pdev->classId] = NULL;
  }
  pdev->pClassData = NULL;
}

/**
  * @}
  */


/** @defgroup MSC_CORE_Private_Functions
  * @{
  */

/**
  * @brief  USBD_MSC_Init
  *         Initialize  the mass storage configuration
  * @param  pdev: device instance
  * @param  cfgidx: configuration index
  * @retval status
  */
uint8_t USBD_MSC_Init(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  UNUSED(cfgidx);
  USBD_MSC_BOT_HandleTypeDef *hmsc;
  USBD_StorageTypeDef *storage;
  int8_t max_lun;
  uint16_t packet_size;

  if (!USBD_MSC_ValidContext(pdev))
  {
    return (uint8_t)USBD_FAIL;
  }

  storage = (USBD_StorageTypeDef *)pdev->pUserData[pdev->classId];
  if (!USBD_MSC_ValidStorage(storage))
  {
    return (uint8_t)USBD_FAIL;
  }
  max_lun = storage->GetMaxLun();
  if (!msc_bot_max_lun_is_valid((int32_t)max_lun))
  {
    return (uint8_t)USBD_FAIL;
  }
  if (pdev->pClassDataCmsit[pdev->classId] != NULL)
  {
    return (uint8_t)USBD_FAIL;
  }

  hmsc = (USBD_MSC_BOT_HandleTypeDef *)USBD_malloc(sizeof(USBD_MSC_BOT_HandleTypeDef));

  if (hmsc == NULL)
  {
    pdev->pClassDataCmsit[pdev->classId] = NULL;
    pdev->pClassData = NULL;
    return (uint8_t)USBD_EMEM;
  }

  (void)USBD_memset(hmsc, 0, sizeof(USBD_MSC_BOT_HandleTypeDef));
  hmsc->max_lun = (uint32_t)max_lun;

  pdev->pClassDataCmsit[pdev->classId] = (void *)hmsc;
  pdev->pClassData = pdev->pClassDataCmsit[pdev->classId];

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if (!USBD_MSC_ValidEndpoint(MSCOutEpAdd) || !USBD_MSC_ValidEndpoint(MSCInEpAdd))
  {
    USBD_MSC_ReleaseHandle(pdev);
    return (uint8_t)USBD_FAIL;
  }

  packet_size = (pdev->dev_speed == USBD_SPEED_HIGH) ? MSC_MAX_HS_PACKET : MSC_MAX_FS_PACKET;
  if (USBD_LL_OpenEP(pdev, MSCOutEpAdd, USBD_EP_TYPE_BULK, packet_size) != USBD_OK)
  {
    USBD_MSC_ReleaseHandle(pdev);
    return (uint8_t)USBD_FAIL;
  }
  pdev->ep_out[MSCOutEpAdd & 0xFU].is_used = 1U;

  if (USBD_LL_OpenEP(pdev, MSCInEpAdd, USBD_EP_TYPE_BULK, packet_size) != USBD_OK)
  {
    (void)USBD_LL_CloseEP(pdev, MSCOutEpAdd);
    pdev->ep_out[MSCOutEpAdd & 0xFU].is_used = 0U;
    USBD_MSC_ReleaseHandle(pdev);
    return (uint8_t)USBD_FAIL;
  }
  pdev->ep_in[MSCInEpAdd & 0xFU].is_used = 1U;

  /* Init the BOT  layer */
  if (MSC_BOT_Init(pdev) != USBD_OK)
  {
    (void)USBD_LL_CloseEP(pdev, MSCOutEpAdd);
    (void)USBD_LL_CloseEP(pdev, MSCInEpAdd);
    pdev->ep_out[MSCOutEpAdd & 0xFU].is_used = 0U;
    pdev->ep_in[MSCInEpAdd & 0xFU].is_used = 0U;
    USBD_MSC_ReleaseHandle(pdev);
    return (uint8_t)USBD_FAIL;
  }

  return (uint8_t)USBD_OK;
}

/**
  * @brief  USBD_MSC_DeInit
  *         DeInitialize  the mass storage configuration
  * @param  pdev: device instance
  * @param  cfgidx: configuration index
  * @retval status
  */
uint8_t USBD_MSC_DeInit(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  UNUSED(cfgidx);

  if (!USBD_MSC_ValidContext(pdev))
  {
    return (uint8_t)USBD_FAIL;
  }

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  /* Close MSC EPs */
  if (USBD_MSC_ValidEndpoint(MSCOutEpAdd))
  {
    (void)USBD_LL_CloseEP(pdev, MSCOutEpAdd);
    pdev->ep_out[MSCOutEpAdd & 0xFU].is_used = 0U;
  }

  /* Close EP IN */
  if (USBD_MSC_ValidEndpoint(MSCInEpAdd))
  {
    (void)USBD_LL_CloseEP(pdev, MSCInEpAdd);
    pdev->ep_in[MSCInEpAdd & 0xFU].is_used = 0U;
  }

  /* Free MSC Class Resources */
  if (pdev->pClassDataCmsit[pdev->classId] != NULL)
  {
    /* De-Init the BOT layer */
    MSC_BOT_DeInit(pdev);

  }
  USBD_MSC_ReleaseHandle(pdev);

  return (uint8_t)USBD_OK;
}
/**
  * @brief  USBD_MSC_Setup
  *         Handle the MSC specific requests
  * @param  pdev: device instance
  * @param  req: USB request
  * @retval status
  */
uint8_t USBD_MSC_Setup(USBD_HandleTypeDef *pdev, USBD_SetupReqTypedef *req)
{
  USBD_MSC_BOT_HandleTypeDef *hmsc;
  USBD_StatusTypeDef ret = USBD_OK;
  uint16_t status_info = 0U;

  if (!USBD_MSC_ValidContext(pdev) || (req == NULL))
  {
    return (uint8_t)USBD_FAIL;
  }
  hmsc = (USBD_MSC_BOT_HandleTypeDef *)pdev->pClassDataCmsit[pdev->classId];

#ifdef USE_USBD_COMPOSITE
  /* Get the Endpoints addresses allocated for this class instance */
  MSCInEpAdd  = USBD_CoreGetEPAdd(pdev, USBD_EP_IN, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
  MSCOutEpAdd = USBD_CoreGetEPAdd(pdev, USBD_EP_OUT, USBD_EP_TYPE_BULK, (uint8_t)pdev->classId);
#endif /* USE_USBD_COMPOSITE */

  if (hmsc == NULL)
  {
    return (uint8_t)USBD_FAIL;
  }

  switch (req->bmRequest & USB_REQ_TYPE_MASK)
  {
    /* Class request */
    case USB_REQ_TYPE_CLASS:
      switch (req->bRequest)
      {
        case BOT_GET_MAX_LUN:
          if ((req->wValue  == 0U) && (req->wLength == 1U) &&
              USBD_MSC_ValidInterface(req->wIndex) && (req->bmRequest == 0xA1U))
          {
            (void)USBD_CtlSendData(pdev, (uint8_t *)&hmsc->max_lun, 1U);
          }
          else
          {
            USBD_CtlError(pdev, req);
            ret = USBD_FAIL;
          }
          break;

        case BOT_RESET :
          if ((req->wValue  == 0U) && (req->wLength == 0U) &&
              USBD_MSC_ValidInterface(req->wIndex) && (req->bmRequest == 0x21U))
          {
            MSC_BOT_Reset(pdev);
          }
          else
          {
            USBD_CtlError(pdev, req);
            ret = USBD_FAIL;
          }
          break;

        default:
          USBD_CtlError(pdev, req);
          ret = USBD_FAIL;
          break;
      }
      break;
    /* Interface & Endpoint request */
    case USB_REQ_TYPE_STANDARD:
      switch (req->bRequest)
      {
        case USB_REQ_GET_STATUS:
          if ((pdev->dev_state == USBD_STATE_CONFIGURED) &&
              (req->wValue == 0U) && USBD_MSC_ValidInterface(req->wIndex) &&
              (req->wLength == 2U) && (req->bmRequest == 0x81U))
          {
            (void)USBD_CtlSendData(pdev, (uint8_t *)&status_info, 2U);
          }
          else
          {
            USBD_CtlError(pdev, req);
            ret = USBD_FAIL;
          }
          break;

        case USB_REQ_GET_INTERFACE:
          if ((pdev->dev_state == USBD_STATE_CONFIGURED) &&
              (req->wValue == 0U) && USBD_MSC_ValidInterface(req->wIndex) &&
              (req->wLength == 1U) && (req->bmRequest == 0x81U))
          {
            (void)USBD_CtlSendData(pdev, (uint8_t *)&hmsc->interface, 1U);
          }
          else
          {
            USBD_CtlError(pdev, req);
            ret = USBD_FAIL;
          }
          break;

        case USB_REQ_SET_INTERFACE:
          if ((pdev->dev_state == USBD_STATE_CONFIGURED) &&
              (req->wValue == 0U) && USBD_MSC_ValidInterface(req->wIndex) &&
              (req->wLength == 0U) && (req->bmRequest == 0x01U))
          {
            hmsc->interface = (uint8_t)(req->wValue);
          }
          else
          {
            USBD_CtlError(pdev, req);
            ret = USBD_FAIL;
          }
          break;

        case USB_REQ_CLEAR_FEATURE:
          if ((pdev->dev_state == USBD_STATE_CONFIGURED) &&
              (req->wLength == 0U) && (req->bmRequest == 0x02U))
          {
            const uint8_t endpoint = (uint8_t)req->wIndex;
            if ((req->wValue == USB_FEATURE_EP_HALT) &&
                ((req->wIndex & 0xFF00U) == 0U) &&
                ((endpoint == MSCInEpAdd) || (endpoint == MSCOutEpAdd)))
            {
              /* Flush the FIFO */
              (void)USBD_LL_FlushEP(pdev, (uint8_t)req->wIndex);

              /* Handle BOT error */
              MSC_BOT_CplClrFeature(pdev, (uint8_t)req->wIndex);
            }
            else
            {
              USBD_CtlError(pdev, req);
              ret = USBD_FAIL;
            }
          }
          else
          {
            USBD_CtlError(pdev, req);
            ret = USBD_FAIL;
          }
          break;

        default:
          USBD_CtlError(pdev, req);
          ret = USBD_FAIL;
          break;
      }
      break;

    default:
      USBD_CtlError(pdev, req);
      ret = USBD_FAIL;
      break;
  }

  return (uint8_t)ret;
}

/**
  * @brief  USBD_MSC_DataIn
  *         handle data IN Stage
  * @param  pdev: device instance
  * @param  epnum: endpoint index
  * @retval status
  */
uint8_t USBD_MSC_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  if (!USBD_MSC_ValidContext(pdev) || (epnum != (MSCInEpAdd & 0x7FU)))
  {
    return (uint8_t)USBD_FAIL;
  }
  MSC_BOT_DataIn(pdev, epnum);

  return (uint8_t)USBD_OK;
}

/**
  * @brief  USBD_MSC_DataOut
  *         handle data OUT Stage
  * @param  pdev: device instance
  * @param  epnum: endpoint index
  * @retval status
  */
uint8_t USBD_MSC_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  if (!USBD_MSC_ValidContext(pdev) || (epnum != (MSCOutEpAdd & 0x7FU)))
  {
    return (uint8_t)USBD_FAIL;
  }
  MSC_BOT_DataOut(pdev, epnum);

  return (uint8_t)USBD_OK;
}
#ifndef USE_USBD_COMPOSITE
/**
  * @brief  USBD_MSC_GetHSCfgDesc
  *         return configuration descriptor
  * @param  length : pointer data length
  * @retval pointer to descriptor buffer
  */
uint8_t *USBD_MSC_GetHSCfgDesc(uint16_t *length)
{
  USBD_EpDescTypeDef *pEpInDesc = USBD_GetEpDesc(USBD_MSC_CfgDesc, MSC_EPIN_ADDR);
  USBD_EpDescTypeDef *pEpOutDesc = USBD_GetEpDesc(USBD_MSC_CfgDesc, MSC_EPOUT_ADDR);

  if (pEpInDesc != NULL)
  {
    pEpInDesc->wMaxPacketSize = MSC_MAX_HS_PACKET;
  }

  if (pEpOutDesc != NULL)
  {
    pEpOutDesc->wMaxPacketSize = MSC_MAX_HS_PACKET;
  }

  *length = (uint16_t)sizeof(USBD_MSC_CfgDesc);
  return USBD_MSC_CfgDesc;
}

/**
  * @brief  USBD_MSC_GetFSCfgDesc
  *         return configuration descriptor
  * @param  length : pointer data length
  * @retval pointer to descriptor buffer
  */
uint8_t *USBD_MSC_GetFSCfgDesc(uint16_t *length)
{
  USBD_EpDescTypeDef *pEpInDesc = USBD_GetEpDesc(USBD_MSC_CfgDesc, MSC_EPIN_ADDR);
  USBD_EpDescTypeDef *pEpOutDesc = USBD_GetEpDesc(USBD_MSC_CfgDesc, MSC_EPOUT_ADDR);

  if (pEpInDesc != NULL)
  {
    pEpInDesc->wMaxPacketSize = MSC_MAX_FS_PACKET;
  }

  if (pEpOutDesc != NULL)
  {
    pEpOutDesc->wMaxPacketSize = MSC_MAX_FS_PACKET;
  }

  *length = (uint16_t)sizeof(USBD_MSC_CfgDesc);
  return USBD_MSC_CfgDesc;
}

/**
  * @brief  USBD_MSC_GetOtherSpeedCfgDesc
  *         return other speed configuration descriptor
  * @param  length : pointer data length
  * @retval pointer to descriptor buffer
  */
uint8_t *USBD_MSC_GetOtherSpeedCfgDesc(uint16_t *length)
{
  USBD_EpDescTypeDef *pEpInDesc = USBD_GetEpDesc(USBD_MSC_CfgDesc, MSC_EPIN_ADDR);
  USBD_EpDescTypeDef *pEpOutDesc = USBD_GetEpDesc(USBD_MSC_CfgDesc, MSC_EPOUT_ADDR);

  if (pEpInDesc != NULL)
  {
    pEpInDesc->wMaxPacketSize = MSC_MAX_FS_PACKET;
  }

  if (pEpOutDesc != NULL)
  {
    pEpOutDesc->wMaxPacketSize = MSC_MAX_FS_PACKET;
  }

  *length = (uint16_t)sizeof(USBD_MSC_CfgDesc);
  return USBD_MSC_CfgDesc;
}
/**
  * @brief  DeviceQualifierDescriptor
  *         return Device Qualifier descriptor
  * @param  length : pointer data length
  * @retval pointer to descriptor buffer
  */
uint8_t *USBD_MSC_GetDeviceQualifierDescriptor(uint16_t *length)
{
  *length = (uint16_t)sizeof(USBD_MSC_DeviceQualifierDesc);

  return USBD_MSC_DeviceQualifierDesc;
}
#endif /* USE_USBD_COMPOSITE */
/**
  * @brief  USBD_MSC_RegisterStorage
  * @param  fops: storage callback
  * @retval status
  */
uint8_t USBD_MSC_RegisterStorage(USBD_HandleTypeDef *pdev, USBD_StorageTypeDef *fops)
{
  if (!USBD_MSC_ValidContext(pdev) || !USBD_MSC_ValidStorage(fops) ||
      (pdev->pClassDataCmsit[pdev->classId] != NULL))
  {
    return (uint8_t)USBD_FAIL;
  }

  pdev->pUserData[pdev->classId] = fops;

  return (uint8_t)USBD_OK;
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
