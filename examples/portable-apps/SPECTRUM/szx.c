#include "szx.h"
#include "inflate.h"
#include <string.h>

enum { Z80_BYTES=37, ULA_BYTES=8, AY_BYTES=18, PALETTE_BYTES=67, CHUNK=8,
       PAGE=SPECTRUM_BANK_BYTES, PAGE_BLOCK=PAGE+11 };
#define ID(a,b,c,d) ((uint32_t)(a)|((uint32_t)(b)<<8)|((uint32_t)(c)<<16)|((uint32_t)(d)<<24))

static uint16_t word(const uint8_t* p) { return (uint16_t)(p[0]|p[1]<<8); }
static uint32_t dword(const uint8_t* p) { return word(p)|((uint32_t)word(p+2)<<16); }
static void put16(uint8_t* p,unsigned v) { p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t* p,uint32_t v) { put16(p,v);put16(p+2,v>>16); }

static uint8_t* header(uint8_t* p,uint32_t id,uint32_t length) {
    put32(p,id);put32(p+4,length);
    return p+CHUNK;
}
static uint8_t* save_z80(uint8_t* p,const spectrum* s) {
    const z80* z=&s->cpu;
    p=header(p,ID('Z','8','0','R'),Z80_BYTES);
    const uint16_t words[]={z->a<<8|z->f,z->bc,z->de,z->hl,z->a_<<8|z->f_,z->bc_,z->de_,z->hl_,
        z->ix,z->iy,z->sp,z->pc};
    for(unsigned i=0;i<12;++i) put16(p+2*i,words[i]);
    p[24]=z->i;p[25]=z->r;p[26]=z->iff1;p[27]=z->iff2;p[28]=z->interrupt_mode;
    put32(p+29,s->frame_tstates);
    p[33]=s->frame_tstates<32?32-s->frame_tstates:0;
    p[34]=(z->iff_delay?1:0)|(z->halted?2:0);put16(p+35,z->mem_ptr);
    return p+Z80_BYTES;
}

uint32_t spectrum_szx_save(spectrum_szx_writer* writer,const spectrum* s) {
    uint8_t* p=writer->header;
    memset(writer,0,sizeof(*writer));
    writer->machine=s;writer->banks=s->pentagon?s->memory->banks:3;
    memcpy(p,"ZXST\x01\x05",6);
    p[6]=s->pentagon?(s->memory->extended?14:13):1;
    p=save_z80(p+8,s);
    p=header(p,ID('S','P','C','R'),ULA_BYTES);
    p[0]=s->border;p[1]=s->pentagon?s->memory->paging:0;
    p[2]=s->pentagon&&s->memory->extended?s->memory->control:0;
    p[3]=s->border|(s->beeper<<4);
    p=header(p+ULA_BYTES,ID('A','Y',0,0),AY_BYTES);
    p[1]=s->ay.adr;
    memcpy(p+2,s->ay.reg,16);
    p+=AY_BYTES;
    if(s->extensions&SPECTRUM_ULAPLUS) {
        p=header(p,ID('P','L','T','T'),PALETTE_BYTES);
        p[0]=s->ulaplus_mode;p[1]=s->ulaplus_select;
        memcpy(p+2,s->ulaplus_palette,64);
        p+=PALETTE_BYTES;
    }
    writer->prefix=(unsigned)(p-writer->header);
    return writer->prefix+writer->banks*PAGE_BLOCK;
}

static unsigned flat_bank(unsigned n) {
    static const uint8_t banks[]={5,2,0};
    return banks[n];
}
static unsigned flat_index(unsigned bank) { return bank==5?0:bank==2?1:2; }

int spectrum_szx_read(void* context,uint32_t offset,uint8_t* out,uint32_t bytes) {
    const spectrum_szx_writer* writer=context;
    const spectrum* s=writer->machine;
    const uint32_t size=writer->prefix+writer->banks*PAGE_BLOCK;
    if(offset>size || bytes>size-offset) return 0;
    while(bytes) {
        uint32_t take;
        if(offset<writer->prefix) {
            take=writer->prefix-offset;if(take>bytes) take=bytes;
            memcpy(out,writer->header+offset,take);
        } else {
            const uint32_t at=offset-writer->prefix,index=at/PAGE_BLOCK,part=at%PAGE_BLOCK;
            const unsigned bank=s->pentagon?index:flat_bank(index);
            if(part<11) {
                uint8_t block[11];
                put32(block,ID('R','A','M','P'));put32(block+4,PAGE+3);
                block[8]=block[9]=0;block[10]=(uint8_t)bank;
                take=11-part;if(take>bytes) take=bytes;
                memcpy(out,block+part,take);
            } else {
                const uint32_t in_page=part-11;
                take=PAGE-in_page;if(take>bytes) take=bytes;
                if(s->memory) {
                    if(!spectrum_bank_read(s->memory,bank,in_page,out,take)) return 0;
                } else memcpy(out,s->ram+flat_index(bank)*PAGE+in_page,take);
            }
        }
        offset+=take;out+=take;bytes-=take;
    }
    return 1;
}

