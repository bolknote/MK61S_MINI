#include "tape.h"
#include "inflate.h"
#include <string.h>

enum { NEXT, PILOT, SYNC1, SYNC2, DATA, PAUSE, PAUSE_END, SYMBOL };
enum { TAP_DATA=0x10, TURBO=0x11, TONE=0x12, PULSES=0x13, PURE=0x14,
       DIRECT=0x15, CSW=0x18, GENERALIZED=0x19, SILENCE=0x20, JUMP=0x23,
       LOOP=0x24, END_LOOP=0x25, CALL=0x26, RETURN=0x27, SELECT=0x28,
       STOP48=0x2a, LEVEL=0x2b };

static unsigned word(const uint8_t* p) { return p[0] | (unsigned)p[1]<<8; }
static uint32_t triple(const uint8_t* p) { return word(p) | (uint32_t)p[2]<<16; }
static uint32_t dword(const uint8_t* p) { return triple(p) | (uint32_t)p[3]<<24; }

enum { FILE_DATA, SYMBOL_TABLE, DECODED_DATA };
static bool tape_read(spectrum_tape* tape,unsigned kind,uint32_t at,uint8_t* out,unsigned n) {
    const bool decoded=kind==DECODED_DATA;
    const unsigned slot=kind==SYMBOL_TABLE;
    const uint32_t size=decoded?tape->decoded_bytes:tape->source.size;
    if(at>size || n>size-at) return false;
    uint32_t* start=&tape->cache_at[slot],*count=&tape->cache_bytes[slot];
    uint8_t* cache=tape->cache[slot];
    if(!slot && tape->cached_decoded!=decoded) {*count=0;tape->cached_decoded=decoded;}
    while(n) {
        if(at<*start || at-*start>=*count) {
            const uint32_t available=size-at;
            *start=at;*count=available<sizeof(tape->cache[slot])?available:sizeof(tape->cache[slot]);
            const bool ok=decoded?
                tape->index_read(tape->index_context,SPECTRUM_TAPE_INDEX_BYTES+at,cache,*count):
                tape->source.read(tape->source.context,at,cache,*count);
            if(!ok) {tape->fault=true;*count=0;return false;}
        }
        const uint32_t inside=at-*start,available=*count-inside;
        const unsigned take=n<available?n:available;
        memcpy(out,cache+inside,take);
        at+=take;out+=take;n-=take;
    }
    return true;
}
static bool read(spectrum_tape* tape,uint32_t at,uint8_t* out,unsigned n) {
    return tape_read(tape,FILE_DATA,at,out,n);
}

static bool generalized_header(spectrum_tape_block* b,const uint8_t h[18]) {
    const uint32_t length=dword(h);
    if(length<14) return false;
    b->bytes=length-14;b->pause=word(h+4);
    b->items=dword(h+6);b->data_items=dword(h+12);
    const unsigned pilot_alphabet=h[11]?h[11]:256,data_alphabet=h[17]?h[17]:256;
    b->pilot=1+2*h[10];b->zero=1+2*h[16];
    b->sync1=(uint16_t)pilot_alphabet;b->sync2=(uint16_t)data_alphabet;
    for(unsigned n=data_alphabet-1,bits=0;;n>>=1) {
        if(!n) {b->bits=(uint8_t)bits;break;}
        ++bits;
    }
    const uint32_t pilot_table=b->items?b->pilot*pilot_alphabet:0;
    if(pilot_table>b->bytes || b->items>(b->bytes-pilot_table)/3) return false;
    const uint32_t data_table=pilot_table+3*b->items;
    const uint32_t data_stream=data_table+(b->data_items?b->zero*data_alphabet:0);
    const uint32_t data_bytes=(b->data_items>>3)*b->bits+(((b->data_items&7)*b->bits+7)>>3);
    if(data_stream<data_table || data_stream>b->bytes || data_bytes!=b->bytes-data_stream) return false;
    b->pilot_stream=b->data+pilot_table;
    b->data_table=b->data+data_table;
    b->data_stream=b->data+data_stream;
    return true;
}

static enum spectrum_error block_at(spectrum_tape* tape,uint32_t* at,spectrum_tape_block* b) {
    uint8_t h[19];
    unsigned header=0;
    uint32_t skip=0;
    memset(b,0,sizeof(*b));
    b->bits=8;
    if(tape->tzx && !read(tape,(*at)++,&b->type,1)) goto invalid;
    if(!tape->tzx) b->type=TAP_DATA;

