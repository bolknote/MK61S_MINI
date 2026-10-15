/* Standard USB requests for the single Full Speed CDC/MSC device.
 * Derived from STMicroelectronics usbd_ctlreq.c, Copyright (c) 2015 STMicroelectronics.
 * All rights reserved. License: STM32_USB_MIDDLEWARE_LICENSE.txt.
 * USB 2.0 chapter 9: one configuration, alternate setting zero, no HS/BOS,
 * composite routing, remote wakeup or test mode. Both descriptors advertise
 * the same self-powered status and no remote-wakeup capability.
 */
#if defined(MK61_USB_BUILD_CTLREQ) && defined(USBCON)
#include <usbd_ctlreq.h>
#include <usbd_ioreq.h>

#ifndef USBD_MAX_STR_DESC_SIZ
#define USBD_MAX_STR_DESC_SIZ 64U
#endif

_Static_assert(USBD_MAX_SUPPORTED_CLASS == 1U && USBD_MAX_NUM_CONFIGURATION == 1U,
               "qualified single-class/single-configuration EP0");
_Static_assert(USBD_LPM_ENABLED == 0U && USBD_CLASS_BOS_ENABLED == 0U &&
               USBD_CLASS_USER_STRING_DESC == 0U && USBD_SUPPORT_USER_STRING_DESC == 0U,
               "qualified FS descriptors have no BOS or custom string extension");

static USBD_StatusTypeDef reject(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  USBD_CtlError(d, r);
  return USBD_FAIL;
}

static USBD_StatusTypeDef class_request(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  const USBD_ClassTypeDef *cls = d->pClass[0];
  d->classId = 0U;
  if (cls == NULL || cls->Setup == NULL || cls->Setup(d, r) != USBD_OK)
    return reject(d, r);
  return USBD_OK;
}

static USBD_StatusTypeDef descriptor(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  uint8_t *(*get)(USBD_SpeedTypeDef, uint16_t *) = NULL;
  uint8_t *data = NULL;
  uint16_t length = 0U;
  const USBD_DescriptorsTypeDef *desc = d->pDesc;
  if (desc == NULL) return reject(d, r);
  if ((r->wValue >> 8) == USB_DESC_TYPE_STRING) {
    switch ((uint8_t)r->wValue) {
      case USBD_IDX_LANGID_STR: get = desc->GetLangIDStrDescriptor; break;
      case USBD_IDX_MFC_STR: get = desc->GetManufacturerStrDescriptor; break;
      case USBD_IDX_PRODUCT_STR: get = desc->GetProductStrDescriptor; break;
      case USBD_IDX_SERIAL_STR: get = desc->GetSerialStrDescriptor; break;
      case USBD_IDX_CONFIG_STR: get = desc->GetConfigurationStrDescriptor; break;
      case USBD_IDX_INTERFACE_STR: get = desc->GetInterfaceStrDescriptor; break;
      default: return reject(d, r);
    }
  } else {
    // Only device/configuration index zero exists. wIndex is not a LANGID here.
    if ((uint8_t)r->wValue != 0U || r->wIndex != 0U) return reject(d, r);
    if (r->wValue == (USB_DESC_TYPE_DEVICE << 8)) get = desc->GetDeviceDescriptor;
    else if (r->wValue == (USB_DESC_TYPE_CONFIGURATION << 8)) {
      data = (uint8_t *)d->pConfDesc;
      if (data != NULL) length = (uint16_t)(data[2] | ((uint16_t)data[3] << 8));
    }
  }
  if (get != NULL) data = get(USBD_SPEED_FULL, &length);
  if (data == NULL || length == 0U) return reject(d, r);
  if (r->wLength == 0U) return USBD_CtlSendStatus(d);
  return USBD_CtlSendData(d, data, MIN(length, r->wLength));
}

USBD_StatusTypeDef USBD_StdDevReq(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  if (d->dev_state != USBD_STATE_DEFAULT && d->dev_state != USBD_STATE_ADDRESSED &&
      d->dev_state != USBD_STATE_CONFIGURED) return reject(d, r);
  if (r->bmRequest == 0x80U) {
    if (r->bRequest == USB_REQ_GET_DESCRIPTOR) return descriptor(d, r);
    if (r->wValue != 0U || r->wIndex != 0U) return reject(d, r);
    if (r->bRequest == USB_REQ_GET_CONFIGURATION && r->wLength == 1U)
      return USBD_CtlSendData(d, (uint8_t *)&d->dev_config, 1U);
    if (r->bRequest == USB_REQ_GET_STATUS && r->wLength == 2U) {
      d->dev_config_status = USBD_SELF_POWERED ? USB_CONFIG_SELF_POWERED : 0U;
      return USBD_CtlSendData(d, (uint8_t *)&d->dev_config_status, 2U);
    }
  } else if (r->bmRequest == 0U && r->wIndex == 0U && r->wLength == 0U) {
    if (r->bRequest == USB_REQ_SET_ADDRESS && r->wValue < 128U &&
        d->dev_state != USBD_STATE_CONFIGURED) {
      d->dev_address = (uint8_t)r->wValue;
      (void)USBD_LL_SetUSBAddress(d, d->dev_address);
      d->dev_state = r->wValue ? USBD_STATE_ADDRESSED : USBD_STATE_DEFAULT;
      return USBD_CtlSendStatus(d);
    }
    if (r->bRequest == USB_REQ_SET_CONFIGURATION && r->wValue <= 1U &&
        d->dev_state != USBD_STATE_DEFAULT) {
      // Reselecting configuration 1 also resets endpoint halt/toggle state.
      if (d->dev_state == USBD_STATE_CONFIGURED)
        (void)USBD_ClrClassConfig(d, (uint8_t)d->dev_config);
      d->dev_config = 0U;
      d->dev_state = USBD_STATE_ADDRESSED;
      if (r->wValue != 0U) {
        if (USBD_SetClassConfig(d, 1U) != USBD_OK) {
          (void)USBD_ClrClassConfig(d, 1U);
          return reject(d, r);
        }
        d->dev_config = 1U;
        d->dev_state = USBD_STATE_CONFIGURED;
      }
      return USBD_CtlSendStatus(d);
    }
  }
  return reject(d, r);
}

