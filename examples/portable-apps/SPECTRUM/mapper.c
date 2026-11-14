#include "spectrum.h"
void spectrum_disk_filter(spectrum* s) {
    z80* z=&s->cpu;const spectrum_disk* d=&s->disk;
    z->m1=d->mode?spectrum_disk_m1:NULL;
    if(d->mode==SPECTRUM_DISK_BETA) {
        z->m1_start=d->mapped?0x4000:0x3D00;z->m1_limit=d->mapped?0xBFFF:0x00FF;
    } else { z->m1_start=0;z->m1_limit=0x3FFF; }
}
static bool transfer(spectrum* s,bool write,uint32_t offset,uint8_t* bytes,unsigned n) {
    spectrum_memory* m=s->memory;
    if(!m || m->fault) return false;
    const bool ok=write?m->io.write(m->io.context,offset,bytes,n):m->io.read(m->io.context,offset,bytes,n);
    if(!ok) m->fault=true;
    return ok;
}
static bool flush(spectrum* s) {
    spectrum_disk* d=&s->disk;
    if(d->dirty && !transfer(s,true,SPECTRUM_DIV_RAM+(d->loaded_control&15)*8192U,(uint8_t*)s->rom+8192,8192)) return false;
    d->dirty=false;return true;
}
static bool mapping(spectrum* s,bool on) {
    spectrum_disk* d=&s->disk;
    if(on==d->mapped && (!on || d->loaded_control==d->control)) return true;
    if(d->cache || d->direct_rom[d->mode] || s->memory->rom_banks[0] || s->memory->paged_rom) {
        d->loaded_control=d->control;d->mapped=on;s->memory->overlay=on;
        spectrum_disk_filter(s);spectrum_refresh_map(s);return true;
    }
    if(!flush(s)) return false;
    if(on && d->mode==SPECTRUM_DISK_BETA) {
        if(!transfer(s,false,SPECTRUM_TRDOS_ROM,(uint8_t*)s->rom,16384)) return false;
    } else if(on) {
        const uint32_t low=(d->control&64) && !(d->control&128)?SPECTRUM_DIV_RAM+3*8192:SPECTRUM_DIV_ROM;
        if(!transfer(s,false,low,(uint8_t*)s->rom,8192) ||
           !transfer(s,false,SPECTRUM_DIV_RAM+(d->control&15)*8192U,(uint8_t*)s->rom+8192,8192)) return false;
    } else if(!transfer(s,false,SPECTRUM_ROM_BASE+((s->memory->paging&16)?16384:0),(uint8_t*)s->rom,16384)) return false;
    d->loaded_control=d->control;d->mapped=on;s->memory->overlay=on;
    spectrum_disk_filter(s);spectrum_refresh_map(s);return true;
}
/* The native canvas has 2 KiB spare while the CPU runs. Keep the ordinary
 * ROM resident and cache only disk-ROM/DivRAM bytes actually accessed.
 * M1 transitions must not copy 16 KiB for every DOS call through RAM. */
