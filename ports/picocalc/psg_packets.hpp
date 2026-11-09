#ifndef MK61_PICOCALC_PSG_PACKETS_HPP
#define MK61_PICOCALC_PSG_PACKETS_HPP
#include "loadable_app_services.h"
#include <cstring>

namespace picocalc::psg_packets {
constexpr unsigned CAPACITY=512,SAMPLES=120,BODY=132,STATE=8+2*BODY+11;
constexpr uint32_t MAGIC=0x31594153u,PCM=0x314d4350u,PWM=0x314d5750u,STATE_MAGIC=0x31534153u;
constexpr uint32_t MAGIC_V2=0x32594153u,PWM_STEREO=0x324d5750u,STATE_V2_MAGIC=0x32534153u;
constexpr uint32_t PWM_STEREO_REPEAT=0x334d5750u;
constexpr unsigned STATE_V2=STATE+24;
struct Options {
    unsigned layout=0,chip=0;int32_t* stereo=nullptr;bool extended=false;
    unsigned state_bytes() const {return extended?STATE_V2:STATE;}
    uint32_t magic() const {return extended?MAGIC_V2:MAGIC;}
    unsigned channels() const {return layout?2:1;}
};
inline Options options(const mk61_service_audio_psg_config* c) {
    return c?Options{c->layout,c->chip,c->stereo,true}:Options{};
}
inline bool valid(const Options& o) {
    return !o.extended || (o.layout<=MK61_PSG_ACB && o.chip<=MK61_PSG_YM && o.stereo && !(uintptr_t(o.stereo)&3));
}
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
inline unsigned config(const mk61_service_audio_psg& r,uint8_t* out,bool pwm=false,unsigned gain=1000,const Options& o={}) {
    put32(out,o.magic());put32(out+4,0);
    if(pwm){out[5]=1;out[6]=uint8_t(gain);out[7]=uint8_t(gain>>8);}
    if(o.extended)out[5]|=uint8_t((o.layout<<1)|(o.chip<<3));
    std::memcpy(out+8,r.psg[0],BODY);std::memcpy(out+8+BODY,r.psg[1],BODY);
    put32(out+8+2*BODY,uint32_t(*r.dc_input));put32(out+12+2*BODY,uint32_t(*r.dc_output));
    std::memcpy(out+16+2*BODY,r.dac,3);
    if(o.extended)for(unsigned i=0;i<6;++i)put32(out+STATE+4*i,uint32_t(o.stereo[i]));
    return o.state_bytes();
}
inline bool restore(const mk61_service_audio_psg& r,const uint8_t* in,unsigned n,const Options& o={}) {
    if(n!=o.state_bytes() || get32(in)!=(o.extended?STATE_V2_MAGIC:STATE_MAGIC) || get32(in+4)!=BODY || in[16+2*BODY]>1)return false;
    const int32_t dc_in=int32_t(get32(in+8+2*BODY)),dc_out=int32_t(get32(in+12+2*BODY));
    if(dc_in < -131072 || dc_in>131072 || dc_out < -32768 || dc_out>32767)return false;
    if(o.extended)for(unsigned i=0;i<6;++i) {
        const int32_t value=int32_t(get32(in+STATE+4*i)),limit=i==4?131072:32768;
        if(value < -limit || value>=limit)return false;
    }
    std::memcpy(r.psg[0],in+8,BODY);std::memcpy(r.psg[1],in+8+BODY,BODY);
    *r.dc_input=dc_in;*r.dc_output=dc_out;std::memcpy(r.dac,in+16+2*BODY,3);
    if(o.extended)for(unsigned i=0;i<6;++i)o.stereo[i]=int32_t(get32(in+STATE+4*i));
    return true;
}
inline const uint8_t* event(const mk61_service_audio_psg& r,uint32_t index) {
    return r.events+(index&(r.event_capacity-1))*8;
}
// AY music commonly leaves all three DACs constant for an entire block.
// Walk only published events in that case, without two per-sample passes.
// -2 asks the general encoder to handle changing DACs or a full packet.
#if defined(PICO_ON_DEVICE)
__attribute__((noinline,section(".time_critical.m3_prepare_sparse")))
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("Os")))
#endif
#endif
inline int prepare_sparse(const mk61_service_audio_psg& r,uint8_t* out,unsigned limit,
                          uint32_t time,uint32_t start,uint32_t w) {
    unsigned at=11;uint32_t cursor=start;
    const uint32_t until=time+limit*140;
    while(cursor!=w) {
        const auto* e=event(r,cursor);const int32_t delta=int32_t(get32(e)-time);
        if(int32_t(get32(e)-until)>0)break;
        if(e[4]<2) {
            if(e[5]>15)return -1;
            if(at+3>CAPACITY)return -2;
            out[at++]=uint8_t(delta<=0?0:(unsigned(delta)-1)/140);
            out[at++]=uint8_t(e[4]*16+e[5]);out[at++]=e[6];
        } else if(e[4]<=4) {
            if(e[4]==2 && e[6]>1)return -1;
            if(e[6]!=r.dac[e[4]-2])return -2;
        } else return -1;
        ++cursor;
    }
    put32(out,MAGIC);out[4]=1;out[5]=uint8_t(limit);out[6]=uint8_t(r.extensions);out[7]=0;
    std::memcpy(out+8,r.dac,3);*r.time=time+limit*140;
    __atomic_store_n(r.read,cursor,__ATOMIC_RELEASE);return int(at);
}
inline void sample_run(uint8_t* beep,uint8_t* covox,uint8_t* specdrum,
                       unsigned from,unsigned to,const uint8_t dac[3]) {
    if(covox)std::memset(covox+from,dac[1],to-from);
    if(specdrum)std::memset(specdrum+from,dac[2],to-from);
    if(beep && dac[0]) {
        while(from<to && (from&7)){beep[from/8]|=uint8_t(1u<<(from&7));++from;}
        const unsigned bytes=(to-from)/8;
        std::memset(beep+from/8,255,bytes);from+=bytes*8;
        if(from<to)beep[from/8]|=uint8_t((1u<<(to-from))-1);
    }
}
// Changing DACs are constant between event groups. Find the exact flags
// from the final value at each affected sample, then fill whole runs. Fall
// back to the bounded partial-block encoder if a full block cannot fit.
inline int prepare_runs(const mk61_service_audio_psg& r,uint8_t* out,unsigned limit,
                        uint32_t time,uint32_t start,uint32_t w) {
    uint32_t cursor=start;unsigned ay=0,flags=0;
    uint8_t dac[3],first[3];std::memcpy(dac,r.dac,3);std::memcpy(first,dac,3);
    while(cursor!=w) {
        const auto* e=event(r,cursor);const int32_t delta=int32_t(get32(e)-time);
        if(delta>int32_t(limit*140))break;
        const unsigned sample=delta<=0?0:(unsigned(delta)-1)/140;
        const uint32_t until=time+(sample+1)*140;
        do {
            e=event(r,cursor);
            if(e[4]<2){if(e[5]>15)return -1;++ay;}
            else if(e[4]<=4){if(e[4]==2 && e[6]>1)return -1;dac[e[4]-2]=e[6];}
            else return -1;
            ++cursor;
        } while(cursor!=w && int32_t(get32(event(r,cursor))-until)<=0);
        if(!sample)std::memcpy(first,dac,3);
        else for(unsigned d=0;d<3;++d)if(dac[d]!=first[d])flags|=1u<<d;
        if(11+((flags&1)?(limit+7)/8:0)+((flags&2)?limit:0)+((flags&4)?limit:0)+3*ay>CAPACITY)return -2;
    }
    const uint32_t accepted=cursor;
    put32(out,MAGIC);out[4]=1;out[5]=uint8_t(limit);out[6]=uint8_t(r.extensions);out[7]=uint8_t(flags);
    std::memcpy(out+8,first,3);
    unsigned at=11;uint8_t *beep=nullptr,*covox=nullptr,*specdrum=nullptr;
    if(flags&1){beep=out+at;const unsigned bytes=(limit+7)/8;std::memset(beep,0,bytes);at+=bytes;}
    if(flags&2){covox=out+at;at+=limit;}
    if(flags&4){specdrum=out+at;at+=limit;}
    unsigned from=0;cursor=start;std::memcpy(dac,r.dac,3);
    while(cursor!=accepted) {
        const auto* e=event(r,cursor);const int32_t delta=int32_t(get32(e)-time);
        const unsigned sample=delta<=0?0:(unsigned(delta)-1)/140;
        sample_run(beep,covox,specdrum,from,sample,dac);from=sample;
        const uint32_t until=time+(sample+1)*140;
        do {
            e=event(r,cursor);
            if(e[4]<2){out[at++]=uint8_t(sample);out[at++]=uint8_t(e[4]*16+e[5]);out[at++]=e[6];}
            else dac[e[4]-2]=e[6];
            ++cursor;
        } while(cursor!=accepted && int32_t(get32(event(r,cursor))-until)<=0);
    }
    sample_run(beep,covox,specdrum,from,limit,dac);
    std::memcpy(r.dac,dac,3);*r.time=time+limit*140;
    __atomic_store_n(r.read,accepted,__ATOMIC_RELEASE);return int(at);
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
    const int sparse=prepare_sparse(r,out,limit,time,start,w);
    if(sparse!=-2)return sparse;
    const int runs=prepare_runs(r,out,limit,time,start,w);
    if(runs!=-2)return runs;
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
