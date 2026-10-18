#ifndef MK61_PICOCALC_NATIVE_KEYBOARD_HPP
#define MK61_PICOCALC_NATIVE_KEYBOARD_HPP
#include "input.hpp"
#include "keyboard_core.hpp"
namespace picocalc {
// One event stream backs both the logical APP keys and legacy scan API.
// Handoff suppresses only the causal gesture through its release.
class NativeKeyboard {
public:
    void event(KeyEvent event,u32 now) {
        if(!event.code || (event.state!=1 && event.state!=3)) return;
        const int raw=controls::native_key(event);
        if(event.state==3 && controls::raw_pressed(raw,now)) return;
        const u64 bit=raw>=0 && raw<40?u64(1)<<raw:0;
        if(suppressed_&bit) { if(event.state==3) suppressed_&=~bit;return; }
        if(event.state==1) immediate_|=bit;
        if(count_<32) { queue_[(head_+count_)%32]=event;++count_; }
    }
    int press() {
        while(count_) { const auto e=pop();if(e.state==1) return e.code; }
        return -1;
    }
    int raw(int state=-1) {
        while(count_) {
            const auto e=pop();
            if(state!=-1 && (state==0)!=(e.state==1)) continue;
            const int key=controls::native_key(e);
            if(e.state==3 && key>=MK61_APP_KEY_RAW_BASE) continue;
            return key|(e.state==3?keyboard_core::RELEASE_MASK:0);
        }
        return -1;
    }
    int last() const { return last_; }
    bool immediate(int key) {
        if(key<0 || key>=40) return false;
        const u64 bit=u64(1)<<key;const bool present=(immediate_&bit) && !(suppressed_&bit);
        immediate_&=~bit;return present;
    }
    void clear_immediate() { immediate_=0; }
    void handoff(int key,u32 now) {
        if(key<0 || key>=40) return;
        const u64 bit=u64(1)<<key;immediate_&=~bit;
        if(controls::raw_pressed(key,now)) suppressed_|=bit;
        bool causal=true;const unsigned old=count_;
        for(unsigned i=0;i<old;++i) {
            const auto e=pop(false);
            if(causal && controls::native_key(e)==key) {
                if(e.state==3) { causal=false;suppressed_&=~bit; }
            } else { queue_[(head_+count_)%32]=e;++count_; }
        }
    }
    bool pending(u32 now) {
        for(int key=0;key<40;++key) if((suppressed_&(u64(1)<<key)) && !controls::raw_pressed(key,now))
            suppressed_&=~(u64(1)<<key);
        return suppressed_!=0;
    }
private:
    KeyEvent pop(bool remember=true) {
        const auto e=queue_[head_];head_=(head_+1)%32;--count_;
        if(remember) last_=controls::native_key(e)|(e.state==3?keyboard_core::RELEASE_MASK:0);
        return e;
    }
    KeyEvent queue_[32]{};
    u8 head_=0,count_=0;
    int last_=-1;
    u64 immediate_=0,suppressed_=0;
};
}
#endif
