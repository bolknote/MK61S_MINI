#include "spectrum.h"
#include <string.h>

#if SPECTRUM_HAS_TIMEX_2068
/* The HOME machine uses the normal 48K maps. Keep two sets of cartridge
 * bytes beyond the 512K cleared by reset so a failed load preserves the
 * inserted cartridge and writes to its RAM. */
enum { CART_BASE=512*1024, CART_BANK_BYTES=65536, CART_SLOT_BYTES=2*CART_BANK_BYTES };
_Static_assert(CART_BASE+2*CART_SLOT_BYTES<=SPECTRUM_ROM_BASE,"Timex cartridge overlaps the ROM");

uint32_t spectrum_timex_chunk(const spectrum_cartridge* cart,unsigned bank,unsigned chunk) {
    return CART_BASE+cart->slot*CART_SLOT_BYTES+bank*CART_BANK_BYTES+chunk*SPECTRUM_TIMEX_CHUNK_BYTES;
}

spectrum_cartridge spectrum_timex_stage(spectrum* s) {
    spectrum_cartridge staged={.slot=s->cartridge.slot^1u};
    spectrum_memory_invalidate(s->memory,spectrum_timex_chunk(&staged,0,0),CART_SLOT_BYTES);
    return staged;
}

static uint32_t overlay(const spectrum* s,unsigned chunk,bool* writing) {
    const unsigned bank=s->timex_mode>>7,bit=1u<<chunk;
    const spectrum_cartridge* cart=&s->cartridge;
    *writing=(cart->writable[bank]&bit)!=0;
    if(cart->present[bank]&bit) return spectrum_timex_chunk(cart,bank,chunk);
    /* The built-in 8K EXROM is mirrored into all eight slots. */
    return bank?SPECTRUM_ROM_BASE+SPECTRUM_ROM_BYTES:UINT32_MAX;
}

void spectrum_timex_map(spectrum* s) {
    const spectrum_memory* m=s->memory;
    const unsigned selected=s->timex_hsr,bank=s->timex_mode>>7;
    if(!m || !selected) return;
    z80* z=&s->cpu;
    for(unsigned chunk=0;chunk<8;++chunk) if(selected&(1u<<chunk)) {
        z->read_map[chunk/2]=NULL;z->write_map[chunk/2]=NULL;
        memset(z->read_pages+chunk*8,0,8*sizeof(*z->read_pages));
        memset(z->write_pages+chunk*8,0,8*sizeof(*z->write_pages));
    }
    const spectrum_cartridge* cart=&s->cartridge;
    const unsigned present=selected&cart->present[bank];
    const unsigned mirrors=bank?selected&~present:0;
    const unsigned cart_tag=spectrum_timex_chunk(cart,bank,0)/SPECTRUM_CACHE_PAGE_BYTES;
    const unsigned exrom=(SPECTRUM_ROM_BASE+SPECTRUM_ROM_BYTES)/SPECTRUM_CACHE_PAGE_BYTES;
    // Rebuild all selected aliases in one walk over the 16 cache tags.
    for(unsigned slot=0;slot<m->page_count;++slot) {
        const unsigned offset=m->tag[slot]-cart_tag;
        const unsigned rom_page=m->tag[slot]-exrom;
        if(offset<64 && (present&(1u<<(offset/8)))) {
            z->read_pages[offset]=m->page_data[slot];
            if(m->dirty[slot] && (cart->writable[bank]&(1u<<(offset/8))))
                z->write_pages[offset]=m->page_data[slot];
        } else if(rom_page<8) {
            for(unsigned chunk=0;chunk<8;++chunk) if(mirrors&(1u<<chunk))
                z->read_pages[chunk*8+rom_page]=m->page_data[slot];
        }
    }
}

bool spectrum_timex_access(spectrum* s,uint16_t address,bool writing,uint8_t* value) {
    const unsigned chunk=address>>13;
    if(!(s->timex_hsr&(1u<<chunk))) return false;
    bool writable;
    const uint32_t base=overlay(s,chunk,&writable);
    if(base!=UINT32_MAX && (!writing || writable)) {
        uint8_t* cell=spectrum_memory_external_byte(s->memory,base+(address&8191u),writing);
        if(cell) {
            if(writing) *cell=*value;
            else *value=*cell;
            spectrum_refresh_map(s);
            return true;
        }
    }
    if(!writing) *value=255;
    return true;
}

enum spectrum_error spectrum_load_dck(spectrum* s,const spectrum_source* source) {
    if(!s->memory || !source || !source->read || !source->size) return SPECTRUM_FORMAT;
    if(s->memory->fault) return SPECTRUM_IO;
    spectrum_cartridge staged=spectrum_timex_stage(s);
    const spectrum_memory_io* io=&s->memory->io;
    uint8_t bytes[1024];
    for(uint32_t at=0;at<source->size;) {
        uint8_t header[9];
        if(source->size-at<sizeof(header)) return SPECTRUM_FORMAT;
        if(!source->read(source->context,at,header,sizeof(header))) return SPECTRUM_IO;
        at+=sizeof(header);
        if(header[0]!=0 && header[0]!=254) return SPECTRUM_UNSUPPORTED;
        const unsigned bank=header[0]?SPECTRUM_TIMEX_EXROM:SPECTRUM_TIMEX_DOCK;
        for(unsigned chunk=0;chunk<8;++chunk) {
            const unsigned type=header[1+chunk],bit=1u<<chunk;
            if(!type) continue;
            if(type>3 || (staged.present[bank]&bit)) return SPECTRUM_FORMAT;
            const uint32_t base=spectrum_timex_chunk(&staged,bank,chunk);
            if(type==1) {
                if(!io->clear(io->context,base,SPECTRUM_TIMEX_CHUNK_BYTES)) return SPECTRUM_IO;
            } else {
                if(source->size-at<SPECTRUM_TIMEX_CHUNK_BYTES) return SPECTRUM_FORMAT;
                for(unsigned offset=0;offset<SPECTRUM_TIMEX_CHUNK_BYTES;offset+=sizeof(bytes)) {
                    if(!source->read(source->context,at,bytes,sizeof(bytes)) ||
                       !io->write(io->context,base+offset,bytes,sizeof(bytes))) return SPECTRUM_IO;
                    at+=sizeof(bytes);
                }
            }
            staged.present[bank]|=(uint8_t)bit;
            if(type&1) staged.writable[bank]|=(uint8_t)bit;
        }
    }
    if(!(staged.present[0]|staged.present[1])) return SPECTRUM_FORMAT;
    spectrum_reset(s);
    if(s->memory->fault) return SPECTRUM_IO;
    s->cartridge=staged;
    return SPECTRUM_OK;
}
#endif
