#include "../examples/portable-apps/SPECTRUM/szx.h"
#include "../examples/portable-apps/SPECTRUM/inflate.h"
#include "../examples/portable-apps/SPECTRUM/tape.h"
#include "../examples/portable-apps/SPECTRUM/ui.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <zlib.h>

static uint8_t ram[49152],rom[16384],psram[SPECTRUM_EXTERNAL_BYTES];
static uint8_t fixed[32768],pages[16384],packed[1049600],workspace[16384];
static spectrum machine;
static spectrum_memory memory;
typedef struct { uint8_t* bytes;uint32_t size; } bytes;

static bool read_bytes(void* raw,uint32_t at,uint8_t* out,uint32_t n) {
    bytes* source=raw;
    if(at>source->size || n>source->size-at) return false;
    memcpy(out,source->bytes+at,n);return true;
}
static bool write_bytes(void* raw,uint32_t at,const uint8_t* in,uint32_t n) {
    bytes* source=raw;
    if(at>source->size || n>source->size-at) return false;
    memcpy(source->bytes+at,in,n);return true;
}
static bool clear_bytes(void* raw,uint32_t at,uint32_t n) {
    bytes* source=raw;
    if(at>source->size || n>source->size-at) return false;
    memset(source->bytes+at,0,n);return true;
}

static void tape_test(void) {
    // LD-BYTES is the real 48K ROM entry at 0556. The flag, payload and
    // checksum traverse the same EAR port as a BASIC LOAD "" command.
    spectrum_init(&machine,ram,rom);
    uint8_t tap[]={6,0,255,17,43,88,105,255^17^43^88^105};
    bytes input={tap,sizeof(tap)};
    spectrum_source source={&input,input.size,read_bytes};
    spectrum_tape tape={0};
    assert(spectrum_tape_open(&tape,&source,false)==SPECTRUM_OK);
    tape.playing=true;machine.ear=spectrum_tape_ear;machine.ear_context=&tape;
    machine.cpu.pc=0x0556;machine.cpu.a=255;machine.cpu.cf=true;
    machine.cpu.de=4;machine.cpu.ix=0xa000;machine.cpu.sp=0xfffc;
    ram[0xbffc]=0;ram[0xbffd]=0x90;ram[0x5000]=0x76;
    for(unsigned i=0;i<4000 && !machine.cpu.halted;++i) spectrum_run(&machine,2048);
    assert(machine.cpu.halted && machine.cpu.cf);
    assert(!memcmp(ram+0x6000,tap+3,4));
    source.size=sizeof(tap)-1;
    assert(spectrum_tape_open(&tape,&source,false)==SPECTRUM_FORMAT);

    uint8_t tzx[]={'Z','X','T','a','p','e','!',26,1,20,
        0x24,2,0,0x12,100,0,2,0,0x25,0x20,0,0,
        0x15,40,0,0,0,4,1,0,0,0xa0};
    input=(bytes){tzx,sizeof(tzx)};source.size=input.size;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_OK);
    tape.playing=true;machine.cpu.pc=0x9000;machine.cpu.cyc=UINT32_MAX-90u;
    assert(spectrum_tape_ear(&tape,&machine.cpu));
    machine.cpu.cyc+=100;
    assert(!spectrum_tape_ear(&tape,&machine.cpu));
    spectrum_tape_toggle(&tape,(uint32_t)machine.cpu.cyc);
    machine.cpu.cyc+=1000;
    spectrum_tape_toggle(&tape,(uint32_t)machine.cpu.cyc);
    for(unsigned i=0;i<3;++i) {
        machine.cpu.cyc+=100;
        assert(spectrum_tape_ear(&tape,&machine.cpu)==(i==0));
    }
    assert(!tape.playing && !tape.fault);
    spectrum_tape_toggle(&tape,(uint32_t)machine.cpu.cyc);
    assert(spectrum_tape_ear(&tape,&machine.cpu));
    for(unsigned i=0;i<3;++i) {
        machine.cpu.cyc+=40;
        assert(spectrum_tape_ear(&tape,&machine.cpu)==(i==1));
    }
    tzx[10]=0x19;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_UNSUPPORTED);

    uint8_t calls[]={'Z','X','T','a','p','e','!',26,1,20,
        0x26,2,0,2,0,4,0, // Call blocks 2 and 4.
        0x23,5,0,         // Then skip both subroutines.
        0x12,90,0,1,0,0x27,
        0x12,60,0,1,0,0x27,
        0x18,16,0,0,0,0,0,0x58,0x1b,0,1,2,0,0,0,1,0,2,0,0,0};
    uint8_t offsets[7*4];
    bytes index={offsets,sizeof(offsets)};
    tape=(spectrum_tape){.index_context=&index,.index_read=read_bytes,.index_write=write_bytes};
    input=(bytes){calls,sizeof(calls)};source.size=input.size;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_OK);
    tape.playing=true;machine.cpu.cyc=1000;
    assert(spectrum_tape_ear(&tape,&machine.cpu) && tape.deadline==1090);
    machine.cpu.cyc=1090;
    assert(!spectrum_tape_ear(&tape,&machine.cpu) && tape.deadline==1150);
    machine.cpu.cyc=1150;
    assert(spectrum_tape_ear(&tape,&machine.cpu) && tape.deadline==1650);
    machine.cpu.cyc=1650;
    assert(!spectrum_tape_ear(&tape,&machine.cpu) && tape.deadline==2650);
    machine.cpu.cyc=2650;
    assert(!spectrum_tape_ear(&tape,&machine.cpu) && !tape.playing && !tape.fault);
}