    switch(b->type) {
    case TAP_DATA: header=tape->tzx?4:2;break;
    case TURBO: header=18;break;
    case TONE: header=4;break;
    case PULSES: header=1;break;
    case PURE: header=10;break;
    case DIRECT: header=8;break;
    case CSW: header=14;break;
    case GENERALIZED: header=18;break;
    case SILENCE: case JUMP: case LOOP: case CALL: case SELECT: case 0x32: header=2;break;
    case END_LOOP: case RETURN: case 0x22: break;
    case STOP48: header=4;break;
    case LEVEL: header=5;break;
    case 0x21: case 0x30: case 0x33: header=1;break;
    case 0x31: header=2;break;
    case 0x35: header=14;break;
    case 0x5a: header=9;break;
    default: return SPECTRUM_UNSUPPORTED;
    }
    if(header && !read(tape,*at,h,header)) goto invalid;
    *at+=header;
    b->data=*at;

    switch(b->type) {
    case TAP_DATA: {
        b->bytes=word(h+(tape->tzx?2:0));
        b->pause=tape->tzx?word(h):1000;
        uint8_t flag;
        if(!b->bytes || !read(tape,*at,&flag,1)) goto invalid;
        b->count=flag<128?8063:3223;
        b->pilot=2168;b->sync1=667;b->sync2=735;b->zero=855;b->one=1710;
        break;
    }
    case TURBO:
        b->pilot=word(h);b->sync1=word(h+2);b->sync2=word(h+4);
        b->zero=word(h+6);b->one=word(h+8);b->count=word(h+10);
        b->bits=h[12];b->pause=word(h+13);b->bytes=triple(h+15);
        if(b->count && !b->pilot) goto invalid;
        goto data;
    case PURE:
        b->zero=word(h);b->one=word(h+2);b->bits=h[4];b->pause=word(h+5);
        b->bytes=triple(h+7);
data:
        if(!b->zero || !b->one) goto invalid;
        goto bits;
    case DIRECT:
        b->zero=word(h);b->pause=word(h+2);b->bits=h[4];b->bytes=triple(h+5);
bits:
        if(!b->zero || !b->bytes || !b->bits || b->bits>8) goto invalid;
        break;
    case TONE:
        b->pilot=word(h);b->count=word(h+2);
        if(!b->pilot || !b->count) goto invalid;
        break;
    case CSW:
        if(h[9]!=1 && h[9]!=2) return SPECTRUM_UNSUPPORTED;
        if(dword(h)<10 || !(b->rate=triple(h+6))) goto invalid;
        b->pause=word(h+4);b->bytes=dword(h)-10;b->count=h[9];b->items=dword(h+10);
        break;
    case GENERALIZED:
        if(!generalized_header(b,h)) goto invalid;
        break;
    case SELECT:
        b->bytes=word(h);
        if(!b->bytes) goto invalid;
        break;
    case PULSES:
        b->count=h[0];b->bytes=2u*b->count;
        break;
    case SILENCE: b->pause=word(h);break;
    case JUMP: b->count=word(h);if(!b->count) goto invalid;break;
    case LOOP: b->count=word(h);if(!b->count) goto invalid;break;
    case CALL: b->count=word(h);skip=2u*b->count;if(!b->count) goto invalid;break;
    case STOP48: if(dword(h)) goto invalid;break;
    case LEVEL: if(dword(h)!=1 || h[4]>1) goto invalid;b->count=h[4];break;
    case 0x21: case 0x30: skip=h[0];break;
    case 0x31: skip=h[1];break;
    case 0x32: skip=word(h);break;
    case 0x33: skip=3u*h[0];break;
    case 0x35: skip=dword(h+10);break;
    }
    if(skip>tape->source.size-*at || b->bytes>tape->source.size-*at-skip) goto invalid;
    *at+=skip+b->bytes;
    return SPECTRUM_OK;
invalid:
    return tape->fault?SPECTRUM_IO:SPECTRUM_FORMAT;
}

