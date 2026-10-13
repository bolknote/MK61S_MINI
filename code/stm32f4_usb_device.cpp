#include "stm32f4_usb_device.hpp"
#if MK61_USB_DIRECT_SUPPORTED && defined(MK61_USB_BUILD_BRIDGE)
#include <stm32f4xx_ll_usb.h>
#include <cstring>
extern "C" {
#include <usbd_core.h>
#include <usbd_if.h>
void USBD_SystemClockConfigFromResume();
}
namespace {
constexpr unsigned ENDPOINTS = 4;
struct Endpoint {
  uint8_t* cursor;
  uint32_t length, count;
  uint16_t maxpacket;
  uint8_t type, stalled;
};
static Endpoint endpoints[2][ENDPOINTS];
static Endpoint (&out)[ENDPOINTS] = endpoints[0];
static Endpoint (&in)[ENDPOINTS] = endpoints[1];
static USBD_HandleTypeDef* device;
static uint32_t setup_words[2];
static volatile bool low_power;
static bool initialized;
struct InterruptGuard {
  uint32_t saved = __get_PRIMASK();
  InterruptGuard() { __disable_irq(); }
  ~InterruptGuard() { __set_PRIMASK(saved); }
};
inline USB_OTG_DeviceTypeDef* regs() {
  return reinterpret_cast<USB_OTG_DeviceTypeDef*>(USB_OTG_FS_PERIPH_BASE + USB_OTG_DEVICE_BASE);
}
inline USB_OTG_INEndpointTypeDef* input(unsigned n) {
  return reinterpret_cast<USB_OTG_INEndpointTypeDef*>(USB_OTG_FS_PERIPH_BASE + USB_OTG_IN_ENDPOINT_BASE + n*USB_OTG_EP_REG_SIZE);
}
inline USB_OTG_OUTEndpointTypeDef* output(unsigned n) {
  return reinterpret_cast<USB_OTG_OUTEndpointTypeDef*>(USB_OTG_FS_PERIPH_BASE + USB_OTG_OUT_ENDPOINT_BASE + n*USB_OTG_EP_REG_SIZE);
}
inline volatile uint32_t& fifo(unsigned n) {
  return *reinterpret_cast<volatile uint32_t*>(USB_OTG_FS_PERIPH_BASE + USB_OTG_FIFO_BASE + n*USB_OTG_FIFO_SIZE);
}
static Endpoint* endpoint(uint8_t address) {
  const unsigned n = address & 0x7FU;
  return n < ENDPOINTS ? &endpoints[(address >> 7U) & 1U][n] : nullptr;
}
static USB_OTG_EPTypeDef descriptor(uint8_t address, const Endpoint& ep) {
  USB_OTG_EPTypeDef result = {};
  result.num = address & 0x7FU; result.is_in = (address & 0x80U) != 0;
  result.is_stall = ep.stalled; result.type = ep.type;
  result.maxpacket = ep.maxpacket; result.tx_fifo_num = result.num;
  result.xfer_buff = ep.cursor; result.xfer_len = ep.length;
  return result;
}
static USBD_StatusTypeDef status(HAL_StatusTypeDef value) {
  return value == HAL_OK ? USBD_OK : USBD_FAIL;
}
static void tx_empty(unsigned n) {
  Endpoint& ep = in[n];
  while(ep.count < ep.length) {
    const uint32_t remaining = ep.length - ep.count;
    const uint32_t bytes = remaining > ep.maxpacket ? ep.maxpacket : remaining;
    if(ep.maxpacket == 0 || (input(n)->DTXFSTS & USB_OTG_DTXFSTS_INEPTFSAV) < (bytes+3U)/4U) break;
    for(uint32_t at = 0; at < bytes; at += 4) {
      uint32_t word = 0;
      const uint32_t part = bytes-at < 4 ? bytes-at : 4;
      std::memcpy(&word, ep.cursor+at, part); // never read beyond an unaligned short packet.
      fifo(n) = word;
    }
    ep.cursor += bytes; ep.count += bytes;
  }
  if(ep.count == ep.length) regs()->DIEPEMPMSK &= ~(1U << n);
}
static void rx_packet(unsigned n, unsigned kind, unsigned bytes) {
  Endpoint* ep = n < ENDPOINTS ? &out[n] : nullptr;
  uint8_t* target = kind == STS_SETUP_UPDT ? reinterpret_cast<uint8_t*>(setup_words) : (ep && kind == STS_DATA_UPDT ? ep->cursor : nullptr);
  const uint32_t capacity = kind == STS_SETUP_UPDT ? sizeof(setup_words) :
      (ep && ep->count < ep->length ? ep->length-ep->count : 0);
  const uint32_t copied = bytes < capacity ? bytes : capacity;
  for(unsigned at = 0; at < bytes; at += 4) {
    const uint32_t word = fifo(0);
    if(target && at < copied) {
      const unsigned part = copied-at < 4 ? copied-at : 4;
      std::memcpy(target+at, &word, part);
    }
  }
  if(ep && kind == STS_DATA_UPDT) {
    if(ep->cursor) ep->cursor += copied;
    ep->count += bytes; // middleware sees malformed oversized CBWs; storage remains bounded.
  }
}
static void gpio_prepare() {
  RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN; (void)RCC->AHB1ENR;
  // Hold D+ low long enough for a real disconnect after warm reset/mode change.
  GPIOA->BSRR = 1U << (12U+16U);
  GPIOA->OTYPER &= ~(1U << 12);
  GPIOA->MODER = (GPIOA->MODER & ~(3U << 24)) | (1U << 24);
  delay(10);
  constexpr uint32_t pairs = (3U << 22) | (3U << 24);
  GPIOA->OTYPER &= ~((1U << 11) | (1U << 12));
  GPIOA->PUPDR &= ~pairs; GPIOA->OSPEEDR |= pairs;
  GPIOA->AFR[1] = (GPIOA->AFR[1] & ~((15U << 12) | (15U << 16))) | (10U << 12) | (10U << 16);
  GPIOA->MODER = (GPIOA->MODER & ~pairs) | (2U << 22) | (2U << 24);
}
} // namespace
namespace stm32f4_usb_device {
void set_low_power(bool enabled) { low_power = enabled; }
void gate_phy() {
  *reinterpret_cast<volatile uint32_t*>(USB_OTG_FS_PERIPH_BASE + USB_OTG_PCGCCTL_BASE) |= USB_OTG_PCGCCTL_STOPCLK;
}
void ungate_phy() {
  *reinterpret_cast<volatile uint32_t*>(USB_OTG_FS_PERIPH_BASE + USB_OTG_PCGCCTL_BASE) &= ~USB_OTG_PCGCCTL_STOPCLK;
}
} // namespace stm32f4_usb_device
extern "C" USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef* pdev) {
  NVIC_DisableIRQ(OTG_FS_IRQn);
  gpio_prepare();
  RCC->AHB2ENR |= RCC_AHB2ENR_OTGFSEN; (void)RCC->AHB2ENR;
  stm32f4_usb_device::ungate_phy();
  USB_DisableGlobalInt(USB_OTG_FS);
  USB_OTG_CfgTypeDef cfg = {};
  cfg.dev_endpoints = ENDPOINTS; cfg.ep0_mps = EP_MPS_64;
  cfg.phy_itface = USB_OTG_EMBEDDED_PHY; cfg.speed = USB_OTG_SPEED_FULL;
  if(USB_CoreInit(USB_OTG_FS,cfg) != HAL_OK || USB_SetCurrentMode(USB_OTG_FS,USB_DEVICE_MODE) != HAL_OK || USB_DevInit(USB_OTG_FS,cfg) != HAL_OK) return USBD_FAIL;
  std::memset(in,0,sizeof(in)); std::memset(out,0,sizeof(out));
  device = pdev; pdev->pData = pdev; low_power = false;
  // Preserve the pinned core's FIFO allocation: RX64, EP0/1/2 TX64, EP3 TX8 words.
  USB_OTG_FS->GRXFSIZ = 64;
  USB_OTG_FS->DIEPTXF0_HNPTXFSIZ = (64U << 16) | 64U;
  USB_OTG_FS->DIEPTXF[0] = (64U << 16) | 128U;
  USB_OTG_FS->DIEPTXF[1] = (64U << 16) | 192U;
  USB_OTG_FS->DIEPTXF[2] = (8U << 16) | 256U;
  USB_DevDisconnect(USB_OTG_FS);
  NVIC_ClearPendingIRQ(OTG_FS_IRQn);
  HAL_NVIC_SetPriority(OTG_FS_IRQn,USBD_IRQ_PRIO,USBD_IRQ_SUBPRIO);
  NVIC_EnableIRQ(OTG_FS_IRQn); initialized = true;
  return USBD_OK;
}
extern "C" USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef*) {
  if(initialized) { stm32f4_usb_device::ungate_phy(); USB_DisableGlobalInt(USB_OTG_FS); USB_DevDisconnect(USB_OTG_FS); USB_StopDevice(USB_OTG_FS); }
  NVIC_DisableIRQ(OTG_FS_IRQn); initialized = false; low_power = false; device = nullptr;
  RCC->AHB2ENR &= ~RCC_AHB2ENR_OTGFSEN;
  return USBD_OK;
}
extern "C" USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef*) { InterruptGuard lock; stm32f4_usb_device::ungate_phy(); USB_EnableGlobalInt(USB_OTG_FS); return status(USB_DevConnect(USB_OTG_FS)); }
extern "C" USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef*) { InterruptGuard lock; stm32f4_usb_device::ungate_phy(); USB_DisableGlobalInt(USB_OTG_FS); USB_StopDevice(USB_OTG_FS); return status(USB_DevDisconnect(USB_OTG_FS)); }
extern "C" USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef*, uint8_t address, uint8_t type, uint16_t mps) {
  InterruptGuard lock; Endpoint* ep = endpoint(address); if(!ep || mps == 0 || mps > 64 || type == EP_TYPE_ISOC) return USBD_FAIL;
  *ep = {}; ep->type = type; ep->maxpacket = mps;
  const auto desc = descriptor(address,*ep); return status(USB_ActivateEndpoint(USB_OTG_FS,&desc));
}
extern "C" USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef*,uint8_t address) {
  InterruptGuard lock; Endpoint* ep = endpoint(address); if(!ep) return USBD_FAIL;
  const auto desc = descriptor(address,*ep); const auto result = status(USB_DeactivateEndpoint(USB_OTG_FS,&desc)); *ep = {}; return result;
}
extern "C" USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef*,uint8_t address) {
  InterruptGuard lock; if(!endpoint(address)) return USBD_FAIL;
  return status((address&0x80U) ? USB_FlushTxFifo(USB_OTG_FS,address&0x7FU) : USB_FlushRxFifo(USB_OTG_FS));
}
extern "C" USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef*,uint8_t address) {
  InterruptGuard lock; Endpoint* ep=endpoint(address); if(!ep) return USBD_FAIL;
  ep->stalled=1; const auto desc=descriptor(address,*ep);
  const auto result=status(USB_EPSetStall(USB_OTG_FS,&desc));
  if((address&0x7FU)==0) USB_EP0_OutStart(USB_OTG_FS,0,reinterpret_cast<uint8_t*>(setup_words));
  return result;
}
extern "C" USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef*,uint8_t address) {
  InterruptGuard lock; Endpoint* ep=endpoint(address); if(!ep) return USBD_FAIL;
  ep->stalled=0; const auto desc=descriptor(address,*ep); return status(USB_EPClearStall(USB_OTG_FS,&desc));
}
extern "C" uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef*,uint8_t address) { const Endpoint* ep=endpoint(address); return ep ? ep->stalled : 1; }
extern "C" USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef*,uint8_t address) { return status(USB_SetDevAddress(USB_OTG_FS,address)); }
extern "C" USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef*,uint8_t address,uint8_t* data,uint32_t size) {
  InterruptGuard lock; Endpoint* ep=endpoint(address|0x80U); if(!ep || !ep->maxpacket || (!data && size)) return USBD_FAIL;
  ep->cursor=data; ep->count=0; ep->length=(address&0x7FU)==0 && size>ep->maxpacket ? ep->maxpacket : size;
  auto desc=descriptor(address|0x80U,*ep); return status(USB_EPStartXfer(USB_OTG_FS,&desc,0));
}
extern "C" USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef*,uint8_t address,uint8_t* data,uint32_t size) {
  InterruptGuard lock; Endpoint* ep=endpoint(address&0x7FU); if(!ep || !ep->maxpacket || (!data && size)) return USBD_FAIL;
  ep->cursor=data; ep->count=0; ep->length=(address&0x7FU)==0 && size>ep->maxpacket ? ep->maxpacket : size;
  auto desc=descriptor(address&0x7FU,*ep); return status(USB_EPStartXfer(USB_OTG_FS,&desc,0));
}
extern "C" uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef*,uint8_t address) { const Endpoint* ep=endpoint(address&0x7FU); return ep ? ep->count : 0; }
extern "C" void USBD_LL_Delay(uint32_t ms) { delay(ms); }
extern "C" void OTG_FS_IRQHandler() {
  if(!device || USB_GetMode(USB_OTG_FS) != USB_OTG_MODE_DEVICE) return;
  uint32_t pending=USB_ReadInterrupts(USB_OTG_FS);
  if(pending&USB_OTG_GINTSTS_MMIS) USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_MMIS;
  if(pending&USB_OTG_GINTSTS_RXFLVL) {
    USB_OTG_FS->GINTMSK &= ~USB_OTG_GINTSTS_RXFLVL;
    for(unsigned packets=0;packets<64 && (USB_OTG_FS->GINTSTS&USB_OTG_GINTSTS_RXFLVL);++packets) {
      const uint32_t item=USB_OTG_FS->GRXSTSP;
      rx_packet(item&USB_OTG_GRXSTSP_EPNUM,(item&USB_OTG_GRXSTSP_PKTSTS)>>17,(item&USB_OTG_GRXSTSP_BCNT)>>4);
    }
    USB_OTG_FS->GINTMSK |= USB_OTG_GINTSTS_RXFLVL;
    pending=USB_ReadInterrupts(USB_OTG_FS);
  }
  if(pending&USB_OTG_GINTSTS_OEPINT) {
    const uint32_t active=USB_ReadDevAllOutEpInterrupt(USB_OTG_FS);
    for(unsigned n=0;n<ENDPOINTS;++n) if(active&(1U<<n)) {
      const uint32_t flags=USB_ReadDevOutEPInterrupt(USB_OTG_FS,n);
      if(flags&USB_OTG_DOEPINT_XFRC) {
        output(n)->DOEPINT=USB_OTG_DOEPINT_XFRC;
        const uint32_t id=*reinterpret_cast<volatile uint32_t*>(USB_OTG_FS_PERIPH_BASE+0x40U);
        if(id==USB_OTG_CORE_ID_310A && (flags&USB_OTG_DOEPINT_STPKTRX)) output(n)->DOEPINT=USB_OTG_DOEPINT_STPKTRX;
        else {
          if(n==0 && out[0].length==0 && id!=USB_OTG_CORE_ID_310A) USB_EP0_OutStart(USB_OTG_FS,0,reinterpret_cast<uint8_t*>(setup_words));
          USBD_LL_DataOutStage(device,n,out[n].cursor);
        }
      }
      if(flags&USB_OTG_DOEPINT_STUP) {
        output(n)->DOEPINT=USB_OTG_DOEPINT_STUP|USB_OTG_DOEPINT_STPKTRX;
        USBD_LL_SetupStage(device,reinterpret_cast<uint8_t*>(setup_words));
      }
      if(flags&USB_OTG_DOEPINT_EPDISD) {
        if(USB_OTG_FS->GINTSTS&USB_OTG_GINTSTS_BOUTNAKEFF) regs()->DCTL |= USB_OTG_DCTL_CGONAK;
      }
      output(n)->DOEPINT=flags&(USB_OTG_DOEPINT_OTEPDIS|USB_OTG_DOEPINT_EPDISD|USB_OTG_DOEPINT_OTEPSPR|USB_OTG_DOEPINT_NAK);
    }
  }
  if(pending&USB_OTG_GINTSTS_IEPINT) {
    const uint32_t active=USB_ReadDevAllInEpInterrupt(USB_OTG_FS);
    for(unsigned n=0;n<ENDPOINTS;++n) if(active&(1U<<n)) {
      const uint32_t flags=USB_ReadDevInEPInterrupt(USB_OTG_FS,n);
      if(flags&USB_OTG_DIEPINT_XFRC) {
        regs()->DIEPEMPMSK &= ~(1U<<n); input(n)->DIEPINT=USB_OTG_DIEPINT_XFRC;
        USBD_LL_DataInStage(device,n,in[n].cursor);
      }
      if(flags&USB_OTG_DIEPINT_EPDISD) USB_FlushTxFifo(USB_OTG_FS,n);
      input(n)->DIEPINT=flags&(USB_OTG_DIEPINT_TOC|USB_OTG_DIEPINT_ITTXFE|USB_OTG_DIEPINT_INEPNE|USB_OTG_DIEPINT_EPDISD);
      if(flags&USB_OTG_DIEPINT_TXFE) tx_empty(n);
    }
  }
  if(pending&USB_OTG_GINTSTS_WKUINT) {
    stm32f4_usb_device::ungate_phy(); regs()->DCTL &= ~USB_OTG_DCTL_RWUSIG;
    if(low_power) { SCB->SCR &= ~(SCB_SCR_SLEEPDEEP_Msk|SCB_SCR_SLEEPONEXIT_Msk); USBD_SystemClockConfigFromResume(); }
    USBD_LL_Resume(device); USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_WKUINT;
  }
  if(pending&USB_OTG_GINTSTS_USBSUSP) {
    if(regs()->DSTS&USB_OTG_DSTS_SUSPSTS) { USBD_LL_Suspend(device); stm32f4_usb_device::gate_phy(); }
    USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_USBSUSP;
  }
  if(pending&USB_OTG_GINTSTS_USBRST) {
    regs()->DCTL &= ~USB_OTG_DCTL_RWUSIG; USB_FlushTxFifo(USB_OTG_FS,0x10);
    for(unsigned n=0;n<ENDPOINTS;++n) {
      input(n)->DIEPINT=0xFB7F; input(n)->DIEPCTL &= ~USB_OTG_DIEPCTL_STALL;
      output(n)->DOEPINT=0xFB7F; output(n)->DOEPCTL=(output(n)->DOEPCTL&~USB_OTG_DOEPCTL_STALL)|USB_OTG_DOEPCTL_SNAK;
    }
    regs()->DAINTMSK=0x10001;
    regs()->DOEPMSK=USB_OTG_DOEPMSK_STUPM|USB_OTG_DOEPMSK_XFRCM|USB_OTG_DOEPMSK_EPDM|USB_OTG_DOEPMSK_OTEPSPRM|USB_OTG_DOEPMSK_NAKM;
    regs()->DIEPMSK=USB_OTG_DIEPMSK_TOM|USB_OTG_DIEPMSK_XFRCM|USB_OTG_DIEPMSK_EPDM;
    regs()->DCFG &= ~USB_OTG_DCFG_DAD;
    USB_EP0_OutStart(USB_OTG_FS,0,reinterpret_cast<uint8_t*>(setup_words));
    USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_USBRST;
  }
  if(pending&USB_OTG_GINTSTS_ENUMDNE) {
    USB_ActivateSetup(USB_OTG_FS); USB_SetTurnaroundTime(USB_OTG_FS,HAL_RCC_GetHCLKFreq(),USB_GetDevSpeed(USB_OTG_FS));
    USBD_LL_SetSpeed(device,USBD_SPEED_FULL); USBD_LL_Reset(device);
    USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_ENUMDNE;
  }
  if(pending&USB_OTG_GINTSTS_SRQINT) { USBD_LL_DevConnected(device); USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_SRQINT; }
  if(pending&USB_OTG_GINTSTS_OTGINT) {
    const uint32_t flags=USB_OTG_FS->GOTGINT;
    if(flags&USB_OTG_GOTGINT_SEDET) USBD_LL_DevDisconnected(device);
    USB_OTG_FS->GOTGINT=flags;
  }
  if(pending&USB_OTG_GINTSTS_SOF) { USBD_LL_SOF(device); USB_OTG_FS->GINTSTS=USB_OTG_GINTSTS_SOF; }
}
extern "C" void OTG_FS_WKUP_IRQHandler() {
  if(low_power) { SCB->SCR &= ~(SCB_SCR_SLEEPDEEP_Msk|SCB_SCR_SLEEPONEXIT_Msk); USBD_SystemClockConfigFromResume(); stm32f4_usb_device::ungate_phy(); }
  EXTI->PR=1U<<18; __DSB();
}
#endif
