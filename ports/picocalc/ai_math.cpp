// AI-only backends chosen by the physical seven-operation comparison.
// Keep the calculator/global EABI and all non-AI callers unchanged.
#include "mk61_ai_math.hpp"
#if MK61_AI_FAST_MATH && defined(PICO_ON_DEVICE)
#include "native_eabi_m0.hpp"
#include "pico.h"
#include "pico/bootrom.h"
#include <atomic>
#include <cstdint>
#include <cstring>
namespace mk61ai::math {
namespace {
using Binary=float(*)(float,float);
std::atomic<const std::uint32_t*> table{nullptr};
inline std::uint32_t bits(float a){std::uint32_t v;__builtin_memcpy(&v,&a,4);return v;}
inline float value(std::uint32_t a){float v;__builtin_memcpy(&v,&a,4);return v;}
template<unsigned Op> inline float fallback(float a,float b) {
 if constexpr(Op==0)return a+b;
 if constexpr(Op==1)return a-b;
 if constexpr(Op==2)return a*b;
 return a/b;
}
template<unsigned Op> inline float binary(float a,float b) {
 const unsigned ea=(bits(a)>>23)&255,eb=(bits(b)>>23)&255;
 const auto* sf=table.load(std::memory_order_relaxed);
 // Raw Qfplib flushes subnormals and treats NaNs as infinities. On ordinary
 // finite operands/results its basic operations are correctly rounded.
 if(sf && ea && ea<255 && eb && eb<255) {
  const float r=reinterpret_cast<Binary>(sf[Op])(a,b);
  const unsigned er=(bits(r)>>23)&255;
  if(er && er<255)return r;
 }
 return fallback<Op>(a,b);
}
}
void initialize() {
 if(table.load(std::memory_order_acquire))return;
 // Older factory ROMs retain the existing IEEE runtime fallback.
 if(rp2040_rom_version()<2)return;
 const auto* sf=static_cast<const std::uint32_t*>(rom_data_lookup(rom_table_code('S','F')));
 if(!sf)return;
 for(unsigned i=0;i<4;++i)if(!(sf[i]&1) || sf[i]>=0x4000)return;
 table.store(sf,std::memory_order_release);
}
float __not_in_flash_func(add)(float a,float b){return binary<0>(a,b);}
float __not_in_flash_func(sub)(float a,float b){return binary<1>(a,b);}
float __not_in_flash_func(mul)(float a,float b){return binary<2>(a,b);}
float __not_in_flash_func(div)(float a,float b){return binary<3>(a,b);}
float __not_in_flash_func(sqrt)(float a){return mk61_m0_sqrtf(a);}
float __not_in_flash_func(exp)(float a){return float(mk61_m0_exp(double(a)));}
}
#endif
