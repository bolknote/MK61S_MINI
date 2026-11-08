#include "../third_party/z80/z80.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static uint8_t ram[65536];
static z80 cpu;

static void begin(void) {
    z80_init(&cpu);
    for(unsigned i=0;i<64;++i) {
        cpu.read_pages[i]=ram+i*1024;cpu.write_pages[i]=ram+i*1024;
    }
}

/* Exhaust all input bytes and all prior flag values, including (HL).
 * The expected flags come from the Z80 arithmetic contract, independently
 * of the interpreter's result-indexed lookup tables. */
static void increments(void) {
    static const size_t registers[]={offsetof(z80,b),offsetof(z80,c),offsetof(z80,d),offsetof(z80,e),
        offsetof(z80,h),offsetof(z80,l),0,offsetof(z80,a)};
    for(unsigned decrement=0;decrement<2;++decrement)for(unsigned reg=0;reg<8;++reg) {
        begin();ram[0]=(uint8_t)(4+reg*8+decrement);
        for(unsigned value=0;value<256;++value)for(unsigned flags=0;flags<256;++flags) {
            cpu.pc=0;cpu.cyc=0;cpu.r=0xFE;cpu.f=(uint8_t)flags;cpu.hl=0x4567;
            uint8_t* target=reg==6?ram+cpu.hl:(uint8_t*)&cpu+registers[reg];
            *target=(uint8_t)value;
            const unsigned result=(value+(decrement?255:1))&255;
            const bool half=decrement?(value&15)==0:(value&15)==15;
            const bool overflow=value==(decrement?128:127);
            const unsigned expected=(flags&1)|(result&0xA8)|(result?0:0x40)|
                (half?16:0)|(overflow?4:0)|(decrement?2:0);
            z80_step(&cpu);
            assert(*target==result && cpu.f==expected);
            assert(cpu.pc==1 && cpu.cyc==(reg==6?11:4) && cpu.r==0xFF);
        }
    }
}

static uint32_t random_state=0xD84B3071;
static uint16_t random_word(void) {
    random_state=random_state*1664525u+1013904223u;return (uint16_t)(random_state>>16);
}

/* ADD HL/IX/IY,rr preserves S/Z/PV, resets N, and takes H from bit11,
 * C from bit15 and the undocumented flags from the high result byte. */
static void word_adds(void) {
    static const uint16_t edges[]={0,1,0x7FF,0x800,0xFFF,0x1000,0x7FFF,0x8000,0xFFFF};
    for(unsigned prefix=0;prefix<3;++prefix)for(unsigned source=0;source<4;++source) {
        begin();const unsigned at=prefix?1:0;
        ram[0]=(uint8_t)(prefix==1?0xDD:0xFD);ram[at]=(uint8_t)(9+source*16);
        for(unsigned value=0;value<65536;++value) {
            const uint16_t other=(value%3)?random_word():edges[(value/3)%9];
            const uint8_t flags=(uint8_t)random_word();
            uint16_t* target=prefix==1?&cpu.ix:prefix==2?&cpu.iy:&cpu.hl;
            cpu.pc=0;cpu.cyc=0;cpu.r=0xFE;cpu.f=flags;cpu.bc=other;cpu.de=other;cpu.sp=other;
            *target=(uint16_t)value;
            const uint16_t operand=source==2?(uint16_t)value:other;
            const uint32_t sum=value+operand;const uint16_t result=(uint16_t)sum;
            const unsigned expected=(flags&0xC4)|((result>>8)&0x28)|
                (((value&0xFFF)+(operand&0xFFF)>0xFFF)?16:0)|(sum>0xFFFF?1:0);
            z80_step(&cpu);
            assert(*target==result && cpu.f==expected && cpu.mem_ptr==(uint16_t)(value+1));
            assert(cpu.pc==at+1 && cpu.cyc==(prefix?15:11) && cpu.r==(prefix?0x80:0xFF));
        }
    }
}

static void exchanges(void) {
    begin();ram[0]=0xD9;
    for(unsigned i=0;i<65536;++i) {
        cpu.pc=0;cpu.cyc=0;cpu.r=0;cpu.f=0xA5;
        const uint16_t bc=cpu.bc=random_word(),de=cpu.de=random_word(),hl=cpu.hl=random_word();
        const uint16_t bs=cpu.bc_=random_word(),ds=cpu.de_=random_word(),hs=cpu.hl_=random_word();
        z80_step(&cpu);
        assert(cpu.bc==bs && cpu.de==ds && cpu.hl==hs);
        assert(cpu.bc_==bc && cpu.de_==de && cpu.hl_==hl);
        assert(cpu.f==0xA5 && cpu.pc==1 && cpu.r==1 && cpu.cyc==4);
    }
}

int main(void) {
    memset(ram,0,sizeof(ram));increments();word_adds();exchanges();
    puts("Z80 INC/DEC: all byte/flag/register inputs; ADD HL/IX/IY,rr: 786432 cases; EXX: 65536 cases PASS");
}
