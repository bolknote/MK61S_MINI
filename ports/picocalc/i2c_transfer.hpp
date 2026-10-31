#ifndef MK61_PICOCALC_I2C_TRANSFER_HPP
#define MK61_PICOCALC_I2C_TRANSFER_HPP
#include <cstdint>
namespace picocalc {
// The BIOS messages fit in the controller FIFO. Queue the entire message,
// then let RX/STOP/abort IRQs advance it without waiting for bus clocks.
class I2cTransfer {
public:
    enum : unsigned { STOP=1, ABORT=2, RX_OVERFLOW=4, READ=0x100, END=0x200 };
    static constexpr unsigned CAPACITY=2;
    template<class Bus> bool begin(Bus& bus,bool read,const uint8_t* bytes,unsigned size,uint64_t now) {
        if(active_ || !size || size>CAPACITY || (!read && !bytes)) return false;
        read_=read;size_=size;used_=0;result_=0;timed_out_=aborted_=false;
        started_=now;deadline_=now+10000;active_=true;
        bus.prepare(read);
        for(unsigned i=0;i<size;++i) bus.put((read?READ:bytes[i])|(i+1==size?END:0));
        return true;
    }
    template<class Bus> bool step(Bus& bus,uint64_t now) {
        if(!active_) return false;
        const unsigned flags=bus.flags();
        bool overflow=false;
        for(unsigned i=0;i<16 && bus.available();++i) {
            const auto byte=bus.get();
            if(!read_ || used_>=size_) overflow=true;
            else bytes_[used_++]=byte;
        }
        aborted_=(flags&(ABORT|RX_OVERFLOW)) || overflow;
        if(aborted_) result_=-1;
        else if(flags&STOP) result_=!read_ || used_==size_?(int)size_:-1;
        else if(now>=deadline_) { timed_out_=true;result_=-2; }
        else return false;
        // Quiesce/reset before publishing completion: flash and clock changes
        // may proceed as soon as the foreground observes the finished job.
        bus.finish(result_<0);active_=false;elapsed_=(uint32_t)(now-started_);return true;
    }
    bool active() const { return active_; }
    uint64_t deadline() const { return deadline_; }
    int result() const { return result_; }
    const uint8_t* bytes() const { return bytes_; }
    bool timed_out() const { return timed_out_; }
    bool aborted() const { return aborted_; }
    uint32_t elapsed() const { return elapsed_; }
private:
    bool active_=false,read_=false,timed_out_=false,aborted_=false;
    unsigned size_=0,used_=0;int result_=0;
    uint8_t bytes_[CAPACITY]{};
    uint64_t started_=0,deadline_=0;uint32_t elapsed_=0;
};
}
#endif
