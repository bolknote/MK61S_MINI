#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Reference executor uses individual Z80 instructions and no batching. */
static uint32_t reference_run(spectrum* s,uint32_t limit) {
    uint32_t done=0;const uint32_t frame=spectrum_frame_cycles(s);
    s->cpu.ldir_until=0;s->cpu.int_pending=s->frame_tstates<32;s->cpu.int_data=255;
    while(done<limit) {
        const unsigned long before=s->cpu.cyc;const uint32_t old=s->frame_tstates;
        z80_step(&s->cpu);const uint32_t cycles=(uint32_t)(s->cpu.cyc-before);
        done+=cycles;s->frame_tstates+=cycles;
        if(s->frame_tstates>=frame) { s->frame_tstates-=frame;++s->frames; }
        if(s->frame_tstates<32) s->cpu.int_pending=true;
        else if(old<32) s->cpu.int_pending=false;
    }
    return done;
}
static uint8_t left[49152],right[49152],rom_l[16384],rom_r[16384];
static uint32_t random_state=0x49133711;
static unsigned random_value(void) { random_state=random_state*1664525U+1013904223U;return random_state; }
static void normalize(z80* z) {
    z->read_byte=NULL;z->write_byte=NULL;z->port_in=NULL;z->port_out=NULL;z->userdata=NULL;z->m1=NULL;
    memset(z->read_map,0,sizeof(z->read_map));memset(z->write_map,0,sizeof(z->write_map));
    memset(z->read_pages,0,sizeof(z->read_pages));memset(z->write_pages,0,sizeof(z->write_pages));
}
static void equal(const spectrum* a,const spectrum* b,unsigned test) {
    z80 x=a->cpu,y=b->cpu;normalize(&x);normalize(&y);
    if(memcmp(&x,&y,sizeof(x)) || a->frames!=b->frames || a->frame_tstates!=b->frame_tstates ||
       memcmp(left,right,sizeof(left)) || memcmp(rom_l,rom_r,sizeof(rom_l))) {
        fprintf(stderr,"Mismatch test=%u phase=%u/%u cycles=%lu/%lu PC=%04X/%04X HL=%04X/%04X DE=%04X/%04X BC=%04X/%04X F=%02X/%02X R=%02X/%02X WZ=%04X/%04X\n",
            test,a->frame_tstates,b->frame_tstates,a->cpu.cyc,b->cpu.cyc,a->cpu.pc,b->cpu.pc,
            a->cpu.hl,b->cpu.hl,a->cpu.de,b->cpu.de,a->cpu.bc,b->cpu.bc,a->cpu.f,b->cpu.f,a->cpu.r,b->cpu.r,a->cpu.mem_ptr,b->cpu.mem_ptr);
        abort();
    }
}
int main(void) {
    static const unsigned counts[]={0,1,2,3,4,5,16,127,255,256,1024,16384,65535};
    static const unsigned phases[]={0,4,11,28,31,32,35,69800,69867,69887};
    static const unsigned slices[]={1,20,21,22,83,84,85,2048,4096,10000};
    static const unsigned sources[]={0,0x1000,0x4000,0x7FFC,0x8000,0xBFFC,0xC000,0xFFFC};
    static const unsigned destinations[]={0x4000,0x4001,0x7FFE,0x8000,0x8001,0xBFFC,0xC000,0xFFFC};
    for(unsigned test=0;test<6000;++test) {
        for(unsigned i=0;i<sizeof(left);++i) left[i]=(uint8_t)(random_value()>>24);
        memset(rom_l,0,sizeof(rom_l));rom_l[0x38]=rom_l[0x66]=0xC9;
        left[0x4000]=0xED;left[0x4001]=0xB0;left[0x4002]=0x76;
        memcpy(right,left,sizeof(left));memcpy(rom_r,rom_l,sizeof(rom_l));
        spectrum a,b;spectrum_init(&a,left,rom_l);spectrum_init(&b,right,rom_r);
        // spectrum_init clears guest RAM; seed it after reset.
        for(unsigned i=0;i<sizeof(left);++i) left[i]=(uint8_t)(random_value()>>24);
        left[0x4000]=0xED;left[0x4001]=0xB0;left[0x4002]=0x76;
        memcpy(right,left,sizeof(left));
        a.pentagon=b.pentagon=(test&1)!=0;
        const unsigned frame=spectrum_frame_cycles(&a),phase=phases[test%10];
        a.frame_tstates=b.frame_tstates=phase>=69800?frame-69888+phase:phase;
        a.cpu.pc=b.cpu.pc=0x8000;a.cpu.sp=b.cpu.sp=0xFF00;
        if(test%5==0) a.cpu.cyc=b.cpu.cyc=UINT32_MAX-(test*17U%2048);
        a.cpu.hl=b.cpu.hl=(uint16_t)sources[(test/10)%8];
        a.cpu.de=b.cpu.de=(uint16_t)destinations[(test/80)%8];
        if(test%7==0) a.cpu.de=b.cpu.de=(uint16_t)(a.cpu.hl+(test%5)); // Forward overlap and identical pointers.
        a.cpu.bc=b.cpu.bc=(uint16_t)counts[(test/640)%13];
        if(test%11==0) a.cpu.bc=b.cpu.bc=(uint16_t)counts[random_value()%13];
        a.cpu.f=b.cpu.f=(uint8_t)random_value();a.cpu.a=b.cpu.a=(uint8_t)random_value();
        a.cpu.r=b.cpu.r=(uint8_t)random_value();a.cpu.mem_ptr=b.cpu.mem_ptr=(uint16_t)random_value();
        a.cpu.iff1=b.cpu.iff1=(test&2)!=0;a.cpu.iff2=b.cpu.iff2=(test&4)!=0;
        a.cpu.iff_delay=b.cpu.iff_delay=(test%13==0);
        a.cpu.nmi_pending=b.cpu.nmi_pending=(test%17==0);a.cpu.interrupt_mode=b.cpu.interrupt_mode=(test/13)%3;
        a.cpu.i=b.cpu.i=0xC0;
        // Exercise 1K views and physical aliases as well as direct 16K windows.
        if(test%3==0) {
            a.cpu.read_map[3]=b.cpu.read_map[3]=NULL;
            for(unsigned p=0;p<16;++p) {
                a.cpu.read_pages[16+p]=left+32768+p*1024;b.cpu.read_pages[16+p]=right+32768+p*1024;
                a.cpu.write_pages[16+p]=left+32768+p*1024;b.cpu.write_pages[16+p]=right+32768+p*1024;
            }
            a.cpu.write_map[3]=b.cpu.write_map[3]=NULL;
        } else if(test%3==1) {
            a.cpu.read_map[3]=a.cpu.write_map[3]=left+16384;
            b.cpu.read_map[3]=b.cpu.write_map[3]=right+16384;
        }
        const unsigned slice=slices[(test/7)%10];
        for(unsigned part=0;part<3;++part) {
            const unsigned actual=spectrum_run(&a,slice),expected=reference_run(&b,slice);
            assert(actual==expected);equal(&a,&b,test);
        }
    }
    puts("6000 LDIR differential cases: flags, BC=0, overlap, self-modification, aliases, page/wrap edges, INT/NMI/EI and slice/frame boundaries PASS");
}
