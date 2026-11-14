/* Finite, RAM-only link experiment. All multibyte control fields are LE. */
#ifndef FASTLINK_H
#define FASTLINK_H
#include <stdint.h>
#define FL_MAGIC 0x314b4c46u
#define FL_ID_MAGIC 0x31444946u
#define FL_MAX_BYTES 96u
#define FL_DMA_BYTES 24u
#define FL_READY_US 500u
#define FL_REPLY_US 4000u
#define FL_BURST_US 1000u
enum { FL_IDENTITY=0,FL_SOFT1=1,FL_SOFT3=2,FL_DMA1=3,FL_UART=4,FL_NRZ4=5 };
#define FL_NRZ_MAX_BYTES 96u
#define FL_NRZ_SYMBOL_CAPACITY (FL_NRZ_MAX_BYTES/4u*10u+1u)
#ifdef FL_NRZ4_ONLY
#define FL_TIMER_MODE FL_NRZ4
#define FL_FOURWIRE_MODE FL_NRZ4
#else
#define FL_TIMER_MODE FL_DMA1
#define FL_FOURWIRE_MODE FL_SOFT3
#endif
static inline uint32_t fl_get(const uint8_t *p) {
 return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline void fl_put(uint8_t *p,uint32_t v) {
 for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));
}
static inline uint32_t fl_crc_step(uint32_t crc,const uint8_t *p,unsigned n) {
 while(n--) {crc^=*p++;for(unsigned b=0;b<8;++b)crc=(crc>>1)^(0xedb88320u&-(crc&1u));}
 return crc;
}
/* Pattern generation is outside the measured GPIO interval. */
static inline void fl_pattern(uint8_t *p,unsigned n,unsigned kind,uint32_t seed) {
 for(unsigned i=0;i<n;++i) {
  seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;
  p[i]=kind==0?0:kind==1?255:kind==2?0x55:kind==3?0xaa:
       kind==4?(uint8_t)(1u<<(i&7)):kind==5?(uint8_t)~(1u<<(i&7)):(uint8_t)seed;
 }
}
/* Groups of three MSB-first bits, exactly matching PIO IN pins,3. */
static inline unsigned fl_group(const uint8_t *p,unsigned at) {
 unsigned result=0;
 for(unsigned k=0;k<3;++k) {unsigned bit=at*3+k;result=(result<<1)|((p[bit/8]>>(7-bit%8))&1u);}
 return result;
}
/* Common start0, eight MSB-first nibbles, common stop15. */
static inline unsigned fl_nrz_symbol(const uint8_t *p,unsigned at) {
 unsigned pos=at%10u;if(!pos)return 0;if(pos==9)return 15;
 --pos;unsigned value=p[at/10u*4u+pos/2u];return (pos&1u?value:value>>4)&15u;
}
#endif
