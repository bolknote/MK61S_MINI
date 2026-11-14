#include "m3_wire.hpp"
extern "C" {
#include "stm3_runtime.h"
#include "stm3_client.h"
#include "../examples/portable-apps/ANOTHER/m3_pcm.h"
uint32_t module_entry(uint32_t, const stm3_api *, stm3_job *);
}
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
using picocalc::m3::Wire;

struct Server {
    stm3_runtime runtime{};
    uint32_t now = 0, calls = 0, module = 0;
    Server() {
        stm3_backend backend{}; backend.context = this;
        backend.micros = [](void *ctx) { return static_cast<Server *>(ctx)->now; };
        backend.load_address = [](void *, const void *) { return 0x20001000u; };
        backend.invoke = [](void *ctx, uint32_t, uint32_t op, const stm3_api *api, stm3_job *job) {
            Server &s = *static_cast<Server *>(ctx); if (op == STM3_INIT) ++s.calls;
            return module_entry(op, api, job);
        };
        stm3_init(&runtime, &backend);
    }
    void send(const Wire &wire) { for (unsigned i = 0; i < wire.tx_bytes; ++i) stm3_feed(&runtime, wire.tx[i]); }
    bool receive(Wire &wire) {
        std::array<uint8_t, 272> reply{};
        const unsigned size = stm3_transmit(&runtime, reply.data(), reply.size());
        for (unsigned i = 0; i < size; ++i) wire.feed(reply[i]);
        return size != 0;
    }
    void exchange(Wire &wire) { send(wire); assert(receive(wire) && wire.complete && !wire.result); }
    void load(Wire &wire) {
        uint8_t package[68]{}; stm3_header header{};
        header.magic=STM3_MAGIC;header.abi=STM3_ABI;header.header_bytes=64;header.package_bytes=68;
        header.image_bytes=4;header.entry_offset=1;header.input_limit=header.output_limit=512;
        header.slice_us=2000;header.target=STM3_TARGET;
        header.payload_crc=stm3_crc32(package+64,4);header.header_crc=stm3_crc32(&header,60);
        std::memcpy(package,&header,64);
        uint8_t arg[4]; Wire::put32(arg,sizeof(package));
        assert(wire.begin(STM3_LOAD_BEGIN,arg,4,now));exchange(wire);
        assert(wire.begin(STM3_LOAD_CHUNK,package,sizeof(package),now,5000,true,0));exchange(wire);
        assert(wire.begin(STM3_LOAD_COMMIT,nullptr,0,now));exchange(wire);module=Wire::get32(wire.reply());
    }
};
int main() {
    Server server; Wire wire; server.load(wire);
    uint8_t packet[176]{};
    aw_m3_put32(packet,AW_M3_MAGIC);aw_m3_put16(packet+4,73);packet[6]=64;packet[7]=3;aw_m3_put16(packet+8,1000);
    for(unsigned ch=0;ch<2;++ch) {
        uint8_t *d=packet+12+ch*8;aw_m3_put16(d,uint16_t(44+ch*66));d[2]=66;d[3]=64;d[5]=63;aw_m3_put16(d+6,256);
        std::memset(packet+44+ch*66,ch?192:64,66);
    }
    uint8_t args[16]; Wire::put32(args,server.module);Wire::put32(args+4,sizeof(packet));
    Wire::put32(args+8,10);Wire::put32(args+12,72);
    assert(wire.begin_pair(STM3_START_RESULT_INPUT,args,sizeof(args),packet,sizeof(packet),server.now,12000));
    server.send(wire);
    for(unsigned i=0;i<10 && server.runtime.state==STM3_RUNNING;++i)stm3_tick(&server.runtime);
    assert(server.receive(wire) && wire.complete && !wire.result && wire.reply_bytes==80 && server.calls==1);
    const uint8_t *out=wire.reply()+8;
    assert(aw_m3_get32(out)==AW_M3_PWM && out[4]==64 && aw_m3_get16(out+6)==73);
    for(unsigned i=0;i<64;++i)assert(out[8+i]==128);
    assert(wire.replay(server.now));server.send(wire);assert(server.receive(wire) && server.calls==1);
    assert(wire.begin(STM3_UNLOAD,nullptr,0,server.now));server.exchange(wire);
    std::puts("Another World M3 transport and replay passed");
}
