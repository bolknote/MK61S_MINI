/**
  ******************************************************************************
  * @file    usbd_cdc_if.c
  * @author  MCD Application Team
  * @brief   Generic media access Layer.
  ******************************************************************************
  * @attention
  *
  * <h2><center>&copy; Copyright (c) 2015 STMicroelectronics.
  * All rights reserved.</center></h2>
  *
  * This software component is licensed by ST under Ultimate Liberty license
  * SLA0044, the "License"; You may not use this file except in compliance with
  * the License. You may obtain a copy of the License at:
  *                      www.st.com/SLA0044
  *
  ******************************************************************************
  */

// One fixed CDC instance. Queue capacities and packet size match the baseline.
#if defined(MK61_USB_BUILD_CDC_IF)
#include <usbd_cdc_if.h>
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
#include "stm32f4_usbd_desc.h"
#else
#include <usbd_desc.h>
#define mk61_usb_descriptors USBD_Desc
#endif
#if MK61_USB_COMPACT_STATE
/* Absolute ELF marker selects the exact ABI in the release symbol gate. */
__asm__(".global mk61_usb_compact_layout\n.set mk61_usb_compact_layout, 1");
#endif
USBD_HandleTypeDef hUSBD_Device_CDC;
CDC_TransmitQueue_TypeDef TransmitQueue;
CDC_ReceiveQueue_TypeDef ReceiveQueue;
volatile bool dtrState, rtsState;
volatile bool receivePended=true;
static bool initialized;
static bool dtr_enabled=true;
static uint32_t transmit_started;
static USBD_CDC_LineCodingTypeDef linecoding={115200,0,0,8};
static uint32_t cdc_if_lock(void) { uint32_t saved=__get_PRIMASK();__disable_irq();return saved; }
static void cdc_if_unlock(uint32_t saved) { __set_PRIMASK(saved); }
static int8_t cdc_if_init(void) {
  CDC_TransmitQueue_Init(&TransmitQueue); CDC_ReceiveQueue_Init(&ReceiveQueue);
  receivePended=true; transmit_started=0;
  return USBD_CDC_SetRxBuffer(&hUSBD_Device_CDC,CDC_ReceiveQueue_ReserveBlock(&ReceiveQueue));
}
static int8_t cdc_if_deinit(void) { dtrState=false;rtsState=false;return USBD_OK; }
static int8_t cdc_if_control(uint8_t cmd,uint8_t* bytes,uint16_t length) {
  switch(cmd) {
  case CDC_SET_LINE_CODING:
    if(length!=7) return USBD_FAIL;
    linecoding.bitrate=(uint32_t)bytes[0]|((uint32_t)bytes[1]<<8)|((uint32_t)bytes[2]<<16)|((uint32_t)bytes[3]<<24);
    linecoding.format=bytes[4];linecoding.paritytype=bytes[5];linecoding.datatype=bytes[6];break;
  case CDC_GET_LINE_CODING:
    bytes[0]=linecoding.bitrate;bytes[1]=linecoding.bitrate>>8;bytes[2]=linecoding.bitrate>>16;bytes[3]=linecoding.bitrate>>24;
    bytes[4]=linecoding.format;bytes[5]=linecoding.paritytype;bytes[6]=linecoding.datatype;break;
  case CDC_SET_CONTROL_LINE_STATE: {
    const uint16_t value=((USBD_SetupReqTypedef*)bytes)->wValue;
    dtrState=!dtr_enabled || (value&CLS_DTR);rtsState=(value&CLS_RTS)!=0;
    if(dtrState) transmit_started=0;
    break;
  }
  case CDC_SEND_BREAK:break;
  default:return USBD_FAIL;
  }
  return USBD_OK;
}
static int8_t cdc_if_receive(uint8_t* bytes,uint32_t* size) {
  (void)bytes;
  if(*size>CDC_QUEUE_MAX_PACKET_SIZE) return USBD_FAIL;
  CDC_ReceiveQueue_CommitBlock(&ReceiveQueue,(uint16_t)*size);
  receivePended=false;
  if(!CDC_resume_receive()) USBD_CDC_ClearBuffer(&hUSBD_Device_CDC);
  return USBD_OK;
}
static int8_t cdc_if_transmitted(uint8_t* bytes,uint32_t* size,uint8_t ep) {
  (void)bytes;(void)size;(void)ep;
  transmit_started=0;CDC_TransmitQueue_CommitRead(&TransmitQueue);CDC_continue_transmit();return USBD_OK;
}
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
static const USBD_CDC_ItfTypeDef mk61_cdc_functions=
#else
#define mk61_cdc_functions USBD_CDC_fops
USBD_CDC_ItfTypeDef USBD_CDC_fops=
#endif
{cdc_if_init,cdc_if_deinit,cdc_if_control,cdc_if_receive,cdc_if_transmitted};
void CDC_init(void) {
  if(initialized) return;
  if(USBD_Init(&hUSBD_Device_CDC,(USBD_DescriptorsTypeDef*)&mk61_usb_descriptors,0)==USBD_OK &&
     USBD_RegisterClass(&hUSBD_Device_CDC,(USBD_ClassTypeDef*)USBD_CDC_CLASS)==USBD_OK &&
     USBD_CDC_RegisterInterface(&hUSBD_Device_CDC,(USBD_CDC_ItfTypeDef*)&mk61_cdc_functions)==USBD_OK) {
    initialized=true;
    if(USBD_Start(&hUSBD_Device_CDC)==USBD_OK) return;
    initialized=false;
  }
  USBD_DeInit(&hUSBD_Device_CDC);
}
void CDC_deInit(void) {
  if(!initialized) return;
  initialized=false;
  USBD_Stop(&hUSBD_Device_CDC);USBD_DeInit(&hUSBD_Device_CDC);
}
bool CDC_connected(void) {
  const uint32_t started=transmit_started;
  return initialized && hUSBD_Device_CDC.dev_state==USBD_STATE_CONFIGURED && dtrState &&
    (!started || (uint32_t)(HAL_GetTick()-started)<3);
}
void CDC_continue_transmit(void) {
  // Reset/disconnect can clear class data between a foreground check and this call.
  const uint32_t saved=cdc_if_lock();
  USBD_CDC_HandleTypeDef* h=(USBD_CDC_HandleTypeDef*)MK61_USBD_ClassData(&hUSBD_Device_CDC);
  if(initialized && h && !h->TxState && CDC_connected()) {
    uint16_t size;uint8_t* bytes=CDC_TransmitQueue_ReadBlock(&TransmitQueue,&size);
    if(size) {
      transmit_started=HAL_GetTick();
      USBD_CDC_SetTxBuffer(&hUSBD_Device_CDC,bytes,size);
      USBD_CDC_TransmitPacket(&hUSBD_Device_CDC);
    }
  }
  cdc_if_unlock(saved);
}
bool CDC_resume_receive(void) {
  const uint32_t saved=cdc_if_lock();bool resumed=false;
  if(initialized && MK61_USBD_ClassData(&hUSBD_Device_CDC) && !receivePended) {
    uint8_t* bytes=CDC_ReceiveQueue_ReserveBlock(&ReceiveQueue);
    if(bytes) {
      receivePended=true;
      USBD_CDC_SetRxBuffer(&hUSBD_Device_CDC,bytes);
      resumed=USBD_CDC_ReceivePacket(&hUSBD_Device_CDC)==USBD_OK;
      if(!resumed) receivePended=false;
    }
  }
  cdc_if_unlock(saved);return resumed;
}
void CDC_enableDTR(bool enable) { dtr_enabled=enable; }
#endif
