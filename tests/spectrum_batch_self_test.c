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
    // INT is a level, and an accepting Z80 clears its pending latch. A
    // short EI handler can accept it again within the same32T ULA pulse.
    for(unsigned im=0;im<3;++im) {
        spectrum a,b;spectrum_init(&a,left,rom_l);spectrum_init(&b,right,rom_r);
        memset(rom_l,0,sizeof(rom_l));memset(rom_r,0,sizeof(rom_r));
        rom_l[0x38]=rom_r[0x38]=0xFB;
        a.cpu.pc=b.cpu.pc=0x8000;a.cpu.sp=b.cpu.sp=0xFF00;
        a.cpu.iff1=b.cpu.iff1=true;a.cpu.interrupt_mode=b.cpu.interrupt_mode=im;
        assert(spectrum_run(&a,100)==reference_run(&b,100));equal(&a,&b,im);
    }
    static const unsigned phases[]={0,1,28,31,32,33,69860,69887};
    static const unsigned slices[]={0,1,4,21,32,33,100,2048,10000,72000};
    for(unsigned test=0;test<3200;++test) {
        spectrum a,b;spectrum_init(&a,left,rom_l);spectrum_init(&b,right,rom_r);
        for(unsigned i=0;i<sizeof(left);++i) left[i]=(uint8_t)(random_value()>>24);
        for(unsigned i=0;i<sizeof(rom_l);++i) rom_l[i]=(uint8_t)(random_value()>>24);
        memcpy(right,left,sizeof(left));memcpy(rom_r,rom_l,sizeof(rom_l));
        a.pentagon=b.pentagon=(test&1)!=0;
        unsigned frame=spectrum_frame_cycles(&a),phase=phases[test%8];
        a.frame_tstates=b.frame_tstates=phase>=69860?frame-69888+phase:phase;
        a.cpu.pc=b.cpu.pc=(uint16_t)random_value();a.cpu.sp=b.cpu.sp=(uint16_t)random_value();
        a.cpu.hl=b.cpu.hl=(uint16_t)random_value();a.cpu.de=b.cpu.de=(uint16_t)random_value();
        a.cpu.bc=b.cpu.bc=(uint16_t)random_value();a.cpu.a=b.cpu.a=(uint8_t)random_value();
        a.cpu.f=b.cpu.f=(uint8_t)random_value();a.cpu.r=b.cpu.r=(uint8_t)random_value();
        a.cpu.i=b.cpu.i=(uint8_t)random_value();
        a.cpu.iff1=b.cpu.iff1=(test&2)!=0;a.cpu.iff2=b.cpu.iff2=(test&4)!=0;
        a.cpu.iff_delay=b.cpu.iff_delay=test%3;
        a.cpu.nmi_pending=b.cpu.nmi_pending=(test%17==0);
        a.cpu.interrupt_mode=b.cpu.interrupt_mode=(test/13)%3;
        if(test%5==0) a.cpu.cyc=b.cpu.cyc=UINT32_MAX-(test%2048);
        unsigned n=slices[test%10];
        assert(spectrum_run(&a,n)==reference_run(&b,n));equal(&a,&b,test);
    }
    puts("3200 randomized Z80 batch/single-step cases: complete CPU/RAM, INT/NMI/EI, self-modification, slice/frame/uint32 edges PASS");
}