enum spectrum_error spectrum_szx_model(const spectrum_source* source,unsigned* model) {
    uint8_t h[8];
    if(!source || !source->read || source->size<sizeof(h)) return SPECTRUM_FORMAT;
    if(!source->read(source->context,0,h,sizeof(h))) return SPECTRUM_IO;
    if(memcmp(h,"ZXST",4)) return SPECTRUM_FORMAT;
    if(h[4]!=1 || h[7]) return SPECTRUM_UNSUPPORTED;
    switch(h[6]) {
    case 1: *model=0;return SPECTRUM_OK;
    case 13: *model=1;return SPECTRUM_OK;
    case 14: *model=2;return SPECTRUM_OK;
    default: return SPECTRUM_UNSUPPORTED;
    }
}

typedef struct {
    uint32_t ram[64];
    uint32_t compressed[64];
    uint8_t cpu[Z80_BYTES],ula[ULA_BYTES],ay[AY_BYTES],palette[PALETTE_BYTES];
    bool has_ay,has_palette;
} snapshot;

static enum spectrum_error inspect(const spectrum_source* source,snapshot* state,unsigned model) {
    bool has_cpu=false,has_ula=false;
    const unsigned banks=model==2?64:model==1?32:8;
    for(uint32_t at=8;at<source->size;) {
        uint8_t h[8];
        if(source->size-at<sizeof(h)) return SPECTRUM_FORMAT;
        if(!source->read(source->context,at,h,sizeof(h))) return SPECTRUM_IO;
        at+=sizeof(h);
        const uint32_t size=dword(h+4);
        if(size>source->size-at) return SPECTRUM_FORMAT;
        uint8_t* out=NULL;
        unsigned length=0;
        switch(dword(h)) {
        case ID('Z','8','0','R'): if(has_cpu) return SPECTRUM_FORMAT;
            out=state->cpu;length=Z80_BYTES;has_cpu=true;break;
        case ID('S','P','C','R'): if(has_ula) return SPECTRUM_FORMAT;
            out=state->ula;length=ULA_BYTES;has_ula=true;break;
        case ID('A','Y',0,0): if(state->has_ay) return SPECTRUM_FORMAT;
            out=state->ay;length=AY_BYTES;state->has_ay=true;break;
        case ID('P','L','T','T'): if(state->has_palette) return SPECTRUM_FORMAT;
            out=state->palette;length=size==66?66:PALETTE_BYTES;state->has_palette=true;break;
        case ID('R','A','M','P'): {
            uint8_t page[3];
            if(size<sizeof(page)) return SPECTRUM_FORMAT;
            if(!source->read(source->context,at,page,sizeof(page))) return SPECTRUM_IO;
            if(word(page)>1) return SPECTRUM_UNSUPPORTED;
            const unsigned bank=page[2];
            if((word(page)==0 && size!=PAGE+sizeof(page)) || bank>=banks ||
               (!model && bank!=0 && bank!=2 && bank!=5) ||
               state->ram[bank]) return SPECTRUM_FORMAT;
            state->ram[bank]=at+sizeof(page);
            if(word(page)) {
                if(size<sizeof(page)+6 || size>=UINT32_C(65536)) return SPECTRUM_FORMAT;
                state->compressed[bank]=size-sizeof(page);
            }
            break;
        }
        }
        if(out) {
            if(size!=length) return SPECTRUM_FORMAT;
            if(!source->read(source->context,at,out,length)) return SPECTRUM_IO;
        }
        at+=size;
    }
    const uint8_t* z=state->cpu;
    if(!has_cpu || !has_ula || z[26]>1 || z[27]>1 || z[28]>2 ||
       dword(z+29)>=(model?71680:SPECTRUM_FRAME_TSTATES) || state->ula[0]>7 ||
       (state->has_ay && state->ay[1]>15)) return SPECTRUM_FORMAT;
    if(!model) return state->ram[0] && state->ram[2] && state->ram[5]?SPECTRUM_OK:SPECTRUM_FORMAT;
    for(unsigned i=0;i<banks;++i) if(!state->ram[i]) return SPECTRUM_FORMAT;
    return SPECTRUM_OK;
}

