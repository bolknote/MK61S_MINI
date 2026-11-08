#ifndef AI_M3_Q4_KERNELS_H
#define AI_M3_Q4_KERNELS_H
#include <stdint.h>

/* Offset-binary Q4, adjacent nibbles; no FP operations in a group dot. */
struct __attribute__((packed,may_alias)) ai_m3_word { uint32_t value; };
static inline uint32_t ai_m3_load_word(const void *p) {
  return ((const struct ai_m3_word *)p)->value;
}
#if defined(__arm__) || defined(__thumb__)
#define AI_M3_EXTRACT(out,value,at,bits) \
  __asm__("sbfx %0,%1,#" #at ",#" #bits : "=r"(out) : "r"(value))
#else
#define AI_M3_EXTRACT(out,value,at,bits) \
  ((out)=(int32_t)((uint32_t)(value)<<(32-(bits)-(at)))>>(32-(bits)))
#endif

static inline int32_t ai_m3_dot1_a8_32(const uint8_t *w,const int8_t *x) {
  int32_t sum=0;
  for(unsigned i=0;i<32;i+=8) {
    const uint32_t p=ai_m3_load_word(w+i/2)^0x88888888u;
#define AI_M3_ONE(at,j) do { int32_t q;AI_M3_EXTRACT(q,p,at,4);sum+=q*x[i+j]; } while(0)
    AI_M3_ONE(0,0);AI_M3_ONE(4,1);AI_M3_ONE(8,2);AI_M3_ONE(12,3);
    AI_M3_ONE(16,4);AI_M3_ONE(20,5);AI_M3_ONE(24,6);AI_M3_ONE(28,7);
#undef AI_M3_ONE
  }
  return sum;
}

static inline void ai_m3_dot2_a8_32(const uint8_t *w0,const uint8_t *w1,
                                   const int8_t *x,int32_t out[2]) {
  int32_t a0=0,a1=0;
  for(unsigned i=0;i<32;i+=8) {
    const uint32_t p0=ai_m3_load_word(w0+i/2)^0x88888888u;
    const uint32_t p1=ai_m3_load_word(w1+i/2)^0x88888888u;
    const uint32_t xa=ai_m3_load_word(x+i),xb=ai_m3_load_word(x+i+4);
#define AI_M3_TWO(word,j,k) do { \
    int32_t q0,q1,v;AI_M3_EXTRACT(v,word,j,8); \
    AI_M3_EXTRACT(q0,p0,k,4);AI_M3_EXTRACT(q1,p1,k,4); \
    a0+=q0*v;a1+=q1*v; \
  } while(0)
    AI_M3_TWO(xa,0,0);AI_M3_TWO(xa,8,4);AI_M3_TWO(xa,16,8);AI_M3_TWO(xa,24,12);
    AI_M3_TWO(xb,0,16);AI_M3_TWO(xb,8,20);AI_M3_TWO(xb,16,24);AI_M3_TWO(xb,24,28);
#undef AI_M3_TWO
  }
  out[0]=a0;out[1]=a1;
}

/* Each pair uses unsigned modulo-2^32 multiplication. Rounding drops the
 * bounded low-half term after eight pairs: abs(sum(n*x_b)) <=15360.
 * Correct the offset only once, outside the pair loop. No signed overflow. */
static inline int32_t ai_m3_swar_a8_32(const uint8_t *w,const uint32_t xp[16],int32_t xsum) {
  int32_t result=0;
  for(unsigned i=0;i<4;i+=2) {
    const uint32_t p0=ai_m3_load_word(w+4*i),p1=ai_m3_load_word(w+4*i+4);
    const uint32_t mask=0x000f000fu;
    const uint32_t *x=xp+4*i;
    uint32_t s=(p0&mask)*x[0]+((p0>>4)&mask)*x[1]+
               ((p0>>8)&mask)*x[2]+((p0>>12)&mask)*x[3]+
               (p1&mask)*x[4]+((p1>>4)&mask)*x[5]+
               ((p1>>8)&mask)*x[6]+((p1>>12)&mask)*x[7];
    result+=(int32_t)(s+0x8000u)>>16;
  }
  return result-8*xsum;
}
static inline int32_t ai_m3_pack_swar_a8_32(const int8_t x[32],uint32_t xp[16]) {
  int32_t sum=0;
  for(unsigned group=0;group<4;++group)for(unsigned j=0;j<4;++j) {
    const int32_t a=x[8*group+j],b=x[8*group+j+4];
    xp[4*group+j]=(uint32_t)b+(uint32_t)a*65536u;sum+=a+b;
  }
  return sum;
}
#undef AI_M3_EXTRACT
#endif
