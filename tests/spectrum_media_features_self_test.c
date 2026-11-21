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

static void rom_save_block(uint8_t flag,const uint8_t* data,unsigned size) {
    const unsigned at=0x9000;
    memcpy(ram+at-0x4000,data,size);
    machine.cpu.pc=0x04c2; // Original SA-BYTES routine used by BASIC SAVE.
    machine.cpu.de=(uint16_t)size;machine.cpu.ix=at;machine.cpu.a=flag;
    machine.cpu.sp=0xbffe;machine.cpu.halted=false;
    ram[0x7ffe]=0;ram[0x7fff]=0x80;ram[0x4000]=0x76;
    for(unsigned step=0;!machine.cpu.halted && step<16000;++step) spectrum_run(&machine,2048);
    assert(machine.cpu.halted && machine.cpu.pc==0x8001);
}
static void tape_record_test(void) {
    uint8_t saved[1024],data[149];
    for(unsigned i=0;i<sizeof(data);++i) data[i]=(uint8_t)(37*i);
    const uint8_t header[]={3,'T','A','P','E',' ',' ',' ',' ',' ',' ',sizeof(data),0,0,144,0,0};
    bytes storage={saved,sizeof(saved)};
    spectrum_tape_recorder recorder={.context=&storage,.write=write_bytes,.capacity=sizeof(saved)};
    spectrum_init(&machine,ram,rom);
    machine.mic_context=&recorder;machine.mic=spectrum_tape_mic;
    rom_save_block(0,header,sizeof(header));
    rom_save_block(255,data,sizeof(data)); // Includes a full PSRAM write buffer and an unaligned tail.
    spectrum_tape_record_finish(&recorder);
    assert(!recorder.fault && recorder.size==sizeof(header)+sizeof(data)+8);
    assert(saved[0]==sizeof(header)+2 && !saved[1] && !saved[2] && !memcmp(saved+3,header,sizeof(header)));
    const unsigned next=sizeof(header)+4;
    assert(saved[next]==sizeof(data)+2 && !saved[next+1] && saved[next+2]==255);
    assert(!memcmp(saved+next+3,data,sizeof(data)));
    uint8_t checksum=0;for(unsigned i=2;i<next;++i) checksum^=saved[i];assert(!checksum);
    for(unsigned i=next+2;i<recorder.size;++i) checksum^=saved[i];assert(!checksum);
    const spectrum_source source={&storage,recorder.size,read_bytes};
    spectrum_tape playback={0};
    assert(spectrum_tape_open(&playback,&source,false)==SPECTRUM_OK);
    puts("Original ROM SAVE writes playable TAP header and data blocks from MIC timing: PASS");
}

