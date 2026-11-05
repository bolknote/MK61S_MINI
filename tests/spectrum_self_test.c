#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t ram[49152],rom[16384];
static spectrum machine;
typedef struct { uint8_t* bytes;uint32_t size,fail_at; } image;
static bool read_image(void* raw,uint32_t offset,uint8_t* out,uint32_t length) {
    const image* i=raw;
    if(offset>i->size || length>i->size-offset || offset>=i->fail_at) return false;
    memcpy(out,i->bytes+offset,length);return true;
}
static spectrum_source source(image* i) { spectrum_source s={i,i->size,read_image};return s; }
static void put_word(uint8_t* p,unsigned value) { p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8); }
static void frame(unsigned n) { spectrum_run(&machine,n*SPECTRUM_FRAME_TSTATES); }
static void tap(unsigned code) {
    uint8_t keys[32]={0};keys[code/8]|=1U<<(code&7);spectrum_keyboard(&machine,keys);frame(4);
    memset(keys,0,sizeof(keys));spectrum_keyboard(&machine,keys);frame(4);
}
static void keyboard_and_ports(void) {
    spectrum_init(&machine,ram,rom);uint8_t keys[32]={0};
    keys['p'/8]|=1U<<('p'&7);keys['a'/8]|=1U<<('a'&7);
    keys[0xA5/8]|=1U<<(0xA5&7);keys[0xB7/8]|=1U<<(0xB7&7);keys[0x85/8]|=1U<<(0x85&7);
    spectrum_keyboard(&machine,keys);
    assert(spectrum_port_in(&machine,0xDFFE)==0xBE);
    assert(spectrum_port_in(&machine,0xFDFE)==0xBE);
    assert(spectrum_port_in(&machine,0xFEFE)==0xBE);
    assert(spectrum_port_in(&machine,0xFFFE)==0xBF);
    assert(spectrum_port_in(&machine,0x001F)==17 && spectrum_port_in(&machine,0xFF1F)==17);
    assert(spectrum_port_in(&machine,0xFFFF)==255);
    // Immediate and register I/O must preserve address bits A8..A15.
    const uint8_t program[]={0x3E,0xDF,0xDB,0xFE,0x32,0,0x90,
        0x01,0xFE,0xFD,0xED,0x78,0x32,1,0x90,0x3E,6,0xD3,0xFE,0x76};
    memcpy(ram+0x4000,program,sizeof(program));machine.cpu.pc=0x8000;
    spectrum_run(&machine,200);
    assert(ram[0x5000]==0xBE && ram[0x5001]==0xBE && machine.border==6);
    assert(machine.cpu.halted);
    const uint8_t original=rom[0];machine.cpu.write_byte(&machine,0,0xAA);assert(rom[0]==original);
    // Simultaneous keys in different rows and release, without autorepeat.
    memset(keys,0,sizeof(keys));keys[','/8]|=1U<<(','&7);spectrum_keyboard(&machine,keys);
    assert(!(machine.keys[7]&2) && !(machine.keys[7]&8));
    memset(keys,0,sizeof(keys));spectrum_keyboard(&machine,keys);
    for(unsigned i=0;i<8;++i) assert(machine.keys[i]==31);
    assert(!machine.joystick);
}
static void video(void) {
    spectrum_reset(&machine);uint8_t bitmap[6144],tiles[768];
    ram[0]=0x81;ram[256]=0x42;ram[32]=0x24;ram[2048]=0x18;ram[4096]=0xFF;
    ram[6144]=0xD1; // FLASH, BRIGHT, blue ink, red paper.
    spectrum_video(&machine,bitmap,tiles);
    assert(bitmap[0]==0x81 && bitmap[32]==0x42 && bitmap[8*32]==0x24);
    assert(bitmap[64*32]==0x18 && bitmap[128*32]==0xFF && tiles[0]==0xA9);
    machine.frames=16;spectrum_video(&machine,bitmap,tiles);assert(tiles[0]==0x9A);
    assert(spectrum_color(0)==0 && spectrum_color(8)==0);
    assert(spectrum_color(9)==0x001F && spectrum_color(10)==0xF800);
    assert(spectrum_color(12)==0x07E0 && spectrum_color(15)==0xFFFF);
}
static void page_window_boundaries(void) {
    spectrum_init(&machine,ram,rom);
    const uint8_t program[]={0x3A,0x00,0x40,0x32,0x01,0x40,0x76};
    memcpy(rom,program,sizeof(program));ram[0]=0xA5;ram[32768]=0x3C;ram[32769]=0x69;
    // A callback-based middle window must not alias the upper page table.
    machine.cpu.read_map[1]=machine.cpu.write_map[1]=NULL;
    machine.cpu.read_pages[16]=machine.cpu.write_pages[16]=ram+32768;
    spectrum_run(&machine,50);
    assert(machine.cpu.a==0xA5 && ram[1]==0xA5 && ram[32769]==0x69);
}
static void snapshots(void) {
    uint8_t* bytes=calloc(1,70000);assert(bytes);
    image i={bytes,49179,UINT32_MAX};spectrum_source s=source(&i);
    put_word(bytes+23,0xFFFF);bytes[25]=1;
    assert(spectrum_load_sna(&machine,&s)==SPECTRUM_FORMAT);
    put_word(bytes+23,0xFFFC);bytes[0]=0x93;bytes[19]=4;bytes[20]=0xAF;
    bytes[21]=0xC5;bytes[22]=0x42;bytes[26]=3;
    put_word(bytes+27+0xBFFC,0x8123);bytes[27+123]=0x5A;
    assert(spectrum_load_sna(&machine,&s)==SPECTRUM_OK);
    assert(machine.cpu.pc==0x8123 && machine.cpu.sp==0xFFFE && machine.cpu.a==0x42);
    assert(machine.cpu.i==0x93 && machine.cpu.r==0xAF && machine.cpu.iff1 && machine.cpu.iff2);
    assert(machine.cpu.sf && machine.cpu.zf && machine.cpu.pf && machine.cpu.cf && machine.border==3);
    assert(ram[123]==0x5A);
    s.size=49180;assert(spectrum_load_sna(&machine,&s)==SPECTRUM_UNSUPPORTED);
    // Z80 v1, uncompressed, all register pairs and flags independent of SNA.
    memset(bytes,0,70000);i.size=30+49152;s=source(&i);
    bytes[0]=0xA5;bytes[1]=0x53;put_word(bytes+6,0x9234);put_word(bytes+8,0xFFFF);
    bytes[10]=0x38;bytes[11]=0x2A;bytes[12]=255;bytes[27]=bytes[28]=1;bytes[29]=2;
    put_word(bytes+23,0x5C3A);put_word(bytes+25,0x1234);memset(bytes+30,0x5B,49152);
    assert(spectrum_load_z80(&machine,&s)==SPECTRUM_OK);
    assert(machine.cpu.pc==0x9234 && machine.cpu.r==0xAA && machine.cpu.sp==0xFFFF);
    assert(machine.cpu.iy==0x5C3A && machine.cpu.ix==0x1234 && machine.cpu.interrupt_mode==2);
    assert(machine.cpu.zf && machine.cpu.hf && machine.cpu.nf && machine.cpu.cf && !machine.cpu.sf);
    for(unsigned j=0;j<49152;++j) assert(ram[j]==0x5B);
    // Z80 v1 RLE plus its optional terminator. Single ED remains literal.
    bytes[12]=32;unsigned at=30,left=49152;
    while(left) { const unsigned n=left<255?left:255;bytes[at++]=0xED;bytes[at++]=0xED;bytes[at++]=(uint8_t)n;bytes[at++]=0xED;left-=n; }
    memcpy(bytes+at,"\0\xED\xED\0",4);i.size=at+4;s=source(&i);
    assert(spectrum_load_z80(&machine,&s)==SPECTRUM_OK);
    for(unsigned j=0;j<49152;++j) assert(ram[j]==0xED);
    bytes[32]=0;assert(spectrum_load_z80(&machine,&s)==SPECTRUM_FORMAT);bytes[32]=255;
    s.size--;assert(spectrum_load_z80(&machine,&s)==SPECTRUM_FORMAT);
    // Z80 v3 banks in non-address order, including a nonzero 7FFD value
    // which is irrelevant to a 48K machine. IF1 ROM paging is rejected.
    memset(bytes,0,70000);put_word(bytes+30,54);put_word(bytes+32,0x8123);bytes[35]=0x30;
    at=86;const unsigned pages[]={5,8,4};
    for(unsigned p=0;p<3;++p) {
        put_word(bytes+at,0xFFFF);bytes[at+2]=(uint8_t)pages[p];at+=3;
        memset(bytes+at,(int)pages[p],16384);at+=16384;
    }
    i.size=at;s=source(&i);assert(spectrum_load_z80(&machine,&s)==SPECTRUM_OK);
    assert(ram[0]==8 && ram[16384]==4 && ram[32768]==5 && machine.cpu.pc==0x8123);
    bytes[36]=255;assert(spectrum_load_z80(&machine,&s)==SPECTRUM_UNSUPPORTED);bytes[36]=0;
    bytes[34]=4;assert(spectrum_load_z80(&machine,&s)==SPECTRUM_UNSUPPORTED);bytes[34]=0;
    bytes[86+3+16384+2]=5;assert(spectrum_load_z80(&machine,&s)==SPECTRUM_FORMAT);
    assert(machine.cpu.pc==0x8123 && ram[0]==8); // Rejected before commit.
    // Random malformed snapshots must never overrun RAM or loop on RLE=0.
    uint32_t random=0x12345678;
    for(unsigned test=0;test<2000;++test) {
        for(unsigned j=0;j<600;++j) { random=random*1664525U+1013904223U;bytes[j]=(uint8_t)(random>>24); }
        i.size=30+(random%570);s=source(&i);(void)spectrum_load_z80(&machine,&s);
    }
    free(bytes);
}
static void basic(const char* path) {
    FILE* f=fopen(path,"rb");assert(f);assert(fread(rom,1,sizeof(rom),f)==sizeof(rom));fclose(f);
    spectrum_init(&machine,ram,rom);frame(200);
    assert(machine.cpu.iy==0x5C3A && machine.cpu.interrupt_mode==1 && machine.cpu.iff1);
    assert(ram[0x1CB4]==255 && ram[0x1CB5]==255); // P_RAMT = 65535.
    printf("ROM ready: PC=%04X IY=%04X ERR_NR=%02X\n",machine.cpu.pc,machine.cpu.iy,ram[0x1C3A]);
    tap('p');tap('1');tap('+');tap('2');tap(13);frame(10);
    // PRINT 1+2 must draw the ROM glyph '3' at the first display cell.
    for(unsigned y=0;y<8;++y) assert(ram[y*256]==rom[0x3D00+('3'-32)*8+y]);
    assert(machine.frames>=200 && machine.frame_tstates<SPECTRUM_FRAME_TSTATES);
    puts("Spectrum ROM boot, keyboard and PRINT 1+2: PASS");
}
static uint8_t* backing;
static bool memory_read(void* context,uint32_t at,uint8_t* out,uint32_t n) {
    (void)context;if(at>SPECTRUM_EXTERNAL_BYTES || n>SPECTRUM_EXTERNAL_BYTES-at) return false;
    memcpy(out,backing+at,n);return true;
}
static bool memory_write(void* context,uint32_t at,const uint8_t* in,uint32_t n) {
    (void)context;if(at>SPECTRUM_EXTERNAL_BYTES || n>SPECTRUM_EXTERNAL_BYTES-at) return false;
    memcpy(backing+at,in,n);return true;
}
static bool memory_clear(void* context,uint32_t at,uint32_t n) {
    (void)context;if(at>SPECTRUM_EXTERNAL_BYTES || n>SPECTRUM_EXTERNAL_BYTES-at) return false;
    memset(backing+at,0,n);return true;
}
static void ay_reg(unsigned reg,unsigned value) {
    machine.cpu.port_out(&machine.cpu,0xFFFD,(uint8_t)reg);
    machine.cpu.port_out(&machine.cpu,0xBFFD,(uint8_t)value);
}
static void pentagon(const char* rom_path) {
    backing=calloc(1,SPECTRUM_EXTERNAL_BYTES);assert(backing);
    char path[1024];assert(strlen(rom_path)<sizeof(path)-16);strcpy(path,rom_path);
    char* leaf=strrchr(path,'/');assert(leaf);++leaf;
    for(unsigned i=0;i<2;++i) {
        strcpy(leaf,i?"128-1.rom":"128-0.rom");FILE* f=fopen(path,"rb");assert(f);
        assert(fread(backing+SPECTRUM_ROM_BASE+i*16384,1,16384,f)==16384);fclose(f);
    }
    spectrum_memory memory;spectrum_memory_io io={NULL,memory_read,memory_write,memory_clear};
    spectrum_init(&machine,ram,rom);assert(spectrum_memory_init(&memory,ram,rom,io));
    spectrum_attach_memory(&machine,&memory);spectrum_run(&machine,200*71680U);
    assert(machine.cpu.iy==0x5C3A && machine.cpu.interrupt_mode==1);
    assert(spectrum_frame_cycles(&machine)==71680);
    for(unsigned bank=0;bank<32;++bank) {
        const uint8_t paging=(uint8_t)((bank&7)|((bank&24)<<3)|16);
        machine.cpu.port_out(&machine.cpu,0x7FFD,paging);
        machine.cpu.write_byte(&machine,0xC100,(uint8_t)(bank^0xA5));
        if(bank==2) assert(machine.cpu.read_byte(&machine,0x8100)==(bank^0xA5));
        if(bank==5) assert(machine.cpu.read_byte(&machine,0x4100)==(bank^0xA5));
    }
    for(unsigned bank=0;bank<32;++bank) {
        const uint8_t paging=(uint8_t)((bank&7)|((bank&24)<<3)|16);
        machine.cpu.port_out(&machine.cpu,0x7FFD,paging);
        assert(machine.cpu.read_byte(&machine,0xC100)==(bank^0xA5));
    }
    assert(memory.loads>32 && memory.writebacks>=29);
    uint8_t pixels[6144],tiles[768],value=0x80;
    assert(spectrum_bank_write(&memory,7,0,&value,1));value=0x47;
    assert(spectrum_bank_write(&memory,7,6144,&value,1));
    machine.cpu.port_out(&machine.cpu,0x7FFD,0x18);spectrum_video(&machine,pixels,tiles);
    assert(pixels[0]==0x80 && tiles[0]==0x8F); // Shadow screen is bank 7, even when unmapped.
    machine.cpu.port_out(&machine.cpu,0x7FFD,0x33);machine.cpu.port_out(&machine.cpu,0x7FFD,0x14);
    assert(memory.paging==0x33 && machine.cpu.read_byte(&machine,0xC100)==(3^0xA5));
    // 128K SNA and Z80 cross 64-KiB file offsets and populate physical banks.
    uint8_t* data=calloc(1,150000);assert(data);put_word(data+23,0xFFFF);data[25]=1;
    unsigned at=27;const unsigned banks[]={5,2,3,0,1,4,6,7};
    for(unsigned i=0;i<8;++i) {
        if(i==3) { put_word(data+at,0x8123);data[at+2]=0x13;at+=4; }
        memset(data+at,(int)banks[i],16384);at+=16384;
    }
    image image_data={data,at,UINT32_MAX};spectrum_source source_data=source(&image_data);
    assert(at==131103 && spectrum_load_sna(&machine,&source_data)==SPECTRUM_OK);
    assert(machine.cpu.pc==0x8123 && machine.cpu.sp==0xFFFF && memory.paging==0x13);
    for(unsigned bank=0;bank<8;++bank) { assert(spectrum_bank_read(&memory,bank,100,&value,1));assert(value==bank); }
    data[49182]=1;assert(spectrum_load_sna(&machine,&source_data)==SPECTRUM_UNSUPPORTED);
    memset(data,0,150000);put_word(data+30,54);put_word(data+32,0x9234);data[34]=9;data[35]=0x17;
    data[38]=8;data[39]=109;data[46]=0x3E;data[47]=15;
    at=86;
    for(unsigned bank=0;bank<8;++bank) {
        put_word(data+at,65535);data[at+2]=(uint8_t)(3+bank);at+=3;
        memset(data+at,(int)(0x10+bank),16384);at+=16384;
    }
    image_data.size=at;source_data=source(&image_data);
    assert(spectrum_load_z80(&machine,&source_data)==SPECTRUM_OK);
    assert(machine.cpu.pc==0x9234 && memory.paging==0x17 && machine.cpu.read_byte(&machine,0xC000)==0x17);
    assert(PSG_readReg(&machine.ay,0)==109 && PSG_readReg(&machine.ay,8)==15 && machine.ay.adr==8);
    assert(spectrum_bank_read(&memory,31,100,&value,1) && value==0);
    free(data);machine.memory=NULL;free(backing);backing=NULL;
    puts("Pentagon ROM boot, all 32 banks, aliases, lock, shadow screen and 128K snapshots: PASS");
}
static int16_t samples[26000];static unsigned sample_count;
static void collect(void* context,int16_t value) { (void)context;assert(sample_count<26000);samples[sample_count++]=value; }
static void sound(void) {
    for(unsigned channel=0;channel<3;++channel) {
        spectrum_init(&machine,ram,rom);machine.cpu.halted=true;
        spectrum_set_audio(&machine,25000,collect,NULL);sample_count=0;
        ay_reg(channel*2,109);ay_reg(7,0x3F^(1U<<channel));ay_reg(8+channel,15);
        spectrum_run(&machine,3500000);
        unsigned crossings=0;
        for(unsigned i=1;i<sample_count;++i) if((samples[i]>0)!=(samples[i-1]>0)) ++crossings;
        assert(sample_count>=25000 && sample_count<=25001 && crossings>1980 && crossings<2025);
    }
    // Noise generator, envelope shapes, port readback and the beeper mixer.
    spectrum_init(&machine,ram,rom);spectrum_set_audio(&machine,25000,collect,NULL);sample_count=0;
    ay_reg(6,3);ay_reg(7,0x37);ay_reg(8,15);spectrum_run(&machine,350000);
    unsigned changes=0;for(unsigned i=1;i<sample_count;++i) if(samples[i]!=samples[i-1]) ++changes;
    assert(changes>500);
    for(unsigned shape=0;shape<16;++shape) {
        spectrum_reset(&machine);ay_reg(7,0x3F);ay_reg(8,16);ay_reg(11,8);ay_reg(13,shape);
        for(unsigned n=0;n<2000;++n) (void)PSG_calc(&machine.ay);
        if(shape<8 || shape==9 || shape==15) assert(machine.ay.env_pause && machine.ay.env_ptr==0);
        else if(shape==11 || shape==13) assert(machine.ay.env_pause && machine.ay.env_ptr==31);
        else assert(!machine.ay.env_pause);
    }
    ay_reg(1,255);assert(spectrum_port_in(&machine,0xFFFD)==15);
    ay_reg(7,0x40);ay_reg(14,0xA5);assert(spectrum_port_in(&machine,0xFFFD)==0xA5);
    ay_reg(7,0);machine.cpu.port_out(&machine.cpu,0xFFFD,14);assert(spectrum_port_in(&machine,0xFFFD)==255);
    spectrum_reset(&machine);machine.cpu.halted=true;sample_count=0;machine.cpu.port_out(&machine.cpu,0xFE,16);
    spectrum_run(&machine,35000);assert(sample_count>=250 && samples[0]>0);
    puts("AY-3-8912 A/B/C pitch, noise, all 16 envelopes, registers and beeper: PASS");
}
static void halt_timing(void) {
    uint8_t* left=calloc(1,49152),*right=calloc(1,49152);assert(left && right);
    const unsigned phases[]={0,4,28,31,32,35,69860,69887};
    memset(rom,0,sizeof(rom));rom[0x38]=rom[0x66]=0xC9;
    for(unsigned model=0;model<2;++model) for(unsigned flags=0;flags<8;++flags)
      for(unsigned phase=0;phase<sizeof(phases)/sizeof(*phases);++phase) {
        spectrum a,b;memset(left,0,49152);memset(right,0,49152);
        left[0x4001]=right[0x4001]=0xC3;left[0x4003]=right[0x4003]=0x80;
        left[0x4000]=right[0x4000]=0x76;
        spectrum_init(&a,left,rom);spectrum_init(&b,right,rom);a.pentagon=b.pentagon=model;
        a.frame_tstates=b.frame_tstates=phases[phase];
        a.cpu.pc=b.cpu.pc=0x8001;a.cpu.sp=b.cpu.sp=0xFFF0;a.cpu.r=b.cpu.r=0xFE;
        a.cpu.halted=b.cpu.halted=true;a.cpu.interrupt_mode=b.cpu.interrupt_mode=1;
        a.cpu.iff1=b.cpu.iff1=(flags&1)!=0;a.cpu.iff_delay=b.cpu.iff_delay=(flags>>1)&1;
        a.cpu.nmi_pending=b.cpu.nmi_pending=(flags&4)!=0;
        const uint32_t frame=spectrum_frame_cycles(&a),limit=3*frame+123;
        uint32_t elapsed=0;
        while(elapsed<limit) {
            b.cpu.int_pending=b.frame_tstates<32;b.cpu.int_data=255;
            const unsigned long before=b.cpu.cyc;z80_step(&b.cpu);
            const uint32_t cycles=(uint32_t)(b.cpu.cyc-before);elapsed+=cycles;b.frame_tstates+=cycles;
            if(b.frame_tstates>=frame) { b.frame_tstates-=frame;++b.frames; }
        }
        assert(spectrum_run(&a,limit)==elapsed);
        assert(a.cpu.cyc==b.cpu.cyc && a.cpu.r==b.cpu.r && a.cpu.pc==b.cpu.pc && a.cpu.sp==b.cpu.sp);
        assert(a.cpu.halted==b.cpu.halted && a.cpu.iff1==b.cpu.iff1 && a.cpu.iff2==b.cpu.iff2);
        assert(a.frame_tstates==b.frame_tstates && a.frames==b.frames && !memcmp(left,right,49152));
      }
    free(left);free(right);puts("HALT batching matches single-step INT/NMI/EI, R wrap and both frame timings: PASS");
}
int main(int argc,char** argv) {
    assert(argc==2);keyboard_and_ports();video();page_window_boundaries();snapshots();basic(argv[1]);pentagon(argv[1]);sound();halt_timing();
    puts("Spectrum CPU, ULA, SNA/Z80 and malformed input: PASS");return 0;
}
