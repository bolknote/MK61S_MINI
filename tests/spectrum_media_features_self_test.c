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
static unsigned wide_reads;
static bool read_wide(void* raw,uint32_t at,uint8_t* out,uint32_t n) {
    ++wide_reads;
    return read_bytes(raw,at,out,n);
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
    tzx[10]=0xff;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_UNSUPPORTED);

    uint8_t calls[]={'Z','X','T','a','p','e','!',26,1,20,
        0x26,2,0,2,0,4,0, // Call blocks 2 and 4.
        0x23,5,0,         // Then skip both subroutines.
        0x12,90,0,1,0,0x27,
        0x12,60,0,1,0,0x27,
        0x18,16,0,0,0,0,0,0x58,0x1b,0,1,2,0,0,0,1,0,2,0,0,0};
    uint8_t offsets[7*sizeof(spectrum_tape_index)];
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

static void generalized_and_select_test(void) {
    /* Jump to selection 2, using a negative offset. Two pilot repeats,
     * then 3 two-bit symbols (same, forced low, forced high). */
    uint8_t tzx[]={'Z','X','T','a','p','e','!',26,1,20,
        0x23,3,0,
        0x19,38,0,0,0,0,0,1,0,0,0,2,1,3,0,0,0,2,3,
        0,10,0,20,0, 0,2,0,
        1,31,0,0,0, 2,32,0,1,0, 3,33,0,0,0, 0x18,
        0x20,0,0,
        0x28,13,0,2,1,0,3,'E','n','d', 0xfe,0xff,3,'R','u','n',
        0x12,55,0,1,0};
    uint8_t offsets[5*sizeof(spectrum_tape_index)];
    bytes index={offsets,sizeof(offsets)},input={tzx,sizeof(tzx)};
    spectrum_source source={&input,input.size,read_bytes};
    spectrum_tape tape={.index_context=&index,.index_read=read_bytes,.index_write=write_bytes};
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_OK);
    machine.cpu.pc=0x8000;machine.cpu.cyc=0xfffffff0u;tape.playing=true;
    assert(!spectrum_tape_ear(&tape,&machine.cpu) && tape.choices==2 && !tape.playing);
    char text[4];
    assert(spectrum_tape_choice(&tape,1,text,sizeof(text)) && !strcmp(text,"Run"));
    assert(!spectrum_tape_choose(&tape,2,(uint32_t)machine.cpu.cyc));
    assert(spectrum_tape_choose(&tape,1,(uint32_t)machine.cpu.cyc));
    const unsigned lengths[]={10,20,10,20,31,32,1,33};
    const bool levels[]={true,false,true,false,false,false,true,true};
    for(unsigned i=0;i<sizeof(lengths)/sizeof(*lengths);++i) {
        assert(spectrum_tape_ear(&tape,&machine.cpu)==levels[i]);
        assert(tape.deadline==(uint32_t)machine.cpu.cyc+lengths[i]);
        machine.cpu.cyc+=lengths[i];
    }
    assert(!spectrum_tape_ear(&tape,&machine.cpu) && !tape.playing && !tape.fault);
    tzx[14]--;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_FORMAT);
    tzx[14]++;
    tzx[61]=200;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_FORMAT);

    // One-symbol data stream has zero bits per symbol and no packed bytes.
    uint8_t single[]={'Z','X','T','a','p','e','!',26,1,20,
        0x19,17,0,0,0,0,0,0,0,0,0,0,0,3,0,0,0,1,1, 3,11,0};
    input=(bytes){single,sizeof(single)};source.size=input.size;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_OK);
    machine.cpu.cyc=0;tape.playing=true;
    for(unsigned i=0;i<3;++i) {
        assert(spectrum_tape_ear(&tape,&machine.cpu) && tape.deadline==11*(i+1));
        machine.cpu.cyc+=11;
    }
    assert(!spectrum_tape_ear(&tape,&machine.cpu) && !tape.playing && !tape.fault);
}

