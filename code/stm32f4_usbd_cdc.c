/**
  ******************************************************************************
  * @file    usbd_cdc.c
  * @author  MCD Application Team
  * @brief   This file provides the high layer firmware functions to manage the
  *          following functionalities of the USB CDC Class:
  *           - Initialization and Configuration of high and low layer
  *           - Enumeration as CDC Device (and enumeration for each implemented memory interface)
  *           - OUT/IN data transfer
  *           - Command IN transfer (class requests management)
  *           - Error management
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
  *  @verbatim
  *
  *          ===================================================================
  *                                CDC Class Driver Description
  *          ===================================================================
  *           This driver manages the "Universal Serial Bus Class Definitions for Communications Devices
  *           Revision 1.2 November 16, 2007" and the sub-protocol specification of "Universal Serial Bus
  *           Communications Class Subclass Specification for PSTN Devices Revision 1.2 February 9, 2007"
  *           This driver implements the following aspects of the specification:
  *             - Device descriptor management
  *             - Configuration descriptor management
  *             - Enumeration as CDC device with 2 data endpoints (IN and OUT) and 1 command endpoint (IN)
  *             - Requests management (as described in section 6.2 in specification)
  *             - Abstract Control Model compliant
  *             - Union Functional collection (using 1 IN endpoint for control)
  *             - Data interface class
  *
  *           These aspects may be enriched or modified for a specific user application.
  *
  *            This driver doesn't implement the following aspects of the specification
  *            (but it is possible to manage these features with some modifications on this driver):
  *             - Any class-specific aspect relative to communication classes should be managed by user application.
  *             - All communication classes other than PSTN are not managed
  *
  *  @endverbatim
  *
  ******************************************************************************
  */

// Fixed Full Speed ACM implementation for one CDC class and endpoints 1/2/3.
#if defined(MK61_USB_BUILD_CDC)
#include "stm32f4_usbd_cdc.h"
#include <usbd_ctlreq.h>
#include <string.h>

