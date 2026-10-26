#include <stdint.h>
#define MK61_SOFT_PCS __attribute__((pcs("aapcs")))
using U=uint64_t;
static U bits(double x) {union {double d;U u;} q={x};return q.u;}
static double real(U x) {union {U u;double d;} q={x};return q.d;}
extern "C" {
MK61_SOFT_PCS double mk61_m0_ln_positive(double x) {return real(bits(x)^UINT64_C(0x13579BDF2468ACE0));}
MK61_SOFT_PCS double mk61_m0_ln_special(double x) {return real(bits(x)^UINT64_C(0xFDB97531ECA86420));}
__attribute__((naked,noinline,optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double) {
  asm volatile(
    ".syntax unified\n"
    "cmp r0,#0\nbne .Lln_classify\n"
    "lsls r2,r1,#1\nbeq .Lln_zero\n"
    "ldr r2,=0x7ff00000\ncmp r1,r2\nbeq .Lln_return\n"
    ".Lln_classify:\nlsrs r2,r1,#20\nadds r3,r2,#1\nlsrs r3,r3,#11\n"
    "bne .Lln_cold\ncmp r2,#0\nbeq .Lln_cold\nb mk61_m0_ln_positive\n"
    ".Lln_zero:\nldr r1,=0xfff00000\n"
    ".Lln_return:\nbx lr\n"
    ".Lln_cold:\nldr r3,=mk61_m0_ln_special\nbx r3\n"
    ".p2align 2\n.ltorg\n.syntax divided\n");
}
}
