#include <stdint.h>
using U=uint64_t;
extern "C" __attribute__((optimize("Os"))) U audit_exp_small_pack(U a,U correction,U error64) {
 const bool negative=bool(a>>63);
 const int e=int((a>>52)&2047U)-1023;
 const uint32_t lo=uint32_t(a),hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U;
 const U m=(U(hi)<<32)|lo;
 const uint32_t error=uint32_t(error64);
  const unsigned shift=unsigned(16-e)-unsigned(negative);
  const U bottom=m<<16;
  const U adjusted=negative?bottom-correction:bottom+correction;
  uint32_t high=(hi>>16)+(negative?0U-unsigned(bottom<correction):unsigned(adjusted<bottom));
  uint32_t low=uint32_t(adjusted),middle=uint32_t(adjusted>>32),qlo,qhi;
  bool unsafe;
  if(shift<32) {
    const uint32_t before=low;low+=1U<<(shift-1);
    const uint32_t old=middle;middle+=unsigned(low<before);high+=unsigned(middle<old);
    unsafe=((low+error)&((1U<<shift)-1U))<=2U*error;
    qlo=(low>>shift)|(middle<<(32-shift));
    qhi=(middle>>shift)|(high<<(32-shift));
  } else {
    const unsigned d=shift-32;
    if(d) {
      const uint32_t old=middle;middle+=1U<<(d-1);high+=unsigned(middle<old);
      const uint32_t expanded=low+error;
      const uint32_t remhigh=(middle+unsigned(expanded<low))&((1U<<d)-1U);
      unsafe=!remhigh && expanded<=2U*error;
      qlo=(middle>>d)|(high<<(32-d));qhi=high>>d;
    } else {
      const uint32_t before=low;low+=0x80000000U;
      const uint32_t old=middle;middle+=unsigned(low<before);high+=unsigned(middle<old);
      unsafe=uint32_t(low+error)<=2U*error;qlo=middle;qhi=high;
    }
  }
  if(unsafe) return UINT64_MAX;
  const U displacement=(U(qhi)<<32)|qlo;
  return negative?UINT64_C(0x3FF0000000000000)-displacement:
                  UINT64_C(0x3FF0000000000000)+displacement;
}
