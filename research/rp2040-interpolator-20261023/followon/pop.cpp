#include "api.h"
using U=uint64_t;
struct Interp {volatile uint32_t accum[2],base[3],pop[3],peek[3],ctrl[2],add[2],base01;};
static Interp* const p=(Interp*)0xd0000080;
static constexpr uint32_t lane(unsigned shift,unsigned lsb,unsigned msb){return shift|(lsb<<5)|(msb<<10);}
struct Data {
  uint8_t texture[4096]{};
  uint32_t pairs[256]{};
  static constexpr int sample(unsigned j){return int(((j*977U+((j*j*37U)^0x5123U))&65535U))-32768;}
  constexpr Data(){
    for(unsigned y=0;y<64;++y)for(unsigned x=0;x<64;++x)texture[y*64+x]=uint8_t((x*13+y*29)^(x*y*3+71));
    for(unsigned j=0;j<256;++j)pairs[j]=uint16_t(sample(j))|(uint32_t(uint16_t(sample((j+1)&255)))<<16);
  }
};
static constexpr Data data;
extern "C" {alignas(4) uint8_t fo_output[2048];}
extern "C" void fo_texture_setup(void){
  p->ctrl[0]=(1U<<18)|lane(16,0,5);p->ctrl[1]=(1U<<18)|lane(10,6,11);p->base[2]=(uint32_t)(uintptr_t)data.texture;
}
extern "C" void fo_audio_setup(void){
  p->ctrl[0]=(1U<<21)|lane(14,2,9);p->ctrl[1]=(1U<<16)|(1U<<15)|lane(8,0,7);p->base[2]=(uint32_t)(uintptr_t)data.pairs;
}
static inline uint32_t du(U seed){return (uint32_t(seed)&1)?0xffff6000U:0x0000c000U;}
static inline uint32_t dv(U seed){return (uint32_t(seed)&2)?0x00015555U:0x00005555U;}
extern "C" __attribute__((noipa)) U fo_texture_cpu(U seed,U count){
  uint32_t u=uint32_t(seed),v=uint32_t(seed>>32);const uint32_t a=du(seed),b=dv(seed);
  for(unsigned i=0;i<unsigned(count);++i){fo_output[i]=data.texture[((v>>16)&63U)*64+((u>>16)&63U)];u+=a;v+=b;}
  return U(u)|(U(v)<<32);
}
extern "C" __attribute__((noipa)) U fo_texture_pop(U seed,U count){
  p->accum[0]=uint32_t(seed);p->accum[1]=uint32_t(seed>>32);p->base[0]=du(seed);p->base[1]=dv(seed);
  for(unsigned i=0;i<unsigned(count);++i)fo_output[i]=*(const uint8_t*)(uintptr_t)p->pop[2];
  return U(p->accum[0])|(U(p->accum[1])<<32);
}
static inline uint32_t step(U seed){return uint32_t(seed>>32)|1U;}
extern "C" __attribute__((noipa)) U fo_audio_cpu(U seed,U count){
  uint32_t phase=uint32_t(seed);auto* out=(int16_t*)fo_output;
  for(unsigned i=0;i<unsigned(count);++i){const uint32_t pair=data.pairs[(phase>>16)&255];const int a=int16_t(pair),b=int16_t(pair>>16);out[i]=int16_t(a+(((b-a)*int((phase>>8)&255))>>8));phase+=step(seed);}
  return phase;
}
extern "C" __attribute__((noipa)) U fo_audio_interp(U seed,U count){
  p->accum[0]=uint32_t(seed);auto* out=(int16_t*)fo_output;
  for(unsigned i=0;i<unsigned(count);++i){p->base01=*(const uint32_t*)(uintptr_t)p->peek[2];out[i]=int16_t(p->peek[1]);p->add[0]=step(seed);}
  return p->accum[0];
}
extern "C" uint32_t fo_pop_hash(unsigned bytes){uint32_t h=0;for(unsigned i=0;i<bytes;++i){h=(h^fo_output[i])*16777619U;h^=h>>16;}return h;}
extern "C" unsigned fo_pop_verify(unsigned group,U seed,unsigned n){
  uint32_t u=uint32_t(seed),v=uint32_t(seed>>32);unsigned failures=0;
  for(unsigned i=0;i<n;++i){
    if(!group){const unsigned x=(u>>16)%64,y=(v>>16)%64;const uint8_t expected=uint8_t((x*13+y*29)^(x*y*3+71));failures+=fo_output[i]!=expected;u+=du(seed);v+=dv(seed);}
    else {const unsigned j=(u>>16)%256;const int a=Data::sample(j),b=Data::sample((j+1)%256);const int product=(b-a)*int((u>>8)&255);const int floor=product>=0?product/256:-int((unsigned(-product)+255)/256);failures+=((int16_t*)fo_output)[i]!=a+floor;u+=step(seed);}
  }
  return failures;
}
