/* STM32F401/F411 OTG FS device registers, four endpoints, embedded PHY.
 * Reset/FIFO/endpoint sequences derived from STM32F4 LL USB, copyright
 * STMicroelectronics. Attribution/license: STM32_USB_LL_LICENSE.txt.
 * Private ST-compatible signatures keep the existing bridge boundary. No
 * host, ULPI, HS, DMA or isochronous implementation is included.
 */
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME && defined(USBCON)
#include <stm32f4xx_ll_usb.h>
extern void HAL_Delay(uint32_t);
#define FS USB_OTG_FS
#define DEV ((USB_OTG_DeviceTypeDef*)(USB_OTG_FS_PERIPH_BASE+USB_OTG_DEVICE_BASE))
#define IN(n) ((USB_OTG_INEndpointTypeDef*)(USB_OTG_FS_PERIPH_BASE+USB_OTG_IN_ENDPOINT_BASE+(n)*USB_OTG_EP_REG_SIZE))
#define OUT(n) ((USB_OTG_OUTEndpointTypeDef*)(USB_OTG_FS_PERIPH_BASE+USB_OTG_OUT_ENDPOINT_BASE+(n)*USB_OTG_EP_REG_SIZE))
#define PHY_CLOCK (*(volatile uint32_t*)(USB_OTG_FS_PERIPH_BASE+USB_OTG_PCGCCTL_BASE))
enum {ENDPOINTS=4,POLL_LIMIT=200000};
static HAL_StatusTypeDef wait_reset(uint32_t mask,uint32_t expected) {
  for(unsigned count=0;count<POLL_LIMIT;++count)if((FS->GRSTCTL&mask)==expected)return HAL_OK;
  return HAL_TIMEOUT;
}
static HAL_StatusTypeDef core_reset(void) {
  if(wait_reset(USB_OTG_GRSTCTL_AHBIDL,USB_OTG_GRSTCTL_AHBIDL)!=HAL_OK)return HAL_TIMEOUT;
  for(volatile unsigned count=10;count;--count) {}
  FS->GRSTCTL|=USB_OTG_GRSTCTL_CSRST;
  return wait_reset(USB_OTG_GRSTCTL_CSRST,0);
}
HAL_StatusTypeDef USB_CoreInit(USB_OTG_GlobalTypeDef* instance,USB_OTG_CfgTypeDef cfg) {
  UNUSED(instance);UNUSED(cfg);
  FS->GUSBCFG|=USB_OTG_GUSBCFG_PHYSEL;
  HAL_StatusTypeDef result=core_reset();
  FS->GCCFG|=USB_OTG_GCCFG_PWRDWN;
  return result;
}
HAL_StatusTypeDef USB_SetCurrentMode(USB_OTG_GlobalTypeDef* instance,USB_OTG_ModeTypeDef mode) {
  UNUSED(instance);UNUSED(mode);
  FS->GUSBCFG=(FS->GUSBCFG&~(USB_OTG_GUSBCFG_FHMOD|USB_OTG_GUSBCFG_FDMOD))|USB_OTG_GUSBCFG_FDMOD;
  for(unsigned elapsed=0;elapsed<200;elapsed+=10) {
    HAL_Delay(10);
    if(!(FS->GINTSTS&USB_OTG_GINTSTS_CMOD))return HAL_OK;
  }
  return HAL_TIMEOUT;
}
HAL_StatusTypeDef USB_FlushTxFifo(USB_OTG_GlobalTypeDef* instance,uint32_t number) {
  UNUSED(instance);
  if(wait_reset(USB_OTG_GRSTCTL_AHBIDL,USB_OTG_GRSTCTL_AHBIDL)!=HAL_OK)return HAL_TIMEOUT;
  FS->GRSTCTL=USB_OTG_GRSTCTL_TXFFLSH|(number<<6);
  return wait_reset(USB_OTG_GRSTCTL_TXFFLSH,0);
}
HAL_StatusTypeDef USB_FlushRxFifo(USB_OTG_GlobalTypeDef* instance) {
  UNUSED(instance);
  if(wait_reset(USB_OTG_GRSTCTL_AHBIDL,USB_OTG_GRSTCTL_AHBIDL)!=HAL_OK)return HAL_TIMEOUT;
  FS->GRSTCTL=USB_OTG_GRSTCTL_RXFFLSH;
  return wait_reset(USB_OTG_GRSTCTL_RXFFLSH,0);
}
HAL_StatusTypeDef USB_DevInit(USB_OTG_GlobalTypeDef* instance,USB_OTG_CfgTypeDef cfg) {
  UNUSED(instance);UNUSED(cfg);
  for(unsigned i=0;i<ENDPOINTS-1;++i)FS->DIEPTXF[i]=0;
  DEV->DCTL|=USB_OTG_DCTL_SDIS;
  FS->GCCFG=(FS->GCCFG|USB_OTG_GCCFG_NOVBUSSENS)&~(USB_OTG_GCCFG_VBUSBSEN|USB_OTG_GCCFG_VBUSASEN);
  PHY_CLOCK=0;DEV->DCFG=(DEV->DCFG&~USB_OTG_DCFG_DSPD)|USB_OTG_SPEED_FULL;
  HAL_StatusTypeDef result=HAL_OK;
  if(USB_FlushTxFifo(FS,0x10)!=HAL_OK)result=HAL_ERROR;
  if(USB_FlushRxFifo(FS)!=HAL_OK)result=HAL_ERROR;
  DEV->DIEPMSK=0;DEV->DOEPMSK=0;DEV->DAINTMSK=0;
  for(unsigned i=0;i<ENDPOINTS;++i) {
    IN(i)->DIEPCTL=(IN(i)->DIEPCTL&USB_OTG_DIEPCTL_EPENA)?USB_OTG_DIEPCTL_SNAK|(i?USB_OTG_DIEPCTL_EPDIS:0):0;
    IN(i)->DIEPTSIZ=0;IN(i)->DIEPINT=0xFB7F;
    OUT(i)->DOEPCTL=(OUT(i)->DOEPCTL&USB_OTG_DOEPCTL_EPENA)?USB_OTG_DOEPCTL_SNAK|(i?USB_OTG_DOEPCTL_EPDIS:0):0;
    OUT(i)->DOEPTSIZ=0;OUT(i)->DOEPINT=0xFB7F;
  }
  FS->GINTMSK=0;FS->GINTSTS=0xBFFFFFFF;
  FS->GINTMSK=USB_OTG_GINTMSK_RXFLVLM|USB_OTG_GINTMSK_USBSUSPM|USB_OTG_GINTMSK_USBRST|
      USB_OTG_GINTMSK_ENUMDNEM|USB_OTG_GINTMSK_IEPINT|USB_OTG_GINTMSK_OEPINT|USB_OTG_GINTMSK_WUIM;
  return result;
}
HAL_StatusTypeDef USB_EnableGlobalInt(USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);FS->GAHBCFG|=USB_OTG_GAHBCFG_GINT;return HAL_OK;}
HAL_StatusTypeDef USB_DisableGlobalInt(USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);FS->GAHBCFG&=~USB_OTG_GAHBCFG_GINT;return HAL_OK;}
HAL_StatusTypeDef USB_SetTurnaroundTime(USB_OTG_GlobalTypeDef* instance,uint32_t clock,uint8_t speed) {
  UNUSED(instance);UNUSED(clock);UNUSED(speed); // Both qualified HCLKs (84/96MHz) use TRDT=6.
  FS->GUSBCFG=(FS->GUSBCFG&~USB_OTG_GUSBCFG_TRDT)|(6U<<10);return HAL_OK;
}
uint8_t USB_GetDevSpeed(const USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);return USBD_FS_SPEED;}
uint32_t USB_GetMode(const USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);return FS->GINTSTS&USB_OTG_GINTSTS_CMOD;}
uint32_t USB_ReadInterrupts(const USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);return FS->GINTSTS&FS->GINTMSK;}
uint32_t USB_ReadDevAllOutEpInterrupt(const USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);return (DEV->DAINT&DEV->DAINTMSK)>>16;}
uint32_t USB_ReadDevAllInEpInterrupt(const USB_OTG_GlobalTypeDef* instance) {UNUSED(instance);return DEV->DAINT&DEV->DAINTMSK&0xFFFF;}
uint32_t USB_ReadDevOutEPInterrupt(const USB_OTG_GlobalTypeDef* instance,uint8_t n) {UNUSED(instance);return OUT(n)->DOEPINT&DEV->DOEPMSK;}
uint32_t USB_ReadDevInEPInterrupt(const USB_OTG_GlobalTypeDef* instance,uint8_t n) {
  UNUSED(instance);return IN(n)->DIEPINT&(DEV->DIEPMSK|(((DEV->DIEPEMPMSK>>n)&1U)<<7));
}
HAL_StatusTypeDef USB_ActivateEndpoint(const USB_OTG_GlobalTypeDef* instance,const USB_OTG_EPTypeDef* ep) {
  UNUSED(instance);const unsigned n=ep->num;
  if(ep->is_in) {
    DEV->DAINTMSK|=1U<<n;
    if(!(IN(n)->DIEPCTL&USB_OTG_DIEPCTL_USBAEP))IN(n)->DIEPCTL|=(ep->maxpacket&USB_OTG_DIEPCTL_MPSIZ)|
        ((uint32_t)ep->type<<18)|(n<<22)|USB_OTG_DIEPCTL_SD0PID_SEVNFRM|USB_OTG_DIEPCTL_USBAEP;
  } else {
    DEV->DAINTMSK|=1U<<(16+n);
    if(!(OUT(n)->DOEPCTL&USB_OTG_DOEPCTL_USBAEP))OUT(n)->DOEPCTL|=(ep->maxpacket&USB_OTG_DOEPCTL_MPSIZ)|
        ((uint32_t)ep->type<<18)|USB_OTG_DOEPCTL_SD0PID_SEVNFRM|USB_OTG_DOEPCTL_USBAEP;
  }
  return HAL_OK;
}
HAL_StatusTypeDef USB_DeactivateEndpoint(const USB_OTG_GlobalTypeDef* instance,const USB_OTG_EPTypeDef* ep) {
  UNUSED(instance);const unsigned n=ep->num;
  if(ep->is_in) {
    if(IN(n)->DIEPCTL&USB_OTG_DIEPCTL_EPENA)IN(n)->DIEPCTL|=USB_OTG_DIEPCTL_SNAK|USB_OTG_DIEPCTL_EPDIS;
    DEV->DEACHMSK&=~(1U<<n);DEV->DAINTMSK&=~(1U<<n);
    IN(n)->DIEPCTL&=~(USB_OTG_DIEPCTL_USBAEP|USB_OTG_DIEPCTL_MPSIZ|USB_OTG_DIEPCTL_TXFNUM|USB_OTG_DIEPCTL_SD0PID_SEVNFRM|USB_OTG_DIEPCTL_EPTYP);
  } else {
    if(OUT(n)->DOEPCTL&USB_OTG_DOEPCTL_EPENA)OUT(n)->DOEPCTL|=USB_OTG_DOEPCTL_SNAK|USB_OTG_DOEPCTL_EPDIS;
    DEV->DEACHMSK&=~(1U<<(16+n));DEV->DAINTMSK&=~(1U<<(16+n));
    OUT(n)->DOEPCTL&=~(USB_OTG_DOEPCTL_USBAEP|USB_OTG_DOEPCTL_MPSIZ|USB_OTG_DOEPCTL_SD0PID_SEVNFRM|USB_OTG_DOEPCTL_EPTYP);
  }
  return HAL_OK;
}
HAL_StatusTypeDef USB_EPStartXfer(USB_OTG_GlobalTypeDef* instance,USB_OTG_EPTypeDef* ep,uint8_t dma) {
  UNUSED(instance);UNUSED(dma);const unsigned n=ep->num;
  if(ep->is_in) {
    uint32_t count=ep->xfer_len?(ep->xfer_len+ep->maxpacket-1U)/ep->maxpacket:1U;
    if(!n)count=1;
    IN(n)->DIEPTSIZ=(IN(n)->DIEPTSIZ&~(USB_OTG_DIEPTSIZ_PKTCNT|USB_OTG_DIEPTSIZ_XFRSIZ))|
        ((count<<19)&USB_OTG_DIEPTSIZ_PKTCNT)|(ep->xfer_len&USB_OTG_DIEPTSIZ_XFRSIZ);
    IN(n)->DIEPCTL|=USB_OTG_DIEPCTL_CNAK|USB_OTG_DIEPCTL_EPENA;
    if(ep->xfer_len)DEV->DIEPEMPMSK|=1U<<n;
  } else {
    const uint32_t count=(!n||!ep->xfer_len)?1U:(ep->xfer_len+ep->maxpacket-1U)/ep->maxpacket;
    ep->xfer_size=count*ep->maxpacket;
    OUT(n)->DOEPTSIZ=(OUT(n)->DOEPTSIZ&~(USB_OTG_DOEPTSIZ_PKTCNT|USB_OTG_DOEPTSIZ_XFRSIZ))|
        ((count<<19)&USB_OTG_DOEPTSIZ_PKTCNT)|(ep->xfer_size&USB_OTG_DOEPTSIZ_XFRSIZ);
    OUT(n)->DOEPCTL|=USB_OTG_DOEPCTL_CNAK|USB_OTG_DOEPCTL_EPENA;
  }
  return HAL_OK;
}
HAL_StatusTypeDef USB_EPSetStall(const USB_OTG_GlobalTypeDef* instance,const USB_OTG_EPTypeDef* ep) {
  UNUSED(instance);const unsigned n=ep->num;
  if(ep->is_in) {
    if(n && !(IN(n)->DIEPCTL&USB_OTG_DIEPCTL_EPENA))IN(n)->DIEPCTL&=~USB_OTG_DIEPCTL_EPDIS;
    IN(n)->DIEPCTL|=USB_OTG_DIEPCTL_STALL;
  } else {
    if(n && !(OUT(n)->DOEPCTL&USB_OTG_DOEPCTL_EPENA))OUT(n)->DOEPCTL&=~USB_OTG_DOEPCTL_EPDIS;
    OUT(n)->DOEPCTL|=USB_OTG_DOEPCTL_STALL;
  }
  return HAL_OK;
}
HAL_StatusTypeDef USB_EPClearStall(const USB_OTG_GlobalTypeDef* instance,const USB_OTG_EPTypeDef* ep) {
  UNUSED(instance);const unsigned n=ep->num;
  const uint32_t reset=ep->type==EP_TYPE_BULK||ep->type==EP_TYPE_INTR?USB_OTG_DIEPCTL_SD0PID_SEVNFRM:0;
  if(ep->is_in)IN(n)->DIEPCTL=(IN(n)->DIEPCTL&~USB_OTG_DIEPCTL_STALL)|reset;
  else OUT(n)->DOEPCTL=(OUT(n)->DOEPCTL&~USB_OTG_DOEPCTL_STALL)|reset;
  return HAL_OK;
}
HAL_StatusTypeDef USB_StopDevice(USB_OTG_GlobalTypeDef* instance) {
  UNUSED(instance);
  for(unsigned n=0;n<ENDPOINTS;++n) {IN(n)->DIEPINT=0xFB7F;OUT(n)->DOEPINT=0xFB7F;}
  DEV->DIEPMSK=0;DEV->DOEPMSK=0;DEV->DAINTMSK=0;
  HAL_StatusTypeDef result=USB_FlushRxFifo(FS);return result==HAL_OK?USB_FlushTxFifo(FS,0x10):result;
}
HAL_StatusTypeDef USB_SetDevAddress(const USB_OTG_GlobalTypeDef* instance,uint8_t address) {
  UNUSED(instance);DEV->DCFG=(DEV->DCFG&~USB_OTG_DCFG_DAD)|(((uint32_t)address<<4)&USB_OTG_DCFG_DAD);return HAL_OK;
}
HAL_StatusTypeDef USB_DevConnect(const USB_OTG_GlobalTypeDef* instance) {
  UNUSED(instance);PHY_CLOCK&=~(USB_OTG_PCGCCTL_STOPCLK|USB_OTG_PCGCCTL_GATECLK);DEV->DCTL&=~USB_OTG_DCTL_SDIS;return HAL_OK;
}
HAL_StatusTypeDef USB_DevDisconnect(const USB_OTG_GlobalTypeDef* instance) {
  UNUSED(instance);PHY_CLOCK&=~(USB_OTG_PCGCCTL_STOPCLK|USB_OTG_PCGCCTL_GATECLK);DEV->DCTL|=USB_OTG_DCTL_SDIS;return HAL_OK;
}
HAL_StatusTypeDef USB_ActivateSetup(const USB_OTG_GlobalTypeDef* instance) {
  UNUSED(instance);IN(0)->DIEPCTL&=~USB_OTG_DIEPCTL_MPSIZ;DEV->DCTL|=USB_OTG_DCTL_CGINAK;return HAL_OK;
}
HAL_StatusTypeDef USB_EP0_OutStart(const USB_OTG_GlobalTypeDef* instance,uint8_t dma,const uint8_t* setup) {
  UNUSED(instance);UNUSED(dma);UNUSED(setup);
  const uint32_t revision=*(volatile const uint32_t*)(USB_OTG_FS_PERIPH_BASE+0x40);
  if(revision>USB_OTG_CORE_ID_300A && (OUT(0)->DOEPCTL&USB_OTG_DOEPCTL_EPENA))return HAL_OK;
  OUT(0)->DOEPTSIZ=(1U<<19)|24U|USB_OTG_DOEPTSIZ_STUPCNT;return HAL_OK;
}
#endif
