#ifndef MK61_PICOCALC_WORKER_DEADLINE_TRACE_HPP
#define MK61_PICOCALC_WORKER_DEADLINE_TRACE_HPP
#include <atomic>
#include <cstdint>
namespace picocalc {
struct WorkerDeadlineTrace {
    enum Step : unsigned { SERVICE=1,FINISH=2,BEGIN=3,ALARM=4,IRQ=5,M3=6,UART=7,FRAME=8,PACE=9,COMPUTE=10,
        LCD_CONTROL=11,LCD_PREPARE=12,LCD_WAIT=13,LCD_CRC=14,LCD_PUBLISH=15 };
    static constexpr uint32_t TIME_MASK=0x0fffffff;
    // One atomic publication lets the PWM IRQ capture a consistent site/time
    // without waiting for a preempted foreground writer (no seqlock/spinlock).
    std::atomic<uint32_t> mark{0},resets{0},fault_site{0},fault_age_us{0};
    uint32_t enter(Step site,uint32_t now) {
        const uint32_t previous=mark.load(std::memory_order_relaxed);
        mark.store((now<<4)|unsigned(site),std::memory_order_release);return previous;
    }
    void leave(Step site,uint32_t previous,uint32_t now) {
        (void)site;(void)now;mark.store(previous,std::memory_order_release);
    }
    void reset_controller(){resets.store(resets.load(std::memory_order_relaxed)+1,std::memory_order_relaxed);}
    void begin_audio() {
        fault_site.store(0,std::memory_order_relaxed);
        fault_age_us.store(0,std::memory_order_relaxed);
    }
    void audio_fault(uint32_t now) {
        const uint32_t current=mark.load(std::memory_order_acquire);
        fault_site.store(current&15,std::memory_order_relaxed);
        fault_age_us.store(current?((now&TIME_MASK)-(current>>4))&TIME_MASK:0,std::memory_order_relaxed);
    }
    template<class Clock> struct Scope {
        WorkerDeadlineTrace& trace;Step site;Clock clock;uint32_t previous;
        Scope(WorkerDeadlineTrace& t,Step s,Clock c):trace(t),site(s),clock(c),previous(t.enter(s,c())){}
        ~Scope(){trace.leave(site,previous,clock());}
        Scope(const Scope&)=delete;
        Scope& operator=(const Scope&)=delete;
    };
};
}
#endif
