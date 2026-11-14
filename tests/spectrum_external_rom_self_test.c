#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint8_t backing[SPECTRUM_EXTERNAL_BYTES],fixed[32768],pages[16384],flat[49152],dummy_rom[16384],saved_rom[57344];
static spectrum s;static spectrum_memory m;
static unsigned reads,writes;static bool failed;
static bool rd(void* p,uint32_t at,uint8_t* out,uint32_t n){
    (void)p;assert(at<=sizeof(backing)&&n<=sizeof(backing)-at);++reads;if(failed)return false;
    memcpy(out,backing+at,n);return true;
}
static bool wr(void* p,uint32_t at,const uint8_t* in,uint32_t n){
    (void)p;assert(at<=sizeof(backing)&&n<=sizeof(backing)-at);
    assert(at<SPECTRUM_ROM_BASE||at>=SPECTRUM_DIV_RAM);++writes;memcpy(backing+at,in,n);return true;
}
static bool clear(void* p,uint32_t at,uint32_t n){(void)p;assert(at<=sizeof(backing)&&n<=sizeof(backing)-at);memset(backing+at,0,n);return true;}
static void out(unsigned port,unsigned v){s.cpu.port_out(&s.cpu,(uint16_t)port,(uint8_t)v);}
static unsigned read_byte(unsigned address){return s.cpu.read_byte(&s,(uint16_t)address);}
static void write_byte(unsigned address,unsigned v){s.cpu.write_byte(&s,(uint16_t)address,(uint8_t)v);}
int main(void){
    for(unsigned i=SPECTRUM_ROM_BASE;i<SPECTRUM_DIV_RAM;++i)backing[i]=(uint8_t)(i*31+(i>>10));
    memcpy(saved_rom,backing+SPECTRUM_ROM_BASE,sizeof(saved_rom));
    uint8_t* tails[]={fixed+15360,fixed+31744,pages+8192};const spectrum_memory_io io={NULL,rd,wr,clear};
    assert(spectrum_memory_init_external_rom(&m,fixed,fixed+16384,tails,pages,io));
    m.extended=true;m.banks=64;
    spectrum_init(&s,flat,dummy_rom);spectrum_attach_memory(&s,&m);
    assert(m.paged_rom&&m.page_count==16&&!s.rom&&!s.cpu.read_map[0]);
    for(unsigned bank=0;bank<2;++bank){
        out(0x7FFD,bank?16:0);
        for(unsigned at=0;at<16384;at+=1021){assert(read_byte(at)==backing[SPECTRUM_ROM_BASE+bank*16384+at]);write_byte(at,0xcc);}
        assert(!s.cpu.write_pages[0]&&!m.fault);
    }
    out(0x7FFD,0);(void)read_byte(0x2200);const unsigned count=reads;
    for(unsigned i=0;i<1000;++i)assert(s.cpu.read_pages[8][i&1023]==backing[SPECTRUM_ROM_BASE+0x2000+(i&1023)]);
    assert(reads==count&&!spectrum_memory_external_byte(&m,SPECTRUM_ROM_BASE,true));
    // Every bank competes with read-only ROM pages. Dirty eviction must write
    // only guest RAM; revisiting ROM pages must preserve the original bytes.
    for(unsigned bank=0;bank<64;++bank){
        out(0x7FFD,(bank&7)|((bank&24)<<3)|(bank&32)|16);
        write_byte(0xC000,bank^0xa5);write_byte(0xFFFF,bank^0x5a);(void)read_byte((bank*251)&16383);
    }
    for(int bank=63;bank>=0;--bank){
        out(0x7FFD,(bank&7)|((bank&24)<<3)|(bank&32)|16);
        assert(read_byte(0xC000)==(unsigned)(bank^0xa5));assert(read_byte(0xFFFF)==(unsigned)(bank^0x5a));
    }
    out(0x7FFD,16);out(0xEFF7,8);write_byte(0,0x55);assert(read_byte(0xC000)==0x55);
    out(0xEFF7,0);assert(read_byte(0)==backing[SPECTRUM_ROM_BASE+16384]);
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_BETA));assert(spectrum_disk_cache_begin(&s,pages));assert(!s.disk.cache);
    spectrum_disk_m1(&s,0x3D00,true);assert(s.disk.mapped&&read_byte(0x1234)==backing[SPECTRUM_TRDOS_ROM+0x1234]);
    write_byte(0x1234,0x11);assert(read_byte(0x1234)==backing[SPECTRUM_TRDOS_ROM+0x1234]);
    spectrum_disk_m1(&s,0x4000,true);assert(!s.disk.mapped&&read_byte(0x1234)==backing[SPECTRUM_ROM_BASE+16384+0x1234]);
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_DIVMMC));out(0xE3,0x80);
    assert(read_byte(0x100)==backing[SPECTRUM_DIV_ROM+0x100]);
    write_byte(0x2100,0xa5);out(0xE3,0x81);write_byte(0x2100,0xb6);out(0xE3,0x80);assert(read_byte(0x2100)==0xa5);
    assert(spectrum_disk_cache_end(&s));assert(backing[SPECTRUM_DIV_RAM+0x100]==0xa5&&backing[SPECTRUM_DIV_RAM+8192+0x100]==0xb6);
    out(0xE3,0x83);write_byte(0x2000,0x76);out(0xE3,0x43);spectrum_disk_m1(&s,0x66,false);
    assert(read_byte(0)==0x76&&read_byte(0x2000)==0x76);write_byte(0,0xcc);write_byte(0x2000,0xcc);assert(read_byte(0)==0x76&&read_byte(0x2000)==0x76);
    assert(spectrum_disk_snapshot(&s) && spectrum_memory_reset(&m));
    out(0xE3,0x83);assert(read_byte(0x2000)==0x76); // loading a snapshot keeps the esxDOS kernel
    spectrum_disk_reset(&s);out(0xE3,0x83);assert(read_byte(0x2000)==0); // reset discards cached DivRAM too
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_NONE));out(0x7FFD,0);
    // Z80's fast LDIR uses the same page views as scalar reads/writes.
    const uint8_t code[]={0x21,0xf0,0x00,0x11,0xf0,0xcf,0x01,0x40,0x04,0xed,0xb0,0x76};
    memcpy(backing+SPECTRUM_ROM_BASE,code,sizeof(code));spectrum_memory_invalidate(&m,SPECTRUM_ROM_BASE,16384);spectrum_refresh_map(&s);
    s.cpu.pc=0;s.cpu.halted=false;spectrum_run(&s,40000);assert(s.cpu.halted);
    for(unsigned i=0;i<1088;++i)assert(read_byte(0xCFF0+i)==backing[SPECTRUM_ROM_BASE+0xF0+i]);
    memcpy(backing+SPECTRUM_ROM_BASE,saved_rom,sizeof(code));
    assert(spectrum_disk_cache_end(&s));assert(!memcmp(saved_rom,backing+SPECTRUM_ROM_BASE,sizeof(saved_rom)));
    spectrum_memory_invalidate(&m,SPECTRUM_ROM_BASE,32768);spectrum_refresh_map(&s);failed=true;
    assert(read_byte(0x3210)==255&&m.fault&&!s.cpu.ldir_until);assert(writes);
    puts("SD/PSRAM ROM: shared16KiB cache, both ROMs, 64 banks, dirty eviction, Beta/DivMMC/MAPRAM, reset, LDIR, ROM protection and read fault PASS");
}