static void run_basic_frames(unsigned count) {
    while(count--) spectrum_run(&machine,SPECTRUM_FRAME_TSTATES);
}
static void basic_key(unsigned key) {
    uint8_t keys[32]={0};keys[key/8]=(uint8_t)(1u<<(key&7));
    spectrum_keyboard(&machine,keys);run_basic_frames(5);
    keys[key/8]=0;spectrum_keyboard(&machine,keys);run_basic_frames(5);
}
static void basic_keys(const char* keys) {
    for(;*keys;++keys) basic_key((unsigned char)*keys);
}
static void basic_save_load_test(void) {
    uint8_t tap[128];bytes storage={tap,sizeof(tap)};
    spectrum_init(&machine,ram,rom);run_basic_frames(250);
    // The 48K editor expands P to PRINT, S to SAVE and J to LOAD in K mode.
    basic_keys("10p\"x\"\r");
    spectrum_tape_recorder recorder={.context=&storage,.write=write_bytes,.capacity=sizeof(tap)};
    machine.mic_context=&recorder;machine.mic=spectrum_tape_mic;
    basic_keys("s\"pico\"\r");
    run_basic_frames(35);basic_key('x');run_basic_frames(500);
    spectrum_tape_record_finish(&recorder);
    const uint8_t line[]={0,10,5,0,0xf5,'"','x','"',13};
    assert(!recorder.fault && recorder.size==34);
    assert(!memcmp(tap+4,"pico      ",10) && !memcmp(tap+24,line,sizeof(line)));

    spectrum_init(&machine,ram,rom);run_basic_frames(250);
    spectrum_tape playback={0};
    const spectrum_source source={&storage,recorder.size,read_bytes};
    assert(spectrum_tape_open(&playback,&source,false)==SPECTRUM_OK);
    machine.ear_context=&playback;machine.ear=spectrum_tape_ear;
    playback.playing=true;
    basic_keys("j\"\"\r");run_basic_frames(550);
    const unsigned prog=(ram[0x1c53]|(ram[0x1c54]<<8))-0x4000;
    assert(prog<=sizeof(ram)-sizeof(line) && !memcmp(ram+prog,line,sizeof(line)));
    puts("48K BASIC keyboard SAVE and LOAD round-trip of a tokenized program PASS");
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

static void raster_128_test(void) {
    static uint8_t frame[SPECTRUM_RASTER_BYTES],buffer[SPECTRUM_RASTER_STRIP_BYTES];
    const uint8_t program[]={
        0x32,0x02,0xd8, // Change bank 5 through its upper-window alias.
        0x3e,0x0f,0xed,0x79, // Show bank 7 and map it into the upper window.
        0x3e,0x06,0x32,0x0b,0xd8, // Change an attribute after the beam passed it.
        0x3e,0x2f,0xed,0x79, // Lock paging with the shadow screen active.
        0xaf,0xed,0x79,0x76 // Attempt to flip back, then HALT.
    };
    bytes backing={psram,sizeof(psram)};
    const spectrum_memory_io io={&backing,read_bytes,write_bytes,clear_bytes};
    uint8_t* tails[]={fixed+15360,fixed+31744};
    uint8_t* runs[]={pages,pages+8192,pages+10240,pages+14336};
    spectrum_init(&machine,ram,rom);
    assert(spectrum_memory_init_fragmented(&memory,fixed,fixed+16384,tails,runs,8,io));
    // Force the ULA to evict CPU-visible pages during a long shadow capture.
    memory.page_count=2;
    spectrum_attach_memory(&machine,&memory);
    assert(spectrum_memory_page(&memory,5));
    spectrum_refresh_map(&machine);
    memset(workspace,255,SPECTRUM_BITMAP_BYTES);
    memset(workspace+SPECTRUM_BITMAP_BYTES,4,SPECTRUM_ATTRIBUTE_BYTES);
    assert(spectrum_bank_write(&memory,5,0,workspace,6912));
    memset(workspace+SPECTRUM_BITMAP_BYTES,2,SPECTRUM_ATTRIBUTE_BYTES);
    assert(spectrum_bank_write(&memory,7,0,workspace,6912));
    assert(spectrum_bank_write(&memory,2,0,program,sizeof(program)));
    machine.cpu.pc=0x8000;machine.cpu.a=5;machine.cpu.bc=0x3ffd;
    machine.cpu.cyc=UINT32_MAX-11;machine.frame_tstates=14362+228-5;
    spectrum_raster_begin(&machine,buffer,frame,raster_copy);
    spectrum_run(&machine,SPECTRUM_128_FRAME_TSTATES-machine.frame_tstates);
    assert(!memory.fault && machine.video_bytes && machine.frames==1);
    assert(memory.locked && memory.paging==0x2f);
    assert(raster_pixel(frame,32+8*31,32)==spectrum_color(4));
    assert(raster_pixel(frame,32+8*2,33)==spectrum_color(4));
    assert(raster_pixel(frame,32+8*6,33)==spectrum_color(4));
    assert(raster_pixel(frame,32+8*7,33)==spectrum_color(2));
    assert(raster_pixel(frame,32+8*11,33)==spectrum_color(2));
    assert(raster_pixel(frame,32+8*11,34)==spectrum_color(6));
    assert(raster_pixel(frame,32+8*31,34)==spectrum_color(2));
    assert(raster_pixel(frame,32+8*31,223)==spectrum_color(2));
    assert(memory.cache[0x1802]==5);
    for(unsigned page=0;page<16;++page)
        assert(machine.cpu.read_pages[48+page]==spectrum_memory_cached_byte(&memory,7*16384+page*1024,false));
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
    static uint8_t captured[2*SPECTRUM_BANK_BYTES];
    bytes copy={captured,sizeof(captured)};
    const spectrum_memory_io capture_io={&copy,read_bytes,write_bytes,clear_bytes};
    for(unsigned bank=4;bank<=7;++bank) {
        for(unsigned offset=0;offset<sizeof(workspace);++offset) workspace[offset]=wide_byte(bank,offset);
        assert(spectrum_bank_write(&memory,bank,0,workspace,sizeof(workspace)));
    }
    memory.io.read=read_wide;
    for(unsigned screen=0;screen<2;++screen) {
        const unsigned bank=screen?7:5;
        assert(spectrum_memory_page(&memory,screen?8:0));
        machine.frames=screen?16:0;
        uint8_t lcd[SPECTRUM_VIDEO_WORK_BYTES],frozen[SPECTRUM_VIDEO_WORK_BYTES];
        spectrum_video_snapshot snapshot={.io=&capture_io};
        memset(captured,0xcd,sizeof(captured));
        assert(spectrum_video_capture(&machine,SPECTRUM_VIDEO_WIDE,lcd,&snapshot));
        for(unsigned strip=0;strip<SPECTRUM_WIDE_STRIPS;++strip) {
            mk61_service_color_frame frame, saved;
            const unsigned first=strip*SPECTRUM_WIDE_STRIP_ROWS;
            const unsigned rows=strip+1==SPECTRUM_WIDE_STRIPS?304-first:SPECTRUM_WIDE_STRIP_ROWS;
            wide_reads=0;
            assert(spectrum_video_strip(&machine,64,strip,lcd,&frame));
            assert(frame.width==320 && frame.height==rows && frame.y==8+first);
            assert((frame.format&~MK61_COLOR_PRESERVE_OUTSIDE)==MK61_COLOR_INDEX4);
            assert(wide_reads<=6); // two attribute spans and up to four pages of bitmap
            assert(spectrum_memory_page(&memory,screen?0:8));
            machine.frames^=16;
            assert(spectrum_video_snapshot_strip(&machine,&snapshot,SPECTRUM_VIDEO_WIDE,strip,frozen,&saved));
            assert(frame.pixel_bytes==saved.pixel_bytes && !memcmp(lcd,frozen,frame.pixel_bytes));
            machine.frames^=16;
            assert(spectrum_memory_page(&memory,screen?8:0));
            const spectrum_video_damage damage={2,14,13,rows<21?rows:21};
            spectrum_pentagon_clip(SPECTRUM_VIDEO_WIDE,&damage,frozen,&saved);
            assert(saved.x==40 && saved.width==240 && saved.y==21+first);
            uint8_t patch[120*8];
            assert(spectrum_pentagon_patch(&machine,SPECTRUM_VIDEO_WIDE,strip,&damage,patch,0));
            assert(saved.pixel_bytes==120*(damage.bottom-13u));
            assert(!memcmp(patch,frozen,saved.pixel_bytes));
            for(unsigned line=0;line<rows;++line) {
                const unsigned y=first+line;
                const unsigned row=y<64?y:y<256?y-64:y-256;
                const unsigned page=y>=64 && y<256?bank:bank-1;
                const unsigned bitmap=(row&7)*256+(row&56)*4+(row&192)*32+(y>=256?0x1800:0);
                const unsigned attrs=(y<64?0x1000:y<256?0x1800:0x1300)+(row/8)*32;
                for(unsigned x=0;x<320;++x) {
                    const unsigned source=(6*x+3)/5,cell=source/8;
                    const unsigned column=cell<8?24+cell:cell<40?8192+cell-8:8+cell-40;
                    const unsigned attr=wide_byte(page,attrs+column),bright=(attr&64)>>3;
                    unsigned ink=(attr&7)|bright,paper=((attr>>3)&7)|bright;
                    if((attr&128) && screen) {const unsigned t=ink;ink=paper;paper=t;}
                    const unsigned mask=128u>>(source&7);
                    const unsigned expect=wide_byte(page,bitmap+column)&mask?ink:paper;
                    const unsigned sample=lcd[line*160+x/2];
                    assert((x&1?sample&15:sample>>4)==expect);
                }
            }
        }
    }
    memory.io.read=read_bytes;

    static const uint8_t attrs[768];
    for(unsigned bank=6;bank<=7;++bank) {
        for(unsigned plane=0;plane<16384;plane+=8192) {
            assert(spectrum_bank_write(&memory,bank,plane+0x1000,attrs,256));
            assert(spectrum_bank_write(&memory,bank,plane+0x1300,attrs,192));
            assert(spectrum_bank_write(&memory,bank,plane+0x1800,attrs,768));
        }
    }
    const uint8_t flash=0xc7;
    // The lower plane's unscanned columns must not dirty the LCD.
    assert(spectrum_bank_write(&memory,6,0x1000,&flash,1));
    assert(spectrum_bank_write(&memory,7,0x1800+32+24,&flash,1));
    assert(spectrum_bank_write(&memory,7,0x3800+64+31,&flash,1));
    spectrum_video_damage dirty[SPECTRUM_WIDE_STRIPS]={0};
    spectrum_wide_gap gaps[SPECTRUM_WIDE_STRIPS];
    uint8_t strip_work[2*sizeof(attrs)];
    assert(spectrum_pentagon_flash(&machine,strip_work,dirty,gaps));
    const unsigned active_strip=64/SPECTRUM_WIDE_STRIP_ROWS;
    for(unsigned strip=0;strip<SPECTRUM_WIDE_STRIPS;++strip) {
        if(strip==active_strip) assert(dirty[strip].left==0 && dirty[strip].right==14 &&
                            dirty[strip].top==8 && dirty[strip].bottom==24);
        else assert(!dirty[strip].bottom && !gaps[strip].right);
    }
    assert(gaps[active_strip].left==1 && gaps[active_strip].right==13);
    memset(dirty,0,sizeof(dirty));
    spectrum_video_include_cell(&dirty[active_strip],6,0,1);
    assert(spectrum_pentagon_flash(&machine,strip_work,dirty,gaps));
    assert(gaps[active_strip].left==7 && gaps[active_strip].right==13); // Keep the guest's write in the left window.
}

static void sinclair128(const char* rom0,const char* rom1) {
    spectrum_init(&machine,ram,rom);
    bytes backing={psram,sizeof(psram)};
    const spectrum_memory_io io={&backing,read_bytes,write_bytes,clear_bytes};
    uint8_t* tails[]={fixed+15360,fixed+31744};
    uint8_t* runs[]={pages,pages+8192,pages+10240,pages+14336};
    FILE* file=fopen(rom0,"rb");assert(file);
    assert(fread(psram+SPECTRUM_ROM_BASE,1,16384,file)==16384);fclose(file);
    file=fopen(rom1,"rb");assert(file);
    assert(fread(psram+SPECTRUM_ROM_BASE+16384,1,16384,file)==16384);fclose(file);
    assert(spectrum_memory_init_fragmented(&memory,fixed,fixed+16384,tails,runs,8,io));
    spectrum_attach_memory(&machine,&memory);
    assert(spectrum_model(&machine)==SPECTRUM_128 && spectrum_frame_cycles(&machine)==70908);
    assert(machine.ay.clk==1773400 && machine.ay2.clk==1773400 && !memory.paging);
    spectrum_run(&machine,200*70908u);
    assert(machine.frames==200 && !memory.fault);
    uint8_t pixels[6144],attrs[768];spectrum_video(&machine,pixels,attrs);
    unsigned drawn=0;for(unsigned i=0;i<sizeof(pixels);++i) drawn+=pixels[i]!=0;
    assert(drawn>100); // The original ROM drew its start menu.

    machine.cpu.port_out(&machine.cpu,0x3ffd,0xc1); // Partial address decode, high bits unused.
    machine.cpu.write_byte(&machine,0xc000,0);     // NOP in contended bank 1.
    machine.cpu.iff1=machine.cpu.halted=false;
    for(unsigned y=0;y<192;++y) for(unsigned x=0;x<228;++x) {
        machine.cpu.pc=0xc000;machine.cpu.cyc=UINT32_MAX-8;machine.frame_tstates=14361+y*228+x;
        unsigned delay=x<128 && (x&7)<6?6-(x&7):0;
        assert(spectrum_run(&machine,1)==4+delay);
    }
    machine.cpu.port_out(&machine.cpu,0x7ffd,0x0a);
    machine.cpu.write_byte(&machine,0xc000,0);
    machine.cpu.pc=0xc000;machine.frame_tstates=14361;
    assert(spectrum_run(&machine,1)==4); // Fixed and switched views of bank 2 are uncontended.
    const uint8_t display[]={0x42,0x81};
    assert(spectrum_bank_write(&memory,7,0,display,2));
    machine.cpu.io_at=machine.frame_origin+14364;
    assert(spectrum_port_in(&machine,0x00ff)==display[0]);
    machine.cpu.io_at+=2;assert(spectrum_port_in(&machine,0x00ff)==display[1]);
    machine.cpu.port_out(&machine.cpu,0x7ffd,0xfb);
    assert(memory.locked);
    machine.cpu.port_out(&machine.cpu,0x7ffd,0);
    assert(memory.paging==0xfb);
    assert(machine.cpu.read_byte(&machine,0)==psram[SPECTRUM_ROM_BASE+16384]);

    machine.frame_tstates=70000;
    spectrum_szx_writer writer;
    const uint32_t count=spectrum_szx_save(&writer,&machine);
    assert(writer.banks==8 && writer.header[6]==2 && spectrum_szx_read(&writer,0,packed,count));
    bytes snapshot={packed,count};const spectrum_source source={&snapshot,count,read_bytes};
    assert(spectrum_load_szx(&machine,&source,NULL,NULL)==SPECTRUM_OK);
    assert(memory.paging==0xfb && memory.locked && machine.frame_tstates==70000);
    uint8_t restored[2];assert(spectrum_bank_read(&memory,7,0,restored,2));
    assert(!memcmp(restored,display,sizeof(restored)));

    // A resumed audio producer crosses 32-bit guest and audio-counter wrap.
    machine.cpu.cyc=UINT32_MAX-4;
    spectrum_sound_begin(&machine,NULL,NULL);
    const uint32_t start=machine.sound.time;
    for(unsigned i=0;i<100;++i) {
        machine.cpu.cyc+=3547;spectrum_sound_publish(&machine);
    }
    assert(atomic_load(&machine.sound.produced)-start==(354700u*35000ull+35468)/35469);
    spectrum_sound_end(&machine);
    puts("Sinclair 128K ROM boot, exact ULA contention, shadow bus, paging/lock, SZX and audio timeline PASS");
}

static void timex_hicolor(void) {
    spectrum_init(&machine,ram,rom);machine.extensions|=SPECTRUM_TIMEX;
    machine.cpu.port_out(&machine.cpu,0x31ff,2);
    assert(spectrum_port_in(&machine,0x50ff)==2 && spectrum_video_mode(&machine)==SPECTRUM_VIDEO_HICOLOR);
    for(unsigned i=0;i<6144;++i) {ram[i]=(uint8_t)(i*17);ram[8192+i]=(uint8_t)(i*19);}
    uint8_t lcd[SPECTRUM_VIDEO_WORK_BYTES];
    machine.frames=16;
    bytes backing={packed,32768};const spectrum_memory_io io={&backing,read_bytes,write_bytes,clear_bytes};
    spectrum_video_snapshot saved={.io=&io};
    assert(spectrum_video_capture(&machine,SPECTRUM_VIDEO_HICOLOR,lcd,&saved));
    memset(ram,0,sizeof(ram));machine.frames=0;machine.cpu.port_out(&machine.cpu,0xff,0);
    for(unsigned strip=0;strip<3;++strip) {
        mk61_service_color_frame frame;
        assert(spectrum_video_snapshot_strip(&machine,&saved,SPECTRUM_VIDEO_HICOLOR,strip,lcd,&frame));
        assert(frame.width==256 && frame.height==64 && frame.y==64+64*strip);
        assert((frame.format&~MK61_COLOR_PRESERVE_OUTSIDE)==MK61_COLOR_CELL565);
        for(unsigned y=0;y<64;++y) for(unsigned x=0;x<32;++x) {
            const unsigned offset=strip*2048+(y&7)*256+(y&56)*4+x,at=y*32+x;
            const unsigned color=(uint8_t)(offset*19),bright=(color&64)>>3;
            unsigned paper=((color>>3)&7)|bright,ink=(color&7)|bright;
            if(color&128) {const unsigned t=paper;paper=ink;ink=t;}
            assert(frame.pixels[at]==(uint8_t)(offset*17));
            const uint8_t* pair=frame.tiles+4*at;
            assert((pair[0]|pair[1]<<8)==spectrum_color(paper) && (pair[2]|pair[3]<<8)==spectrum_color(ink));
        }
    }
    puts("Timex 8x1 attributes, exact native 256x192 pixels and immutable PSRAM capture PASS");
}

static void timex_hires(void) {
    spectrum_init(&machine,ram,rom);machine.extensions|=SPECTRUM_TIMEX;
    machine.cpu.port_out(&machine.cpu,0x31ff,22); // Red ink, cyan paper.
    assert(spectrum_port_in(&machine,0x50ff)==22 && spectrum_video_mode(&machine)==SPECTRUM_VIDEO_HIRES);
    for(unsigned i=0;i<6144;++i) {ram[i]=(uint8_t)(i*17);ram[8192+i]=(uint8_t)(i*19+1);}
    uint8_t lcd[SPECTRUM_VIDEO_WORK_BYTES];
    bytes backing={packed,32768};const spectrum_memory_io io={&backing,read_bytes,write_bytes,clear_bytes};
    spectrum_video_snapshot saved={.io=&io};
    assert(spectrum_video_capture(&machine,SPECTRUM_VIDEO_HIRES,lcd,&saved));
    assert(saved.border==spectrum_color(5));
    memset(ram,0,sizeof(ram));machine.cpu.port_out(&machine.cpu,0xff,6);
    for(unsigned strip=0;strip<3;++strip) {
        mk61_service_color_frame frame;
        assert(spectrum_video_snapshot_strip(&machine,&saved,SPECTRUM_VIDEO_HIRES,strip,lcd,&frame));
        assert(frame.x==0 && frame.width==320 && frame.height==64 && frame.y==64+64*strip);
        assert(frame.format==(MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE) && !frame.tile_bytes);
        assert(frame.palette[0]==spectrum_color(5) && frame.palette[8]==spectrum_color(2));
        for(unsigned y=0;y<64;++y) for(unsigned x=0;x<320;++x) {
            const unsigned offset=strip*2048+(y&7)*256+(y&56)*4;
            unsigned expected=0;
            for(unsigned step=0;step<8;++step) {
                const unsigned source=(8*x+step)/5,i=offset+(source>>4);
                const uint8_t byte=(source&8)?(uint8_t)(i*19+1):(uint8_t)(i*17);
                expected+=(byte>>(7-(source&7)))&1;
            }
            const uint8_t pair=frame.pixels[y*160+x/2];
            assert(((pair>>((x&1)?0:4))&15)==expected);
        }
    }
    machine.cpu.port_out(&machine.cpu,0xff,22);machine.cpu.pc=0x8000;
    spectrum_szx_writer writer;
    const unsigned size=spectrum_szx_save(&writer,&machine);
    assert(size && size<=sizeof(packed) && spectrum_szx_read(&writer,0,packed,size));
    bytes file={packed,size};const spectrum_source source={&file,size,read_bytes};
    spectrum_reset(&machine);
    assert(spectrum_load_szx(&machine,&source,workspace,workspace+12288)==SPECTRUM_OK);
    assert(spectrum_video_mode(&machine)==SPECTRUM_VIDEO_HIRES && machine.timex_mode==22);

    memset(packed,0,32+54+3*(16384+3));
    packed[30]=54;packed[33]=0x80;packed[34]=14;packed[36]=22;
    const unsigned pages[]={8,4,5};
    for(unsigned i=0;i<3;++i) {
        uint8_t* block=packed+32+54+i*(16384+3);
        block[0]=block[1]=255;block[2]=(uint8_t)pages[i];
    }
    file.size=32+54+3*(16384+3);
    const spectrum_source z80={&file,file.size,read_bytes};
    unsigned model;
    assert(spectrum_z80_model(&z80,&model)==SPECTRUM_OK && model==SPECTRUM_TC2048);
    assert(spectrum_load_z80(&machine,&z80)==SPECTRUM_OK && machine.timex_mode==22);
    packed[36]=7;
    assert(spectrum_load_z80(&machine,&z80)==SPECTRUM_UNSUPPORTED);
    puts("Timex HiRes: interleaved columns, exact 8-to-5 coverage, frozen palette and SZX/Z80 restore PASS");
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
    machine.sound.selected=1;machine.ay2.adr=13;
    PSG_writeReg(&machine.ay2,0,123);PSG_writeReg(&machine.ay2,8,15);
    if(model==1) {
        machine.disk.spi.io=(spectrum_disk_io){.context=&backing,.bytes=1048576,.read=read_bytes,.readonly=true};
        assert(spectrum_disk_mode(&machine,SPECTRUM_DISK_DIVMMC));
        for(unsigned i=0;i<128*1024;++i)psram[SPECTRUM_DIV_RAM+i]=(uint8_t)((i>>9)^i);
        assert(spectrum_disk_out(&machine,0xe3,0xc5));
        spectrum_disk_write_memory(&machine,0x2310,0xa7);
        spectrum_spi* card=&machine.disk.spi;
        card->idle=false;card->selected=true;card->high_capacity=true;card->data_mode=1;
        card->cursor=50;card->block[49]=0x23;card->reads=77;machine.disk.spi_data=0x17;
    }
    spectrum_szx_writer writer;
    const unsigned size=spectrum_szx_save(&writer,&machine);
    assert(size && size<=sizeof(packed));
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
    if(model==1) {
        machine.disk.spi.io.bytes+=512;
        assert(spectrum_load_szx(&machine,&source,workspace,workspace+12288)==SPECTRUM_MEDIA);
        machine.disk.spi.io.bytes-=512;
    }
    assert(spectrum_load_szx(&machine,&source,workspace,workspace+12288)==SPECTRUM_OK);
    assert(machine.cpu.pc==0xbaca && machine.cpu.a==0x99 && machine.cpu.bc_==0x1234 &&
        machine.cpu.mem_ptr==0x4444 && machine.cpu.halted && !machine.cpu.iff1 && machine.cpu.iff2);
    assert(machine.frame_tstates==164 && machine.border==6 && machine.beeper &&
        machine.ulaplus_mode==1 && machine.ulaplus_palette[31]==0x98);
    assert(machine.ay.adr==7 && machine.ay.reg[0]==89);
    assert(machine.sound.selected==1 && machine.sound.selected_reg[1]==13 &&
           machine.ay2.adr==13 && machine.ay2.reg[0]==123 && machine.ay2.reg[8]==15);
    if(model==1) {
        assert(machine.disk.control==0xc5 && machine.disk.mapped && machine.disk.spi_data==0x17);
        assert(!machine.disk.spi.idle && machine.disk.spi.selected && machine.disk.spi.reads==77);
        assert(spectrum_spi_transfer(&machine.disk.spi,255)==0x23);
        for(unsigned i=0;i<128*1024;++i)
            assert(psram[SPECTRUM_DIV_RAM+i]==(i==5*8192+0x310?0xa7:(uint8_t)((i>>9)^i)));
    }
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
        assert(spectrum_video_mode(&machine)==SPECTRUM_VIDEO_16C);
        assert(spectrum_video_strip(&machine,1,0,lcd,&frame));
        assert(frame.width==256 && frame.height==64 && lcd[0]==0x92 && lcd[1]==0x65);
        uint8_t expected[256*64/2];
        bytes copy={packed,2*SPECTRUM_BANK_BYTES};
        const spectrum_memory_io capture_io={&copy,read_bytes,write_bytes,clear_bytes};
        spectrum_video_snapshot captured={.io=&capture_io};
        memset(packed,0xcd,copy.size);
        assert(spectrum_video_capture(&machine,SPECTRUM_VIDEO_16C,lcd,&captured));
        for(unsigned bank=0;bank<2;++bank) for(unsigned offset=6144;offset<8192;++offset)
            assert(packed[bank*SPECTRUM_BANK_BYTES+offset]==0xcd);
        for(unsigned strip=0;strip<3;++strip) {
            assert(spectrum_video_strip(&machine,1,strip,lcd,&frame));
            memcpy(expected,lcd,sizeof(expected));
            assert(spectrum_video_snapshot_strip(&machine,&captured,1,strip,lcd,&frame));
            assert(!memcmp(expected,lcd,sizeof(expected)));
            const spectrum_video_damage damage={0,5,0,13};
            spectrum_pentagon_clip(SPECTRUM_VIDEO_16C,&damage,lcd,&frame);
            uint8_t patch[20*13];
            assert(spectrum_pentagon_patch(&machine,SPECTRUM_VIDEO_16C,strip,&damage,patch,0));
            assert(frame.pixel_bytes==sizeof(patch) && !memcmp(patch,lcd,sizeof(patch)));
        }
        assert(!spectrum_video_strip(&machine,64,SPECTRUM_WIDE_STRIPS,lcd,&frame));
        wide_scanlines();
    }
}

int main(int argc,char** argv) {
    assert(argc==4);
    FILE* file=fopen(argv[1],"rb");assert(file);
    assert(fread(rom,1,sizeof(rom),file)==sizeof(rom));fclose(file);
    tape_test();tape_record_test();basic_save_load_test();generalized_and_select_test();csw_zrle_test();compressed_page_test();
    contention_test();raster_test();raster_128_test();
    for(unsigned model=0;model<3;++model) snapshot_test(model);
    sinclair128(argv[2],argv[3]);timex_hicolor();timex_hires();
    puts("ROM TAP load, TZX Generalized/Select/CSW, ULA bus timing and scanlines, zlib, SZX and EFF7 PASS");
    return 0;
}