static bool cache_flush(spectrum* s,unsigned index) {
    spectrum_disk* d=&s->disk;
    if(d->cache_dirty[index]) {
        if(!transfer(s,true,d->tag[index]*1024U,d->cache+index*1024,1024)) return false;
        d->cache_dirty[index]=false;
    }
    return true;
}
static uint8_t* cache_byte(spectrum* s,uint32_t address,bool writing) {
    spectrum_disk* d=&s->disk;const unsigned tag=address/1024;
    unsigned index=d->recent;
    if(d->tag[index]!=tag) {
        index^=1;
        if(d->tag[index]!=tag) {
            if(!cache_flush(s,index) || !transfer(s,false,tag*1024U,d->cache+index*1024,1024)) return NULL;
            d->tag[index]=(uint16_t)tag;
        }
        d->recent=(uint8_t)index;
    }
    if(writing) d->cache_dirty[index]=true;
    return d->cache+index*1024+(address&1023);
}
bool spectrum_disk_cache_begin(spectrum* s,uint8_t cache[SPECTRUM_DISK_CACHE_BYTES]) {
    spectrum_disk* d=&s->disk;
    if(!d->mode) return true;
    if(s->memory && s->memory->paged_rom)return true;
    if(d->mode==SPECTRUM_DISK_BETA && d->direct_rom[d->mode]) return true;
    if(!s->memory || !cache || d->cache || !flush(s)) return false;
    if(d->mapped && !s->memory->rom_banks[0] && !transfer(s,false,SPECTRUM_ROM_BASE+((s->memory->paging&16)?16384:0),(uint8_t*)s->rom,16384)) return false;
    d->cache=cache;d->tag[0]=d->tag[1]=65535;d->recent=1;
    d->cache_dirty[0]=d->cache_dirty[1]=false;s->memory->overlay_cached=true;spectrum_refresh_map(s);return true;
}
bool spectrum_disk_cache_end(spectrum* s) {
    spectrum_disk* d=&s->disk;
    if(s->memory && s->memory->paged_rom) {
        const bool ok=spectrum_memory_sync(s->memory);spectrum_refresh_map(s);return ok;
    }
    if(!d->cache) return true;
    const bool ok=cache_flush(s,0) && cache_flush(s,1);
    d->cache=NULL;s->memory->overlay_cached=false;
    if(!ok) return false;
    if(s->memory->rom_banks[0]) { spectrum_refresh_map(s);return true; }
    if(d->mapped) { d->mapped=false;return mapping(s,true); }
    return true;
}
static uint32_t external_base(const spectrum_disk* d,uint16_t address) {
    return d->mode==SPECTRUM_DISK_BETA?SPECTRUM_TRDOS_ROM:
        address>=8192?SPECTRUM_DIV_RAM+(d->control&15)*8192U-8192:
        (d->control&64) && !(d->control&128)?SPECTRUM_DIV_RAM+3*8192:SPECTRUM_DIV_ROM;
}
void spectrum_disk_map_pages(spectrum* s,const uint8_t* read[64],uint8_t* write[64]) {
    spectrum_memory* m=s->memory;const spectrum_disk* d=&s->disk;
    if(!m || !m->paged_rom || !d->mapped)return;
    for(unsigned i=0;i<16;++i) {
        const uint16_t address=(uint16_t)(i*1024);const uint32_t offset=external_base(d,address)+address;
        read[i]=spectrum_memory_cached_byte(m,offset,false);
        const bool writable=d->mode==SPECTRUM_DISK_DIVMMC && address>=8192 &&
            !((d->control&64) && !(d->control&128) && (d->control&15)==3);
        write[i]=writable?spectrum_memory_cached_byte(m,offset,true):NULL;
    }
}
uint8_t spectrum_disk_read_memory(spectrum* s,uint16_t address) {
    const spectrum_disk* d=&s->disk;
    if(d->direct_rom[d->mode] && (d->mode==SPECTRUM_DISK_BETA ||
       (address<8192 && (!(d->control&64) || (d->control&128))))) return d->direct_rom[d->mode][address];
    const uint32_t base=external_base(d,address);
    if(s->memory->paged_rom) {
        const uint8_t* p=spectrum_memory_external_byte(s->memory,base+address,false);
        if(s->memory->fault)s->cpu.ldir_until=0;
        spectrum_refresh_map(s);return p?*p:255;
    }
    if(!d->cache) { uint8_t value=255;(void)transfer(s,false,base+address,&value,1);return value; }
    uint8_t* value=cache_byte(s,base+address,false);return value?*value:255;
}
bool spectrum_disk_mode(spectrum* s,unsigned mode) {
    if(mode>SPECTRUM_DISK_DIVMMC || (mode && !s->memory)) return false;
    if(s->disk.mapped && !mapping(s,false)) return false;
    s->disk.mode=(uint8_t)mode;spectrum_disk_reset(s);return !(s->memory && s->memory->fault);
}
void spectrum_disk_reset(spectrum* s) {
    spectrum_disk* d=&s->disk;
    /* Reset is a power cycle for the interface, including sticky MAPRAM. */
    d->cache=NULL;d->mapped=d->automap=d->dirty=false;d->control=d->loaded_control=0;d->spi_data=255;
    spectrum_fdc_reset(&d->fdc);spectrum_spi_reset(&d->spi);
    if(d->mode==SPECTRUM_DISK_DIVMMC && s->memory) {
        if(!s->memory->io.clear(s->memory->io.context,SPECTRUM_DIV_RAM,128U*1024U))s->memory->fault=true;
        else spectrum_memory_invalidate(s->memory,SPECTRUM_DIV_RAM,128U*1024U);
    }
    spectrum_disk_filter(s);spectrum_refresh_map(s);
}
bool spectrum_disk_snapshot(spectrum* s) {
    /* Snapshot formats contain no DivMMC state. Keep the running esxDOS
     * kernel in DivRAM, so its IM1 and NMI hooks remain usable after load. */
    if(!flush(s)) return false;
    if(s->memory && s->memory->paged_rom && !spectrum_memory_sync(s->memory)) return false;
    spectrum_disk* d=&s->disk;d->mapped=d->automap=false;d->control&=64;
    spectrum_fdc_reset(&d->fdc);spectrum_spi_select(&d->spi,255);
    spectrum_disk_filter(s);spectrum_refresh_map(s);
    return true;
}
void spectrum_disk_m1(void* raw,uint16_t pc,bool before) {
    spectrum* s=raw;spectrum_disk* d=&s->disk;
    if(!d->mode || !s->memory) return;
    const bool rom48=!s->pentagon || (s->memory->paging&16);
    if(d->mode==SPECTRUM_DISK_BETA) {
        if(before && d->mapped && pc>=0x4000) (void)mapping(s,false);
        else if(before && !d->mapped && rom48 && (pc&0xFF00)==0x3D00) (void)mapping(s,true);
    } else {
        if(before && rom48 && (pc&0xFF00)==0x3D00) d->automap=true;
        if(!before) {
            if(pc>=0x1FF8 && pc<=0x1FFF) d->automap=false;
            else if(pc==0 || pc==8 || pc==0x38 || pc==0x66 || (rom48 && (pc==0x4C6 || pc==0x562))) d->automap=true;
        }
        (void)mapping(s,(d->control&128) || d->automap);
    }
}
void spectrum_disk_write_memory(spectrum* s,uint16_t address,uint8_t value) {
    spectrum_disk* d=&s->disk;
    if(d->mode==SPECTRUM_DISK_DIVMMC && d->mapped && address>=8192 &&
       !((d->control&64) && !(d->control&128) && (d->control&15)==3)) {
        if(s->memory->paged_rom) {
            uint8_t* byte=spectrum_memory_external_byte(s->memory,SPECTRUM_DIV_RAM+(d->control&15)*8192U+address-8192,true);
            if(byte)*byte=value;
            if(s->memory->fault)s->cpu.ldir_until=0;
            spectrum_refresh_map(s);
        } else if(d->cache) {
            uint8_t* byte=cache_byte(s,SPECTRUM_DIV_RAM+(d->control&15)*8192U+address-8192,true);
            if(byte) *byte=value;
        } else if(s->memory->rom_banks[0]) {
            (void)transfer(s,true,SPECTRUM_DIV_RAM+(d->control&15)*8192U+address-8192,&value,1);
        } else { ((uint8_t*)s->rom)[address]=value;d->dirty=true; }
    }
}
bool spectrum_disk_in(spectrum* s,uint16_t port,uint8_t* value) {
    spectrum_disk* d=&s->disk;const uint8_t p=(uint8_t)port;
    if(d->mode==SPECTRUM_DISK_BETA && d->mapped && (p&31)==31 && (p<128 || p==255)) {
        *value=spectrum_fdc_read(&d->fdc,p,(uint32_t)s->cpu.cyc);return true;
    }
    if(d->mode==SPECTRUM_DISK_DIVMMC) {
        if(p==0xE3) { *value=d->control;return true; }
        if(p==0xEB) { *value=d->spi_data;d->spi_data=spectrum_spi_transfer(&d->spi,255);return true; }
    }
    return false;
}
bool spectrum_disk_out(spectrum* s,uint16_t port,uint8_t value) {
    spectrum_disk* d=&s->disk;const uint8_t p=(uint8_t)port;
    if(d->mode==SPECTRUM_DISK_BETA && d->mapped && (p&31)==31 && (p<128 || p==255)) {
        spectrum_fdc_write(&d->fdc,p,value,(uint32_t)s->cpu.cyc);return true;
    }
    if(d->mode==SPECTRUM_DISK_DIVMMC) {
        if(p==0xE3) { d->control=(value&0xCF)|(d->control&64);(void)mapping(s,(d->control&128) || d->automap);return true; }
        if(p==0xE7) { spectrum_spi_select(&d->spi,value);d->spi_data=255;return true; }
        if(p==0xEB) { d->spi_data=spectrum_spi_transfer(&d->spi,value);return true; }
    }
    return false;
}
