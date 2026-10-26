#include <stdint.h>
using U=uint64_t;
static constexpr uint32_t exp_step_low=3588551130U;
extern "C" __attribute__((optimize("Os"))) U audit_exp_direction(U q,U arguments,U parameters) {
 const int32_t delta32=int32_t(uint32_t(arguments));
 const uint32_t n=uint32_t(arguments>>32);
 const uint32_t product_fraction=uint32_t(parameters);
 const U delta=parameters&UINT64_C(0xFFFFFFFF00000000);
 bool safe=false;
        const uint32_t head=1U-uint32_t(delta>>32);
        const uint32_t g=(head+1023U)>>10;
        const uint32_t curvature=(3U*g*g+65535U)>>16;
        const uint32_t f=(n*exp_step_low)>>24;
        const uint32_t delta_upper=257U+curvature-(f?f-1U:0U);
        const uint32_t top=uint32_t(q>>48)+24U;
        const uint32_t effect=(delta_upper*top+65535U)>>16;
        const int32_t bias=delta32>>24;
        const int32_t product_upper=int32_t((product_fraction>>31)<<8)-
                                    int32_t(product_fraction>>24);
        safe=int32_t(effect)+bias+product_upper+2<=256;
 const int32_t upper=int32_t(effect)+bias+product_upper+2;
 return (U(uint32_t(upper))<<32)|unsigned(safe);
}
