#ifndef FL_IDENTITY_GUARD_H
#define FL_IDENTITY_GUARD_H
#include "link.h"
/* ST ES096 Rev15 section2.2.2: DBGMCU_IDCODE reads zero in user software.
 * https://www.st.com/resource/en/errata_sheet/cd00190234-stm32f101x8-b-stm32f102x8-b-and-stm32f103x8-b-medium-density-device-limitations-stmicroelectronics.pdf
 * Accept that documented zero only alongside verified BIOS CRC, geometry,
 * stock RCC and a Cortex-M3 CPUID. A readable, different device ID fails. */
static __attribute__((noinline,noclone,noipa)) int fl_identity_valid(const uint8_t *p,unsigned n) {
 if(n!=120)return 0;
 const unsigned device=fl_get(p+40)&0xfffu;
 return fl_get(p)==0x3155334du&&fl_get(p+4)==1&&fl_get(p+8)==0x410&&
  fl_get(p+12)==0x08002000u&&fl_get(p+16)==29844&&fl_get(p+20)==0x3be158b4u&&
  fl_get(p+36)==fl_get(p+20)&&(device==0||device==0x410u)&&fl_get(p+44)==64&&
  (fl_get(p+48)&0x003ffffcu)==0x001d0408u&&fl_get(p+56)==0&&
  !(fl_get(p+64)&(1u<<12))&&fl_get(p+108)==FL_ID_MAGIC&&
  (fl_get(p+112)&0xff0ffff0u)==0x410fc230u&&fl_get(p+116)==2;
}
#endif
