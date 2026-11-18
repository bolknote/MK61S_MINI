#include "../examples/portable-apps/SPECTRUM/szx.h"
#include "../examples/portable-apps/SPECTRUM/tape.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <zlib.h>

static spectrum machine;
static spectrum_memory memory;
static uint8_t psram[SPECTRUM_EXTERNAL_BYTES],sram[SPECTRUM_FIXED_BYTES],pages[16384];
static uint8_t disk[192*1024],snapshot[192*1024],low[12288],high[4096];
typedef struct { uint8_t* data;uint32_t size; } buffer;
static buffer backing={psram,sizeof(psram)};

static bool read_bytes(void* raw,uint32_t at,uint8_t* out,uint32_t bytes) {
    const buffer* source=raw;
    if(at>source->size || bytes>source->size-at) return false;
    memcpy(out,source->data+at,bytes);return true;
}
static bool write_bytes(void* raw,uint32_t at,const uint8_t* in,uint32_t bytes) {
    const buffer* target=raw;
    if(at>target->size || bytes>target->size-at) return false;
    memcpy(target->data+at,in,bytes);return true;
}
static bool clear_bytes(void* raw,uint32_t at,uint32_t bytes) {
    const buffer* target=raw;
    if(at>target->size || bytes>target->size-at) return false;
    memset(target->data+at,0,bytes);return true;
}
static void setup(bool ntsc) {
    const spectrum_memory_io io={&backing,read_bytes,write_bytes,clear_bytes};
    uint8_t* tails[]={sram+15360,sram+31744};
    uint8_t* runs[]={pages,pages+8192,pages+10240,pages+14336};
    memset(&machine,0,sizeof(machine));
    assert(spectrum_memory_init_fragmented(&memory,sram,sram+16384,tails,runs,32,io));
    machine.timex_ntsc=ntsc;
    spectrum_attach_memory(&machine,&memory);
}
static void out(uint16_t port,uint8_t value) { machine.cpu.port_out(&machine.cpu,port,value); }
static uint8_t peek(uint16_t address) {
    const uint8_t* page=machine.cpu.read_pages[address>>10];
    return page?page[address&1023]:machine.cpu.read_byte(&machine,address);
}
static void poke(uint16_t address,uint8_t value) {
    uint8_t* page=machine.cpu.write_pages[address>>10];
    if(page)page[address&1023]=value;
    else machine.cpu.write_byte(&machine,address,value);
}
static void guest(const uint8_t* code,unsigned size) {
    const uint16_t address=0x8000;
    assert(spectrum_bank_write(&memory,2,0,code,size));
    machine.cpu.pc=address;machine.cpu.halted=false;
    spectrum_run(&machine,384);
    assert(machine.cpu.halted && !memory.fault);
}
static void paging(void) {
    setup(true);
    psram[SPECTRUM_ROM_BASE]=0x12;psram[SPECTRUM_ROM_BASE+16384]=0x34;
    const uint8_t dock[]={0,2,0,1,0,0,0,0,3};
    const uint8_t exrom[]={254,0,0,0,3,0,0,0,0};
    unsigned size=0;
    memcpy(disk+size,dock,sizeof(dock));size+=sizeof(dock);
    memset(disk+size,0x5a,8192);size+=8192;
    memset(disk+size,0x3b,8192);size+=8192;
    memcpy(disk+size,exrom,sizeof(exrom));size+=sizeof(exrom);
    memset(disk+size,0xad,8192);size+=8192;
    buffer image={disk,size};spectrum_source source={&image,size,read_bytes};
    assert(spectrum_load_dck(&machine,&source)==SPECTRUM_OK);
    assert(peek(0)==0x12 && !machine.timex_hsr);
    // F4 selects DOCK through Z80 OUT. Write to RAM, attempt a ROM write,
    // and read both back through the CPU's hot 1K maps.
    const uint8_t code[]={0x3e,0x85,0xd3,0xf4,0x3e,0x99,0x32,0x00,0x40,0x32,0x00,0x00,
        0x3a,0x00,0x40,0x47,0x3a,0x00,0x00,0x4f,0x76};
    guest(code,sizeof(code));
    assert(machine.cpu.b==0x99 && machine.cpu.c==0x5a && peek(0xe000)==0x3b);
    assert(spectrum_port_in(&machine,0x51f4)==0x85);
    assert(memory.cache[0]==0);
    out(0x23ff,0x80);assert(peek(0)==0x34 && peek(0xe000)==0x34);
    out(0x12f4,8);assert(peek(0x6000)==0xad);poke(0x6000,0xc3);
    out(0xff,0);assert(peek(0x6000)==255);poke(0x6000,0x55);
    out(0xf4,0);assert(peek(0x6000)==0);
    out(0xf4,8);out(0xff,0x82);assert(peek(0x6000)==0xc3);
    assert(spectrum_port_in(&machine,0xaaff)==0x82);

    spectrum_hicolor_changes changes;
    spectrum_hicolor_watch(&machine,&changes);
    poke(0x6000,0xb1);assert(!changes.strips[0].bottom && !memory.cache[8192]);
    out(0xf4,0);poke(0x6000,0x81);assert(changes.strips[0].bottom==1 && memory.cache[8192]==0x81);
    spectrum_hicolor_watch(&machine,NULL);
    out(0xf4,8);
    const spectrum_cartridge before=machine.cartridge;
    --source.size;
    assert(spectrum_load_dck(&machine,&source)==SPECTRUM_FORMAT);
    assert(!memcmp(&before,&machine.cartridge,sizeof(before)) && peek(0x6000)==0xb1);
    spectrum_reset(&machine);
    out(0xf4,8);out(0xff,0x82);assert(peek(0x6000)==0xb1);
    machine.frame_tstates=58000;
    spectrum_szx_writer writer;
    size=spectrum_szx_save(&writer,&machine);
    assert(size && size<sizeof(snapshot) && writer.header[6]==12);
    assert(spectrum_szx_read(&writer,0,snapshot,size));
    image=(buffer){snapshot,size};source=(spectrum_source){&image,size,read_bytes};
    assert(spectrum_load_szx(&machine,&source,low,high)==SPECTRUM_OK);
    assert(machine.frame_tstates==58000 && peek(0x6000)==0xb1);
    out(0xf4,0x85);out(0xff,0);assert(peek(0)==0x5a && peek(0x4000)==0x99);

    // Compress the last EXROM DOCK record exactly as third-party SZX files do.
    const unsigned header=size-8192-11;
    assert(!memcmp(snapshot+header,"DOCK",4) && snapshot[header+8]==2);
    uLongf compressed=sizeof(disk);
    assert(compress2(disk,&compressed,snapshot+header+11,8192,6)==Z_OK);
    memcpy(snapshot+header+11,disk,compressed);
    const unsigned chunk_size=(unsigned)compressed+3;
    snapshot[header+4]=(uint8_t)chunk_size;snapshot[header+5]=(uint8_t)(chunk_size>>8);
    snapshot[header+8]=3;
    image.size=source.size=header+11+(unsigned)compressed;
    assert(spectrum_load_szx(&machine,&source,low,high)==SPECTRUM_OK && peek(0x6000)==0xb1);
    snapshot[image.size-1]^=1;
    assert(spectrum_load_szx(&machine,&source,low,high)==SPECTRUM_FORMAT && peek(0x6000)==0xb1);
    puts("Timex HOME/DOCK/EXROM, RAM/ROM, CPU maps, reset, malformed DCK and compressed SZX round trip PASS");
}

