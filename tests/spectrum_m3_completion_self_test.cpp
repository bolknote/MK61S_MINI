#include "m3_wire.hpp"
extern "C" {
#include "stm3_runtime.h"
}
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
using picocalc::m3::Wire;

struct Server {
    stm3_runtime runtime{};
    uint32_t now=0,cost=0,invocations=0;
    bool immediate=false;
    uint32_t module=0;
    std::array<uint8_t,272> last_reply{};
    unsigned last_bytes=0;
    Server() {
        stm3_backend b{};b.context=this;
        b.micros=[](void* p){return static_cast<Server*>(p)->now;};
        b.load_address=[](void*,const void*){return 0x20001000u;};
        b.invoke=[](void* p,uint32_t,uint32_t op,const stm3_api*,stm3_job* j)->uint32_t {
            auto& s=*static_cast<Server*>(p);
            if(op==STM3_CANCEL || op==STM3_FINI)return STM3_DONE;
            s.now+=s.cost;
            if(op==STM3_INIT){++s.invocations;j->output_bytes=j->input_bytes;}
            const unsigned end=s.immediate?j->input_bytes:
                (j->progress+16<j->input_bytes?j->progress+16:j->input_bytes);
            if(op==STM3_INIT && !s.immediate)return STM3_MORE;
            for(unsigned i=j->progress;i<end;++i)j->output[i]=j->input[i]^0x5a;
            j->progress=end;return end==j->input_bytes?STM3_DONE:STM3_MORE;
        };
        stm3_init(&runtime,&b);
    }
    void send(const Wire& w) {for(unsigned i=0;i<w.tx_bytes;++i)stm3_feed(&runtime,w.tx[i]);}
    unsigned receive(Wire* w=nullptr) {
        last_bytes=stm3_transmit(&runtime,last_reply.data(),last_reply.size());
        if(w)for(unsigned i=0;i<last_bytes;++i)w->feed(last_reply[i]);
        return last_bytes;
    }
    void exchange(Wire& w) {send(w);assert(receive(&w) && w.complete && !w.pending);}
    void load(Wire& w) {
        stm3_header h{};h.magic=STM3_MAGIC;h.abi=STM3_ABI;h.header_bytes=64;h.package_bytes=68;
        h.image_bytes=4;h.entry_offset=1;h.input_limit=h.output_limit=512;h.slice_us=2000;h.target=STM3_TARGET;
        uint8_t package[68]{};h.payload_crc=stm3_crc32(package+64,4);h.header_crc=stm3_crc32(&h,60);
        std::memcpy(package,&h,64);uint8_t arg[4];Wire::put32(arg,sizeof(package));
        assert(w.begin(STM3_LOAD_BEGIN,arg,4,now));exchange(w);assert(!w.result);
        assert(w.begin(STM3_LOAD_CHUNK,package,sizeof(package),now,5000,true,0));exchange(w);assert(!w.result);
        assert(w.begin(STM3_LOAD_COMMIT,nullptr,0,now));exchange(w);assert(!w.result);module=Wire::get32(w.reply());
    }
    void input(Wire& w,unsigned n) {
        std::array<uint8_t,512> data{};for(unsigned i=0;i<n;++i)data[i]=uint8_t(i);
        for(unsigned at=0;at<n;) {
            const unsigned take=n-at<252?n-at:252;
            assert(w.begin(STM3_WRITE,data.data()+at,take,now,5000,true,at));exchange(w);assert(!w.result);at+=take;
        }
    }
    void start(Wire& w,unsigned n,unsigned out,unsigned deadline=10) {
        uint8_t arg[16];Wire::put32(arg,module);Wire::put32(arg+4,n);
        Wire::put32(arg+8,deadline);Wire::put32(arg+12,out);
        assert(w.begin(STM3_START_RESULT,arg,sizeof(arg),now,12000));send(w);
    }
};

