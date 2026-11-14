#pragma once
#include "mk61_ai_kernels.h"
#include <cstdint>
extern "C" std::int32_t interp_dot32(const std::uint8_t*,std::int32_t sum);
extern "C" std::int32_t packed_dot32(const std::uint8_t*,const mk61ai_lut8x32*);
namespace interp_lut8 {
using U=std::uint32_t;
// Each CPU has private INTERP0/1 state. No DMA or other core accesses SIO.
// The pinned resident/IRQ sources do not use these interpolators. Preserve
// all programmable state, including lanes not used by the experiment.
struct State {
 U saved[2][7]{};
 static volatile U* reg(unsigned unit,unsigned offset) {
  return reinterpret_cast<volatile U*>(0xd0000080U+unit*64+offset);
 }
 static constexpr unsigned offsets[7]={0,4,8,12,16,44,48};
 static U read(unsigned unit,unsigned index) {
  const U value=*reg(unit,offsets[index]);
  return index>=5?value&0x007fffffU:value; // OVERF flags are read-only/derived.
 }
 void save() {for(unsigned u=0;u<2;++u)for(unsigned i=0;i<7;++i)saved[u][i]=read(u,i);}
 void configure() {
  // Both lanes use ACCUM0. Select bits1..8 after shifts0/8, producing
  // halfword byte offsets without losing the top bit of the fourth index.
  for(unsigned u=0;u<2;++u) {*reg(u,44)=0x2020;*reg(u,48)=0x12028;}
 }
 static void bases(const mk61ai_lut8x32* t) {
  *reg(0,8)=U(reinterpret_cast<std::uintptr_t>(t->subset[0]));
  *reg(0,12)=U(reinterpret_cast<std::uintptr_t>(t->subset[1]));
  *reg(1,8)=U(reinterpret_cast<std::uintptr_t>(t->subset[2]));
  *reg(1,12)=U(reinterpret_cast<std::uintptr_t>(t->subset[3]));
  asm volatile("":::"memory");
 }
 bool restore() {
  for(unsigned u=0;u<2;++u)for(unsigned i=0;i<7;++i)*reg(u,offsets[i])=saved[u][i];
  bool ok=true;
  for(unsigned u=0;u<2;++u)for(unsigned i=0;i<7;++i)ok=ok && read(u,i)==saved[u][i];
  return ok;
 }
};
}
