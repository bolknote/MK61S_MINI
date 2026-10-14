/* Single-instance Full Speed CDC/MSC control engine.
 * Endpoint-zero sequencing derived from ST's USB Device core; copyright
 * STMicroelectronics, license in STM32_USB_MIDDLEWARE_LICENSE.txt.
 * Only one mutually-exclusive class is active. No composite, HS or ISO path.
 */
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME && defined(USBCON)
#include <usbd_core.h>
#include <usbd_ctlreq.h>
#include <usbd_ioreq.h>
static USBD_ClassTypeDef* active(USBD_HandleTypeDef* d) {return d->pClass[0];}
static USBD_StatusTypeDef deinit_class(USBD_HandleTypeDef* d) {
  d->classId=0;
  return active(d)&&active(d)->DeInit?(USBD_StatusTypeDef)active(d)->DeInit(d,(uint8_t)d->dev_config):USBD_OK;
}
USBD_StatusTypeDef USBD_Init(USBD_HandleTypeDef* d,USBD_DescriptorsTypeDef* desc,uint8_t id) {
  if(!d||!desc)return USBD_FAIL;
  d->pClass[0]=NULL;d->pUserData[0]=NULL;d->pConfDesc=NULL;d->pDesc=desc;
  d->NumClasses=0;d->classId=0;d->id=id;d->dev_speed=USBD_SPEED_FULL;
  d->dev_state=USBD_STATE_DEFAULT;d->dev_config=0;d->dev_address=0;
  return USBD_LL_Init(d);
}
USBD_StatusTypeDef USBD_DeInit(USBD_HandleTypeDef* d) {
  if(!d)return USBD_FAIL;
  (void)USBD_LL_Stop(d);d->dev_state=USBD_STATE_DEFAULT;(void)deinit_class(d);
  d->pUserData[0]=NULL;d->pDesc=NULL;d->pConfDesc=NULL;
  return USBD_LL_DeInit(d);
}
USBD_StatusTypeDef USBD_RegisterClass(USBD_HandleTypeDef* d,USBD_ClassTypeDef* cls) {
  if(!d||!cls||!cls->GetFSConfigDescriptor)return USBD_FAIL;
  uint16_t length=0;d->pClass[0]=cls;d->classId=0;
  d->pConfDesc=cls->GetFSConfigDescriptor(&length);d->NumClasses=1;
  return d->pConfDesc&&length>=USB_LEN_CFG_DESC?USBD_OK:USBD_FAIL;
}
USBD_StatusTypeDef USBD_Start(USBD_HandleTypeDef* d) {return USBD_LL_Start(d);}
USBD_StatusTypeDef USBD_Stop(USBD_HandleTypeDef* d) {(void)USBD_LL_Stop(d);return deinit_class(d);}
USBD_StatusTypeDef USBD_SetClassConfig(USBD_HandleTypeDef* d,uint8_t config) {
  d->classId=0;return active(d)&&active(d)->Init?(USBD_StatusTypeDef)active(d)->Init(d,config):USBD_FAIL;
}
USBD_StatusTypeDef USBD_ClrClassConfig(USBD_HandleTypeDef* d,uint8_t config) {
  d->classId=0;return active(d)&&active(d)->DeInit?(USBD_StatusTypeDef)active(d)->DeInit(d,config):USBD_FAIL;
}
uint8_t USBD_CoreFindIF(USBD_HandleTypeDef* d,uint8_t index) {
  return d->pConfDesc && index<((uint8_t*)d->pConfDesc)[4]?0:0xFF;
}
uint8_t USBD_CoreFindEP(USBD_HandleTypeDef* d,uint8_t address) {
  unsigned n=address&0x7F;
  if(n>=MK61_USBD_ENDPOINTS)return 0xFF;
  return (address&0x80?d->ep_in[n].is_used:d->ep_out[n].is_used)?0:0xFF;
}
USBD_StatusTypeDef USBD_LL_SetupStage(USBD_HandleTypeDef* d,uint8_t* setup) {
  USBD_ParseSetupRequest(&d->request,setup);d->ep0_state=USBD_EP0_SETUP;d->ep0_data_len=d->request.wLength;
  switch(d->request.bmRequest&0x1F) {
    case USB_REQ_RECIPIENT_DEVICE:return USBD_StdDevReq(d,&d->request);
    case USB_REQ_RECIPIENT_INTERFACE:return USBD_StdItfReq(d,&d->request);
    case USB_REQ_RECIPIENT_ENDPOINT:return USBD_StdEPReq(d,&d->request);
    default:return USBD_LL_StallEP(d,d->request.bmRequest&0x80);
  }
}
USBD_StatusTypeDef USBD_LL_DataOutStage(USBD_HandleTypeDef* d,uint8_t n,uint8_t* data) {
  if(n>=MK61_USBD_ENDPOINTS)return USBD_FAIL;
  if(!n) {
    USBD_EndpointTypeDef* ep=&d->ep_out[0];
    if(d->ep0_state==USBD_EP0_DATA_OUT) {
      if(ep->rem_length>ep->maxpacket) {
        ep->rem_length-=ep->maxpacket;
        return USBD_CtlContinueRx(d,data,MIN(ep->rem_length,ep->maxpacket));
      }
      if(d->dev_state==USBD_STATE_CONFIGURED && active(d) && active(d)->EP0_RxReady) {
        d->classId=0;active(d)->EP0_RxReady(d);
      }
      return USBD_CtlSendStatus(d);
    }
  } else if(d->dev_state==USBD_STATE_CONFIGURED && USBD_CoreFindEP(d,n)==0 && active(d)&&active(d)->DataOut) {
    d->classId=0;return (USBD_StatusTypeDef)active(d)->DataOut(d,n);
  }
  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_DataInStage(USBD_HandleTypeDef* d,uint8_t n,uint8_t* data) {
  if(n>=MK61_USBD_ENDPOINTS)return USBD_FAIL;
  if(!n) {
    USBD_EndpointTypeDef* ep=&d->ep_in[0];
    if(d->ep0_state==USBD_EP0_DATA_IN) {
      if(ep->rem_length>ep->maxpacket) {
        ep->rem_length-=ep->maxpacket;(void)USBD_CtlContinueSendData(d,data,ep->rem_length);
        (void)USBD_LL_PrepareReceive(d,0,NULL,0);
      } else if(ep->maxpacket==ep->rem_length && ep->total_length>=ep->maxpacket && ep->total_length<d->ep0_data_len) {
        (void)USBD_CtlContinueSendData(d,NULL,0);d->ep0_data_len=0;(void)USBD_LL_PrepareReceive(d,0,NULL,0);
      } else {
        if(d->dev_state==USBD_STATE_CONFIGURED && active(d)&&active(d)->EP0_TxSent) {
          d->classId=0;active(d)->EP0_TxSent(d);
        }
        (void)USBD_LL_StallEP(d,0x80);(void)USBD_CtlReceiveStatus(d);
      }
    }
  } else if(d->dev_state==USBD_STATE_CONFIGURED && USBD_CoreFindEP(d,n|0x80)==0 && active(d)&&active(d)->DataIn) {
    d->classId=0;return (USBD_StatusTypeDef)active(d)->DataIn(d,n);
  }
  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_Reset(USBD_HandleTypeDef* d) {
  d->dev_state=USBD_STATE_DEFAULT;d->ep0_state=USBD_EP0_IDLE;d->dev_config=0;
  d->dev_remote_wakeup=0;d->dev_test_mode=0;d->classId=0;
  USBD_StatusTypeDef result=deinit_class(d);
  (void)USBD_LL_OpenEP(d,0,USBD_EP_TYPE_CTRL,USB_MAX_EP0_SIZE);
  d->ep_out[0].is_used=1;d->ep_out[0].maxpacket=USB_MAX_EP0_SIZE;
  (void)USBD_LL_OpenEP(d,0x80,USBD_EP_TYPE_CTRL,USB_MAX_EP0_SIZE);
  d->ep_in[0].is_used=1;d->ep_in[0].maxpacket=USB_MAX_EP0_SIZE;
  return result;
}
USBD_StatusTypeDef USBD_LL_SetSpeed(USBD_HandleTypeDef* d,USBD_SpeedTypeDef speed) {UNUSED(speed);d->dev_speed=USBD_SPEED_FULL;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_Suspend(USBD_HandleTypeDef* d) {
  if(d->dev_state!=USBD_STATE_SUSPENDED)d->dev_old_state=d->dev_state;
  d->dev_state=USBD_STATE_SUSPENDED;return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_Resume(USBD_HandleTypeDef* d) {if(d->dev_state==USBD_STATE_SUSPENDED)d->dev_state=d->dev_old_state;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_SOF(USBD_HandleTypeDef* d) {UNUSED(d);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_DevConnected(USBD_HandleTypeDef* d) {UNUSED(d);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_DevDisconnected(USBD_HandleTypeDef* d) {d->dev_state=USBD_STATE_DEFAULT;return deinit_class(d);}
USBD_StatusTypeDef USBD_RunTestMode(USBD_HandleTypeDef* d) {UNUSED(d);return USBD_FAIL;}
#endif