USBD_StatusTypeDef USBD_StdItfReq(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  // CDC has interfaces 0/1, MSC only 0. Never truncate the host's 16-bit index.
  const uint8_t *config = (const uint8_t *)d->pConfDesc;
  if (d->dev_state != USBD_STATE_CONFIGURED || config == NULL ||
      r->wIndex >= config[4] || (r->bmRequest & USB_REQ_TYPE_MASK) == USB_REQ_TYPE_VENDOR ||
      (r->bmRequest & USB_REQ_TYPE_MASK) == USB_REQ_TYPE_MASK)
    return reject(d, r);
  if (class_request(d, r) != USBD_OK) return USBD_FAIL;
  return r->wLength == 0U ? USBD_CtlSendStatus(d) : USBD_OK;
}

USBD_StatusTypeDef USBD_StdEPReq(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  const unsigned number = r->wIndex & 15U;
  const uint8_t address = (uint8_t)r->wIndex;
  // Check reserved bits before indexing either four-entry endpoint array.
  if ((r->wIndex & 0xFF70U) != 0U || number >= MK61_USBD_ENDPOINTS)
    return reject(d, r);
  USBD_EndpointTypeDef *ep = (address & 0x80U) ? &d->ep_in[number] : &d->ep_out[number];
  if (d->dev_state != USBD_STATE_CONFIGURED) {
    if (d->dev_state != USBD_STATE_ADDRESSED || number != 0U) return reject(d, r);
  } else if (ep->is_used == 0U) return reject(d, r);
  if (r->bmRequest == 0x82U && r->bRequest == USB_REQ_GET_STATUS &&
      r->wValue == 0U && r->wLength == 2U) {
    ep->status = number != 0U && USBD_LL_IsStallEP(d, address) != 0U;
    return USBD_CtlSendData(d, (uint8_t *)&ep->status, 2U);
  }
  if (r->bmRequest == 0x02U && r->wValue == USB_FEATURE_EP_HALT &&
      r->wLength == 0U && number != 0U) {
    if (r->bRequest == USB_REQ_SET_FEATURE) (void)USBD_LL_StallEP(d, address);
    else if (r->bRequest == USB_REQ_CLEAR_FEATURE) {
      (void)USBD_LL_ClearStallEP(d, address);
      // Only MSC needs a BOT reset-recovery notification. CDC has no HALT
      // callback; its Setup handles interface requests, not endpoint requests.
      const uint8_t *config = (const uint8_t *)d->pConfDesc;
      if (config != NULL && config[4] == 1U && class_request(d, r) != USBD_OK)
        return USBD_FAIL;
    } else return reject(d, r);
    return USBD_CtlSendStatus(d);
  }
  return reject(d, r);
}

void USBD_ParseSetupRequest(USBD_SetupReqTypedef *r, uint8_t *p)
{
  r->bmRequest = p[0];
  r->bRequest = p[1];
  r->wValue = (uint16_t)(p[2] | ((uint16_t)p[3] << 8));
  r->wIndex = (uint16_t)(p[4] | ((uint16_t)p[5] << 8));
  r->wLength = (uint16_t)(p[6] | ((uint16_t)p[7] << 8));
}

void USBD_CtlError(USBD_HandleTypeDef *d, USBD_SetupReqTypedef *r)
{
  (void)r;
  (void)USBD_LL_StallEP(d, 0x80U);
  (void)USBD_LL_StallEP(d, 0U);
}

void USBD_GetString(uint8_t *text, uint8_t *out, uint16_t *length)
{
  if (text == NULL || out == NULL || length == NULL) return;
  uint16_t bytes = 2U;
  while (*text != 0U && bytes + 2U <= USBD_MAX_STR_DESC_SIZ && bytes + 2U <= 254U) {
    out[bytes++] = *text++;
    out[bytes++] = 0U;
  }
  out[0] = (uint8_t)bytes;
  out[1] = USB_DESC_TYPE_STRING;
  *length = bytes;
}
#endif