static void compressed_page_test(void) {
    uint8_t in[16384],encoded[17000],result[16384];
    for(unsigned i=0;i<sizeof(in);++i) in[i]=(uint8_t)(i%137 ^ (i>>9));
    for(unsigned kind=0;kind<3;++kind) {
        z_stream z={0};
        assert(deflateInit2(&z,kind==0?0:6,Z_DEFLATED,15,8,kind==1?Z_FIXED:Z_DEFAULT_STRATEGY)==Z_OK);
        z.next_in=in;z.avail_in=sizeof(in);z.next_out=encoded;z.avail_out=sizeof(encoded);
        assert(deflate(&z,Z_FINISH)==Z_STREAM_END);
        bytes data={encoded,(uint32_t)z.total_out};
        assert(deflateEnd(&z)==Z_OK);
        const spectrum_source source={&data,data.size,read_bytes};
        const spectrum_inflate_output out={result,result+12288,12288,sizeof(result)};
        unsigned used=0;
        assert(spectrum_inflate(&source,0,source.size,&out,&used)==SPECTRUM_OK && used==sizeof(in));
        assert(!memcmp(in,result,sizeof(in)));
        encoded[source.size-1]^=1;
        assert(spectrum_inflate(&source,0,source.size,&out,&used)==SPECTRUM_FORMAT);
    }
}

