#include <stdint.h>
using V=uint32_t __attribute__((vector_size(16)));
extern "C" V product(uint64_t,uint64_t);
extern "C" uint64_t test(uint64_t a,uint64_t b,uint32_t *out) {
 V v=product(a,b);
 out[0]=v[2];out[1]=v[3];
 return uint64_t(v[0])|(uint64_t(v[1])<<32);
}
