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
        if(s->pentagon) z80_step(&s->cpu);else (void)spectrum_run(s,1);
        const uint32_t cycles=(uint32_t)(s->cpu.cyc-before);
        if(!s->pentagon) {done+=cycles;continue;}
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
    z->bus=z->io_at=0;z->wait=NULL;z->port_span=NULL;
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
static void test_memory_loop(bool verify) {
    static const uint8_t fill[]={0x36,0x02,0x2b,0xbc,0x20,0xfa,0x76};
    static const uint8_t check[]={0xa7,0xed,0x52,0x19,0x23,0x30,0x06,0x35,0x28,0x03,0x35,0x28,0xf3,0x76};
    static const uint16_t pc[]={0x11db,0x8120,0x47fa,0x83fc};
    static const uint16_t hl[]={0xffff,0xc019,0x83ff,0x8127,0x4040,0x9140,0x8003,0x0001};
    static const unsigned phases[]={0,30,32,14334,69880};
    static const unsigned slices[]={127,128,129,512,2048,10240};
    for(unsigned test=0;test<640;++test) {
        spectrum a,b;
        memset(rom_l,0,sizeof(rom_l));rom_l[0x38]=rom_l[0x66]=0xc9;
        spectrum_init(&a,left,rom_l);spectrum_init(&b,right,rom_r);
        if(verify) {
            memset(left,2,sizeof(left));
            const unsigned next=hl[test%8]+43u;
            if(test%3==0 && next>=0x4000 && next<0x10000) left[next-0x4000]=1;
        }
        const unsigned address=pc[(test/8)%4];
        memcpy(address<0x4000?rom_l+address:left+address-0x4000,
               verify?check:fill,verify?sizeof(check):sizeof(fill));
        memcpy(right,left,sizeof(left));memcpy(rom_r,rom_l,sizeof(rom_l));
        a.cpu.pc=b.cpu.pc=address;a.cpu.hl=b.cpu.hl=hl[test%8];
        a.cpu.a=b.cpu.a=test%7==0?(uint8_t)(a.cpu.h-1):0x3f;
        a.cpu.de=b.cpu.de=test%11==0?a.cpu.hl+7:0xffff;
        a.cpu.i=b.cpu.i=test%17==0?0x40:0x3f;
        a.cpu.r=b.cpu.r=(uint8_t)random_value();a.cpu.f=b.cpu.f=(uint8_t)random_value();
        a.cpu.sp=b.cpu.sp=0xfdec;
        a.cpu.iff1=b.cpu.iff1=test%13==0;
        a.cpu.iff_delay=b.cpu.iff_delay=test%19==0;
        a.cpu.nmi_pending=b.cpu.nmi_pending=test%31==0;
        a.frame_tstates=b.frame_tstates=phases[(test/32)%5];
        if(test&1) a.cpu.cyc=b.cpu.cyc=UINT32_MAX-143;
        if(test%8==5 && address==0x8120) {
            // The guest's fill page aliases the physical instruction page.
            a.cpu.write_pages[0x9000>>10]=left+0x4000;
            b.cpu.write_pages[0x9000>>10]=right+0x4000;
            if(verify) {
                a.cpu.hl=b.cpu.hl=0x90ff;
                a.cpu.read_pages[0x9000>>10]=a.cpu.write_pages[0x9000>>10];
                b.cpu.read_pages[0x9000>>10]=b.cpu.write_pages[0x9000>>10];
            }
        }
        const unsigned slice=slices[(test/5)%6];
        for(unsigned part=0;part<3;++part) {
            assert(spectrum_run(&a,slice)==reference_run(&b,slice));
            equal(&a,&b,6000+test);
        }
    }
    printf("48K %s loops: exact scalar state and timing, exits, IRQ, contended buses and aliased code PASS\n",
           verify?"verify/clear":"fill");
}
static void test_delay_loops(void) {
    static const uint8_t djnz[]={0x10,0xfe,0x76};
    static const uint8_t dec_a[]={0x3d,0x20,0xfd,0x76};
    static const unsigned phases[]={10,32,14340,57345,69875};
    static const uint16_t locations[]={0x05e9,0x07ff,0x4030,0x8ffe};
    for(unsigned test=0;test<1024;++test) {
        const unsigned address=locations[(test/2)%4];
        const bool is_djnz=(test&1)!=0;
        spectrum a,b;
        memset(rom_l,0,sizeof(rom_l));rom_l[0x38]=rom_l[0x66]=0xc9;
        spectrum_init(&a,left,rom_l);spectrum_init(&b,right,rom_r);
        uint8_t* bytes=address<0x4000?rom_l+address:left+address-0x4000;
        memcpy(bytes,is_djnz?djnz:dec_a,is_djnz?sizeof(djnz):sizeof(dec_a));
        memcpy(right,left,sizeof(left));memcpy(rom_r,rom_l,sizeof(rom_l));
        a.cpu.pc=b.cpu.pc=address;a.cpu.sp=b.cpu.sp=0xfeff;
        a.cpu.a=b.cpu.a=a.cpu.b=b.cpu.b=(uint8_t)(test/4);
        a.cpu.r=b.cpu.r=(uint8_t)random_value();a.cpu.f=b.cpu.f=(uint8_t)random_value();
        a.cpu.i=b.cpu.i=test%7==0?0x40:0x3f;
        a.cpu.iff1=b.cpu.iff1=test%9==0;
        a.cpu.iff_delay=b.cpu.iff_delay=test%19==0;
        a.cpu.nmi_pending=b.cpu.nmi_pending=test%31==0;
        a.frame_tstates=b.frame_tstates=phases[(test/8)%5];
        if(test&2) a.cpu.cyc=b.cpu.cyc=UINT32_MAX-70;
        const unsigned budget=52+test%3000;
        assert(spectrum_run(&a,budget)==reference_run(&b,budget));
        equal(&a,&b,7000+test);
    }
    puts("48K tape delay loops: exact scalar state and timing, wrapping counters, IRQ and buses PASS");
}
static void test_bit_poll(void) {
    static const uint16_t locations[]={0x0170,0x33a0,0x3ffe,0x4780};
    static const uint16_t operands[]={0x2100,0x5c3b,0x8400,0xc101};
    static const unsigned phases[]={12,32,14328,14351,14459,57333,69875};
    for(unsigned test=0;test<1024;++test) {
        const unsigned pc=locations[(test/8)%4],hl=operands[(test/32)%4],bit=test&7;
        const uint8_t loop[]={0xcb,(uint8_t)(0x46+8*bit),0x28,0xfc,0x76};
        spectrum a,b;
        spectrum_init(&a,left,rom_l);spectrum_init(&b,right,rom_r);
        memset(rom_l,0,sizeof(rom_l));
        rom_l[0x38]=rom_l[0x66]=0xc9;
        for(unsigned i=0;i<sizeof(loop);++i) {
            const unsigned address=pc+i;
            if(address<0x4000) rom_l[address]=loop[i];else left[address-0x4000]=loop[i];
        }
        const uint8_t value=test%7==0?(uint8_t)(1u<<bit):0;
        if(hl<0x4000) rom_l[hl]=value;else left[hl-0x4000]=value;
        memcpy(rom_r,rom_l,sizeof(rom_l));memcpy(right,left,sizeof(left));
        a.cpu.pc=b.cpu.pc=pc+(test%11==0?2:0);a.cpu.hl=b.cpu.hl=hl;
        a.cpu.sp=b.cpu.sp=0xff00;
        a.cpu.mem_ptr=b.cpu.mem_ptr=(uint16_t)random_value();
        a.cpu.f=b.cpu.f=(uint8_t)(0x40|random_value());a.cpu.r=b.cpu.r=(uint8_t)random_value();
        a.cpu.iff1=b.cpu.iff1=test%13==0;a.cpu.iff_delay=b.cpu.iff_delay=test%17==0;
        a.cpu.nmi_pending=b.cpu.nmi_pending=test%19==0;
        if(test&1) a.cpu.contention_mask=b.cpu.contention_mask=0x4000;
        if(test&2) a.cpu.cyc=b.cpu.cyc=UINT32_MAX-94;
        if(test%23==0) a.cpu.read_pages[hl>>10]=b.cpu.read_pages[hl>>10]=NULL;
        a.frame_tstates=b.frame_tstates=phases[(test/2)%7];
        const unsigned budget=128+test*29%3300;
        assert(spectrum_run(&a,budget)==reference_run(&b,budget));
        equal(&a,&b,8000+test);
    }
    puts("BIT/JR polling: exact scalar state and timing, both bit levels, IRQ, bus waits, mapped access and wrap PASS");
}
typedef struct {
    spectrum machine;
    uint32_t edge;
    bool initial_level,space;
} pulse_input;
static uint8_t edge_value(const z80* cpu) {
    const pulse_input* tape=cpu->userdata;
    const bool level=tape->initial_level^((int32_t)(tape->edge-(uint32_t)cpu->cyc)<=0);
    return (tape->space?0xbe:0xbf)|(level?0x40:0);
}
static uint8_t edge_read(z80* cpu,uint16_t port) {
    (void)port;
    return edge_value(cpu);
}
static uint32_t edge_span(const z80* cpu,uint16_t port,uint8_t mask,uint8_t match) {
    assert(port==0x7ffe);
    const pulse_input* tape=cpu->userdata;
    const int32_t until=(int32_t)(tape->edge-(uint32_t)cpu->cyc);
    return until>0 && (edge_value(cpu)&mask)==match?(uint32_t)until:0;
}
static void test_edge_poll(void) {
    static const uint8_t loop[]={0x04,0xc8,0x3e,0x7f,0xdb,0xfe,0x1f,0xd0,0xa9,0xe6,0x20,0x28,0xf3,0x76};
    static const unsigned phases[]={8,32,14301,14335,14341,14456,57342,69851};
    for(unsigned test=0;test<1024;++test) {
        pulse_input a,b;
        memset(rom_l,0,sizeof(rom_l));rom_l[0x38]=rom_l[0x66]=0xc9;
        memcpy(rom_l+0x05ed,loop,sizeof(loop));memcpy(rom_r,rom_l,sizeof(rom_l));
        spectrum* s=&a.machine,*r=&b.machine;
        spectrum_init(s,left,rom_l);spectrum_init(r,right,rom_r);
        left[0x4000]=right[0x4000]=0x76;
        left[0xbffc]=right[0xbffc]=0;left[0xbffd]=right[0xbffd]=0x80;
        s->cpu.pc=r->cpu.pc=test%11==0?0x05f8:0x05ed;s->cpu.sp=r->cpu.sp=0xfffc;
        s->cpu.userdata=&a;r->cpu.userdata=&b;
        s->cpu.port_in=r->cpu.port_in=edge_read;s->cpu.port_span=edge_span;
        s->cpu.a=r->cpu.a=(uint8_t)random_value();
        s->cpu.f=r->cpu.f=(uint8_t)random_value();s->cpu.r=r->cpu.r=(uint8_t)random_value();
        s->cpu.b=r->cpu.b=test%17==0?0xfd:(uint8_t)random_value();
        s->cpu.i=r->cpu.i=test%7==0?0x40:0x3f;
        s->cpu.iff1=r->cpu.iff1=test%9==0;
        s->cpu.iff_delay=r->cpu.iff_delay=test%19==0;
        s->cpu.nmi_pending=r->cpu.nmi_pending=test%31==0;
        s->frame_tstates=r->frame_tstates=phases[test%8];
        if(test&8) s->cpu.cyc=r->cpu.cyc=UINT32_MAX-600;
        a.initial_level=b.initial_level=(test&16)!=0;
        a.space=b.space=test%13==0;
        s->cpu.c=r->cpu.c=a.initial_level^(test%5==0)?0x20:0;
        a.edge=b.edge=(uint32_t)s->cpu.cyc+test*101%2600;
        const unsigned budget=128+test*47%2500;
        for(unsigned part=0;part<2;++part) {
            assert(spectrum_run(s,budget)==reference_run(r,budget));
            assert(s->cpu.io_at==r->cpu.io_at);
            equal(s,r,8000+test);
        }
    }
    puts("48K EAR polling: exact scalar state, keyboard abort, pulse edges, contention and cycle wrap PASS");
}
int main(void) {
    static const unsigned counts[]={0,1,2,3,4,5,16,127,255,256,1024,16384,65535};
    static const unsigned phases[]={0,4,11,28,31,32,35,14240,14335,14400,57342,57343,69800,69867,69887};
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
        if(test&4) a.cpu.contention_mask=b.cpu.contention_mask=0x4000; // Switchable odd 128K bank.
        const unsigned frame=spectrum_frame_cycles(&a),phase=phases[(test/2)%(sizeof(phases)/sizeof(*phases))];
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
                a.cpu.read_pages[48+p]=left+32768+p*1024;b.cpu.read_pages[48+p]=right+32768+p*1024;
                a.cpu.write_pages[48+p]=left+32768+p*1024;b.cpu.write_pages[48+p]=right+32768+p*1024;
            }
            a.cpu.write_map[3]=b.cpu.write_map[3]=NULL;
        } else if(test%3==1) {
            a.cpu.read_map[3]=a.cpu.write_map[3]=left+16384;
            b.cpu.read_map[3]=b.cpu.write_map[3]=right+16384;
            for(unsigned p=0;p<16;++p) {
                a.cpu.read_pages[48+p]=a.cpu.write_pages[48+p]=left+16384+p*1024;
                b.cpu.read_pages[48+p]=b.cpu.write_pages[48+p]=right+16384+p*1024;
            }
        }
        const unsigned slice=slices[(test/7)%10];
        for(unsigned part=0;part<3;++part) {
            const unsigned actual=spectrum_run(&a,slice),expected=reference_run(&b,slice);
            assert(actual==expected);equal(&a,&b,test);
        }
    }
    puts("6000 LDIR differential cases: flags, BC=0, overlap, self-modification, aliases, page/wrap edges, INT/NMI/EI and slice/frame boundaries PASS");
    test_memory_loop(false);test_memory_loop(true);test_delay_loops();test_bit_poll();test_edge_poll();
}
