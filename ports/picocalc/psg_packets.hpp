#ifndef MK61_PICOCALC_PSG_PACKETS_HPP
#define MK61_PICOCALC_PSG_PACKETS_HPP
#include "loadable_app_services.h"
#include <cstring>

namespace picocalc::psg_packets {
constexpr unsigned CAPACITY=512,SAMPLES=120,BODY=132,STATE=8+2*BODY+11;
constexpr uint32_t MAGIC=0x31594153u,PCM=0x314d4350u,PWM=0x314d5750u,STATE_MAGIC=0x31534153u;
inline uint32_t get32(const uint8_t* p) {
    return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;
}
inline void put32(uint8_t* p,uint32_t n) { for(unsigned i=0;i<4;++i)p[i]=uint8_t(n>>(8*i)); }
inline bool valid(const mk61_service_audio_psg& r) {
    return r.local.sample && r.local.rate==25000 && r.local.volume<=100 && r.module_path &&
        r.psg[0] && r.psg[1] && r.psg_bytes==BODY && !(r.extensions&~15u) &&
        r.events && r.event_capacity && r.event_capacity<=1024 && !(r.event_capacity&(r.event_capacity-1)) &&
        r.read && r.write && r.produced && r.time && r.running && r.dac && r.dc_input && r.dc_output &&
        !(uintptr_t(r.read)&3) && !(uintptr_t(r.write)&3) && !(uintptr_t(r.produced)&3) && !(uintptr_t(r.time)&3);
}
inline unsigned config(const mk61_service_audio_psg& r,uint8_t* out,bool pwm=false,unsigned gain=1000) {
    put32(out,MAGIC);put32(out+4,0);
    if(pwm){out[5]=1;out[6]=uint8_t(gain);out[7]=uint8_t(gain>>8);}
    std::memcpy(out+8,r.psg[0],BODY);std::memcpy(out+8+BODY,r.psg[1],BODY);
    put32(out+8+2*BODY,uint32_t(*r.dc_input));put32(out+12+2*BODY,uint32_t(*r.dc_output));
    std::memcpy(out+16+2*BODY,r.dac,3);return STATE;
}
inline bool restore(const mk61_service_audio_psg& r,const uint8_t* in,unsigned n) {
    if(n!=STATE || get32(in)!=STATE_MAGIC || get32(in+4)!=BODY || in[16+2*BODY]>1)return false;
    const int32_t dc_in=int32_t(get32(in+8+2*BODY)),dc_out=int32_t(get32(in+12+2*BODY));
    if(dc_in < -131072 || dc_in>131072 || dc_out < -32768 || dc_out>32767)return false;
    std::memcpy(r.psg[0],in+8,BODY);std::memcpy(r.psg[1],in+8+BODY,BODY);
    *r.dc_input=dc_in;*r.dc_output=dc_out;std::memcpy(r.dac,in+16+2*BODY,3);return true;
}
inline const uint8_t* event(const mk61_service_audio_psg& r,uint32_t index) {
    return r.events+(index&(r.event_capacity-1))*8;
}
/* Returns bytes,0=not ready,-1=invalid producer state. No heap and <128B
 * stack: core1 also services this between LCD strips on its 2KiB stack. */
inline int prepare(const mk61_service_audio_psg& r,uint8_t* out,unsigned minimum=SAMPLES,unsigned maximum=SAMPLES) {
    if(!maximum || maximum>SAMPLES || minimum>maximum)return -1;
    if(!__atomic_load_n(r.running,__ATOMIC_ACQUIRE))return 0;
    const uint32_t available=__atomic_load_n(r.produced,__ATOMIC_ACQUIRE),time=*r.time;
    const int32_t ahead=int32_t(available-time);
    if(ahead<140)return 0;
    const uint32_t start=__atomic_load_n(r.read,__ATOMIC_RELAXED),w=__atomic_load_n(r.write,__ATOMIC_ACQUIRE);
    if(w-start>r.event_capacity || r.dac[0]>1)return -1;
    unsigned limit=unsigned(ahead)/140;if(limit>maximum)limit=maximum;
    // Wait for a useful block, but always drain a full producer ring.
    if(limit<minimum && w-start<r.event_capacity)return 0;
    uint32_t cursor=start,accepted=start;
    uint8_t dac[3]={r.dac[0],r.dac[1],r.dac[2]},first[3]={0,0,0};
    unsigned count=0,flags=0,ay=0;
    for(unsigned i=0;i<limit;++i) {
        const uint32_t until=time+(i+1)*140;
        unsigned added=0;
        while(cursor!=w) {
            const auto* e=event(r,cursor);if(int32_t(get32(e)-until)>0)break;
            if(e[4]<2){if(e[5]>15)return -1;++added;}
            else if(e[4]<=4){if(e[4]==2 && e[6]>1)return -1;dac[e[4]-2]=e[6];}
            else return -1;
            ++cursor;
        }
        unsigned next_flags=flags;
        if(!i)std::memcpy(first,dac,3);
        else for(unsigned d=0;d<3;++d)if(dac[d]!=first[d])next_flags|=1u<<d;
        const unsigned n=i+1,bytes=11+((next_flags&1)?(n+7)/8:0)+((next_flags&2)?n:0)+
            ((next_flags&4)?n:0)+3*(ay+added);
        if(bytes>CAPACITY)break;
        count=n;flags=next_flags;ay+=added;accepted=cursor;
    }
    if(!count)return -1;
    put32(out,MAGIC);out[4]=1;out[5]=uint8_t(count);out[6]=uint8_t(r.extensions);out[7]=uint8_t(flags);
    std::memcpy(out+8,first,3);
    unsigned at=11;uint8_t *beep=nullptr,*covox=nullptr,*specdrum=nullptr;
    if(flags&1){beep=out+at;const unsigned bytes=(count+7)/8;std::memset(beep,0,bytes);at+=bytes;}
    if(flags&2){covox=out+at;at+=count;}
    if(flags&4){specdrum=out+at;at+=count;}
    std::memcpy(dac,r.dac,3);cursor=start;
    for(unsigned i=0;i<count;++i) {
        const uint32_t until=time+(i+1)*140;
        while(cursor!=accepted) {
            const auto* e=event(r,cursor);if(int32_t(get32(e)-until)>0)break;
            if(e[4]<2){out[at++]=uint8_t(i);out[at++]=uint8_t(e[4]*16+e[5]);out[at++]=e[6];}
            else dac[e[4]-2]=e[6];
            ++cursor;
        }
        if(beep)beep[i/8]|=uint8_t(dac[0]<<(i&7));
        if(covox)covox[i]=dac[1];if(specdrum)specdrum[i]=dac[2];
    }
    std::memcpy(r.dac,dac,3);*r.time=time+count*140;
    __atomic_store_n(r.read,accepted,__ATOMIC_RELEASE);
    return int(at);
}
}
#endif
