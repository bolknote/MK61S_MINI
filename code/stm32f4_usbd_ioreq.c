/* Endpoint-zero stages compatible with ST USB Device requests; ST copyright,
 * derived protocol sequencing under STM32_USB_MIDDLEWARE_LICENSE.txt. */
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME && defined(USBCON)
#include <usbd_ioreq.h>
#include <usbd_core.h>
USBD_StatusTypeDef USBD_CtlSendData(USBD_HandleTypeDef* d,uint8_t* buffer,uint32_t size) {
  d->ep0_state=USBD_EP0_DATA_IN;d->ep_in[0].total_length=size;d->ep_in[0].rem_length=size;
  return USBD_LL_Transmit(d,0,buffer,size);
}
USBD_StatusTypeDef USBD_CtlContinueSendData(USBD_HandleTypeDef* d,uint8_t* buffer,uint32_t size) {return USBD_LL_Transmit(d,0,buffer,size);}
USBD_StatusTypeDef USBD_CtlPrepareRx(USBD_HandleTypeDef* d,uint8_t* buffer,uint32_t size) {
  d->ep0_state=USBD_EP0_DATA_OUT;d->ep_out[0].total_length=size;d->ep_out[0].rem_length=size;
  return USBD_LL_PrepareReceive(d,0,buffer,size);
}
USBD_StatusTypeDef USBD_CtlContinueRx(USBD_HandleTypeDef* d,uint8_t* buffer,uint32_t size) {return USBD_LL_PrepareReceive(d,0,buffer,size);}
USBD_StatusTypeDef USBD_CtlSendStatus(USBD_HandleTypeDef* d) {d->ep0_state=USBD_EP0_STATUS_IN;return USBD_LL_Transmit(d,0,NULL,0);}
USBD_StatusTypeDef USBD_CtlReceiveStatus(USBD_HandleTypeDef* d) {d->ep0_state=USBD_EP0_STATUS_OUT;return USBD_LL_PrepareReceive(d,0,NULL,0);}
#endif
