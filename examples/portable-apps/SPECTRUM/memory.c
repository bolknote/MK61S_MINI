#include "memory.h"
#include <string.h>
static int cached(const spectrum_memory* m,unsigned tag) {
    for(unsigned i=0;i<m->page_count;++i) if(m->tag[i]==tag) return (int)i;
    return -1;
}
static uint8_t* fixed(spectrum_memory* m,unsigned bank) {
    return bank==5?m->cache:bank==2?m->fixed2:NULL;
}
static uint8_t* fixed_byte(spectrum_memory* m,unsigned bank,unsigned offset) {
    return offset<SPECTRUM_BANK_HEAP_BYTES?fixed(m,bank)+offset:
        m->fixed_tail[bank==2]+offset-SPECTRUM_BANK_HEAP_BYTES;
}
uint8_t* spectrum_memory_fixed(spectrum_memory* m,unsigned bank) {
    uint8_t* base=fixed(m,bank);
    return base && m->fixed_tail[bank==2]==base+SPECTRUM_BANK_HEAP_BYTES?base:NULL;
}
static uint8_t* slot_bytes(spectrum_memory* m,unsigned slot) {
    return slot>=8?m->pages_tail+(slot-8)*SPECTRUM_CACHE_PAGE_BYTES:m->pages+slot*SPECTRUM_CACHE_PAGE_BYTES;
}
static unsigned bank_value(const spectrum_memory* m,uint8_t paging) {
    unsigned bank=paging&7;
    if(!m->extended) bank|=(paging>>3)&24;
    else if(!(m->control&4)) bank|=((paging>>3)&24)|(paging&32);
    return bank;
}
static bool flush_slot(spectrum_memory* m,unsigned slot) {
    if(m->dirty[slot]) {
        if(!m->io.write(m->io.context,m->tag[slot]*SPECTRUM_CACHE_PAGE_BYTES,
            slot_bytes(m,slot),SPECTRUM_CACHE_PAGE_BYTES)) { m->fault=true;return false; }
        ++m->writebacks;m->dirty[slot]=false;
    }
    return true;
}
bool spectrum_memory_flush_pages(spectrum_memory* m) {
    for(unsigned i=0;i<m->page_count;++i) {
        if(!flush_slot(m,i)) return false;
        m->tag[i]=65535;
    }
    return true;
}
bool spectrum_memory_sync(spectrum_memory* m) {
    for(unsigned i=0;i<m->page_count;++i)if(!flush_slot(m,i))return false;
    return true;
}
void spectrum_memory_invalidate(spectrum_memory* m,uint32_t first,uint32_t bytes) {
    for(unsigned i=0;i<m->page_count;++i) {
        const uint32_t address=m->tag[i]*1024u;
        if(address>=first && address-first<bytes){m->tag[i]=65535;m->dirty[i]=false;}
    }
}
uint8_t* spectrum_memory_cached_byte(spectrum_memory* m,uint32_t address,bool writing) {
    const int slot=cached(m,address/1024);
    if(slot<0 || (writing && (!m->dirty[slot] || (address>=SPECTRUM_ROM_BASE && address<SPECTRUM_DIV_RAM))))return NULL;
    return slot_bytes(m,(unsigned)slot)+(address&1023);
}
uint8_t* spectrum_memory_mapped(spectrum_memory* m,bool writing) {
    const unsigned bank=bank_value(m,m->paging);uint8_t* direct=spectrum_memory_fixed(m,bank);
    if(direct) return direct;
    /* Reads may use any contiguous bank; stores may bypass traps only
     * after every page has been marked dirty. */
    if(!m->window) return NULL;
    for(unsigned i=0;i<16;++i) if(m->tag[i]!=bank*16+i || (writing && !m->dirty[i])) return NULL;
    return m->window;
}
void spectrum_memory_map_pages(spectrum_memory* m,const uint8_t* read[64],uint8_t* write[64]) {
    memset(read,0,64*sizeof(*read));memset(write,0,64*sizeof(*write));
    if(!m) return;
    const unsigned upper=bank_value(m,m->paging);
    const bool ram0=m->extended && (m->control&8) && !m->overlay;
    /* Walk the cache once. Repeated tag searches for every guest page make
     * rebuilding the CPU view needlessly expensive at every 7FFD OUT. */
    for(unsigned slot=0;slot<m->page_count;++slot) {
        const unsigned tag=m->tag[slot],bank=tag/16,page=tag&15;
        uint8_t* bytes=slot_bytes(m,slot);
        if(ram0 && bank==0) { read[page]=bytes;if(m->dirty[slot]) write[page]=bytes; }
        if(m->paged_rom && !ram0 && !m->overlay && tag==(SPECTRUM_ROM_BASE/1024+((m->paging&16)?16u:0u)+page))read[page]=bytes;
        if(bank==upper) { read[48+page]=bytes;if(m->dirty[slot]) write[48+page]=bytes; }
    }
    for(unsigned page=0;page<16;++page) {
        read[16+page]=write[16+page]=fixed_byte(m,5,page*1024);
        read[32+page]=write[32+page]=fixed_byte(m,2,page*1024);
        if(fixed(m,upper)) read[48+page]=write[48+page]=fixed_byte(m,upper,page*1024);
    }
}
static uint8_t* page(spectrum_memory* m,unsigned tag) {
    int active=cached(m,tag);
    if(active<0) {
        /* Natural placement permits a full direct view for flat 48K RAM;
         * mixed banks retain their pages across 7FFD changes. */
        unsigned slot=tag&(m->page_count-1);
        if(m->tag[slot]!=65535) {
            for(slot=0;slot<m->page_count && m->tag[slot]!=65535;++slot) {}
            if(slot==m->page_count) { slot=m->victim;m->victim=(m->victim+1)&(m->page_count-1); }
        }
        active=(int)slot;uint8_t* bytes=slot_bytes(m,slot);
        if(!flush_slot(m,slot) || !m->io.read(m->io.context,tag*SPECTRUM_CACHE_PAGE_BYTES,bytes,SPECTRUM_CACHE_PAGE_BYTES)) goto fault;
        m->tag[slot]=(uint16_t)tag;++m->loads;
    }
    m->recent=(uint8_t)active;return slot_bytes(m,(unsigned)active);
fault:
    m->fault=true;m->dummy=255;return &m->dummy;
}
uint8_t* spectrum_memory_external_byte(spectrum_memory* m,uint32_t address,bool writing) {
    if(m->fault || address>=SPECTRUM_EXTERNAL_BYTES)return NULL;
    if(writing && address>=SPECTRUM_ROM_BASE && address<SPECTRUM_DIV_RAM)return NULL;
    uint8_t* bytes=page(m,address/1024);
    if(m->fault)return NULL;
    if(writing)m->dirty[m->recent]=true;
    return bytes+(address&1023);
}
uint8_t* spectrum_memory_byte(spectrum_memory* m,uint16_t address,bool writing) {
    const bool low=address<0x4000;
    if(low && !(m->extended && (m->control&8) && !m->overlay)) {
        if(m->paged_rom)return writing?NULL:spectrum_memory_external_byte(m,SPECTRUM_ROM_BASE+((m->paging&16)?16384u:0u)+address,false);
        return (uint8_t*)m->rom+address;
    }
    if(!low && address<0xC000) return fixed_byte(m,address<0x8000?5:2,address&16383);
    const unsigned bank=low?0:bank_value(m,m->paging),offset=address&16383;
    if(fixed(m,bank)) return fixed_byte(m,bank,offset);
    uint8_t* bytes=page(m,bank*16+offset/SPECTRUM_CACHE_PAGE_BYTES);
    if(m->fault) return &m->dummy;
    if(writing) m->dirty[m->recent]=true;
    return bytes+offset%SPECTRUM_CACHE_PAGE_BYTES;
}
bool spectrum_memory_page(spectrum_memory* m,uint8_t value) {
    if(m->fault) return false;
    if(m->locked) return true;
    if(m->rom_banks[0]) m->rom=m->rom_banks[(value>>4)&1];
    else if(!m->paged_rom && (!m->overlay || m->overlay_cached) && ((value^m->paging)&16)) {
        if(!m->io.read(m->io.context,SPECTRUM_ROM_BASE+((value&16)?16384:0),(uint8_t*)m->rom,16384)) { m->fault=true;return false; }
    }
    m->paging=value;
    if(!m->extended || (m->control&4)) m->locked=(value&32)!=0;
    return true;
}
bool spectrum_memory_control(spectrum_memory* m,uint8_t value) {
    if(m->fault) return false;
    if(m->extended && !m->locked) m->control=value;
    return true;
}
bool spectrum_memory_reset(spectrum_memory* m) {
    m->fault=false;m->overlay=m->overlay_cached=false;m->paging=m->extended?16:0;m->control=0;m->locked=false;m->loads=m->writebacks=0;m->recent=m->victim=0;
    if(!m->io.clear(m->io.context,0,m->banks*16384U)) { m->fault=true;return false; }
    if(m->rom_banks[0]) m->rom=m->rom_banks[m->extended?1:0];
    else if(!m->paged_rom && !m->io.read(m->io.context,SPECTRUM_ROM_BASE+(m->extended?16384:0),(uint8_t*)m->rom,16384)) { m->fault=true;return false; }
    memset(m->cache,0,SPECTRUM_BANK_HEAP_BYTES);memset(m->fixed2,0,SPECTRUM_BANK_HEAP_BYTES);
    memset(m->fixed_tail[0],0,1024);memset(m->fixed_tail[1],0,1024);
    for(unsigned i=0;i<m->page_count;++i) memset(slot_bytes(m,i),0,1024);
    memset(m->dirty,0,sizeof(m->dirty));
    for(unsigned i=0;i<16;++i) m->tag[i]=65535;
    return true;
}
bool spectrum_memory_init(spectrum_memory* m,uint8_t cache[SPECTRUM_CACHE_BYTES],uint8_t rom[16384],spectrum_memory_io io) {
    if(!cache) return false;
    return spectrum_memory_init_pages(m,cache,cache+SPECTRUM_FIXED_BYTES,rom,io);
}
bool spectrum_memory_init_pages(spectrum_memory* m,uint8_t fixed_cache[SPECTRUM_FIXED_BYTES],uint8_t pages[2*SPECTRUM_CACHE_PAGE_BYTES],uint8_t rom[16384],spectrum_memory_io io) {
    if(!m || !fixed_cache || !pages || !rom || !io.read || !io.write || !io.clear) return false;
    uint8_t* tails[]={fixed_cache+15360,fixed_cache+31744,NULL};
    return spectrum_memory_init_split(m,fixed_cache,fixed_cache+16384,tails,pages,rom,NULL,io);
}
bool spectrum_memory_init_mapped(spectrum_memory* m,uint8_t fixed_cache[SPECTRUM_FIXED_BYTES],uint8_t pages[2*SPECTRUM_CACHE_PAGE_BYTES],uint8_t window[16384],const uint8_t* rom0,const uint8_t* rom1,spectrum_memory_io io) {
    if(!m || !fixed_cache || !pages || !window || !rom0 || !rom1 || !io.read || !io.write || !io.clear) return false;
    uint8_t* tails[]={fixed_cache+15360,fixed_cache+31744,window+8192};
    if(!spectrum_memory_init_split(m,fixed_cache,fixed_cache+16384,tails,window,rom0,rom1,io)) return false;
    m->window=window;return true;
}
bool spectrum_memory_init_split(spectrum_memory* m,uint8_t* fixed5,uint8_t* fixed2,uint8_t* tails[3],uint8_t* pages,const uint8_t* rom0,const uint8_t* rom1,spectrum_memory_io io) {
    if(!m || !fixed5 || !fixed2 || !tails || !tails[0] || !tails[1] || !pages || !rom0 ||
       (rom1 && !tails[2]) || !io.read || !io.write || !io.clear) return false;
    memset(m,0,sizeof(*m));m->cache=fixed5;m->fixed2=fixed2;m->fixed_tail[0]=tails[0];m->fixed_tail[1]=tails[1];
    m->pages=pages;m->pages_tail=tails[2];m->page_count=rom1?16:2;m->rom=rom0;m->io=io;m->banks=32;
    if(rom1) { m->rom_banks[0]=rom0;m->rom_banks[1]=rom1; }
    return spectrum_memory_reset(m);
}
bool spectrum_memory_init_external_rom(spectrum_memory* m,uint8_t* fixed5,uint8_t* fixed2,uint8_t* tails[3],uint8_t* pages,spectrum_memory_io io) {
    if(!m || !fixed5 || !fixed2 || !tails || !tails[0] || !tails[1] || !tails[2] || !pages || !io.read || !io.write || !io.clear)return false;
    memset(m,0,sizeof(*m));m->cache=fixed5;m->fixed2=fixed2;m->fixed_tail[0]=tails[0];m->fixed_tail[1]=tails[1];
    m->pages=pages;m->pages_tail=tails[2];m->page_count=16;m->paged_rom=true;m->io=io;m->banks=32;
    return spectrum_memory_reset(m);
}
bool spectrum_bank_read(spectrum_memory* m,unsigned bank,unsigned offset,uint8_t* out,unsigned bytes) {
    if(m->fault || bank>=m->banks || offset>16384 || bytes>16384-offset || (!out && bytes)) return false;
    if(fixed(m,bank)) {
        while(bytes) {
            const unsigned left=1024-offset%1024,n=bytes<left?bytes:left;
            memcpy(out,fixed_byte(m,bank,offset),n);offset+=n;out+=n;bytes-=n;
        }
        return true;
    }
    while(bytes) {
        const unsigned left=SPECTRUM_CACHE_PAGE_BYTES-offset%SPECTRUM_CACHE_PAGE_BYTES;
        const unsigned n=bytes<left?bytes:left,tag=bank*16+offset/SPECTRUM_CACHE_PAGE_BYTES;
        const int active=cached(m,tag);
        if(active>=0) memcpy(out,slot_bytes(m,(unsigned)active)+offset%SPECTRUM_CACHE_PAGE_BYTES,n);
        else if(!m->io.read(m->io.context,bank*16384U+offset,out,n)) { m->fault=true;return false; }
        offset+=n;out+=n;bytes-=n;
    }
    return true;
}
bool spectrum_bank_write(spectrum_memory* m,unsigned bank,unsigned offset,const uint8_t* in,unsigned bytes) {
    if(m->fault || bank>=m->banks || offset>16384 || bytes>16384-offset || (!in && bytes)) return false;
    if(fixed(m,bank)) {
        while(bytes) {
            const unsigned left=1024-offset%1024,n=bytes<left?bytes:left;
            memcpy(fixed_byte(m,bank,offset),in,n);offset+=n;in+=n;bytes-=n;
        }
        return true;
    }
    while(bytes) {
        const unsigned left=SPECTRUM_CACHE_PAGE_BYTES-offset%SPECTRUM_CACHE_PAGE_BYTES;
        const unsigned n=bytes<left?bytes:left,tag=bank*16+offset/SPECTRUM_CACHE_PAGE_BYTES;
        const int active=cached(m,tag);
        if(active>=0) { memcpy(slot_bytes(m,(unsigned)active)+offset%SPECTRUM_CACHE_PAGE_BYTES,in,n);m->dirty[active]=true; }
        else if(!m->io.write(m->io.context,bank*16384U+offset,in,n)) { m->fault=true;return false; }
        offset+=n;in+=n;bytes-=n;
    }
    return true;
}
