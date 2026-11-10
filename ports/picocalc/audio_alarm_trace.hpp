#ifndef MK61_PICOCALC_AUDIO_ALARM_TRACE_HPP
#define MK61_PICOCALC_AUDIO_ALARM_TRACE_HPP
#include <cstdint>
#include <cstddef>
#if defined(__GNUC__) && !defined(__clang__)
#define MK61_ALARM_COMPACT(name) __attribute__((noinline,optimize("Os"),section(".audio_alarm_diagnostics." name)))
#else
#define MK61_ALARM_COMPACT(name)
#endif
namespace picocalc {
// Only the owned IRQ writes this state. The first fault freezes both live
// observations; there is no second retained copy. An IRQ cannot nest itself.
struct AudioAlarmTrace {
    struct Sample {uint32_t at=0,end=0,target=0,head=0,filled=0,fraction=0,armed=0,entry=0,callbacks=0,from_target=0;int32_t interval=0;};
    struct Snapshot {Sample arm,fire;uint32_t callback_at=0,callback_head=0,callback_filled=0,valid=0;};
    struct Raw {uint32_t at=0,end=0,target=0,head=0,filled=0,fraction=0;};
    struct Arm {Raw raw;uint32_t from_target=0,callbacks=0;} arm;
    struct Fire {Raw raw;uint32_t callbacks=0;} fire;
    uint32_t sequence=0,start_before=0,start_after=0,start_fraction=0;
    uint32_t callback_at=0,callback_head=0,callback_filled=0,meta=0;
    enum :uint32_t { CONFIGURED=1,FROZEN=2,ARM_VALID=4,INDEX_SHIFT=3,ARM_ARMED=32,FIRE_ARMED=64,
                    ARM_DELAY_SHIFT=7,CURRENT_DELAY_SHIFT=9,DELAY_MASK=3 };
    bool recording()const{return(meta&(CONFIGURED|FROZEN))==CONFIGURED;}
    uint32_t mask()const{return(meta&CONFIGURED)?1u<<((meta>>INDEX_SHIFT)&3):0;}
    static uint32_t delay_code(int32_t delay){return delay==0?0:delay==-40?1:delay==-1280?2:3;}
    static int32_t delay_value(uint32_t code){return code==0?0:code==1?-40:code==2?-1280:INT32_MIN;}
    MK61_ALARM_COMPACT("configure") void configure(uint32_t owned_mask){
        *this={};if(!owned_mask||owned_mask>8||(owned_mask&(owned_mask-1)))return;
        unsigned index=0;while((1u<<index)!=owned_mask)++index;
        meta=CONFIGURED|(index<<INDEX_SHIFT);
    }
    template<class Port,class Clock> void sample(Raw& out,uint32_t armed_bit,Port p,Clock clock){
        out.at=clock();out.target=p.target();out.head=p.head();out.filled=p.filled();out.fraction=p.fraction();
        const uint32_t armed=p.armed()&mask();out.end=clock();
        meta=armed?meta|armed_bit:meta&~armed_bit;
    }
    template<class Port,class Clock> void enter(Port p,Clock clock){
        if(!recording())return;
        fire.callbacks=0;meta&=~(DELAY_MASK<<CURRENT_DELAY_SHIFT);
        sample(fire.raw,FIRE_ARMED,p,clock);++sequence;
    }
    void callback(){if(recording())++fire.callbacks;}
    void planned(int32_t delay){if(recording())meta=(meta&~(DELAY_MASK<<CURRENT_DELAY_SHIFT))|(delay_code(delay)<<CURRENT_DELAY_SHIFT);}
    template<class Port,class Clock> void after(Port p,Clock clock){
        if(!recording())return;
        sample(arm.raw,ARM_ARMED,p,clock);arm.from_target=fire.raw.target;arm.callbacks=fire.callbacks;
        const uint32_t code=(meta>>CURRENT_DELAY_SHIFT)&DELAY_MASK;
        meta=(meta&~(DELAY_MASK<<ARM_DELAY_SHIFT))|(code<<ARM_DELAY_SHIFT)|ARM_VALID;
    }
    MK61_ALARM_COMPACT("fault") void fault(uint32_t at,uint32_t head,uint32_t filled){
        if(!recording())return;
        callback_at=at;callback_head=head;callback_filled=filled;meta|=FROZEN;
    }
    static void expand(Sample& s,const Raw&r){s.at=r.at;s.end=r.end;s.target=r.target;s.head=r.head;s.filled=r.filled;s.fraction=r.fraction;}
    MK61_ALARM_COMPACT("snapshot") Snapshot snapshot()const{
        Snapshot s;expand(s.arm,arm.raw);expand(s.fire,fire.raw);
        const bool frozen=meta&FROZEN;
        s.arm.armed=(meta&ARM_ARMED)?mask():0;s.fire.armed=(meta&FIRE_ARMED)?mask():0;
        s.arm.entry=(meta&ARM_VALID)?sequence-unsigned(frozen):0;s.fire.entry=sequence;
        s.arm.callbacks=arm.callbacks;s.fire.callbacks=fire.callbacks;s.arm.from_target=arm.from_target;
        s.arm.interval=delay_value((meta>>ARM_DELAY_SHIFT)&DELAY_MASK);
        s.callback_at=callback_at;s.callback_head=callback_head;s.callback_filled=callback_filled;s.valid=frozen;
        return s;
    }
};
static_assert(sizeof(AudioAlarmTrace)==92,"Exact arm/fire data must fit inactive local DMA storage");
}
#undef MK61_ALARM_COMPACT
#endif