static void csw_zrle_test(void) {
    enum { PULSES=560, RUN_BYTES=5*PULSES };
    uint8_t rle[RUN_BYTES],scratch[1024];
    static uint8_t backing[SPECTRUM_TAPE_INDEX_BYTES+RUN_BYTES],tzx[RUN_BYTES+50];
    for(unsigned i=0;i<PULSES;++i) {
        unsigned n=1+(i%83)*1000;
        const uint8_t pulse[]={0,(uint8_t)n,(uint8_t)(n>>8),(uint8_t)(n>>16),0};
        memcpy(rle+5*i,pulse,sizeof(pulse));
    }
    const uint8_t header[]={'Z','X','T','a','p','e','!',26,1,20,
        0x18,0,0,0,0,0,0,0xe0,0x67,0x35,2,(uint8_t)PULSES,PULSES>>8,0,0};
    memcpy(tzx,header,sizeof(header));
    unsigned long length=sizeof(tzx)-sizeof(header);
    assert(compress2(tzx+sizeof(header),&length,rle,sizeof(rle),9)==Z_OK);
    tzx[11]=(uint8_t)(length+10);tzx[12]=(uint8_t)((length+10)>>8);
    bytes input={tzx,sizeof(header)+(uint32_t)length},storage={backing,sizeof(backing)};
    spectrum_source source={&input,input.size,read_bytes};
    spectrum_tape tape={.index_context=&storage,.index_read=read_bytes,.index_write=write_bytes,
                        .decode_scratch=scratch};
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_OK);
    assert(tape.decoded_bytes==sizeof(rle));
    assert(!memcmp(backing+SPECTRUM_TAPE_INDEX_BYTES,rle,sizeof(rle)));
    for(unsigned pass=0;pass<2;++pass) {
        spectrum_tape_rewind(&tape);
        machine.cpu.cyc=0;tape.playing=true;
        for(unsigned i=0;i<PULSES;++i) {
            assert(spectrum_tape_ear(&tape,&machine.cpu)==(!(i&1)));
            assert(tape.deadline==machine.cpu.cyc+1+(i%83)*1000);
            machine.cpu.cyc=tape.deadline;
        }
        assert(!spectrum_tape_ear(&tape,&machine.cpu) && !tape.playing && !tape.fault);
    }
    tape.decode_scratch=scratch;tzx[21]++;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_FORMAT);
    tzx[21]--;tzx[input.size-1]^=1;
    assert(spectrum_tape_open(&tape,&source,true)==SPECTRUM_FORMAT);
}

