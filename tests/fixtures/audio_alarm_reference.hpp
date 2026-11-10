// Test-only reference before diagnostic storage compaction.
#ifndef MK61_TEST_AUDIO_ALARM_REFERENCE_HPP
#define MK61_TEST_AUDIO_ALARM_REFERENCE_HPP
#include <cstdint>
#include <cstddef>
#if defined(__GNUC__) && !defined(__clang__)
#define MK61_ALARM_DIAGNOSTIC_COMPACT(name) __attribute__((noinline,optimize("Os"),section(".audio_alarm_diagnostics." name)))
#else
#define MK61_ALARM_DIAGNOSTIC_COMPACT(name)
#endif
namespace picocalc {
// Diagnostic records only. All observations run on the owned IRQ's core.
// Arm is sampled immediately after the unchanged SDK IRQ handler returns;
// timestamps bracket register reads rather than pretending they are atomic.
struct LegacyAlarmTrace {
    struct Registers {
        const volatile uint32_t* target=nullptr;
        const volatile uint32_t* remaining=nullptr;
        const volatile uint32_t* filled=nullptr;
        const volatile uint32_t* fraction=nullptr;
        const volatile uint32_t* armed=nullptr;
    } regs;
    struct Sample {
        uint32_t at=0,end=0,target=0,head=0,filled=0,fraction=0,armed=0;
        uint32_t entry=0,callbacks=0,from_target=0;
        int32_t interval=0;
    };
    struct Snapshot {
        Sample arm,fire;
        uint32_t callback_at=0,callback_head=0,callback_filled=0,valid=0;
    } captured;
    Sample arm,fire;
    uint32_t sequence=0,callbacks=0,mask=0;
    int32_t interval=0;
    uint32_t start_before=0,start_after=0,start_fraction=0;
    bool configured=false;
    MK61_ALARM_DIAGNOSTIC_COMPACT("configure") void configure(Registers r,uint32_t owned_mask) {
        *this={};regs=r;mask=owned_mask;
        configured=r.target && r.remaining && r.filled && r.fraction && r.armed && mask;
    }
    template<class Clock> void sample(Sample& s,Clock clock)const {
        s.at=clock();s.target=*regs.target;
        s.head=UINT32_MAX-*regs.remaining;s.filled=*regs.filled;
        s.fraction=*regs.fraction;s.armed=*regs.armed&mask;
        s.end=clock();
    }
    template<class Clock> void enter(Clock clock) {
        if(!configured)return;
        callbacks=0;interval=0;
        sample(fire,clock);fire.entry=++sequence;
    }
    void callback(){if(configured)++callbacks;}
    void planned(int32_t delay){if(configured)interval=delay;}
    template<class Clock> void after(Clock clock) {
        if(!configured)return;
        sample(arm,clock);arm.entry=sequence;arm.callbacks=callbacks;arm.interval=interval;arm.from_target=fire.target;
    }
    MK61_ALARM_DIAGNOSTIC_COMPACT("fault") void fault(uint32_t at,uint32_t head,uint32_t filled) {
        if(!configured || captured.valid)return;
        captured.arm=arm;captured.fire=fire;captured.fire.callbacks=callbacks;
        captured.callback_at=at;captured.callback_head=head;captured.callback_filled=filled;
        captured.valid=1;
    }
    MK61_ALARM_DIAGNOSTIC_COMPACT("snapshot") Snapshot snapshot()const {
        if(captured.valid)return captured;
        Snapshot result;result.arm=arm;result.fire=fire;return result;
    }
};
#if defined(__ARM_ARCH_6M__)
static_assert(sizeof(LegacyAlarmTrace::Sample)==44 && sizeof(LegacyAlarmTrace::Snapshot)==104);
static_assert(offsetof(LegacyAlarmTrace,captured)==20 && offsetof(LegacyAlarmTrace,arm)==124 &&
              offsetof(LegacyAlarmTrace,fire)==168 && offsetof(LegacyAlarmTrace,sequence)==212 &&
              offsetof(LegacyAlarmTrace,callbacks)==216 && offsetof(LegacyAlarmTrace,mask)==220 &&
              offsetof(LegacyAlarmTrace,interval)==224 && offsetof(LegacyAlarmTrace,configured)==240);
static_assert(sizeof(LegacyAlarmTrace)==244);
#endif
}
#undef MK61_ALARM_DIAGNOSTIC_COMPACT
#endif
