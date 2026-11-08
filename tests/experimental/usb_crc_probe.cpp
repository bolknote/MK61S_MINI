#include "usb_crc_probe.hpp"
#include "compute_clock.hpp"
#include "compact_format.hpp"
#include "usb_screen.hpp"
#include <Arduino.h>
namespace usb_crc_probe {
volatile uint32_t mode;
static uint32_t requested;
static volatile uint32_t results[128];
static bool restore_usb_irq;
uint32_t control(uint32_t operation, uint32_t index, uint32_t value) {
  switch(operation) {
    case 0xC006:
      for(auto& result:results)result=0xFFFFFFFFU;
      if(requested&0xC0U)usb_screen::cancel();
      restore_usb_irq=(requested&0x80U) && NVIC_GetEnableIRQ(OTG_FS_IRQn);
      if(restore_usb_irq)NVIC_DisableIRQ(OTG_FS_IRQn);
      mode=requested;
      compute_clock::backend::set_fast((mode & 0x20U)!=0);
      return 0x55435231;
    case 0xC007: return mode;
    case 0xC008: return DBGMCU->IDCODE;
    case 0xC009:
      if(index>=128)return 0;
      results[index]=value;return 1;
    case 0xC00A:
      mode=(mode&15U)|0x10U;
      compute_clock::backend::set_fast(false);
      if(restore_usb_irq){restore_usb_irq=false;NVIC_EnableIRQ(OTG_FS_IRQn);}
      return 1;
    case 0xC00B: return index<128?results[index]:0;
    case 0xC00C:
      if((index & 15U)>9 || (index & ~0xFFU) || (index & 0x30U)==0x30U)return 0;
      requested=index;mode=(index&15U)|0x10U;
      compute_clock::backend::set_fast(false);return 0x55435231;
    case 0xC00D:return requested;
    case 0xC00E: {
      const uint32_t saved=__get_PRIMASK();
      if(index)__disable_irq();
      const uint32_t began=DWT->CYCCNT;
      uint32_t errors=0;
      for(unsigned round=0;round<8;++round) {
        char text[16];
        const int count=compact_format::snprintf(text,sizeof(text),"%lu",1430475313UL);
        const char expected[]="1430475313";
        unsigned bad=count!=10;
        for(unsigned i=0;i<sizeof(expected);++i)if(text[i]!=expected[i])bad=1;
        errors+=bad;
      }
      results[index?100:101]=DWT->CYCCNT-began;
      __set_PRIMASK(saved);
      return errors;
    }
    default: return 0;
  }
}
}
extern "C" unsigned usb_crc_mode_c(){return usb_crc_probe::mode;}