static void timing(bool ntsc) {
    setup(ntsc);
    assert(spectrum_frame_cycles(&machine)==(ntsc?58688:69888));
    assert(machine.ay.clk==(ntsc?1764000:1750000));
    machine.cpu.pc=0x4000;machine.frame_tstates=ntsc?9168:14320;
    assert(spectrum_run(&machine,1)==10);
    out(0x41fe,5);out(0x00f4,0);out(0x01f5,8);out(0x00f6,13);
    assert(machine.border==5 && machine.ay.reg[8]==13 && spectrum_port_in(&machine,0x02f6)==13);
    out(0x0ff5,14);
    machine.joystick=1|4|16;
    assert(spectrum_port_in(&machine,0x01f6)==0x75 && spectrum_port_in(&machine,0x02f6)==255);
    machine.joystick_mode=1;
    assert(spectrum_port_in(&machine,0x02f6)==0x75 && spectrum_port_in(&machine,0x01f6)==255);
    machine.frame_tstates=0;machine.cpu.halted=machine.cpu.iff1=true;
    machine.cpu.sp=0xafff;machine.cpu.interrupt_mode=1;
    out(0xff,64);spectrum_run(&machine,4);assert(machine.cpu.halted && !machine.cpu.int_pending);
    out(0xff,0);spectrum_run(&machine,1);assert(!machine.cpu.halted && machine.cpu.pc==0x38);

    machine.cpu.cyc=UINT32_MAX-900;spectrum_sound_begin(&machine,NULL,NULL);
    const uint32_t audio=machine.sound.time;
    for(unsigned i=0;i<151;++i) {machine.cpu.cyc+=2039;spectrum_sound_publish(&machine);}
    const uint32_t cycles=151*2039;
    assert(atomic_load(&machine.sound.produced)-audio==(ntsc?(cycles*125+125)/126:cycles));
}