static unsigned ula_delay(unsigned time) {
    static const unsigned delay[]={6,5,4,3,2,1,0,0};
    if(time<14335 || time>=14335+192*224) return 0;
    const unsigned col=(time-14335)%224;
    return col<128?delay[col%8]:0;
}
static void timed_cpu(const uint8_t* program,unsigned bytes,uint16_t pc,unsigned phase,bool pentagon) {
    spectrum_init(&machine,ram,rom);
    memcpy(ram+pc-0x4000,program,bytes);
    machine.pentagon=pentagon;
    machine.cpu.pc=pc;machine.cpu.cyc=UINT32_MAX-11;machine.frame_tstates=phase;
    machine.cpu.hl=0x4200;machine.cpu.de=0x4300;
    machine.cpu.ix=0x4200;machine.cpu.sp=0x4400;
}
static void contention_test(void) {
    const uint8_t nop[]={0},inc[]={0x34},idx[]={0xdd,0x34,0},ldir[]={0xed,0xb0};
    const uint8_t out[]={0xd3,0xfe},bit[]={0xcb,0x46},push[]={0xf5};
    for(unsigned t=14330;t<14571;++t) {
        timed_cpu(nop,sizeof(nop),0x4000,t,false);
        assert(spectrum_run(&machine,1)==4+ula_delay(t));
        timed_cpu(nop,sizeof(nop),0x4000,t,true);
        assert(spectrum_run(&machine,1)==4);
        timed_cpu(inc,sizeof(inc),0x8000,t,false);
        unsigned at=t+4;at+=ula_delay(at)+3;at+=ula_delay(at)+1;at+=ula_delay(at)+3;
        assert(spectrum_run(&machine,1)==at-t);
        timed_cpu(idx,sizeof(idx),0x4000,t,false);
        at=t;at+=ula_delay(at)+4;at+=ula_delay(at)+4;at+=ula_delay(at)+3;
        for(unsigned i=0;i<5;++i) at+=ula_delay(at)+1;
        at+=ula_delay(at)+3;at+=ula_delay(at)+1;at+=ula_delay(at)+3;
        assert(spectrum_run(&machine,1)==at-t);
        timed_cpu(ldir,sizeof(ldir),0x8000,t,false);machine.cpu.bc=2;
        at=t+8;at+=ula_delay(at)+3;at+=ula_delay(at)+3;
        for(unsigned i=0;i<7;++i) at+=ula_delay(at)+1;
        assert(spectrum_run(&machine,1)==at-t);
        timed_cpu(out,sizeof(out),0x8000,t,false);machine.cpu.a=0x43;
        at=t+7;at+=ula_delay(at)+1;at+=ula_delay(at)+3;
        assert(spectrum_run(&machine,1)==at-t && machine.border==3);
        timed_cpu(bit,sizeof(bit),0x8000,t,false);
        at=t+8;at+=ula_delay(at)+3;at+=ula_delay(at)+1;
        assert(spectrum_run(&machine,1)==at-t);
        timed_cpu(push,sizeof(push),0x8000,t,false);machine.cpu.i=0x40;
        at=t+4;at+=ula_delay(at)+1;at+=ula_delay(at)+3;at+=ula_delay(at)+3;
        assert(spectrum_run(&machine,1)==at-t);
    }
    timed_cpu(nop,sizeof(nop),0x4000,14335,false);
    machine.cpu.pc++;machine.cpu.halted=true;
    assert(spectrum_run(&machine,1)==10);
    timed_cpu(nop,sizeof(nop),0x4000,69887,false);
    assert(spectrum_run(&machine,5)==8 && machine.frames==1 && machine.frame_tstates==7);
}

static bool raster_copy(void* context,unsigned strip,const uint8_t* source) {
    uint8_t* part=(uint8_t*)context+strip*SPECTRUM_RASTER_STRIP_BYTES;
    memcpy(part,source,SPECTRUM_RASTER_PACKED_STRIP_BYTES);
    spectrum_raster_expand(part);return true;
}
static unsigned raster_pixel(const uint8_t* frame,unsigned x,unsigned y) {
    const unsigned cells=SPECTRUM_RASTER_STRIP_ROWS*40,cell=(y%SPECTRUM_RASTER_STRIP_ROWS)*40+x/8;
    const uint8_t* part=frame+(y/SPECTRUM_RASTER_STRIP_ROWS)*cells*5;
    const uint8_t* colors=part+cells+cell*4+(part[cell]&(128u>>(x&7))?2:0);
    return colors[0]|colors[1]<<8;
}
static void raster_test(void) {
    static uint8_t frame[SPECTRUM_RASTER_BYTES],buffer[SPECTRUM_RASTER_BYTES/SPECTRUM_RASTER_STRIPS];
    const uint8_t out[]={0xd3,0xfe,0x76};
    const unsigned screen=14336;
    timed_cpu(out,sizeof(out),0x8000,screen-32*224-16,false);
    machine.cpu.a=2;
    spectrum_raster_begin(&machine,buffer,frame,raster_copy);
    spectrum_run(&machine,32*224);
    assert(machine.frames==0 && machine.video_cell>=32*40);
    assert(raster_pixel(frame,8,0)==0 && raster_pixel(frame,16,0)==spectrum_color(2));
    assert(raster_pixel(frame,0,1)==spectrum_color(2));

    const uint8_t store[]={0x32,0x02,0x58,0x76};
    timed_cpu(store,sizeof(store),0x8000,screen-5,false);
    machine.cpu.a=2;
    ram[0]=ram[1]=ram[2]=ram[256+2]=255;
    ram[6144]=ram[6145]=ram[6146]=4;
    spectrum_raster_begin(&machine,buffer,frame,raster_copy);
    spectrum_run(&machine,69888-machine.frame_tstates);
    assert(raster_pixel(frame,32,32)==spectrum_color(4));
    assert(raster_pixel(frame,40,32)==spectrum_color(4));
    assert(raster_pixel(frame,48,32)==spectrum_color(4));
    assert(raster_pixel(frame,48,33)==spectrum_color(2));
    spectrum_raster_end(&machine);
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
        const spectrum_inflate_output out={.first=result,.second=result+12288,.split=12288,.limit=sizeof(result)};
        unsigned used=0;
        assert(spectrum_inflate(&source,0,source.size,&out,&used)==SPECTRUM_OK && used==sizeof(in));
        assert(!memcmp(in,result,sizeof(in)));
        encoded[source.size-1]^=1;
        assert(spectrum_inflate(&source,0,source.size,&out,&used)==SPECTRUM_FORMAT);
    }
}

