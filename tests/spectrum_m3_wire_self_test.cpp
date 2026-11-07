#include "m3_wire.hpp"
extern "C" {
#include "stm3_runtime.h"
}
#include <array>
#include <cassert>
#include <cstdio>
using picocalc::m3::Wire;
struct Server {
    stm3_runtime runtime{};unsigned invocations=0;uint32_t now=0,cost=0;
    Server() {
        stm3_backend backend{};backend.context=this;backend.micros=[](void* p){return static_cast<Server*>(p)->now;};
        backend.load_address=[](void*,const void*){return uint32_t(0x20001000);};
        backend.invoke=[](void* raw,uint32_t,uint32_t op,const stm3_api*,stm3_job* job)->uint32_t {
            auto& s=*static_cast<Server*>(raw);if(op==STM3_FINI || op==STM3_CANCEL)return STM3_DONE;
            assert(op==STM3_INIT);++s.invocations;s.now+=s.cost;job->output_bytes=job->input_bytes;
            for(unsigned i=0;i<job->input_bytes;++i)job->output[i]=job->input[i]^0x5a;
            return STM3_DONE;
        };
        stm3_init(&runtime,&backend);
    }
    void exchange(Wire& w) {
        for(unsigned i=0;i<w.tx_bytes;++i)stm3_feed(&runtime,w.tx[i]);
        uint8_t bytes[272];const unsigned n=stm3_transmit(&runtime,bytes,sizeof(bytes));assert(n);
        for(unsigned i=0;i<n;++i)w.feed(bytes[i]);assert(w.complete && !w.pending);
    }
};
int main() {
    Server server;Wire w;assert(w.begin(STM3_HELLO,nullptr,0,0));server.exchange(w);
    assert(!w.result && w.reply_bytes==36 && Wire::get32(w.reply())==STM3_ABI);
    assert(Wire::get32(w.reply()+32)&STM3_TRANSPORT_START_RESULT_INPUT);
    assert(!w.begin(0,nullptr,0,0) && !w.begin(128,nullptr,0,0));
    assert(!w.begin(1,nullptr,0xffffffffu,0));
    std::array<uint8_t,512> bytes{};
    assert(!w.begin_pair(STM3_START_RESULT_INPUT,bytes.data(),200,bytes.data(),57,0));
    assert(!w.begin_pair(STM3_START_RESULT_INPUT,nullptr,1,bytes.data(),1,0));
    stm3_header header{};header.magic=STM3_MAGIC;header.abi=STM3_ABI;header.header_bytes=64;header.package_bytes=68;
    header.image_bytes=4;header.bss_bytes=4;header.entry_offset=1;header.input_limit=header.output_limit=512;
    header.stack_hint=128;header.slice_us=2000;header.target=STM3_TARGET;
    const uint8_t code[4]={0x70,0x47,0x00,0xbf};header.payload_crc=stm3_crc32(code,4);header.header_crc=stm3_crc32(&header,60);
    std::memcpy(bytes.data(),&header,64);std::memcpy(bytes.data()+64,code,4);
    uint8_t args[12];Wire::put32(args,68);assert(w.begin(STM3_LOAD_BEGIN,args,4,0));server.exchange(w);assert(!w.result);
    assert(w.begin(STM3_LOAD_CHUNK,bytes.data(),68,0,5000,true,0));server.exchange(w);assert(!w.result && Wire::get32(w.reply())==68);
    assert(w.begin(STM3_LOAD_COMMIT,nullptr,0,0));server.exchange(w);assert(!w.result);
    const uint32_t module=Wire::get32(w.reply());
    for(unsigned i=0;i<512;++i)bytes[i]=uint8_t(i);
    for(unsigned at=0;at<512;at+=252) {
        const unsigned n=512-at<252?512-at:252;
        assert(w.begin(STM3_WRITE,bytes.data()+at,n,0,5000,true,at));server.exchange(w);assert(!w.result);
    }
    Wire::put32(args,module);Wire::put32(args+4,512);Wire::put32(args+8,1000);
    assert(w.begin(STM3_START,args,12,0));server.exchange(w);assert(!w.result && server.invocations==1);
    const uint32_t job=Wire::get32(w.reply());
    assert(w.replay(100));server.exchange(w);assert(!w.result && Wire::get32(w.reply())==job && server.invocations==1);
    for(unsigned at=0;at<512;at+=252) {
        const unsigned n=512-at<252?512-at:252;
        Wire::put32(args,job);Wire::put32(args+4,at);Wire::put32(args+8,n);
        assert(w.begin(STM3_READ,args,12,0));server.exchange(w);assert(!w.result && w.reply_bytes==n);
        for(unsigned i=0;i<n;++i)assert(w.reply()[i]==uint8_t(bytes[at+i]^0x5a));
    }
    Wire::put32(args,job+1);assert(w.begin(STM3_STATUS,args,4,0));server.exchange(w);assert(w.result==STM3_E_JOB);
    assert(w.begin(STM3_UNLOAD,nullptr,0,0));server.exchange(w);assert(!w.result);
    // A DONE returned after the resident's2ms slice is still a fault. Do
    // not read/accept it, repeat START, or weaken the limit to get audio.
    std::memcpy(bytes.data(),&header,64);std::memcpy(bytes.data()+64,code,4);
    Wire::put32(args,68);assert(w.begin(STM3_LOAD_BEGIN,args,4,0));server.exchange(w);assert(!w.result);
    assert(w.begin(STM3_LOAD_CHUNK,bytes.data(),68,0,5000,true,0));server.exchange(w);assert(!w.result);
    assert(w.begin(STM3_LOAD_COMMIT,nullptr,0,0));server.exchange(w);assert(!w.result);
    Wire::put32(args,Wire::get32(w.reply()));Wire::put32(args+4,1);Wire::put32(args+8,100);
    server.cost=2001;assert(w.begin(STM3_START,args,12,0));server.exchange(w);
    assert(w.result==STM3_E_TIME && server.runtime.state==STM3_FAULT && server.invocations==2);
    assert(w.replay(0));server.exchange(w);assert(w.result==STM3_E_TIME && server.invocations==2);
    Wire::put32(args,server.runtime.job_id);Wire::put32(args+4,0);Wire::put32(args+8,1);
    assert(w.begin(STM3_READ,args,12,0));server.exchange(w);assert(w.result==STM3_E_STATE && !w.reply_bytes);
    assert(w.begin(STM3_UNLOAD,nullptr,0,0));server.exchange(w);assert(!w.result && server.runtime.state==STM3_EMPTY);
    // Timeouts remain correct over the hardware's32-bit microsecond wrap.
    assert(w.begin(STM3_HELLO,nullptr,0,0xfffffff0u,50));w.tick(0x10);assert(w.pending);w.tick(0x22);assert(w.result==Wire::TIMEOUT);
    assert(w.replay(100));server.exchange(w);assert(!w.result);
    for(unsigned noise=0;noise<6;++noise) {
        assert(w.begin(STM3_HELLO,nullptr,0,0));
        uint8_t raw[52]{};raw[0]=1;raw[1]=STM3_HELLO|128;raw[2]=uint8_t(w.sequence);raw[3]=uint8_t(w.sequence>>8);raw[4]=40;
        Wire::put32(raw+48,Wire::crc(raw,48));
        if(noise==0)raw[2]^=1;else if(noise==1)raw[1]^=1;else if(noise==2)raw[6]=1;
        else if(noise==3)raw[4]=0xff;else if(noise==4)raw[0]=2;else raw[51]^=1;
        if(noise<5)Wire::put32(raw+48,Wire::crc(raw,48));
        uint8_t encoded[64];const unsigned n=Wire::encode(raw,sizeof(raw),encoded);
        for(unsigned i=0;i<n;++i)w.feed(encoded[i]);w.feed(0);assert(w.complete && w.result==Wire::FRAME && !w.reply_bytes);
    }
    assert(w.begin(STM3_HELLO,nullptr,0,0));for(unsigned i=0;i<300;++i)w.feed(1);w.feed(0);assert(w.result==Wire::FRAME);
    std::puts("Async M3 wire: real compact server, full512B IO, maximum READs, replay at-most-once, CRC/sequence/bounds errors and timer wrap PASS");
}
