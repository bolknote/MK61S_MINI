#include <stdint.h>
using U=uint64_t;
extern "C" U audit_exp_gate(U q,U arguments) {
 const int32_t delta32=int32_t(uint32_t(arguments));
 const unsigned tail=unsigned(q)&1023U;
 const unsigned distance=tail>512U?tail-512U:512U-tail;
 bool safe=false;
          const uint32_t top=uint32_t(q>>48)+24U;
          const uint32_t bound=((top*275U+16383U)>>14)+129U;
          const int32_t bias=delta32>>24;
          const int32_t margin=int32_t(distance<<8)+(tail>512U?bias:-bias-1);
          safe=margin>int32_t(bound);
 return (U(bound)<<32)|unsigned(safe);
}