USBD_CDC_HandleTypeDef _hcdc;
static const uint8_t configuration[USB_CDC_CONFIG_DESC_SIZ] = {
  9,2,67,0,2,1,0,0xC0,USBD_MAX_POWER,
  9,4,0,0,1,2,2,1,0,
  5,0x24,0,0x10,1,
  5,0x24,1,0,1,
  4,0x24,2,2,
  5,0x24,6,0,1,
  7,5,CDC_CMD_EP,3,CDC_CMD_PACKET_SIZE,0,CDC_FS_BINTERVAL,
  9,4,1,0,2,0x0A,0,0,0,
  7,5,CDC_OUT_EP,2,64,0,0,
  7,5,CDC_IN_EP,2,64,0,0
};
static uint8_t* fs_descriptor(uint16_t* size) {
  *size = sizeof(configuration);
  return (uint8_t*)configuration; // ST control API takes a mutable pointer, but only reads.
}
static USBD_CDC_HandleTypeDef* handle(USBD_HandleTypeDef* d) {
  return (USBD_CDC_HandleTypeDef*)d->pClassDataCmsit[0];
}
static USBD_CDC_ItfTypeDef* interface(USBD_HandleTypeDef* d) {
  return (USBD_CDC_ItfTypeDef*)d->pUserData[0];
}
static uint8_t cdc_init(USBD_HandleTypeDef* d, uint8_t configuration_index) {
  (void)configuration_index;
  if(d->classId != 0 || d->dev_speed != USBD_SPEED_FULL || !interface(d)) return USBD_FAIL;
  memset(&_hcdc,0,sizeof(_hcdc));
  _hcdc.CmdOpCode=0xFF;
  d->pClassDataCmsit[0]=d->pClassData=&_hcdc;
  if(USBD_LL_OpenEP(d,CDC_IN_EP,USBD_EP_TYPE_BULK,64)!=USBD_OK ||
     USBD_LL_OpenEP(d,CDC_OUT_EP,USBD_EP_TYPE_BULK,64)!=USBD_OK ||
     USBD_LL_OpenEP(d,CDC_CMD_EP,USBD_EP_TYPE_INTR,CDC_CMD_PACKET_SIZE)!=USBD_OK) return USBD_FAIL;
  d->ep_in[CDC_IN_EP&15].is_used=1;
  d->ep_out[CDC_OUT_EP&15].is_used=1;
  d->ep_in[CDC_CMD_EP&15].is_used=1;
  d->ep_in[CDC_CMD_EP&15].bInterval=CDC_FS_BINTERVAL;
  if(interface(d)->Init()!=0 || !_hcdc.RxBuffer) return USBD_FAIL;
  return USBD_LL_PrepareReceive(d,CDC_OUT_EP,_hcdc.RxBuffer,64);
}
static uint8_t cdc_deinit(USBD_HandleTypeDef* d,uint8_t configuration_index) {
  (void)configuration_index;
  USBD_LL_CloseEP(d,CDC_IN_EP); USBD_LL_CloseEP(d,CDC_OUT_EP); USBD_LL_CloseEP(d,CDC_CMD_EP);
  d->ep_in[CDC_IN_EP&15].is_used=0;
  d->ep_out[CDC_OUT_EP&15].is_used=0;
  d->ep_in[CDC_CMD_EP&15].is_used=0;
  d->ep_in[CDC_CMD_EP&15].bInterval=0;
  if(handle(d) && interface(d)) interface(d)->DeInit();
  d->pClassDataCmsit[0]=d->pClassData=NULL;
  return USBD_OK;
}
static uint8_t reject(USBD_HandleTypeDef* d,USBD_SetupReqTypedef* r) {
  USBD_CtlError(d,r); return USBD_FAIL;
}
static uint8_t cdc_setup(USBD_HandleTypeDef* d,USBD_SetupReqTypedef* r) {
  USBD_CDC_HandleTypeDef* h=handle(d);
  if(!h || !interface(d) || r->wIndex>1) return reject(d,r);
  if((r->bmRequest&USB_REQ_TYPE_MASK)==USB_REQ_TYPE_CLASS) {
    // ACM control requests belong to the communications interface only.
    if(r->wIndex!=0) return reject(d,r);
    switch(r->bRequest) {
    case CDC_GET_LINE_CODING:
      if(r->bmRequest!=0xA1 || r->wValue || !r->wLength) return reject(d,r);
      interface(d)->Control(r->bRequest,(uint8_t*)h->data,7);
      return USBD_CtlSendData(d,(uint8_t*)h->data,MIN(r->wLength,7));
    case CDC_SET_LINE_CODING:
      if(r->bmRequest!=0x21 || r->wValue || r->wLength!=7) return reject(d,r);
      h->CmdOpCode=r->bRequest; h->CmdLength=7;
      return USBD_CtlPrepareRx(d,(uint8_t*)h->data,7);
    case CDC_SET_CONTROL_LINE_STATE:
    case CDC_SEND_BREAK:
      if(r->bmRequest!=0x21 || r->wLength) return reject(d,r);
      return interface(d)->Control(r->bRequest,(uint8_t*)r,0)==0 ? USBD_OK:USBD_FAIL;
    default: return reject(d,r);
    }
  }
  if((r->bmRequest&USB_REQ_TYPE_MASK)!=USB_REQ_TYPE_STANDARD || d->dev_state!=USBD_STATE_CONFIGURED)
    return reject(d,r);
  // Replies persist until EP0 completion; never expose stack locals to the IRQ.
  h->data[0]=0;
  switch(r->bRequest) {
  case USB_REQ_GET_STATUS:
    if(r->bmRequest!=0x81 || r->wValue || r->wLength!=2) return reject(d,r);
    return USBD_CtlSendData(d,(uint8_t*)h->data,2);
  case USB_REQ_GET_INTERFACE:
    if(r->bmRequest!=0x81 || r->wValue || r->wLength!=1) return reject(d,r);
    return USBD_CtlSendData(d,(uint8_t*)h->data,1);
  case USB_REQ_SET_INTERFACE:
    return r->bmRequest==0x01 && !r->wValue && !r->wLength ? USBD_OK : reject(d,r);
  default: return reject(d,r);
  }
}
static uint8_t cdc_rx_ready(USBD_HandleTypeDef* d) {
  USBD_CDC_HandleTypeDef* h=handle(d);
  if(!h || !interface(d)) return USBD_FAIL;
  if(h->CmdOpCode==CDC_SET_LINE_CODING) {
    if(USBD_LL_GetRxDataSize(d,0)!=7) { h->CmdOpCode=0xFF;return reject(d,&d->request); }
    interface(d)->Control(h->CmdOpCode,(uint8_t*)h->data,h->CmdLength);
    h->CmdOpCode=0xFF;
  }
  return USBD_OK;
}
static uint8_t cdc_data_in(USBD_HandleTypeDef* d,uint8_t ep) {
  USBD_CDC_HandleTypeDef* h=handle(d);
  if(!h || ep!=(CDC_IN_EP&15)) return USBD_FAIL;
  // Fixed packet size: no cast of the owned bridge to a HAL PCD handle.
  if(d->ep_in[ep].total_length && !(d->ep_in[ep].total_length&63)) {
    d->ep_in[ep].total_length=0;
    return USBD_LL_Transmit(d,CDC_IN_EP,NULL,0);
  }
  h->TxState=0;
  if(interface(d)->TransmitCplt) interface(d)->TransmitCplt(h->TxBuffer,&h->TxLength,ep);
  return USBD_OK;
}
static uint8_t cdc_data_out(USBD_HandleTypeDef* d,uint8_t ep) {
  USBD_CDC_HandleTypeDef* h=handle(d);
  if(!h || ep!=(CDC_OUT_EP&15)) return USBD_FAIL;
  h->RxLength=USBD_LL_GetRxDataSize(d,ep);
  if(h->RxLength>64) return USBD_FAIL;
  interface(d)->Receive(h->RxBuffer,&h->RxLength);
  return USBD_OK;
}
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
const USBD_ClassTypeDef USBD_CDC
#else
USBD_ClassTypeDef USBD_CDC
#endif
= {
  cdc_init,cdc_deinit,cdc_setup,NULL,cdc_rx_ready,cdc_data_in,cdc_data_out,
  NULL,NULL,NULL,NULL,fs_descriptor,NULL,NULL
};
uint8_t USBD_CDC_RegisterInterface(USBD_HandleTypeDef* d,USBD_CDC_ItfTypeDef* api) {
  if(!api || d->classId!=0) return USBD_FAIL;
  d->pUserData[0]=api; return USBD_OK;
}
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef* d,uint8_t* data,uint32_t size) {
  USBD_CDC_HandleTypeDef* h=handle(d); if(!h || (!data && size)) return USBD_FAIL;
  h->TxBuffer=data; h->TxLength=size; return USBD_OK;
}
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef* d,uint8_t* data) {
  USBD_CDC_HandleTypeDef* h=handle(d); if(!h) return USBD_FAIL;
  h->RxBuffer=data; return USBD_OK;
}
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef* d) {
  USBD_CDC_HandleTypeDef* h=handle(d); if(!h) return USBD_FAIL;
  if(h->TxState) return USBD_BUSY;
  h->TxState=1; d->ep_in[CDC_IN_EP&15].total_length=h->TxLength;
  const uint8_t status=USBD_LL_Transmit(d,CDC_IN_EP,h->TxBuffer,h->TxLength);
  if(status!=USBD_OK) h->TxState=0;
  return status;
}
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef* d) {
  USBD_CDC_HandleTypeDef* h=handle(d); if(!h || !h->RxBuffer) return USBD_FAIL;
  return USBD_LL_PrepareReceive(d,CDC_OUT_EP,h->RxBuffer,64);
}
uint8_t USBD_CDC_ClearBuffer(USBD_HandleTypeDef* d) {
  // Completed OUT remains unarmed (NAK); the reader resumes once a block is free.
  return handle(d) ? USBD_OK : USBD_FAIL;
}
#endif