void spectrum_tape_rewind(spectrum_tape* tape) {
    tape->next=tape->tzx?10:0;tape->depth=0;tape->phase=NEXT;
    tape->index_block=tape->call_next=tape->call_count=0;
    tape->choices=0;
    tape->playing=tape->timed=tape->level=tape->fault=false;
    tape->cache_bytes[0]=tape->cache_bytes[1]=0;
}

void spectrum_tape_toggle(spectrum_tape* tape,uint32_t cycles) {
    if(!tape->source.read || tape->choices) return;
    if(tape->timed) {
        if(tape->playing) tape->deadline-=cycles;
        else tape->deadline+=cycles;
    }
    tape->playing=!tape->playing;
}

/* Decode at mount time, when emulation and its audio deadlines are paused.
 * The two SRAM windows cache sequential output and older PSRAM history. */
typedef struct {
    spectrum_tape* tape;
    uint32_t base, cursor, history;
    unsigned filled;
    uint32_t pulses, long_pulse;
    unsigned extra;
    bool bad;
} csw_output;

static bool csw_flush(csw_output* out) {
    return !out->filled || out->tape->index_write(out->tape->index_context,
        out->base+out->cursor,out->tape->decode_scratch,out->filled);
}
static bool csw_write(void* context,uint32_t at,uint8_t value) {
    csw_output* out=context;
    out->tape->decode_scratch[out->filled++]=value;
    if(out->extra) {
        out->long_pulse|=(uint32_t)value<<(8*(4-out->extra));
        if(!--out->extra && !out->long_pulse) out->bad=true;
    } else {
        ++out->pulses;
        if(!value) {out->extra=4;out->long_pulse=0;}
    }
    if(out->filled==512) {
        if(!csw_flush(out)) return false;
        out->cursor=at+1;out->filled=0;
    }
    return true;
}
static bool csw_read(void* context,uint32_t at,uint8_t* value) {
    csw_output* out=context;
    uint8_t* cache=out->tape->decode_scratch;
    if(at>=out->cursor) *value=cache[at-out->cursor];
    else {
        const uint32_t sector=at&~511u;
        if(sector!=out->history) {
            if(!out->tape->index_read(out->tape->index_context,out->base+sector,cache+512,512))
                return false;
            out->history=sector;
        }
        *value=cache[512+(at&511u)];
    }
    return true;
}
static enum spectrum_error decode_csw(spectrum_tape* tape,const spectrum_tape_block* block,
                                       spectrum_tape_index* index) {
    if(!tape->index_read || !tape->index_write || !tape->decode_scratch) return SPECTRUM_UNSUPPORTED;
    const unsigned remaining=SPECTRUM_TAPE_CSW_BYTES-tape->decoded_bytes;
    if(block->items>remaining) return SPECTRUM_UNSUPPORTED;
    const unsigned limit=block->items>remaining/5?remaining:5*block->items;
    csw_output sink={.tape=tape,.base=SPECTRUM_TAPE_INDEX_BYTES+tape->decoded_bytes,.history=UINT32_MAX};
    const spectrum_inflate_output output={.limit=limit,.context=&sink,.read=csw_read,.write=csw_write};
    unsigned used;
    const enum spectrum_error result=spectrum_inflate(&tape->source,block->data,block->bytes,&output,&used);
    if(result) return result;
    if(sink.bad || sink.extra || sink.pulses!=block->items) return SPECTRUM_FORMAT;
    if(!csw_flush(&sink)) return SPECTRUM_IO;
    index->decoded=tape->decoded_bytes;index->bytes=used;tape->decoded_bytes+=used;
    return SPECTRUM_OK;
}

/* The block length bounds every option independently of its text contents.
 * Selection uses signed offsets relative to the select block itself. */
static bool choice(spectrum_tape* tape,const spectrum_tape_block* block,
                   unsigned option,int16_t* delta,char* label,unsigned capacity) {
    uint8_t count,entry[3];
    if(!read(tape,block->data,&count,1) || option>=count) return false;
    uint32_t at=block->data+1,end=block->data+block->bytes;
    for(unsigned i=0;i<count;++i) {
        if(end-at<sizeof(entry) || !read(tape,at,entry,sizeof(entry))) return false;
        at+=sizeof(entry);
        if(entry[2]>end-at) return false;
        if(i==option) {
            if(delta) *delta=(int16_t)word(entry);
            if(capacity) {
                const unsigned length=entry[2]<capacity?entry[2]:capacity-1;
                if(!read(tape,at,(uint8_t*)label,length)) return false;
                for(unsigned k=0;k<length;++k)
                    if((unsigned char)label[k]<32 || (unsigned char)label[k]>126) label[k]='?';
                label[length]=0;
            }
        }
        at+=entry[2];
    }
    return at==end;
}

