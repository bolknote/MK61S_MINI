#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include "../examples/portable-apps/SPECTRUM/media.h"
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint8_t ram[49152],rom[16384],backing[SPECTRUM_EXTERNAL_BYTES+SPECTRUM_TRD_BYTES];
static spectrum s;
static uint32_t read_bytes,write_bytes,read_requests;
static bool rd(void* p,uint32_t at,uint8_t* out,uint32_t n) { ++read_requests;read_bytes+=n;memcpy(out,(uint8_t*)p+at,n);return true; }
static bool wr(void* p,uint32_t at,const uint8_t* in,uint32_t n) { write_bytes+=n;memcpy((uint8_t*)p+at,in,n);return true; }
static bool clear(void* p,uint32_t at,uint32_t n) { memset((uint8_t*)p+at,0,n);return true; }
static void out(unsigned port,unsigned value) { s.cpu.port_out(&s.cpu,(uint16_t)port,(uint8_t)value); }
static void ay(unsigned chip,unsigned reg,unsigned value) { out(0xFFFD,chip?254:255);out(0xFFFD,reg);out(0xBFFD,value); }
static void devices(void) {
    spectrum_init(&s,ram,rom);
    ay(0,8,15);ay(1,8,7);assert(s.ay.reg[8]==15 && s.ay2.reg[8]==7);
    out(0xFFFD,8);assert(spectrum_port_in(&s,0xFFFD)==7);
    out(0xFFFD,255);out(0xFFFD,8);assert(spectrum_port_in(&s,0xFFFD)==15);
    out(0xFFFD,254);out(0xFFFD,8);s.extensions&=~SPECTRUM_TURBOSOUND;
    out(0xBFFD,5);assert(s.ay.reg[8]==5 && s.ay2.reg[8]==7);
    s.extensions|=SPECTRUM_TURBOSOUND;
    out(0xFB,255);out(0xDF,0);assert(s.sound.covox==255 && s.sound.specdrum==0);
    out(0xBF3B,61);out(0xFF3B,255);out(0xBF3B,64);out(0xFF3B,1);
    assert(spectrum_palette(&s,61)==0xFFFF && spectrum_port_in(&s,0xFF3B)==1);
    ram[0]=0x80;ram[6144]=0xE5;uint8_t bits[6144],tiles[1536];
    spectrum_video8(&s,bits,tiles);assert(bits[0]==128 && tiles[0]==60 && tiles[1]==53);
    s.frames=16;spectrum_video8(&s,bits,tiles);assert(tiles[0]==60 && tiles[1]==53);
    out(0xBF3B,64);out(0xFF3B,0);spectrum_video8(&s,bits,tiles);assert(tiles[0]==13 && tiles[1]==12);
    for(unsigned mode=1;mode<=2;++mode) {
        s.joystick_mode=(uint8_t)mode;uint8_t keys[32]={0};keys[0xB4/8]|=1U<<(0xB4&7);keys[0x85/8]|=1U<<(0x85&7);
        spectrum_keyboard(&s,keys);assert(spectrum_port_in(&s,31)==255);
        if(mode==1) assert(!(s.keys[4]&1) && !(s.keys[4]&16));
        else assert(!(s.keys[3]&1) && !(s.keys[3]&16));
    }
    puts("TurboSound chip isolation, DAC ports, ULAplus CLUT/flash, Sinclair joysticks: PASS");
}
static void mapping(void) {
  for(unsigned cached=0;cached<2;++cached) {
    uint8_t disk_cache[SPECTRUM_DISK_CACHE_BYTES];
    spectrum_memory m;const spectrum_memory_io io={backing,rd,wr,clear};
    memset(backing,0x11,sizeof(backing));memset(backing+SPECTRUM_ROM_BASE+16384,0x22,16384);
    memset(backing+SPECTRUM_TRDOS_ROM,0x33,16384);memset(backing+SPECTRUM_DIV_ROM,0x44,8192);
    spectrum_init(&s,ram,rom);assert(spectrum_memory_init(&m,ram,rom,io));spectrum_attach_memory(&s,&m);
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_BETA));
    if(cached) assert(spectrum_disk_cache_begin(&s,disk_cache));
    spectrum_disk_m1(&s,0x3D00,true);assert(!s.disk.mapped);
    assert(spectrum_memory_page(&m,16));spectrum_disk_m1(&s,0x3D00,true);assert(s.disk.mapped && s.cpu.read_byte(&s,0)==0x33);
    assert(spectrum_memory_page(&m,0));assert(s.cpu.read_byte(&s,0)==0x33);spectrum_disk_m1(&s,0x4000,true);
    assert(!s.disk.mapped && rom[0]==0x11 && !m.overlay);
    if(cached) {
        assert(spectrum_memory_page(&m,16));read_bytes=0;
        for(unsigned i=0;i<100;++i) {
            spectrum_disk_m1(&s,0x3D00,true);assert(s.cpu.read_byte(&s,0x3D00)==0x33);
            spectrum_disk_m1(&s,0x4000,true);assert(s.cpu.read_byte(&s,0)==0x22);
        }
        assert(read_bytes==1024);assert(spectrum_disk_cache_end(&s));assert(spectrum_memory_page(&m,0));
    }
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_DIVMMC));
    if(cached) assert(spectrum_disk_cache_begin(&s,disk_cache));
    spectrum_disk_m1(&s,0,true);assert(!s.disk.mapped);spectrum_disk_m1(&s,0,false);assert(s.disk.mapped && s.cpu.read_byte(&s,0)==0x44);
    s.cpu.write_byte(&s,0x2100,0xA5);out(0xE3,1);assert(s.cpu.read_byte(&s,0x2100)==0);
    s.cpu.write_byte(&s,0x2100,0xB6);out(0xE3,0);assert(s.cpu.read_byte(&s,0x2100)==0xA5);
    spectrum_disk_m1(&s,0x1FF8,true);assert(s.disk.mapped);spectrum_disk_m1(&s,0x1FF8,false);
    assert(!s.disk.mapped && rom[0]==0x11);
    if(cached) assert(spectrum_disk_cache_end(&s));
    assert(backing[SPECTRUM_DIV_RAM+0x100]==0xA5 && backing[SPECTRUM_DIV_RAM+8192+0x100]==0xB6);
    if(cached) assert(spectrum_disk_cache_begin(&s,disk_cache));
    out(0xE3,0x83);s.cpu.write_byte(&s,0x2000,0x76);out(0xE3,0x43);
    spectrum_disk_m1(&s,0x66,false);assert(s.cpu.read_byte(&s,0)==0x76 && s.disk.mapped);
    s.cpu.write_byte(&s,0,0xCC);s.cpu.write_byte(&s,0x2000,0xCC);assert(s.cpu.read_byte(&s,0)==0x76 && s.cpu.read_byte(&s,0x2000)==0x76);
    if(cached) { assert(spectrum_disk_cache_end(&s));assert(spectrum_disk_cache_begin(&s,disk_cache));assert(s.cpu.read_byte(&s,0)==0x76);assert(spectrum_disk_cache_end(&s)); }
    out(0xE3,0);assert(s.disk.control&64);spectrum_reset(&s);assert(!s.disk.control && !s.disk.mapped && rom[0]==0x11);
    s.memory=NULL;
  }
  puts("Beta/DivMMC M1 timing, cached ROM overlay, bank writeback, sticky MAPRAM/protection: PASS");
}
static void pentagon_1024(void) {
    spectrum_memory m;const spectrum_memory_io io={backing,rd,wr,clear};
    spectrum_init(&s,ram,rom);assert(spectrum_memory_init(&m,ram,rom,io));
    m.extended=true;m.banks=64;assert(spectrum_memory_reset(&m));spectrum_attach_memory(&s,&m);
    assert(!m.control && !m.locked && m.paging==16);
    for(unsigned bank=0;bank<64;++bank) {
        const uint8_t port=(uint8_t)((bank&7)|((bank&24)<<3)|(bank&32)|16);
        out(0x7FFD,port);s.cpu.write_byte(&s,0xC000,(uint8_t)(bank^0xA5));s.cpu.write_byte(&s,0xFFFF,(uint8_t)(bank^0x5A));
        assert(!m.locked);
    }
    for(int bank=63;bank>=0;--bank) {
        out(0x7FFD,(bank&7)|((bank&24)<<3)|(bank&32)|16);
        assert(s.cpu.read_byte(&s,0xC000)==(uint8_t)(bank^0xA5));
        assert(s.cpu.read_byte(&s,0xFFFF)==(uint8_t)(bank^0x5A));
    }
    out(0xEFF7,8);out(0x7FFD,16);s.cpu.write_byte(&s,0,0xDA);
    assert(s.cpu.read_byte(&s,0xC000)==0xDA);s.cpu.write_byte(&s,0xC000,0x75);assert(s.cpu.read_byte(&s,0)==0x75);
    out(0xEFF7,0);assert(s.cpu.read_byte(&s,0)==backing[SPECTRUM_ROM_BASE+16384]);
    out(0xEFF7,4);out(0x7FFD,0xD6);assert(s.cpu.read_byte(&s,0xC000)==(6^0xA5));
    out(0x7FFD,0x30);assert(m.locked);out(0xEFF7,0);out(0x7FFD,7);assert(m.control==4 && m.paging==0x30);
    spectrum_reset(&s);assert(!m.locked && !m.control && m.paging==16 && !m.fault);
    assert(s.cpu.read_byte(&s,0xC000)==0);s.memory=NULL;
    puts("Pentagon 1024: all 64 banks, last cache tag, EFF7 128K gate/lock, RAM0 alias, reset: PASS");
}
static void full_window(void) {
    spectrum_memory m;uint8_t pages[2*SPECTRUM_CACHE_PAGE_BYTES];
    const spectrum_memory_io io={backing,rd,wr,clear};
    memset(backing+SPECTRUM_ROM_BASE,0x11,16384);memset(backing+SPECTRUM_ROM_BASE+16384,0x22,16384);
    spectrum_init(&s,ram,rom);
    assert(spectrum_memory_init_mapped(&m,ram,pages,ram+32768,backing+SPECTRUM_ROM_BASE,backing+SPECTRUM_ROM_BASE+16384,io));
    m.extended=true;m.banks=64;assert(spectrum_memory_reset(&m));spectrum_attach_memory(&s,&m);
    for(unsigned pass=0;pass<2;++pass) for(unsigned n=0;n<64;++n) {
        const unsigned bank=pass?63-n:n;
        out(0x7FFD,(bank&7)|((bank&24)<<3)|(bank&32)|16);
        const uint8_t write_code[]={0x3E,(uint8_t)(bank^0xA5),0x32,0,0xCF,0x2F,0x32,0xFD,0xFF,0xF3,0x76};
        const uint8_t read_code[]={0x3A,0,0xCF,0x32,0,0x82,0x3A,0xFD,0xFF,0x32,1,0x82,0xF3,0x76};
        memcpy(ram+0x4100,pass?read_code:write_code,pass?sizeof(read_code):sizeof(write_code));
        s.cpu.pc=0x8100;s.cpu.halted=false;spectrum_run(&s,200);
        if(pass) assert(ram[0x4200]==(uint8_t)(bank^0xA5) && ram[0x4201]==(uint8_t)(bank^0x5A));
    }
    out(0xEFF7,8);out(0x7FFD,20);
    const uint8_t aliases[]={0x3E,0xDA,0x32,0x23,1,0x3A,0,0xCF,0x32,0,0x82,0xF3,0x76};
    memcpy(ram+0x4100,aliases,sizeof(aliases));s.cpu.pc=0x8100;s.cpu.halted=false;spectrum_run(&s,200);
    assert(ram[0x4200]==(4^0xA5));out(0x7FFD,16);assert(s.cpu.read_byte(&s,0xC123)==0xDA);
    out(0xEFF7,0);assert(s.cpu.read_map[0]==backing+SPECTRUM_ROM_BASE+16384);
    out(0xEFF7,8);
    const uint8_t dos[]={0x3A,0,2,0x32,0,0x82,0xC3,0,0x81};
    memcpy(backing+SPECTRUM_TRDOS_ROM+0x3D00,dos,sizeof(dos));backing[SPECTRUM_TRDOS_ROM+0x200]=0x5A;
    ram[0x4100]=0xF3;ram[0x4101]=0x76;s.disk.xip_rom[SPECTRUM_DISK_BETA]=backing+SPECTRUM_TRDOS_ROM;
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_BETA));
    const uint32_t before=read_bytes;s.cpu.pc=0x3D00;s.cpu.halted=false;spectrum_run(&s,200);
    assert(ram[0x4200]==0x5A && !s.disk.mapped && !s.cpu.read_map[0] && read_bytes==before);
    assert(backing[SPECTRUM_ROM_BASE]==0x11 && backing[SPECTRUM_ROM_BASE+16384]==0x22 && !m.fault);
    s.memory=NULL;puts("Mapped ROMs, 16K page cache, 64 banks, CPU direct windows, RAM0 aliases and zero-copy Beta M1: PASS");
}
static uint8_t (*original_reader)(void*,uint16_t);
static unsigned read_callbacks;
static uint8_t count_read(void* context,uint16_t address) { ++read_callbacks;return original_reader(context,address); }
static void retained_pages(void) {
    spectrum_memory m;uint8_t small[2048];const spectrum_memory_io io={backing,rd,wr,clear};
    spectrum_init(&s,ram,rom);
    assert(spectrum_memory_init_mapped(&m,ram,small,ram+32768,backing+SPECTRUM_ROM_BASE,backing+SPECTRUM_ROM_BASE+16384,io));
    m.extended=true;m.banks=64;assert(spectrum_memory_reset(&m));spectrum_attach_memory(&s,&m);
    for(unsigned bank=0;bank<8;++bank) {
        const uint8_t a=(uint8_t)(bank+0x40),b=(uint8_t)(bank+0x70);
        assert(spectrum_bank_write(&m,bank,0x123,&a,1) && spectrum_bank_write(&m,bank,0x1234,&b,1));
    }
    const uint8_t read_code[]={0xF3,0x3A,0x23,0xC1,0x32,0,0x82,0x3A,0x34,0xD2,0x32,1,0x82,0x76};
    memcpy(ram+0x4100,read_code,sizeof(read_code));original_reader=s.cpu.read_byte;s.cpu.read_byte=count_read;
    const uint32_t reads=read_bytes,writes=write_bytes;
    for(unsigned pass=0;pass<101;++pass) {
        if(pass==1) { assert(read_bytes-reads==12*1024 && write_bytes==writes);read_callbacks=0; }
        for(unsigned bank=0;bank<8;++bank) {
            out(0x7FFD,16|bank);s.cpu.pc=0x8100;s.cpu.halted=false;spectrum_run(&s,200);
            assert(ram[0x4200]==bank+0x40 && ram[0x4201]==bank+0x70);
        }
    }
    assert(!read_callbacks && read_bytes-reads==12*1024 && write_bytes==writes);
    const uint8_t write_code[]={0xF3,0x3E,0x77,0x32,0x23,0xC1,0x3E,0x66,0x32,0x34,0xD2,0x76};
    memcpy(ram+0x4100,write_code,sizeof(write_code));
    for(unsigned bank=0;bank<8;++bank) { out(0x7FFD,16|bank);s.cpu.pc=0x8100;s.cpu.halted=false;spectrum_run(&s,200); }
    assert(write_bytes==writes); // Dirty bytes stay cached until eviction.
    for(unsigned bank=8;bank<64;++bank) {
        out(0x7FFD,(bank&7)|((bank&24)<<3)|(bank&32)|16);
        (void)s.cpu.read_byte(&s,0xC000);
    }
    assert(write_bytes-writes==12*1024); // Never write an unchanged 16K bank.
    for(unsigned bank=0;bank<8;++bank) {
        uint8_t a,b;assert(spectrum_bank_read(&m,bank,0x123,&a,1) && spectrum_bank_read(&m,bank,0x1234,&b,1));
        assert(a==0x77 && b==0x66);
    }
    s.cpu.read_byte=original_reader;s.memory=NULL;
    puts("Eight-bank working set retained across 800 switches; zero hot read callbacks/I/O, only dirty 1K writeback: PASS");
}
static void scl(void) {
    uint8_t source[9+14+256+4]={0};memcpy(source,"SINCLAIR",8);source[8]=1;memcpy(source+9,"TEST    C",9);
    source[22]=1;memset(source+23,0xA5,256);uint32_t sum=0;
    for(unsigned i=0;i<sizeof(source)-4;++i) sum+=source[i];
    for(unsigned i=0;i<4;++i) source[sizeof(source)-4+i]=(uint8_t)(sum>>(i*8));
    spectrum_source src={source,sizeof(source),rd};const spectrum_memory_io io={backing,rd,wr,clear};
    assert(spectrum_scl_unpack(&src,&io,SPECTRUM_EXTERNAL_BYTES)==SPECTRUM_OK);
    const uint8_t* trd=backing+SPECTRUM_EXTERNAL_BYTES;
    assert(!memcmp(trd,"TEST    C",9) && trd[14]==0 && trd[15]==1);
    assert(trd[0x8E1]==1 && trd[0x8E2]==1 && trd[0x8E4]==1 && trd[0x8E5]==0xEF && trd[0x8E6]==9);
    for(unsigned i=0;i<256;++i) assert(trd[4096+i]==0xA5);
    source[23]^=1;assert(spectrum_scl_unpack(&src,&io,SPECTRUM_EXTERNAL_BYTES)==SPECTRUM_FORMAT);
    source[8]=129;assert(spectrum_scl_unpack(&src,&io,SPECTRUM_EXTERNAL_BYTES)==SPECTRUM_FORMAT);
    source[8]=128;assert(spectrum_scl_unpack(&src,&io,SPECTRUM_EXTERNAL_BYTES)==SPECTRUM_FORMAT);
    puts("SCL SUM32 validation, directory/geometry and sector expansion: PASS");
}
static _Atomic bool finished;
static void* consumer(void* unused) {
    (void)unused;
    while(!atomic_load_explicit(&finished,memory_order_acquire) ||
          atomic_load(&s.sound.read)!=atomic_load(&s.sound.write)) {
        spectrum_sound_render(&s);sched_yield();
    }
    return NULL;
}
static void yielding(void* unused) { (void)unused;sched_yield(); }
static void concurrent_audio(void) {
    spectrum_init(&s,ram,rom);spectrum_sound_begin(&s,yielding,NULL);
    pthread_t thread;atomic_init(&finished,false);assert(!pthread_create(&thread,NULL,consumer,NULL));
    for(unsigned i=0;i<100000;++i) {
        s.cpu.cyc+=140;spectrum_sound_write(&s,i&1,8,i&15);spectrum_sound_publish(&s);
    }
    atomic_store_explicit(&finished,true,memory_order_release);assert(!pthread_join(thread,NULL));
    spectrum_sound_end(&s);assert(s.ay.reg[8]==14 && s.ay2.reg[8]==15);
    assert(atomic_load(&s.sound.read)==atomic_load(&s.sound.write));
    s.cpu.cyc=UINT32_MAX-400;spectrum_sound_begin(&s,NULL,NULL);
    for(unsigned i=0;i<8;++i) { s.cpu.cyc+=140;spectrum_sound_publish(&s);spectrum_sound_render(&s); }
    assert(s.sound.time==(uint32_t)s.cpu.cyc);spectrum_sound_end(&s);
    puts("Two-thread audio SPSC, 100000 events, backpressure, pause and uint32 time wrap: PASS");
}
static void video_pages(void) {
    spectrum_memory m;uint8_t pages[2048];
    spectrum_memory_io io={backing,rd,wr,clear};
    spectrum_init(&s,ram,rom);
    assert(spectrum_memory_init_mapped(&m,ram,pages,ram+32768,backing+SPECTRUM_ROM_BASE,backing+SPECTRUM_ROM_BASE+16384,io));
    spectrum_attach_memory(&s,&m);out(0x7FFD,8|16);s.frames=16;
    uint8_t* source=backing+7*16384;
    for(unsigned i=0;i<6912;++i) source[i]=(uint8_t)((i*37)^(i>>3)^(i>>8));
    uint8_t* flat_ram=calloc(1,49152);assert(flat_ram);spectrum flat;
    spectrum_init(&flat,flat_ram,rom);memcpy(flat_ram,source,6912);flat.frames=16;
    uint8_t actual[7680],expected[7680];
    spectrum_video8(&flat,expected,expected+6144);
    read_requests=read_bytes=0;spectrum_video8(&s,actual,actual+6144);
    assert(!memcmp(actual,expected,sizeof(actual)) && read_requests==7 && read_bytes==6912);
    // A full screen in the cache, including modified bytes, needs no I/O.
    out(0x7FFD,7|8|16);
    for(unsigned p=0;p<7;++p) (void)s.cpu.read_byte(&s,(uint16_t)(0xC000+p*1024));
    s.cpu.write_byte(&s,0xC123,0xAA);flat_ram[0x123]=0xAA;
    spectrum_video8(&flat,expected,expected+6144);
    read_requests=read_bytes=0;spectrum_video8(&s,actual,actual+6144);
    assert(!memcmp(actual,expected,sizeof(actual)) && !read_requests && !read_bytes);
    free(flat_ram);spectrum_init(&s,ram,rom);
    puts("All 192 banked screen rows match flat ULA: seven page reads instead of 25; dirty cached screen needs zero I/O: PASS");
}
int main(void) { devices();mapping();pentagon_1024();full_window();retained_pages();video_pages();scl();concurrent_audio();return 0; }