static void snapshot_test(unsigned model) {
    spectrum_init(&machine,ram,rom);
    bytes backing={psram,sizeof(psram)};
    if(model) {
        uint8_t* tails[]={fixed+15360,fixed+31744};
        uint8_t* runs[]={pages,pages+8192,pages+10240,pages+14336};
        const spectrum_memory_io io={&backing,read_bytes,write_bytes,clear_bytes};
        assert(spectrum_memory_init_fragmented(&memory,fixed,fixed+16384,tails,runs,model==2?64:32,io));
        spectrum_attach_memory(&machine,&memory);
    }
    memset(ram,0xac,sizeof(ram));
    if(model) {
        for(unsigned bank=0;bank<memory.banks;++bank) {
            memset(workspace,(int)bank,sizeof(workspace));
            assert(spectrum_bank_write(&memory,bank,0,workspace,sizeof(workspace)));
        }
        assert(spectrum_memory_control(&memory,model==2?0x49:0));
        assert(spectrum_memory_page(&memory,model==2?0xf8:0xc8));
    }
    machine.cpu.a=0x99;machine.cpu.bc_=0x1234;machine.cpu.pc=0xbaca;
    machine.cpu.iff2=true;machine.cpu.halted=true;machine.cpu.mem_ptr=0x4444;
    machine.frame_tstates=164;machine.border=6;machine.beeper=1;machine.ulaplus_mode=1;
    machine.ulaplus_palette[31]=0x98;machine.ay.adr=7;PSG_writeReg(&machine.ay,0,89);
    spectrum_szx_writer writer;
    const unsigned size=spectrum_szx_save(&writer,&machine);
    assert(size<=sizeof(packed));
    for(unsigned at=0;at<size;) {
        const unsigned n=size-at<667?size-at:667;
        assert(spectrum_szx_read(&writer,at,packed+at,n));at+=n;
    }
    bytes data={packed,size};
    spectrum_source source={&data,data.size,read_bytes};
    unsigned selected=9;
    assert(spectrum_szx_model(&source,&selected)==SPECTRUM_OK && selected==model);
    const unsigned first_page=writer.prefix+11;
    packed[first_page-1]=255;
    assert(spectrum_load_szx(&machine,&source,workspace,workspace+12288)==SPECTRUM_FORMAT);
    assert(machine.cpu.pc==0xbaca);
    packed[first_page-1]=model?0:5;
    // Replace one raw RAMP payload with a zlib stream from another writer.
    uint8_t encoded[17000];
    unsigned long n=sizeof(encoded);
    assert(compress2(encoded,&n,packed+first_page,16384,6)==Z_OK && n<16384);
    memmove(packed+first_page+n,packed+first_page+16384,size-first_page-16384);
    memcpy(packed+first_page,encoded,n);
    const unsigned block=(unsigned)n+3;
    packed[first_page-7]=(uint8_t)block;packed[first_page-6]=(uint8_t)(block>>8);
    packed[first_page-5]=packed[first_page-4]=0;packed[first_page-3]=1;
    data.size=source.size=size-16384+(unsigned)n;
    spectrum_reset(&machine);
    assert(spectrum_load_szx(&machine,&source,workspace,workspace+12288)==SPECTRUM_OK);
    assert(machine.cpu.pc==0xbaca && machine.cpu.a==0x99 && machine.cpu.bc_==0x1234 &&
        machine.cpu.mem_ptr==0x4444 && machine.cpu.halted && !machine.cpu.iff1 && machine.cpu.iff2);
    assert(machine.frame_tstates==164 && machine.border==6 && machine.beeper &&
        machine.ulaplus_mode==1 && machine.ulaplus_palette[31]==0x98);
    assert(machine.ay.adr==7 && machine.ay.reg[0]==89);
    if(model) {
        for(unsigned bank=0;bank<memory.banks;++bank) {
            assert(spectrum_bank_read(&memory,bank,0,workspace,sizeof(workspace)));
            for(unsigned i=0;i<sizeof(workspace);++i) assert(workspace[i]==bank);
        }
    } else for(unsigned i=0;i<sizeof(ram);++i) assert(ram[i]==0xac);

    if(model==2) {
        uint8_t fill=0x51;
        assert(spectrum_bank_write(&memory,6,0,&fill,1));
        fill=0x2e;assert(spectrum_bank_write(&memory,7,0,&fill,1));
        uint8_t lcd[10240];
        mk61_service_color_frame frame;
        assert(spectrum_video_mode(&machine)==0x41);
        assert(spectrum_video_strip(&machine,1,0,lcd,&frame));
        assert(frame.width==256 && frame.height==64 && lcd[0]==0x92 && lcd[1]==0x65);
        fill=0x97;assert(spectrum_bank_write(&memory,6,0x001c,&fill,1));
        assert(spectrum_video_strip(&machine,64,0,lcd,&frame));
        assert(frame.width==320 && frame.height==104 && frame.y==8 && lcd[0]==0x97);
        assert(spectrum_video_strip(&machine,64,1,lcd,&frame) && frame.y==112);
        assert(spectrum_video_strip(&machine,64,2,lcd,&frame) && frame.y==216 && frame.height==96);
    }
}

int main(int argc,char** argv) {
    assert(argc==2);
    FILE* file=fopen(argv[1],"rb");assert(file);
    assert(fread(rom,1,sizeof(rom),file)==sizeof(rom));fclose(file);
    tape_test();compressed_page_test();
    for(unsigned model=0;model<3;++model) snapshot_test(model);
    puts("ROM TAP load, TZX pulse/control/CSW, zlib, all SZX banks and both EFF7 renderers PASS");
    return 0;
}