static void original(const char* home,const char* exrom) {
    FILE* file=fopen(home,"rb");assert(file);
    assert(fread(psram+SPECTRUM_ROM_BASE,1,16384,file)==16384 && fgetc(file)==EOF);fclose(file);
    file=fopen(exrom,"rb");assert(file);
    assert(fread(psram+SPECTRUM_ROM_BASE+16384,1,8192,file)==8192 && fgetc(file)==EOF);fclose(file);
    for(unsigned ntsc=0;ntsc<2;++ntsc) {
        setup(ntsc!=0);
        for(unsigned frame=0;frame<140;++frame) spectrum_run(&machine,spectrum_frame_cycles(&machine));
        unsigned drawn=0;
        for(unsigned i=0;i<6144;++i) drawn+=memory.cache[i]!=0;
        assert(drawn>=100 && !memory.fault && !machine.timex_hsr);
        // Invoke EXROM LD-BYTES with an actual tape signal on EAR.
        uint8_t tap[]={6,0,255,17,43,88,105,255^17^43^88^105};
        buffer media={tap,sizeof(tap)};
        const spectrum_source tape_source={&media,media.size,read_bytes};
        spectrum_tape tape={0};
        assert(spectrum_tape_open(&tape,&tape_source,false)==SPECTRUM_OK);
        tape.playing=true;machine.ear=spectrum_tape_ear;machine.ear_context=&tape;
        out(0xff,0x80);out(0xf4,1);
        poke(0xbff0,0);poke(0xbff1,0x80);poke(0x8000,0x76);
        machine.cpu.pc=0x00fc;machine.cpu.sp=0xbff0;machine.cpu.ix=0xa000;
        machine.cpu.de=4;machine.cpu.a=255;machine.cpu.cf=true;
        for(unsigned i=0;i<5000 && !machine.cpu.halted;++i) spectrum_run(&machine,2048);
        assert(machine.cpu.halted && machine.cpu.cf && !tape.fault);
        for(unsigned i=0;i<4;++i) assert(peek(0xa000+i)==tap[3+i]);
        machine.ear=NULL;machine.ear_context=NULL;
        // An original LROS fixture. The real EXROM selects and jumps to it.
        memset(disk,0,9+8192);
        disk[1]=2;
        const uint8_t lros[]={0,1,0x10,0,0xfe};
        const uint8_t program[]={0xf3,0x3e,0x4d,0x32,0x00,0xc0,0x76};
        memcpy(disk+9,lros,sizeof(lros));memcpy(disk+9+0x10,program,sizeof(program));
        buffer image={disk,9+8192};const spectrum_source source={&image,image.size,read_bytes};
        assert(spectrum_load_dck(&machine,&source)==SPECTRUM_OK);
        for(unsigned frame=0;frame<140 && peek(0xc000)!=0x4d;++frame)
            spectrum_run(&machine,spectrum_frame_cycles(&machine));
        assert(peek(0xc000)==0x4d && machine.cpu.halted && (machine.timex_hsr&1) && !(machine.timex_mode&128));
    }
    puts("Original TS2068/TC2068 HOME and EXROM boot, tape waveform load and handoff to LROS cartridge PASS");
}
int main(int argc,char** argv) {
    paging();timing(false);timing(true);
    puts("Timex PAL/NTSC frame length, ULA contention, INT inhibit, AY ports/joystick, audio clock wrap PASS");
    if(argc==3) original(argv[1],argv[2]);
    else assert(argc==1);
    return 0;
}