enum spectrum_error spectrum_tape_open(spectrum_tape* check,const spectrum_source* source,bool tzx) {
    if(!source || !source->read) return SPECTRUM_FORMAT;
    check->source=*source;check->tzx=tzx;
    spectrum_tape_rewind(check);check->index_count=0;check->decoded_bytes=0;
    if(tzx) {
        uint8_t header[10];
        if(!read(check,0,header,sizeof(header))) return check->fault?SPECTRUM_IO:SPECTRUM_FORMAT;
        if(memcmp(header,"ZXTape!\x1a",8)) return SPECTRUM_FORMAT;
        if(header[8]!=1) return SPECTRUM_UNSUPPORTED;
    }
    unsigned depth=0;
    uint32_t at=check->next;
    if(at>=source->size) return SPECTRUM_FORMAT;
    while(at<source->size) {
        spectrum_tape_block block;
        spectrum_tape_index entry={.file=at};
        enum spectrum_error error=block_at(check,&at,&block);
        if(error) return error;
        if(tzx && check->index_count>=4096) return SPECTRUM_UNSUPPORTED;
        if(block.type==CSW && block.count==2) {
            error=decode_csw(check,&block,&entry);
            if(error) return error;
        }
        if(block.type==SELECT && !choice(check,&block,0,NULL,NULL,0))
            return check->fault?SPECTRUM_IO:SPECTRUM_FORMAT;
        if(tzx && check->index_write &&
           !check->index_write(check->index_context,check->index_count*sizeof(entry),
                               (const uint8_t*)&entry,sizeof(entry))) return SPECTRUM_IO;
        if(tzx) ++check->index_count;
        if((block.type==JUMP || block.type==CALL || block.type==RETURN || block.type==SELECT) &&
           (!check->index_read || !check->index_write)) return SPECTRUM_UNSUPPORTED;
        if(block.type==LOOP && ++depth>4) return SPECTRUM_UNSUPPORTED;
        if(block.type==END_LOOP) {
            if(!depth) return SPECTRUM_FORMAT;
            --depth;
        }
    }
    if(depth) return SPECTRUM_FORMAT;
    check->decode_scratch=NULL;
    spectrum_tape_rewind(check);
    return SPECTRUM_OK;
}

static bool seek_block(spectrum_tape* tape,unsigned from,int16_t delta) {
    const int32_t to=(int32_t)from+delta;
    if(to<0 || to>tape->index_count || !tape->index_read) return false;
    if(to==tape->index_count) tape->next=tape->source.size;
    else if(!tape->index_read(tape->index_context,(uint32_t)to*sizeof(spectrum_tape_index),
                             (uint8_t*)&tape->next,sizeof(tape->next))) return false;
    tape->index_block=(uint16_t)to;
    return true;
}

static bool call_next(spectrum_tape* tape) {
    if(tape->call_next==tape->call_count) {
        const bool ok=seek_block(tape,tape->call_block,1);
        tape->call_count=0;
        return ok;
    }
    uint8_t offset[2];
    const uint32_t at=tape->call_offsets+2u*tape->call_next++;
    return read(tape,at,offset,2) && seek_block(tape,tape->call_block,(int16_t)word(offset));
}

bool spectrum_tape_choice(spectrum_tape* tape,unsigned option,char* label,unsigned capacity) {
    return tape->choices && choice(tape,&tape->block,option,NULL,label,capacity);
}
bool spectrum_tape_choose(spectrum_tape* tape,unsigned option,uint32_t cycles) {
    int16_t delta;
    if(!tape->choices || !choice(tape,&tape->block,option,&delta,NULL,0) ||
       !seek_block(tape,tape->index_block-1,delta)) return false;
    tape->choices=0;tape->playing=tape->timed=true;tape->deadline=cycles;
    return true;
}

