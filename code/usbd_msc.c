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

/* Specialization for the calculator's mutually exclusive CDC/MSC modes:
 * one class slot, interface zero, one disk, Full Speed endpoints 81/01. */
#include "native_libc.h"
#include "usbd_msc.h"

_Static_assert(MSC_EPIN_ADDR == 0x81U && MSC_EPOUT_ADDR == 0x01U,
               "fixed MSC endpoint layout changed");
_Static_assert(MSC_MEDIA_PACKET % MK61_MSC_SECTOR_SIZE == 0U,
               "BOT buffer must contain whole FAT sectors");
#if defined(STM32F411xE)
_Static_assert(sizeof(USBD_MSC_BOT_HandleTypeDef) == 8264U,
               "update lazy MSC ELF reserve for changed transport layout");
#if MK61_USE_NATIVE_LIBC
__asm__(".global mk61_lazy_msc_bytes\n.set mk61_lazy_msc_bytes, 8264");
#else
__asm__(".global mk61_lazy_msc_bytes\n.set mk61_lazy_msc_bytes, 8296");
#endif
static USBD_MSC_BOT_HandleTypeDef *prepared_handle;
#define transport (*prepared_handle)
uint8_t MK61_MSC_SetPreparedHandle(void *memory, uint32_t size)
{
  if (memory == NULL || ((uintptr_t)memory & 3U) != 0U ||
      size != sizeof(USBD_MSC_BOT_HandleTypeDef) ||
      (prepared_handle != NULL && prepared_handle != memory)) return 0U;
  prepared_handle = memory;
  return 1U;
}
#else
_Static_assert(MSC_MEDIA_PACKET == 512U &&
               sizeof(USBD_MSC_BOT_HandleTypeDef) == 584U,
               "F401 transport must fit the guarded RAM layout");
static USBD_MSC_BOT_HandleTypeDef transport;
#endif
/* SET_CONFIGURATION runs in USB IRQ context: foreground prepare() provides
 * F411's retained buffer. F401's small buffer is static. Never grow the heap
 * or invoke USBDISK.APP here. */
static USBD_HandleTypeDef *owner;

__ALIGN_BEGIN static const uint8_t USBD_MSC_CfgDesc[USB_MSC_CONFIG_DESC_SIZ]  __ALIGN_END =
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

static void release_handle(USBD_HandleTypeDef *pdev)
{
  if (owner != pdev) return;
  pdev->pClassDataCmsit[0] = NULL;
  pdev->pClassData = NULL;
  owner = NULL;
  (void)USBD_memset(&transport, 0, sizeof(transport));
}

uint8_t USBD_MSC_Init(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  (void)cfgidx;
  if (pdev == NULL || pdev->classId != 0U || owner != NULL ||
      pdev->pClassDataCmsit[0] != NULL) return USBD_FAIL;
#if defined(STM32F411xE)
  if (prepared_handle == NULL) return USBD_FAIL;
#endif
  (void)USBD_memset(&transport, 0, sizeof(transport));
  owner = pdev;
  pdev->pClassData = pdev->pClassDataCmsit[0] = &transport;
  if (USBD_LL_OpenEP(pdev, MSC_EPOUT_ADDR, USBD_EP_TYPE_BULK, 64U) != USBD_OK)
    goto fail;
  pdev->ep_out[1].is_used = 1U;
  if (USBD_LL_OpenEP(pdev, MSC_EPIN_ADDR, USBD_EP_TYPE_BULK, 64U) != USBD_OK)
    goto close_out;
  pdev->ep_in[1].is_used = 1U;
  if (MSC_BOT_Init(pdev) == USBD_OK) return USBD_OK;
  (void)USBD_LL_CloseEP(pdev, MSC_EPIN_ADDR);
  pdev->ep_in[1].is_used = 0U;
close_out:
  (void)USBD_LL_CloseEP(pdev, MSC_EPOUT_ADDR);
  pdev->ep_out[1].is_used = 0U;
fail:
  release_handle(pdev);
  return USBD_FAIL;
}

