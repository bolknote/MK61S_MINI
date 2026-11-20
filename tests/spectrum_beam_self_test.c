#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static spectrum machine;
static uint8_t ram[SPECTRUM_RAM_BYTES],rom[SPECTRUM_ROM_BYTES];
static uint8_t strip[2*320*SPECTRUM_BEAM_ROWS],first_strip[sizeof(strip)];
static unsigned strips;

static bool save_strip(void* context,unsigned index,const uint8_t* bytes) {
    unsigned mode=*(const unsigned*)context;
    assert(index==strips++);
    if(!index) {
        memcpy(first_strip,bytes,spectrum_beam_row_bytes(mode)*SPECTRUM_BEAM_ROWS);
#if SPECTRUM_HAS_TIMEX
        spectrum_timex_beam_expand(first_strip);
#endif
    }
    return true;
}

static void check_line(unsigned first,unsigned last,uint16_t expected) {
    for(unsigned x=first;x<last;++x) {
        const uint16_t rgb=SPECTRUM_HAS_PENTAGON?spectrum_color((first_strip[x/2]>>((x&1)?0:4))&15):
            (uint16_t)(first_strip[2*x]|(first_strip[2*x+1]<<8));
        assert(rgb==expected);
    }
}

#if SPECTRUM_HAS_PENTAGON
static uint8_t psram[SPECTRUM_EXTERNAL_BYTES],fixed[32768],pages[16384],white[16384];
static spectrum_memory memory;
static bool read_bytes(void* context,uint32_t at,uint8_t* out,uint32_t count) {
    (void)context;
    assert(at<=sizeof(psram) && count<=sizeof(psram)-at);
    memcpy(out,psram+at,count);return true;
}
static bool write_bytes(void* context,uint32_t at,const uint8_t* in,uint32_t count) {
    (void)context;
    assert(at<=sizeof(psram) && count<=sizeof(psram)-at);
    memcpy(psram+at,in,count);return true;
}
static bool clear_bytes(void* context,uint32_t at,uint32_t count) {
    (void)context;
    assert(at<=sizeof(psram) && count<=sizeof(psram)-at);
    memset(psram+at,0,count);return true;
}

static void pentagon_screen(unsigned mode,unsigned start) {
    uint8_t* tails[]={fixed+15360,fixed+31744};
    uint8_t* runs[]={pages,pages+8192,pages+10240,pages+14336};
    spectrum_init(&machine,ram,rom);
    assert(spectrum_memory_init_fragmented(&memory,fixed,fixed+16384,tails,runs,64,
        (spectrum_memory_io){NULL,read_bytes,write_bytes,clear_bytes}));
    spectrum_attach_memory(&machine,&memory);
    memset(white,0xff,sizeof(white));
    assert(spectrum_bank_write(&memory,6,0,white,sizeof(white)));
    assert(spectrum_bank_write(&memory,7,0,white,sizeof(white)));
    const uint8_t code[]={0xed,0x79,0x76}; // OUT (C), A; HALT
    assert(spectrum_bank_write(&memory,2,0,code,sizeof(code)));
    machine.cpu.port_out(&machine.cpu,0xeff7,(uint8_t)mode);
    machine.cpu.pc=0x8000;machine.cpu.bc=0x7ffd;machine.cpu.a=8;
    machine.cpu.cyc=machine.frame_tstates=start+48;
    unsigned width=spectrum_beam_width(mode);
    strips=0;
    spectrum_beam_begin(&machine,mode,strip,&mode,save_strip);
    spectrum_run(&machine,spectrum_frame_cycles(&machine)-machine.frame_tstates);
    assert(strips==spectrum_beam_height(mode)/SPECTRUM_BEAM_ROWS);
    assert(!memory.fault && !machine.beam_geometry_changed && machine.frames==1);
    check_line(0,16,spectrum_color(0));
    check_line(width-16,width,spectrum_color(15));

    strips=0;
    spectrum_beam_begin(&machine,mode,strip,&mode,save_strip);
    machine.cpu.port_out(&machine.cpu,0xeff7,mode==SPECTRUM_VIDEO_16C?64:1);
    spectrum_run(&machine,spectrum_frame_cycles(&machine)-machine.frame_tstates);
    assert(machine.beam_geometry_changed && !strips);
}
#endif

int main(void) {
#if SPECTRUM_HAS_PENTAGON
    pentagon_screen(SPECTRUM_VIDEO_16C,17988);
    pentagon_screen(SPECTRUM_VIDEO_WIDE,17988-64*224-32);
    puts("Pentagon 16C/Wide retains both screen pages across a mid-line 7FFD write PASS");
#else
    // At the left the row uses bright red HiColor ink. A Z80 OUT in its
    // middle switches to HiRes with two set planes and non-bright red ink.
    spectrum_init(&machine,ram,rom);
    machine.extensions=SPECTRUM_TIMEX;
    machine.cpu.port_out(&machine.cpu,0x00ff,SPECTRUM_VIDEO_HICOLOR);
    memset(ram,0xff,32);
    memset(ram+8192,0x42,32);
    memset(ram+8192+16,0xff,16);
    const uint8_t code[]={0x3e,0x16,0xd3,0xff,0x76}; // LD A,$16; OUT ($ff),A; HALT
    memcpy(ram+16384,code,sizeof(code));
    machine.cpu.pc=0x8000;
    machine.cpu.cyc=machine.frame_tstates=14336+48;
    unsigned mode=SPECTRUM_VIDEO_HICOLOR;
    spectrum_beam_begin(&machine,mode,strip,&mode,save_strip);
    spectrum_run(&machine,SPECTRUM_FRAME_TSTATES-machine.frame_tstates);
    assert(strips==24 && machine.frames==1);
    assert(spectrum_timex_mode(&machine)==SPECTRUM_VIDEO_HIRES);
    check_line(0,40,spectrum_color(10));
    check_line(180,320,spectrum_color(2));
    puts("Timex retains HiColor and HiRes on the same scanline after a port FF write PASS");
#endif
    return 0;
}