static bool begin_symbol(spectrum_tape* tape) {
    spectrum_tape_block* b=&tape->block;
    unsigned symbol,alphabet,stride;
    uint32_t table;
    uint8_t value[3];
    if(tape->pulses || b->items) {
        if(!tape->pulses) {
            const uint32_t at=b->pilot_stream;
            b->pilot_stream+=3;--b->items;
            if(!read(tape,at,value,3) || !word(value+1)) return false;
            tape->value=value[0];tape->pulses=word(value+1);
        }
        --tape->pulses;symbol=tape->value;alphabet=b->sync1;stride=b->pilot;table=b->data;
    } else if(b->data_items) {
        symbol=0;
        for(unsigned i=0;i<b->bits;++i) {
            if(!read(tape,b->data_stream+tape->byte,value,1)) return false;
            symbol=(symbol<<1)|((value[0]>>(7-tape->bit))&1u);
            if(++tape->bit==8) {tape->bit=0;++tape->byte;}
        }
        --b->data_items;alphabet=b->sync2;stride=b->zero;table=b->data_table;
    } else {
        tape->phase=PAUSE;return true;
    }
    tape->symbol_at=table+symbol*stride;
    if(symbol>=alphabet || !tape_read(tape,SYMBOL_TABLE,tape->symbol_at,value,1) || value[0]>3) return false;
    ++tape->symbol_at;tape->half=0;tape->phase=SYMBOL;
    tape->fraction=stride/2;tape->level=value[0]>=2 ? (value[0]&1)!=0
                                                   : tape->level^(value[0]==0);
    return true;
}