uint8_t USBD_MSC_DeInit(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  (void)cfgidx;
  if (pdev == NULL || pdev->classId != 0U) return USBD_FAIL;
  if (owner == pdev) {
    MSC_BOT_DeInit(pdev);
    (void)USBD_LL_CloseEP(pdev, MSC_EPIN_ADDR);
    (void)USBD_LL_CloseEP(pdev, MSC_EPOUT_ADDR);
    pdev->ep_in[1].is_used = pdev->ep_out[1].is_used = 0U;
    release_handle(pdev);
  }
  return USBD_OK;
}

uint8_t USBD_MSC_Setup(USBD_HandleTypeDef *pdev, USBD_SetupReqTypedef *req)
{
  static const uint16_t zero = 0U; /* max LUN, alternate setting, status */
  if (req == NULL || MK61_MSC_Handle(pdev) == NULL) return USBD_FAIL;
  if (pdev->dev_state == USBD_STATE_CONFIGURED && req->wIndex == 0U &&
      req->wValue == 0U) {
    if ((req->bmRequest == 0xA1U && req->bRequest == BOT_GET_MAX_LUN && req->wLength == 1U) ||
        (req->bmRequest == 0x81U && req->bRequest == USB_REQ_GET_INTERFACE && req->wLength == 1U))
      return USBD_CtlSendData(pdev, (uint8_t *)&zero, 1U);
    if (req->bmRequest == 0x81U && req->bRequest == USB_REQ_GET_STATUS && req->wLength == 2U)
      return USBD_CtlSendData(pdev, (uint8_t *)&zero, 2U);
    if (req->bmRequest == 0x21U && req->bRequest == BOT_RESET && req->wLength == 0U) {
      MSC_BOT_Reset(pdev);
      return USBD_OK;
    }
    if (req->bmRequest == 0x01U && req->bRequest == USB_REQ_SET_INTERFACE && req->wLength == 0U)
      return USBD_OK;
  }
  if (pdev->dev_state == USBD_STATE_CONFIGURED &&
      req->bmRequest == 0x02U && req->bRequest == USB_REQ_CLEAR_FEATURE &&
      req->wValue == USB_FEATURE_EP_HALT && req->wLength == 0U &&
      (req->wIndex == MSC_EPIN_ADDR || req->wIndex == MSC_EPOUT_ADDR)) {
    (void)USBD_LL_FlushEP(pdev, (uint8_t)req->wIndex);
    MSC_BOT_CplClrFeature(pdev, (uint8_t)req->wIndex);
    return USBD_OK;
  }
  USBD_CtlError(pdev, req);
  return USBD_FAIL;
}

uint8_t USBD_MSC_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  if (epnum != 1U || MK61_MSC_Handle(pdev) == NULL) return USBD_FAIL;
  MSC_BOT_DataIn(pdev, epnum);
  return USBD_OK;
}
uint8_t USBD_MSC_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  if (epnum != 1U || MK61_MSC_Handle(pdev) == NULL) return USBD_FAIL;
  MSC_BOT_DataOut(pdev, epnum);
  return USBD_OK;
}
uint8_t *USBD_MSC_GetFSCfgDesc(uint16_t *length)
{
  *length = sizeof(USBD_MSC_CfgDesc);
  return (uint8_t *)USBD_MSC_CfgDesc;
}

#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
const USBD_ClassTypeDef USBD_MSC
#else
USBD_ClassTypeDef USBD_MSC
#endif
= {
  USBD_MSC_Init, USBD_MSC_DeInit, USBD_MSC_Setup,
  NULL, NULL, USBD_MSC_DataIn, USBD_MSC_DataOut, NULL, NULL, NULL,
  NULL, USBD_MSC_GetFSCfgDesc, NULL, NULL
};
