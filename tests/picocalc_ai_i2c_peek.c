/* Read-only RP2040 bus diagnostic. No FIFO/clear-register reads, no MMIO
 * writes, no I2C/UART configuration and no model execution. */
#include "mk61_app.h"
#include <stdint.h>
static uint32_t peek(uint32_t address) {
  return *(const volatile uint32_t *)(uintptr_t)address;
}
int main(void) {
  const mk61_app_services *s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT);
  if(!s)return 1;
  for(unsigned sample=0;sample<16;++sample) {
    const uint32_t con=peek(0x40048000),enable=peek(0x4004806c),status=peek(0x40048070);
    const uint32_t raw=peek(0x40048034),tx=peek(0x40048074),rx=peek(0x40048078);
    const uint32_t abort=peek(0x40048080),enabled=peek(0x4004809c),mask=peek(0x40048030);
    const uint32_t scl=peek(0x4004801c),sda=peek(0x40048020);
    const uint32_t pins=peek(0xd0000004)&0xc0u,fn6=peek(0x40014034),fn7=peek(0x4001403c);
    const uint32_t sleep0=peek(0x400080a8),sleep1=peek(0x400080ac),reset=peek(0x4000c008);
    char line[384];
    const int n=mk61_app_snprintf(s,line,sizeof(line),
      "AI_I2C_PEEK i=%u CON=%08X EN=%08X ES=%08X ST=%08X RAW=%08X MASK=%08X TX=%u RX=%u ABRT=%08X HC=%u LC=%u PINS=%02X F6=%08X F7=%08X S0=%08X S1=%08X RD=%08X\r\n",
      sample,con,enable,enabled,status,raw,mask,tx,rx,abort,scl,sda,pins,fn6,fn7,sleep0,sleep1,reset);
    if(n<=0 || (unsigned)n>=sizeof(line))return 2;
    /* NativeHost rejects DEBUG_WRITE >128 bytes. Preserve one logical line
     * with bounded writes and check the result instead of losing telemetry. */
    for(unsigned at=0;at<(unsigned)n;) {
      unsigned take=(unsigned)n-at;if(take>96)take=96;
      if(!s->call(MK61_SERVICE_DEBUG_WRITE,take,0,0,line+at))return 3;
      at+=take;
    }
    mk61_api->delay_ms(1);
  }
  return 0;
}