static uint32_t next_pulse(spectrum_tape* tape,bool model48) {
    spectrum_tape_block* b=&tape->block;
    // Bound metadata and empty loop traversal in a single port read.
    for(unsigned steps=0;steps<256;++steps) {
        switch(tape->phase) {
        case NEXT:
            if(tape->next==tape->source.size) return 0;
            if(block_at(tape,&tape->next,b)!=SPECTRUM_OK) {tape->fault=true;return 0;}
            const unsigned index=tape->index_block++;
            switch(b->type) {
            case TAP_DATA: case TURBO: case TONE:
                tape->pulses=b->count;tape->phase=PILOT;tape->byte=0;tape->bit=tape->half=0;
                break;
            case PULSES: case PURE: case DIRECT:
                tape->phase=DATA;tape->byte=0;tape->bit=tape->half=0;
                break;
            case CSW:
                if(b->count==2) {
                    spectrum_tape_index entry;
                    if(!tape->index_read(tape->index_context,index*sizeof(entry),(uint8_t*)&entry,sizeof(entry)))
                        goto broken;
                    b->data=entry.decoded;b->bytes=entry.bytes;
                }
                tape->phase=DATA;tape->byte=0;tape->fraction=0;break;
            case GENERALIZED:
                tape->phase=DATA;tape->pulses=tape->byte=tape->bit=0;
                break;
            case SELECT:
                if(!read(tape,b->data,&tape->choices,1)) goto broken;
                return 0;
            case SILENCE:
                if(!b->pause) return 0;
                tape->phase=PAUSE;break;
            case STOP48: if(model48) return 0;break;
            case LEVEL: tape->level=b->count!=0;break;
            case JUMP:
                if(!seek_block(tape,index,(int16_t)b->count)) {tape->fault=true;return 0;}
                break;
            case CALL:
                if(tape->call_count) {tape->fault=true;return 0;}
                tape->call_offsets=b->data;tape->call_block=index;
                tape->call_next=0;tape->call_count=b->count;
                if(!call_next(tape)) {tape->fault=true;return 0;}
                break;
            case RETURN:
                if(!tape->call_count || !call_next(tape)) {tape->fault=true;return 0;}
                break;
            case LOOP:
                if(tape->depth>=4) {tape->fault=true;return 0;}
                tape->loop_start[tape->depth]=tape->next;
                tape->loop_block[tape->depth]=tape->index_block;
                tape->loop_left[tape->depth++]=b->count;
                break;
            case END_LOOP:
                if(!tape->depth) {tape->fault=true;return 0;}
                if(--tape->loop_left[tape->depth-1]) {
                    tape->next=tape->loop_start[tape->depth-1];
                    tape->index_block=tape->loop_block[tape->depth-1];
                }
                else --tape->depth;
                break;
            }
            break;
        case PILOT:
            if(tape->pulses) {--tape->pulses;tape->level=!tape->level;return b->pilot;}
            tape->phase=SYNC1;
            break;
        case SYNC1:
            tape->phase=SYNC2;
            if(b->sync1) {tape->level=!tape->level;return b->sync1;}
            break;
        case SYNC2:
            tape->phase=DATA;
            if(b->sync2) {tape->level=!tape->level;return b->sync2;}
            break;
        case DATA:
            if(b->type==GENERALIZED) {
                if(!begin_symbol(tape)) goto broken;
                break;
            }
            if(b->type==CSW && !b->items) {
                if(tape->byte!=b->bytes) goto broken;
            } else if(b->type==CSW && tape->byte==b->bytes) goto broken;
            if(tape->byte==b->bytes) {tape->phase=PAUSE;break;}
            if(b->type==CSW) {
                uint8_t count[4];
                const unsigned kind=b->count==2?DECODED_DATA:FILE_DATA;
                if(!tape_read(tape,kind,b->data+tape->byte++,count,1)) goto broken;
                uint32_t samples=count[0];
                if(!samples) {
                    if(b->bytes-tape->byte<4 ||
                       !tape_read(tape,kind,b->data+tape->byte,count,4)) goto broken;
                    samples=dword(count);tape->byte+=4;
                }
                const uint64_t ticks=(uint64_t)samples*3500000+tape->fraction;
                const uint64_t duration=ticks/b->rate;
                if(!samples || duration>=INT32_MAX) goto broken;
                tape->fraction=(uint32_t)(ticks-duration*b->rate);
                --b->items;
                tape->level=!tape->level;
                if(duration) return (uint32_t)duration;
                break;
            }
            if(b->type==PULSES) {
                uint8_t pair[2];
                if(!read(tape,b->data+tape->byte,pair,2) || !word(pair)) {tape->fault=true;return 0;}
                tape->byte+=2;tape->level=!tape->level;return word(pair);
            }
            if(!tape->bit && !tape->half && !read(tape,b->data+tape->byte,&tape->value,1)) {
                tape->fault=true;return 0;
            }
            {
                const bool one=(tape->value&(128u>>tape->bit))!=0;
                if(b->type==DIRECT) tape->level=one;
                else tape->level=!tape->level;
                tape->half^=1;
                if(b->type==DIRECT || !tape->half) {
                    tape->half=0;
                    if(++tape->bit==(tape->byte+1==b->bytes?b->bits:8)) {++tape->byte;tape->bit=0;}
                }
                return one && b->type!=DIRECT?b->one:b->zero;
            }
        case SYMBOL: {
            uint8_t pair[2];
            if(!tape->fraction) {tape->phase=DATA;break;}
            if(!tape_read(tape,SYMBOL_TABLE,tape->symbol_at,pair,2)) goto broken;
            const unsigned duration=word(pair);
            if(!duration) {tape->phase=DATA;break;}
            tape->symbol_at+=2;--tape->fraction;
            if(tape->half) tape->level=!tape->level;
            tape->half=1;
            return duration;
        }
        case PAUSE:
            tape->phase=NEXT;
            if(!b->pause) break;
            tape->phase=PAUSE_END;
            tape->level=!tape->level;
            return 3500;
        case PAUSE_END:
            tape->phase=NEXT;tape->level=false;
            if(b->pause>1) return ((uint32_t)b->pause-1)*3500;
            break;
        }
    }
broken:
    tape->fault=true;
    return 0;
}

bool spectrum_tape_ear(void* context,const z80* cpu) {
    spectrum_tape* tape=context;
    if(!tape->playing) return false;
    const spectrum* machine=cpu->userdata;
    const uint32_t now=(uint32_t)cpu->cyc;
    if(!tape->timed) {
        // The BASIC keyboard scanner also reads FE. Start at the ROM tape
        // routine or at the first EAR read by a loader running from RAM.
        if(cpu->pc<0x4000 && (cpu->pc<0x0556 || cpu->pc>0x0605)) return false;
        tape->deadline=now;tape->timed=true;
    }
    while((int32_t)(now-tape->deadline)>=0) {
        const uint32_t duration=next_pulse(tape,!machine->pentagon);
        if(!duration) {
            tape->playing=tape->timed=false;
            if(!tape->choices) tape->level=false;
            break;
        }
        tape->deadline+=duration;
    }
    return tape->level;
}
