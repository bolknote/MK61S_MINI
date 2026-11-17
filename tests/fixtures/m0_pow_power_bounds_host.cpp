#include "native_eabi_m0_pow_power_bounds.inc"

using m0_pow_power_bounds::PowerBounds;
using Kernel=PowerBounds<8>;

static void set_number(Kernel::Number& value,uint64_t low,uint64_t high) {
    for(unsigned i=0;i<4;++i) {
        value.word[i]=uint16_t(low>>(16*i));
        value.word[i+4]=uint16_t(high>>(16*i));
    }
    value.scale=0;
    value.exact=true;
}

static void store_number(const Kernel::Number& value,uint64_t* out) {
    out[0]=out[1]=0;
    for(unsigned i=0;i<4;++i) {
        out[0]|=uint64_t(value.word[i])<<(16*i);
        out[1]|=uint64_t(value.word[i+4])<<(16*i);
    }
    out[2]=value.scale.low;
    out[3]=uint64_t(value.exact);
}

extern "C" int side128(uint64_t x,uint64_t y,uint64_t lower) {
    return Kernel::side(x,y,lower);
}
extern "C" int side256(uint64_t x,uint64_t y,uint64_t lower) {
    return PowerBounds<16>::side(x,y,lower);
}
extern "C" int side4096(uint64_t x,uint64_t y,uint64_t lower) {
    uint64_t rounded=lower;
    if(!m0_pow_power_bounds::resolve(x,y,rounded)) return 0;
    return rounded==lower?-1:1;
}
extern "C" int side8192(uint64_t x,uint64_t y,uint64_t lower) {
    return PowerBounds<512>::side(x,y,lower);
}

template<unsigned Words>
static unsigned square_words(uint16_t* words,bool exact) {
    using Square=PowerBounds<Words>;
    typename Square::Number a;
    for(unsigned i=0;i<Words;++i) a.word[i]=words[i];
    a.scale=0;
    a.exact=exact;
    Square::square(a);
    for(unsigned i=0;i<Words;++i) words[i]=a.word[i];
    return unsigned(2*a.scale.low+a.exact);
}

extern "C" unsigned square128(uint16_t* words,bool exact) { return square_words<8>(words,exact); }
extern "C" unsigned square4096(uint16_t* words,bool exact) { return square_words<256>(words,exact); }
extern "C" unsigned square8192(uint16_t* words,bool exact) { return square_words<512>(words,exact); }

extern "C" void product128(uint64_t alo,uint64_t ahi,uint64_t blo,uint64_t bhi,uint64_t* out) {
    Kernel::Number a,b;
    set_number(a,alo,ahi);
    set_number(b,blo,bhi);
    Kernel::multiply(a,b,0);
    store_number(a,out);
}
extern "C" void upper128(uint64_t alo,uint64_t ahi,uint64_t nlo,uint64_t nhi,uint64_t* out) {
    Kernel::Number a;
    set_number(a,alo,ahi);
    Kernel::raise_bound(a,mk61_u128::words(nlo,nhi));
    store_number(a,out);
}