static uint8_t wide_byte(unsigned bank,unsigned offset) {
    return (uint8_t)(offset*7u+(offset>>8)*11u+bank*19u);
}

static void wide_scanlines(void) {
    for(unsigned bank=4;bank<=7;++bank) {
        for(unsigned offset=0;offset<sizeof(workspace);++offset) workspace[offset]=wide_byte(bank,offset);
        assert(spectrum_bank_write(&memory,bank,0,workspace,sizeof(workspace)));
    }
    memory.io.read=read_wide;
    for(unsigned screen=0;screen<2;++screen) {
        const unsigned bank=screen?7:5;
        assert(spectrum_memory_page(&memory,screen?8:0));
        machine.frames=screen?16:0;
        for(unsigned strip=0;strip<3;++strip) {
            uint8_t lcd[10240];
            mk61_service_color_frame frame;
            const unsigned rows=strip<2?104:96;
            wide_reads=0;
            assert(spectrum_video_strip(&machine,64,strip,lcd,&frame));
            assert(frame.width==320 && frame.height==rows && frame.y==8+104*strip);
            assert(wide_reads<=54); // three areas, two planes, eight phases and attributes
            for(unsigned line=0;line<rows;++line) {
                const unsigned y=104*strip+line;
                const unsigned row=y<64?y:y<256?y-64:y-256;
                const unsigned page=y>=64 && y<256?bank:bank-1;
                const unsigned bitmap=(row&7)*256+(row&56)*4+(row&192)*32+(y>=256?0x1800:0);
                const unsigned attrs=(y<64?0x1000:y<256?0x1800:0x1300)+(row/8)*32;
                for(unsigned x=0;x<40;++x) {
                    const unsigned column=x<4?28+x:x<36?8192+x-4:8+x-36;
                    assert(lcd[line*40+x]==wide_byte(page,bitmap+column));
                    if(line%8) continue;
                    const unsigned attr=wide_byte(page,attrs+column),bright=(attr&64)>>3;
                    unsigned ink=(attr&7)|bright,paper=((attr>>3)&7)|bright;
                    if((attr&128) && screen) {const unsigned t=ink;ink=paper;paper=t;}
                    assert(frame.tiles[(line/8)*40+x]==(paper<<4|ink));
                }
            }
        }
    }
    memory.io.read=read_bytes;
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
        wide_scanlines();
    }
}

int main(int argc,char** argv) {
    assert(argc==2);
    FILE* file=fopen(argv[1],"rb");assert(file);
    assert(fread(rom,1,sizeof(rom),file)==sizeof(rom));fclose(file);
    tape_test();generalized_and_select_test();csw_zrle_test();compressed_page_test();
    contention_test();raster_test();
    for(unsigned model=0;model<3;++model) snapshot_test(model);
    puts("ROM TAP load, TZX Generalized/Select/CSW, ULA bus timing and scanlines, zlib, SZX and EFF7 PASS");
    return 0;
}
