#include <assert.h>
#include <stdint.h>
#include <stdio.h>
int main(void) {
    unsigned cases=0;
    for(unsigned n=1;n<=16;++n) {
        const uint32_t all=(1U<<n)-1;
        for(uint32_t a=0;a<=all;++a)for(unsigned scenario=0;scenario<4;++scenario) {
            const uint32_t b=(~a)&all,c=((a<<1)|(a>>(n-1)))&all;
            const int32_t va=scenario&1?0:4080,vb=scenario&2?48:4080,vc=4080;
            const int32_t initial=scenario&1?-32768:32767;
            int32_t sequential=initial;
            for(unsigned t=0;t<n;++t) {
                const int32_t mix=(((a>>t)&1)?va:0)+(((b>>t)&1)?vb:0)+(((c>>t)&1)?vc:0);
                sequential=(sequential+mix)>>1;
            }
            const int32_t weighted=(initial+(int32_t)(a*va+b*vb+c*vc))>>n;
            assert(weighted==sequential);++cases;
        }
    }
    printf("Exact weighted IIR: %u exhaustive masks/ticks1..16/signed starts/max amplitudes agree with sequential tick filter PASS\n",cases);
}