int main() {
    for(bool immediate:{false,true}) {
        Server s;Wire w;s.immediate=immediate;s.load(w);s.input(w,244);s.start(w,244,244);
        if(!immediate) {
            assert(s.runtime.deferred && s.runtime.state==STM3_RUNNING && !s.receive());
            const auto before=s.runtime.steps;s.send(w);assert(!s.receive());
            assert(s.invocations==1 && s.runtime.steps==before);
            Wire conflict;conflict.sequence=w.sequence-1;uint8_t wrong[16]{};
            assert(conflict.begin(STM3_START_RESULT,wrong,sizeof(wrong),s.now));s.send(conflict);
            assert(s.runtime.sequence_conflicts==1 && !s.receive());
            conflict.fail(Wire::TIMEOUT);conflict.sequence=w.sequence;
            assert(conflict.begin(STM3_HELLO,nullptr,0,s.now));s.send(conflict);
            assert(s.runtime.sequence_conflicts==2 && !s.receive());
            for(unsigned i=0;i<15;++i){stm3_tick(&s.runtime);assert(!s.receive());}
            stm3_tick(&s.runtime);
        }
        assert(s.receive(&w) && !w.result && w.reply_bytes==252);
        assert(Wire::get32(w.reply())==s.runtime.job_id && !Wire::get32(w.reply()+4));
        for(unsigned i=0;i<244;++i)assert(w.reply()[8+i]==uint8_t(i^0x5a));
        assert(s.invocations==1 && !s.runtime.deferred && s.runtime.state==STM3_FINISHED);
        // A lost or replayed completion cannot repeat the native job.
        const auto reply=s.last_reply;const unsigned n=s.last_bytes;
        assert(w.replay(s.now));s.send(w);assert(s.receive(&w)==n);
        assert(reply==s.last_reply && !w.result && s.invocations==1);
        assert(w.begin(STM3_UNLOAD,nullptr,0,s.now));s.exchange(w);assert(!w.result && s.runtime.state==STM3_EMPTY);
    }
    for(unsigned fault=0;fault<3;++fault) {
        Server s;Wire w;s.load(w);s.input(w,64);s.now=0xfffffff0u;
        if(fault==0)s.cost=2001; // INIT overrun, even though code returned MORE.
        s.start(w,64,64);
        if(fault==1){s.cost=2001;stm3_tick(&s.runtime);} // STEP overrun.
        if(fault==2){s.now+=10001;stm3_tick(&s.runtime);} // Deadline over timer wrap.
        assert(s.receive(&w) && w.result==STM3_E_TIME && !w.reply_bytes);
        assert(s.runtime.state==STM3_FAULT && !s.runtime.deferred && s.invocations==1);
        assert(w.replay(s.now));s.exchange(w);assert(w.result==STM3_E_TIME && s.invocations==1);
    }
    {
        Server s;Wire w;s.load(w);s.input(w,64);
        s.start(w,64,245);assert(s.receive(&w) && w.result==STM3_E_SIZE && !s.invocations);
        s.start(w,16,64);assert(!s.receive());stm3_tick(&s.runtime);
        assert(s.receive(&w) && w.result==STM3_E_SIZE && s.invocations==1);
        s.start(w,64,64);assert(!s.receive());
        w.tick(s.now+12000);assert(w.result==Wire::TIMEOUT);
        for(unsigned i=0;i<4;++i)stm3_tick(&s.runtime);
        // Drop the completed reply, then replay the original request.
        assert(s.receive());const auto completed=s.last_reply;const auto n=s.last_bytes;
        assert(w.replay(s.now));s.exchange(w);
        assert(!w.result && s.last_bytes==n && s.last_reply==completed && s.invocations==2);
    }
    std::puts("M3 completion: deferred/inline max244-byte replies, no polls, duplicate pending/done at-most-once, conflicting sequences, lost reply recovery, INIT/STEP/deadline E_TIME and timer wrap PASS");
}