static void restore_cpu(spectrum* s,const uint8_t* p) {
    z80* z=&s->cpu;
    z->f=p[0];z->a=p[1];z->bc=word(p+2);z->de=word(p+4);z->hl=word(p+6);
    z->f_=p[8];z->a_=p[9];z->bc_=word(p+10);z->de_=word(p+12);z->hl_=word(p+14);
    z->ix=word(p+16);z->iy=word(p+18);z->sp=word(p+20);z->pc=word(p+22);
    z->i=p[24];z->r=p[25];z->iff1=p[26];z->iff2=p[27];z->interrupt_mode=p[28];
    z->iff_delay=p[34]&1;z->halted=(p[34]&2)!=0;z->mem_ptr=word(p+35);
    z->cyc=s->frame_tstates=dword(p+29);
}

enum spectrum_error spectrum_load_szx(spectrum* s,const spectrum_source* source,uint8_t* low,uint8_t* high) {
    unsigned model;
    enum spectrum_error result=spectrum_szx_model(source,&model);
    if(result) return result;
    if(model!=(s->pentagon?(s->memory->extended?2u:1u):0u)) return SPECTRUM_UNSUPPORTED;
    snapshot state={0};
    result=inspect(source,&state,model);
    if(result) return result;
    const spectrum_inflate_output output={low,high,12288,PAGE};
    bool packed=false;
    for(unsigned bank=0;bank<64;++bank) packed|=state.compressed[bank]!=0;
    if(packed && (!low || !high)) return SPECTRUM_UNSUPPORTED;
    // These areas can borrow clean cache slots. Flush and invalidate before
    // validating data so a malformed compressed block cannot destroy RAM.
    if(packed && s->memory) {
        if(!spectrum_memory_flush_pages(s->memory)) return SPECTRUM_IO;
        spectrum_refresh_map(s);
    }
    for(unsigned bank=0;bank<64 && packed;++bank) if(state.compressed[bank]) {
        unsigned used;
        result=spectrum_inflate(source,state.ram[bank],state.compressed[bank],&output,&used);
        if(result || used!=PAGE) return result?result:SPECTRUM_FORMAT;
    }

    if(!spectrum_disk_snapshot(s)) return SPECTRUM_IO;
    spectrum_reset_cpu(s);
    if(s->memory && !spectrum_memory_reset(s->memory)) return SPECTRUM_IO;
    uint8_t buffer[1024];
    for(unsigned bank=0;bank<64;++bank) if(state.ram[bank]) {
        if(state.compressed[bank]) {
            unsigned used;
            result=spectrum_inflate(source,state.ram[bank],state.compressed[bank],&output,&used);
            if(result || used!=PAGE ||
               (s->memory && (!spectrum_bank_write(s->memory,bank,0,low,12288) ||
                              !spectrum_bank_write(s->memory,bank,12288,high,4096)))) return SPECTRUM_IO;
            if(!s->memory) {
                uint8_t* ram=s->ram+flat_index(bank)*PAGE;
                memcpy(ram,low,12288);memcpy(ram+12288,high,4096);
            }
            continue;
        }
        for(unsigned at=0;at<PAGE;at+=sizeof(buffer)) {
            uint8_t* target=s->memory?buffer:s->ram+flat_index(bank)*PAGE+at;
            if(!source->read(source->context,state.ram[bank]+at,target,sizeof(buffer)) ||
               (s->memory && !spectrum_bank_write(s->memory,bank,at,buffer,sizeof(buffer)))) return SPECTRUM_IO;
        }
    }
    if(model && (!spectrum_memory_control(s->memory,state.ula[2]) ||
                 !spectrum_memory_page(s->memory,state.ula[1]))) return SPECTRUM_IO;
    restore_cpu(s,state.cpu);
    s->border=state.ula[0];s->beeper=(state.ula[3]>>4)&1;
    if(state.has_ay) {
        for(unsigned i=0;i<16;++i) PSG_writeReg(&s->ay,i,state.ay[i+2]);
        s->ay.adr=state.ay[1];s->sound.selected_reg[0]=s->ay.adr;
    }
    if(state.has_palette) {
        s->ulaplus_mode=state.palette[0]&1;s->ulaplus_select=state.palette[1];
        memcpy(s->ulaplus_palette,state.palette+2,64);
    }
    spectrum_refresh_map(s);
    return SPECTRUM_OK;
}
