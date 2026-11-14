#include "spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static spectrum s;
static spectrum_memory memory;
static uint8_t fixed[32768],pages[2048],window[16384],roms[2][16384],esx[8192],dcache[2048];
static uint8_t external[SPECTRUM_EXTERNAL_BYTES],*disk;
static uint32_t disk_size;
static unsigned long long read_bytes,write_bytes,reads,writes;
static bool rd(void* p,uint32_t at,uint8_t* out,uint32_t n) {
    assert((uint64_t)at+n<=(p==external?sizeof(external):disk_size));
    if(p==external) { read_bytes+=n;++reads; }
    memcpy(out,(uint8_t*)p+at,n);return true;
}
static bool wr(void* p,uint32_t at,const uint8_t* in,uint32_t n) {
    assert(p==external && (uint64_t)at+n<=sizeof(external));
    write_bytes+=n;++writes;memcpy((uint8_t*)p+at,in,n);return true;
}
static bool zero(void* p,uint32_t at,uint32_t n) {
    assert(p==external && (uint64_t)at+n<=sizeof(external));
    memset((uint8_t*)p+at,0,n);return true;
}
static void load(const char* path,void* out,unsigned n) {
    FILE* f=fopen(path,"rb");assert(f);assert(fread(out,1,n,f)==n);fclose(f);
}
void host_init(const char* assets,const char* image) {
    char path[1024];free(disk);disk=NULL;memset(&s,0,sizeof(s));memset(&memory,0,sizeof(memory));
    load("third_party/spectrum-rom/128-0.rom",roms[0],16384);
    load("third_party/spectrum-rom/128-1.rom",roms[1],16384);
    snprintf(path,sizeof(path),"%s/esxmmc.rom",assets);load(path,esx,sizeof(esx));
    FILE* f=fopen(image,"rb");assert(f);assert(!fseek(f,0,SEEK_END));disk_size=(uint32_t)ftell(f);rewind(f);
    disk=malloc(disk_size);assert(disk);assert(fread(disk,1,disk_size,f)==disk_size);fclose(f);
    s.ram=fixed;s.rom=roms[0];s.extensions=15;
    spectrum_memory_io io={external,rd,wr,zero};
    assert(spectrum_memory_init_mapped(&memory,fixed,pages,window,roms[0],roms[1],io));
    spectrum_attach_memory(&s,&memory);s.disk.xip_rom[SPECTRUM_DISK_DIVMMC]=esx;
    s.disk.spi.io=(spectrum_disk_io){disk,disk_size,rd,NULL,true,0,0};
    assert(spectrum_disk_mode(&s,SPECTRUM_DISK_DIVMMC));spectrum_reset(&s);
    assert(spectrum_disk_cache_begin(&s,dcache));
}
void host_frames(unsigned n) {
    while(n--) { spectrum_run(&s,spectrum_frame_cycles(&s));assert(!memory.fault); }
}
void host_keys(unsigned key,int press) {
    static uint8_t keys[32];if(!key)memset(keys,0,sizeof(keys));
    else if(press)keys[key/8]|=1U<<(key&7);else keys[key/8]&=~(1U<<(key&7));
    spectrum_keyboard(&s,keys);
}
void host_tap(unsigned key) { host_keys(0,0);host_keys(key,1);host_frames(4);host_keys(0,0);host_frames(4); }
void host_status(char* out,unsigned n) {
    snprintf(out,n,"PC=%04X SP=%04X frames=%u phase=%u bank=%02X fault=%u disk=%u mapped=%u AY=%u/%u/%u read=%llu/%llu write=%llu/%llu",
       s.cpu.pc,s.cpu.sp,s.frames,s.frame_tstates,memory.paging,memory.fault,s.disk.spi.reads,s.disk.mapped,
       s.ay.reg[8],s.ay.reg[9],s.ay.reg[10],read_bytes,reads,write_bytes,writes);
}
void host_video(uint8_t* out) {
    spectrum_video8(&s,out,out+6144);
    for(unsigned i=0;i<64;++i) { unsigned color=spectrum_palette(&s,i);out[7680+2*i]=(uint8_t)color;out[7681+2*i]=(uint8_t)(color>>8); }
}
void host_mem(uint16_t at,uint8_t* out,unsigned n) {
    for(unsigned i=0;i<n;++i)out[i]=s.cpu.read_byte(&s,(uint16_t)(at+i));
}
void host_poke(uint16_t at,const uint8_t* bytes,unsigned n) {
    for(unsigned i=0;i<n;++i)s.cpu.write_byte(&s,(uint16_t)(at+i),bytes[i]);
}
void host_nmi(void) { z80_gen_nmi(&s.cpu); }
void host_registers(uint8_t* h) {
    z80* z=&s.cpu;memset(h,0,55);
    h[0]=z->a;h[1]=z->f;h[2]=z->c;h[3]=z->b;h[4]=z->l;h[5]=z->h;
    h[8]=(uint8_t)z->sp;h[9]=(uint8_t)(z->sp>>8);h[10]=z->i;h[11]=z->r&127;
    h[12]=(z->r>>7)|(s.border<<1);h[13]=z->e;h[14]=z->d;h[15]=z->c_;h[16]=z->b_;
    h[17]=z->e_;h[18]=z->d_;h[19]=z->l_;h[20]=z->h_;h[21]=z->a_;h[22]=z->f_;
    h[23]=(uint8_t)z->iy;h[24]=(uint8_t)(z->iy>>8);h[25]=(uint8_t)z->ix;h[26]=(uint8_t)(z->ix>>8);
    h[27]=z->iff1;h[28]=z->iff2;h[29]=z->interrupt_mode;h[30]=23;
    uint16_t pc=z->pc;if(z->halted)--pc;
    h[32]=(uint8_t)pc;h[33]=(uint8_t)(pc>>8);h[34]=3;h[35]=memory.paging;
    h[38]=s.ay.adr;memcpy(h+39,s.ay.reg,16);
}
void host_bank(unsigned bank,uint8_t* out) { assert(spectrum_bank_read(&memory,bank,0,out,16384)); }
void host_palette_state(uint8_t* out) { out[0]=s.ulaplus_mode;memcpy(out+1,s.ulaplus_palette,64); }
static bool src_rd(void* p,uint32_t at,uint8_t* out,uint32_t n) { memcpy(out,(uint8_t*)p+at,n);return true; }
int host_load_snapshot(uint8_t* bytes,unsigned n,const uint8_t* palette) {
    spectrum_source source={bytes,n,src_rd};
    unsigned error=spectrum_load_z80(&s,&source);
    if(!error && palette) { s.ulaplus_mode=palette[0];memcpy(s.ulaplus_palette,palette+1,64); }
    return (int)error;
}
void host_disconnect(void) { assert(spectrum_disk_cache_end(&s));assert(spectrum_disk_mode(&s,0)); }
