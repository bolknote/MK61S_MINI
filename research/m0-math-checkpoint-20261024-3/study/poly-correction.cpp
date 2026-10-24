#include <stdint.h>

// Exploratory isolated cold kernel. It is not linked into the runtime.
extern "C" __attribute__((noinline,optimize("Os")))
int32_t atan_poly_tail(uint64_t z,uint64_t c3,uint32_t c7,int32_t r5) {
  const uint32_t m1=uint32_t(c3>>33)*((uint32_t(z)&0xFFFFFFU)>>8);
  const uint32_t m2=((uint32_t(c3)&0x1FFFFU)>>1)*uint32_t(z>>40);
  const uint32_t missing=uint32_t((uint64_t(m1)+m2+(1U<<28))>>29);
  r5+=int32_t(missing);
  const bool negative5=r5<0;
  const uint32_t magnitude5=negative5?uint32_t(-r5):uint32_t(r5);
  int32_t delta5=int32_t(((magnitude5+2)*13108U)>>16);
  if(negative5) delta5=-delta5;
  r5-=5*delta5;

  const uint32_t c9=(((c7>>6)*uint32_t(z>>40))+(1U<<23))>>24;
  const uint32_t ninth=((c9+4)*7282U)>>16;
  const int32_t r9=int32_t(c9-9*ninth);

  const uint32_t lo=uint32_t(c3),hi=uint32_t(c3>>32);
  uint32_t fold3=(lo&65535U)+(lo>>16)+hi;
  fold3=(fold3&255U)+(fold3>>8);
  const uint32_t div3=(fold3*21846U)>>16;
  int32_t r3=int32_t(fold3-3*div3);
  if(r3==2) r3=-1;
  const uint32_t fold7=(c7>>9)+(c7&511U);
  const uint32_t div7=(fold7*9363U)>>16;
  int32_t r7=int32_t(fold7-7*div7);
  if(r7>3) r7-=7;

  const int32_t bias=-105*r3+63*r5-45*r7+35*r9;
  const uint32_t magnitude=bias<0?uint32_t(-bias):uint32_t(bias);
  int32_t correction=int32_t(magnitude>=158)+int32_t(magnitude>=473);
  if(bias<0) correction=-correction;
  return delta5+int32_t(ninth)+correction;
}
