/**
  ******************************************************************************
  * @file    usbd_msc.h
  * @author  MCD Application Team
  * @brief   Header for the usbd_msc.c file
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __USBD_MSC_H
#define __USBD_MSC_H

#include "msc_memory_policy.h"


#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include  "usbd_msc_bot.h"
#include  "usbd_msc_scsi.h"
#include  "usbd_ioreq.h"
#if defined(STM32F411xE)
uint8_t MK61_MSC_SetPreparedHandle(void* memory, uint32_t size);
#endif

/** @addtogroup USBD_MSC_BOT
  * @{
  */

/** @defgroup USBD_MSC
  * @brief This file is the Header file for usbd_msc.c
  * @{
  */


/** @defgroup USBD_BOT_Exported_Defines
  * @{
  */
#include "msc_disk.h"

#define MSC_MAX_FS_PACKET            0x40U
#define MSC_MAX_HS_PACKET            0x200U

#define BOT_GET_MAX_LUN              0xFE
#define BOT_RESET                    0xFF
#define USB_MSC_CONFIG_DESC_SIZ      32

#ifndef MSC_EPIN_ADDR
#define MSC_EPIN_ADDR                0x81U
#endif /* MSC_EPIN_ADDR */

#ifndef MSC_EPOUT_ADDR
#define MSC_EPOUT_ADDR               0x01U
#endif /* MSC_EPOUT_ADDR */

/**
  * @}
  */

/** @defgroup USB_CORE_Exported_Types
  * @{
  */
typedef struct
{
  uint8_t bot_data[MSC_MEDIA_PACKET];
  USBD_MSC_BOT_CBWTypeDef cbw;
  USBD_MSC_BOT_CSWTypeDef csw;
  uint32_t scsi_blk_addr;
  uint32_t scsi_blk_len;
  uint16_t bot_data_length;
  uint8_t bot_state;
  uint8_t bot_status;
  USBD_SCSI_SenseTypeDef scsi_sense[SENSE_LIST_DEEPTH];
  uint8_t scsi_sense_head;
  uint8_t scsi_sense_tail;
  uint8_t scsi_medium_state;
  uint8_t host_eject_latched;
} USBD_MSC_BOT_HandleTypeDef;

/* Structure for MSC process */
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
extern const USBD_ClassTypeDef USBD_MSC;
#else
extern USBD_ClassTypeDef USBD_MSC;
#endif
#define USBD_MSC_CLASS    &USBD_MSC

/* The calculator switches CDC and MSC in the single class slot. Validate
 * public/deferred entry points once, rather than indexing generic instances
 * in every command handler. USB IRQ teardown clears this pointer first. */
static inline USBD_MSC_BOT_HandleTypeDef *MK61_MSC_Handle(USBD_HandleTypeDef *pdev)
{
  return pdev != NULL && pdev->classId == 0U && pdev->pClass[0] == &USBD_MSC
      ? (USBD_MSC_BOT_HandleTypeDef *)pdev->pClassDataCmsit[0] : NULL;
}



/**
  * @}
  */

/**
  * @}
  */

#ifdef __cplusplus
}
#endif

#endif  /* __USBD_MSC_H */
/**
  * @}
  */
