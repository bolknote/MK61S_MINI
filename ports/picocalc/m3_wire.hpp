#ifndef MK61_PICOCALC_M3_WIRE_HPP
#define MK61_PICOCALC_M3_WIRE_HPP
#include <cstdint>
#include <cstring>
namespace picocalc::m3 {
/* Async counterpart of the qualified stm3_client protocol. One request is
 * outstanding. TX stays pinned until its owner releases DMA; RX decodes in
 * place. The UART adapter owns all clocks, registers and DMA channels. */
struct Wire {
    enum Error { TIMEOUT=-1,FRAME=-2,SIZE=-3,IO=-4 };
    uint8_t tx[272]{},frame[272]{};
    uint16_t sequence=0;
    uint8_t command=0;
    unsigned tx_bytes=0,rx_bytes=0,reply_bytes=0;
    uint32_t started=0,timeout=0;
    int result=0;
    bool pending=false,complete=false,overflow=false;
    static uint32_t get32(const uint8_t* p) {
        return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;
    }
    static void put32(uint8_t* p,uint32_t v) {for(unsigned i=0;i<4;++i)p[i]=uint8_t(v>>(8*i));}
    static uint32_t crc(const uint8_t* p,unsigned n) {
        uint32_t v=~0u;
        while(n--){v^=*p++;for(unsigned i=0;i<8;++i)v=(v>>1)^(0xedb88320u&(0u-(v&1)));}
        return ~v;
    }
    static unsigned encode(const uint8_t* in,unsigned n,uint8_t* out) {
        unsigned at=1,code_at=0;uint8_t code=1;
        for(unsigned i=0;i<n;++i) {
            if(!in[i]){out[code_at]=code;code_at=at++;code=1;}
            else {out[at++]=in[i];if(++code==255){out[code_at]=code;code_at=at++;code=1;}}
        }
        out[code_at]=code;return at;
    }
    static unsigned decode(uint8_t* bytes,unsigned n) {
        unsigned at=0,i=0;
        while(i<n) {
            const unsigned code=bytes[i++];if(!code || code-1>n-i)return 0;
            for(unsigned j=1;j<code;++j){if(!bytes[i])return 0;bytes[at++]=bytes[i++];}
            if(code!=255 && i<n)bytes[at++]=0;
        }
        return at;
    }
    bool begin(uint8_t op,const uint8_t* input,unsigned n,uint32_t now,uint32_t deadline=5000,
               bool prefix=false,uint32_t offset=0) {
        if(pending || !op || (op&128) || n>(prefix?252u:256u) || (n && !input) || !deadline || deadline>1000000)return false;
        ++sequence;command=op;started=now;timeout=deadline;
        rx_bytes=reply_bytes=0;result=0;complete=overflow=false;
        const unsigned payload=n+(prefix?4:0);
        if(n)std::memmove(frame+8+(prefix?4:0),input,n);
        frame[0]=1;frame[1]=op;frame[2]=uint8_t(sequence);frame[3]=uint8_t(sequence>>8);
        frame[4]=uint8_t(payload);frame[5]=uint8_t(payload>>8);frame[6]=frame[7]=0;
        if(prefix)put32(frame+8,offset);
        put32(frame+8+payload,crc(frame,8+payload));
        tx[0]=0;const unsigned bytes=encode(frame,12+payload,tx+1);
        tx[bytes+1]=0;tx_bytes=bytes+2;pending=true;return true;
    }
    void fail(int error) {result=error;pending=false;complete=true;reply_bytes=0;}
    bool replay(uint32_t now,uint32_t deadline=5000) {
        if(pending || !tx_bytes || !deadline || deadline>1000000)return false;
        started=now;timeout=deadline;rx_bytes=reply_bytes=0;
        result=0;complete=overflow=false;pending=true;return true;
    }
    void feed(uint8_t value) {
        if(!pending)return;
        if(value) {
            if(rx_bytes<sizeof(frame))frame[rx_bytes++]=value;else overflow=true;
            return;
        }
        if(!rx_bytes && !overflow)return;
        if(overflow){fail(FRAME);return;}
        const unsigned n=decode(frame,rx_bytes);
        if(n<16){fail(FRAME);return;}
        const unsigned payload=unsigned(frame[4])|(unsigned(frame[5])<<8);
        if(frame[0]!=1 || frame[1]!=(command|128u) ||
           (unsigned(frame[2])|(unsigned(frame[3])<<8))!=sequence || frame[6] || frame[7] ||
           payload<4 || payload>256 || n!=12+payload || get32(frame+n-4)!=crc(frame,n-4)) {fail(FRAME);return;}
        const uint32_t status=get32(frame+8);
        if(status>9){fail(FRAME);return;}
        result=int(status);reply_bytes=status?0:payload-4;pending=false;complete=true;
    }
    void tick(uint32_t now) {if(pending && uint32_t(now-started)>=timeout)fail(TIMEOUT);}
    const uint8_t* reply() const {return frame+12;}
};
}
#endif
