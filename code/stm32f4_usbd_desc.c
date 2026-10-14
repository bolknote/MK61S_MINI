/**
  ******************************************************************************
  * @file    usbd_desc.c
  * @author  MCD Application Team
  * @brief   This file provides the USBD descriptors and string formatting method.
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
// Fixed Full Speed CDC descriptors; MSC reuses the same string scratch space.
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME && defined(USBCON)
#include <usbd_core.h>
#include <usbd_ctlreq.h>
#include <utils.h>
#include "stm32f4_usbd_desc.h"
#ifndef USB_MANUFACTURER_STRING
#define USB_MANUFACTURER_STRING "STMicroelectronics"
#endif
#ifndef USB_PRODUCT_STRING
#define USB_PRODUCT_STRING CONCATS(BOARD_NAME, "CDC in FS Mode")
#endif
#define CONFIG_TEXT CONCATS(BOARD_NAME, "CDC Config")
#define INTERFACE_TEXT CONCATS(BOARD_NAME, "CDC Interface")
_Static_assert(USBD_MAX_STR_DESC_SIZ == 64, "qualified EP0 string capacity");
_Static_assert(sizeof(USB_MANUFACTURER_STRING) <= 32, "manufacturer descriptor capacity");
_Static_assert(sizeof(USB_PRODUCT_STRING) <= 32, "product descriptor capacity");
_Static_assert(sizeof(CONFIG_TEXT) <= 32, "configuration descriptor capacity");
_Static_assert(sizeof(INTERFACE_TEXT) <= 32, "interface descriptor capacity");
__ALIGN_BEGIN uint8_t USBD_StrDesc[USBD_MAX_STR_DESC_SIZ] __ALIGN_END;
static const uint8_t device_desc[] = {
  18, USB_DESC_TYPE_DEVICE, 0, 2, 2, 2, 0, USB_MAX_EP0_SIZE,
  LOBYTE(USBD_VID), HIBYTE(USBD_VID), LOBYTE(USBD_PID), HIBYTE(USBD_PID),
  0, 2, USBD_IDX_MFC_STR, USBD_IDX_PRODUCT_STR, USBD_IDX_SERIAL_STR, 1
};
static const uint8_t language_desc[] = {4, USB_DESC_TYPE_STRING, 9, 4};
static uint8_t* device(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); *length = sizeof(device_desc); return (uint8_t*)device_desc;
}
static uint8_t* language(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); *length = sizeof(language_desc); return (uint8_t*)language_desc;
}
static uint8_t* text(const char* value, uint16_t* length) {
  USBD_GetString((uint8_t*)value, USBD_StrDesc, length); return USBD_StrDesc;
}
static uint8_t* manufacturer(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); return text(USB_MANUFACTURER_STRING, length);
}
static uint8_t* product(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); return text(USB_PRODUCT_STRING, length);
}
static void hex_unicode(uint32_t value, uint8_t* out, unsigned count) {
  for(unsigned i = 0; i < count; ++i, value <<= 4) {
    unsigned digit = value >> 28;
    out[2*i] = (uint8_t)(digit < 10 ? '0' + digit : 'A' + digit - 10);
    out[2*i+1] = 0;
  }
}
static uint8_t* serial(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); *length = 26;
  USBD_StrDesc[0] = 26; USBD_StrDesc[1] = USB_DESC_TYPE_STRING;
  const uint32_t first = *(const uint32_t*)DEVICE_ID1 + *(const uint32_t*)DEVICE_ID3;
  memset(USBD_StrDesc + 2, 0, 24);
  if(first) {
    hex_unicode(first, USBD_StrDesc + 2, 8);
    hex_unicode(*(const uint32_t*)DEVICE_ID2, USBD_StrDesc + 18, 4);
  }
  return USBD_StrDesc;
}
static uint8_t* configuration(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); return text(CONFIG_TEXT, length);
}
static uint8_t* interface(USBD_SpeedTypeDef speed, uint16_t* length) {
  UNUSED(speed); return text(INTERFACE_TEXT, length);
}
const USBD_DescriptorsTypeDef mk61_usb_descriptors = {
  device, language, manufacturer, product, serial, configuration, interface
};
#endif
