#include "m3_wire.hpp"
extern "C" {
#include "stm3_runtime.h"
#include "stm3_client.h"
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
    {
        // A valid CRC does not make an old-version request executable.
        Server s;Wire w;s.load(w);s.input(w,16);
        uint8_t raw[28]{},encoded[32]{};raw[0]=1;raw[1]=STM3_START_RESULT;
        raw[2]=uint8_t(w.sequence+1);raw[3]=uint8_t((w.sequence+1)>>8);raw[4]=16;
        Wire::put32(raw+8,s.module);Wire::put32(raw+12,16);Wire::put32(raw+16,10);Wire::put32(raw+20,16);
        Wire::put32(raw+24,Wire::crc(raw,24));const unsigned n=Wire::encode(raw,28,encoded);
        for(unsigned i=0;i<n;++i)stm3_feed(&s.runtime,encoded[i]);stm3_feed(&s.runtime,0);
        assert(!s.receive()&&!s.invocations&&s.runtime.state==STM3_READY);
    }
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
        // Cancelling a finished job must not rerun native synthesis.
        // Lost/replayed completion is still tested before a new command.
        // A lost or replayed completion cannot repeat the native job.
        const auto reply=s.last_reply;const unsigned n=s.last_bytes;
        assert(w.replay(s.now));s.send(w);assert(s.receive(&w)==n);
        assert(reply==s.last_reply && !w.result && s.invocations==1);
        assert(w.begin(STM3_UNLOAD,nullptr,0,s.now));s.exchange(w);assert(!w.result && s.runtime.state==STM3_EMPTY);
    }
    {
        // The real-time form carries the entire small input in the same
        // at-most-once request as START_RESULT. No WRITE acknowledgement is
        // needed, and malformed lengths do not change resident input memory.
        Server s;Wire w;s.immediate=true;s.load(w);
        std::array<uint8_t,240> input{};for(unsigned i=0;i<input.size();++i)input[i]=uint8_t(i*3+1);
        uint8_t arg[16];Wire::put32(arg,s.module);Wire::put32(arg+4,input.size());
        Wire::put32(arg+8,10);Wire::put32(arg+12,input.size());
        assert(w.begin_pair(STM3_START_RESULT_INPUT,arg,sizeof(arg),input.data(),input.size(),s.now,12000));
        s.exchange(w);assert(!w.result && w.reply_bytes==8+input.size() && s.invocations==1);
        for(unsigned i=0;i<input.size();++i)assert(w.reply()[8+i]==uint8_t(input[i]^0x5a));
        assert(w.begin(STM3_UNLOAD,nullptr,0,s.now));s.exchange(w);assert(!w.result);
        s.load(w);Wire::put32(arg,s.module);Wire::put32(arg+4,input.size()-1);
        Wire::put32(arg+8,10);Wire::put32(arg+12,1);
        const auto invocations=s.invocations;
        assert(w.begin_pair(STM3_START_RESULT_INPUT,arg,sizeof(arg),input.data(),input.size(),s.now,12000));
        s.exchange(w);assert(w.result==STM3_E_SIZE && s.invocations==invocations);
        for(uint8_t value:s.runtime.input)assert(value==0);
    }
    // Result v2 uses one ceiling contract for both fused commands.
    for(bool immediate:{false,true})for(unsigned command:{11u,12u})
    for(unsigned actual:{0u,1u,16u,118u,240u})for(unsigned ceiling:{0u,1u,118u,244u,245u}) {
        Server s;Wire w;s.immediate=immediate;s.load(w);s.input(w,actual);
        uint8_t arg[16];Wire::put32(arg,s.module);Wire::put32(arg+4,actual);
        Wire::put32(arg+8,10);Wire::put32(arg+12,ceiling);
        std::array<uint8_t,240> input{};
        for(unsigned i=0;i<actual;++i)input[i]=uint8_t(i);
        if(command==12)assert(w.begin_pair(command,arg,16,input.data(),actual,s.now,12000));
        else assert(w.begin(command,arg,16,s.now,12000));
        s.send(w);
        if(ceiling>244) {
            assert(s.receive(&w)&&w.result==STM3_E_SIZE&&!s.invocations);continue;
        }
        if(s.runtime.state==STM3_RUNNING) {
            s.send(w);assert(!s.receive()&&s.invocations==1);
            while(s.runtime.state==STM3_RUNNING)stm3_tick(&s.runtime);
        }
        const unsigned count=actual<ceiling?actual:ceiling;
        assert(s.receive(&w)&&!w.result&&w.reply_bytes==8+count&&s.invocations==1);
        for(unsigned i=0;i<count;++i)assert(w.reply()[8+i]==uint8_t(i^0x5a));
        const auto reply=s.last_reply;const unsigned n=s.last_bytes;
        assert(w.replay(s.now));s.exchange(w);
        assert(s.last_reply==reply&&s.last_bytes==n&&s.invocations==1);
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
        assert(s.receive(&w) && !w.result && w.reply_bytes==24 && s.invocations==1);
        s.start(w,64,64);assert(!s.receive());
        w.tick(s.now+12000);assert(w.result==Wire::TIMEOUT);
        for(unsigned i=0;i<4;++i)stm3_tick(&s.runtime);
        // Drop the completed reply, then replay the original request.
        assert(s.receive());const auto completed=s.last_reply;const auto n=s.last_bytes;
        assert(w.replay(s.now));s.exchange(w);
        assert(!w.result && s.last_bytes==n && s.last_reply==completed && s.invocations==2);
    }
    {
        Server s;Wire w;s.load(w);s.input(w,64);
        uint8_t arg[16];Wire::put32(arg,s.module);Wire::put32(arg+4,64);
        Wire::put32(arg+8,10);Wire::put32(arg+12,244);
        assert(w.begin(STM3_START_RESULT,arg,15,s.now));s.exchange(w);
        assert(w.result==STM3_E_ARGUMENT&&!s.invocations);
        assert(w.begin_pair(STM3_START_RESULT_INPUT,arg,16,arg,1,s.now));s.exchange(w);
        assert(w.result==STM3_E_SIZE&&!s.invocations);
        // Truncated COBS and bad CRC cannot execute a native job.
        assert(w.begin(STM3_START_RESULT,arg,16,s.now));
        for(unsigned i=0;i<w.tx_bytes/2;++i)stm3_feed(&s.runtime,w.tx[i]);
        stm3_feed(&s.runtime,0);assert(!s.receive()&&!s.invocations);
        Wire damaged=w;damaged.tx[damaged.tx_bytes-3]^=0x40;s.send(damaged);
        assert(!s.receive()&&!s.invocations);
        s.send(w);assert(!s.receive()&&s.invocations==1);
        // A second command cannot cancel or overwrite an outstanding reply.
        Wire cancel;cancel.sequence=w.sequence;uint8_t job[4];Wire::put32(job,s.runtime.job_id);
        assert(cancel.begin(STM3_CANCEL_JOB,job,4,s.now));s.send(cancel);
        assert(!s.receive()&&s.runtime.state==STM3_RUNNING);
        for(unsigned i=0;i<4;++i)stm3_tick(&s.runtime);
        assert(s.receive(&w)&&!w.result&&w.reply_bytes==72);
        assert(w.begin(STM3_CANCEL_JOB,job,4,s.now));s.exchange(w);
        assert(w.result==STM3_E_STATE&&s.invocations==1);
        assert(w.begin(STM3_UNLOAD,nullptr,0,s.now));s.exchange(w);assert(!w.result);
        s.load(w);s.input(w,64);
        Wire::put32(arg,s.module);Wire::put32(arg+4,64);Wire::put32(arg+8,10);
        assert(w.begin(STM3_START,arg,12,s.now));s.exchange(w);assert(!w.result);
        Wire::put32(job,s.runtime.job_id);
        assert(w.begin(STM3_CANCEL_JOB,job,4,s.now));s.exchange(w);
        assert(!w.result&&s.runtime.state==STM3_CANCELLED);
        const auto backend=s.runtime.backend;stm3_init(&s.runtime,&backend);
        assert(s.runtime.state==STM3_EMPTY&&!s.runtime.deferred&&!s.runtime.have_reply);
        assert(w.begin(STM3_HELLO,nullptr,0,s.now));s.exchange(w);
        assert(!w.result&&(Wire::get32(w.reply()+32)&STM3_TRANSPORT_RESULT_V2));
        s.load(w);s.input(w,16);s.immediate=true;s.start(w,16,244);
        assert(s.receive(&w)&&!w.result&&w.reply_bytes==24);
    }
    {
        // Public C SDK and async C++ adapter operate on the same wire v2.
        Server s;Wire w;s.load(w);s.input(w,16);
        struct Link {Server* server;unsigned at=0;};Link link{&s};
        stm3_client_io io{};io.context=&link;
        io.micros=[](void* p){return ++static_cast<Link*>(p)->server->now;};
        io.send=[](void* p,const uint8_t* data,unsigned n,uint32_t)->int {
            auto& l=*static_cast<Link*>(p);l.at=0;
            for(unsigned i=0;i<n;++i)stm3_feed(&l.server->runtime,data[i]);return 1;
        };
        io.read_byte=[](void* p,uint32_t)->int {
            auto& l=*static_cast<Link*>(p);auto& s=*l.server;
            if(l.at>=s.last_bytes){
                for(unsigned i=0;i<20&&!s.receive();++i)stm3_tick(&s.runtime);
                l.at=0;
            }
            return l.at<s.last_bytes?s.last_reply[l.at++]:-1;
        };
        s.last_bytes=0;stm3_client c;stm3_client_init(&c,&io);c.seq=w.sequence;
        uint8_t arg[16],reply[252];Wire::put32(arg,s.module);Wire::put32(arg+4,16);
        Wire::put32(arg+8,10);Wire::put32(arg+12,244);unsigned n=sizeof(reply);
        assert(!stm3_client_request(&c,S3_START_RESULT,arg,16,reply,&n,12000));
        assert(n==24&&s.invocations==1);
        const auto exact=s.last_reply;const unsigned bytes=s.last_bytes;s.last_bytes=0;
        n=sizeof(reply);assert(!stm3_client_replay(&c,reply,&n,12000));
        assert(n==24&&s.last_reply==exact&&s.last_bytes==bytes&&s.invocations==1);
    }
    std::puts("M3 completion: deferred/inline max244-byte replies, no polls, duplicate pending/done at-most-once, conflicting sequences, lost reply recovery, INIT/STEP/deadline E_TIME and timer wrap PASS");
}
