#include "m3_tx.hpp"
#include "m3_rx.hpp"
#include "m3_wire.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <deque>
#include <vector>
using picocalc::m3::Transmit;
struct Port {
    bool available=true,stalled=false;
    const uint8_t* source=nullptr;
    unsigned remaining=0,starts=0,aborts=0;
    std::deque<uint8_t> fifo;
    std::vector<uint8_t> wire;
    bool dma_available()const{return available;}
    void fill(){if(!stalled)while(remaining && fifo.size()<32){fifo.push_back(*source++);--remaining;}}
    void start(const uint8_t* p,unsigned n){assert(!remaining);source=p;remaining=n;++starts;fill();}
    bool busy()const{return remaining!=0;}
    void abort(){source=nullptr;remaining=0;++aborts;}
    bool writable()const{return fifo.size()<32;}
    void write(uint8_t byte){assert(writable());fifo.push_back(byte);}
    void tick(){fill();if(!fifo.empty()){wire.push_back(fifo.front());fifo.pop_front();}fill();}
};
static unsigned random_state=0xc0def00d;
static unsigned random_word(){random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static unsigned run(bool dma,unsigned n,unsigned period) {
    Port port;port.available=dma;Transmit tx;std::vector<uint8_t> bytes(n);
    for(auto& b:bytes)b=uint8_t(random_word());
    assert(tx.pump(port,bytes.data(),n,65535));unsigned ticks=0;
    while(port.wire.size()<n && ticks<100000) {
        port.tick();++ticks;
        if(ticks%period==0)assert(tx.pump(port,bytes.data(),n,65535));
    }
    assert(port.wire==bytes && tx.queued());assert(tx.complete(port));assert(tx.complete(port));
    assert(!tx.active && tx.source==nullptr && !port.busy());
    assert(tx.dma_requests==unsigned(dma) && tx.fifo_requests==unsigned(!dma));
    assert(port.starts==unsigned(dma));return ticks;
}
static void tx_tests() {
    for(unsigned n=1;n<=272;++n)for(unsigned period:{1u,7u,31u,32u,33u,74u,160u}){
        run(false,n,period);assert(run(true,n,period)==n);
    }
    const auto fifo=run(false,57,74),dma=run(true,57,74);
    assert(fifo==99 && dma==57);
    printf("TX57: FIFO=%u byte-times DMA=%u, eliminated gap=%u byte-times (186.7us at2.25M)\n",fifo,dma,fifo-dma);
    for(unsigned cut=0;cut<=272;++cut){
        Port port;Transmit tx;std::vector<uint8_t> bytes(272,0xa5);
        assert(tx.pump(port,bytes.data(),272,1));for(unsigned i=0;i<cut;++i)port.tick();
        tx.cancel(port);bytes.clear();bytes.shrink_to_fit();
        for(unsigned i=0;i<300;++i)port.tick();assert(!port.busy() && !tx.active);
    }
    for(bool dma:{false,true}) {
        Port port;port.available=dma;Transmit tx;std::array<uint8_t,272> bytes{};
        assert(tx.pump(port,bytes.data(),272,4));assert(!tx.pump(port,bytes.data(),271,4));
        assert(!tx.pump(port,bytes.data(),272,5));assert(!tx.pump(port,bytes.data()+1,271,4));
        assert(!tx.complete(port));assert(!tx.active && !port.busy());
        port.fifo.clear();assert(tx.pump(port,bytes.data(),272,0));
        for(unsigned ticks=0;port.wire.size()<272 && ticks<10000;++ticks){port.tick();assert(tx.pump(port,bytes.data(),272,0));}
        // Previous partial FIFO output is retained physically; isolate next request.
        tx.cancel(port);
    }
    picocalc::m3::Wire wire;std::array<uint8_t,16> args{};assert(wire.begin(11,args.data(),args.size(),100,12000));
    Port stopped;stopped.stalled=true;Transmit tx;assert(tx.pump(stopped,wire.tx,wire.tx_bytes,wire.sequence));
    wire.tick(12101);assert(wire.result==picocalc::m3::Wire::TIMEOUT && wire.complete && !wire.pending);
    assert(!tx.complete(stopped));assert(!stopped.busy() && wire.result==picocalc::m3::Wire::TIMEOUT);
    Port port;Transmit epochs;std::array<uint8_t,3> bytes{{0,255,1}};
    for(unsigned i=0;i<65538;++i){assert(epochs.pump(port,bytes.data(),3,uint16_t(i)));for(unsigned j=0;j<3;++j)port.tick();assert(epochs.complete(port));}
    assert(epochs.dma_requests==65538 && port.wire.size()==3*65538);
}
struct Receive {
    std::array<uint8_t,514> guarded{};
    uint32_t head,tail,received=0;
    std::vector<uint8_t> sent,got;
    unsigned heads=0,add_during_feed=0;
    explicit Receive(uint32_t start):head(start),tail(start){guarded.fill(0xa5);}
    void append(unsigned n){for(unsigned i=0;i<n;++i){const uint8_t b=uint8_t(sent.size()*31+7);guarded[1+(head++&511)]=b;sent.push_back(b);}}
    bool drain(){heads=0;return picocalc::m3::drain_receive<512>(guarded.data()+1,tail,received,[&]{++heads;return head;},[&](const uint8_t* p,unsigned n){assert(p>=guarded.data()+1 && p+n<=guarded.data()+513);got.insert(got.end(),p,p+n);if(add_during_feed){const unsigned added=add_during_feed;add_during_feed=0;append(added);}});}
    void guards(){assert(guarded[0]==0xa5 && guarded[513]==0xa5);}
};
static void rx_tests() {
    for(unsigned start=0;start<512;++start)for(unsigned n:{0u,1u,31u,32u,63u,64u,271u,272u,511u,512u}) {
        Receive r(0xfffffe00u+start);r.append(n);assert(r.drain());assert(r.sent==r.got && r.tail==r.head && r.received==n && r.heads<=4);r.guards();
    }
    for(unsigned n=0;n<=512;++n){Receive r(random_word());r.append(n);assert(r.drain());assert(r.sent==r.got);r.guards();}
    for(unsigned trial=0;trial<10000;++trial){Receive r(random_word());const unsigned n=random_word()%273,m=random_word()%239;r.append(n?n:1);r.add_during_feed=m;assert(r.drain());assert(r.sent==r.got && r.received==r.sent.size() && r.heads<=4);r.guards();}
    Receive overflow(0xfffffff0);overflow.append(513);assert(!overflow.drain());assert(overflow.got.empty() && overflow.tail==overflow.head);overflow.guards();
    Receive growing(500);growing.append(32);growing.add_during_feed=600;assert(!growing.drain());assert(growing.got.size()==12 || growing.got.size()==32);assert(growing.tail==growing.head);growing.guards();
    // Data ending while the first snapshot is parsed is consumed this turn.
    Receive final(0xfffffff8);final.append(8);final.add_during_feed=17;assert(final.drain());assert(final.received==25 && final.sent==final.got);
}
int main(){tx_tests();rx_tests();puts("M3 UART: exact FIFO/DMA bytes, pressure, immutable pin, cancel/timeout/sequence wrap, RX ring/counter wrap, concurrent arrivals and bounded overflow PASS");}
