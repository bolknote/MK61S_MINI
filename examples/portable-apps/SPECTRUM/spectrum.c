#include "spectrum.h"
#include <string.h>

static bool low_ram(const spectrum_memory* m) {
    return SPECTRUM_HAS_PENTAGON && m && m->extended && (m->control&8) && !m->overlay;
}
static bool mapped_disk(const spectrum* s) {
    return s->disk.mapped && (s->disk.cache || s->disk.direct_rom[s->disk.mode] ||
        (s->memory && (s->memory->rom_banks[0] || s->memory->paged_rom)));
}
void spectrum_refresh_map(spectrum* s) {
    z80* z=&s->cpu;
    z->contention_mask=spectrum_is_128(s) && (s->memory->paging&1)?0x4000:0xc000;
    if(s->memory && s->memory->paged_rom)s->rom=NULL;
    if(s->memory && s->memory->rom_banks[0]) s->rom=s->memory->rom;
    z->read_map[0]=mapped_disk(s)?(s->disk.mode==SPECTRUM_DISK_BETA?s->disk.direct_rom[SPECTRUM_DISK_BETA]:NULL):
        low_ram(s->memory)?NULL:s->rom;
    z->write_map[0]=NULL;
    for(unsigned i=1;i<3;++i) {
        uint8_t* bytes=s->memory?spectrum_memory_fixed(s->memory,i==1?5:2):s->ram+(i-1)*16384;
        z->read_map[i]=z->write_map[i]=bytes;
    }
    z->read_map[3]=s->memory?spectrum_memory_mapped(s->memory,false):s->ram+32768;
    z->write_map[3]=s->memory?spectrum_memory_mapped(s->memory,true):s->ram+32768;
    spectrum_memory_map_pages(s->memory,z->read_pages,z->write_pages);
    spectrum_disk_map_pages(s,z->read_pages,z->write_pages);
    for(unsigned window=0;window<4;++window) for(unsigned page=0;page<16;++page) {
        const unsigned i=window*16+page;
        if(z->read_map[window]) z->read_pages[i]=z->read_map[window]+page*1024;
        if(z->write_map[window]) z->write_pages[i]=z->write_map[window]+page*1024;
    }
}

static uint8_t read_byte(void* raw,uint16_t address) {
    spectrum* s=raw;
    if(address<0x4000 && mapped_disk(s)) return spectrum_disk_read_memory(s,address);
    if(!s->memory) return address<0x4000?s->rom[address]:s->ram[address-0x4000];
    if(address<0x4000 && !s->memory->paged_rom && !low_ram(s->memory)) return s->rom[address];
    const uint8_t* value=spectrum_memory_byte(s->memory,address,false);
    if(address<0x4000 || address>=0xc000) {
        if(s->memory->fault) s->cpu.ldir_until=0;
        spectrum_refresh_map(s);
    }
    return value?*value:255;
}
static void write_byte(void* raw,uint16_t address,uint8_t value) {
    spectrum* s=raw;
    if(address<0x4000 && !low_ram(s->memory)) {
        spectrum_disk_write_memory(s,address,value);return;
    }
    if(!s->memory) {
        s->ram[address-0x4000]=value;
        return;
    }
    *spectrum_memory_byte(s->memory,address,true)=value;
    if(address<0x4000 || address>=0xc000) {
        if(s->memory->fault) s->cpu.ldir_until=0;
        spectrum_refresh_map(s);
    }
}
enum { ULA_CONTENTION_START=14335, ULA_128_CONTENTION_START=14361 };
static unsigned ula_bitmap(unsigned y,unsigned x) {
    return ((y&192)<<5)|((y&7)<<8)|((y&56)<<2)|x;
}
static unsigned ula_attribute(unsigned y,unsigned x) { return 6144+(y>>3)*32+x; }
static unsigned ula_128_line(unsigned at) { return ((at>>2)*18397u)>>20; }
static uint8_t floating_bus_128(spectrum* s) {
    const uint32_t at=s->cpu.io_at-s->frame_origin-(ULA_128_CONTENTION_START+1);
    if(at>=192*228) return 0xFF;
    const unsigned y=ula_128_line(at),column_time=at-y*228;
    const unsigned phase=column_time&7;
    if(column_time>=128 || phase<2 || phase>5) return 0xFF;
    const unsigned x=(column_time>>3)*2+(phase>=4);
    const unsigned offset=phase&1?ula_attribute(y,x):ula_bitmap(y,x);
    uint8_t value;
    return spectrum_bank_read(s->memory,(s->memory->paging&8)?7:5,offset,&value,1)?value:0xFF;
}
uint8_t spectrum_port_in(spectrum* s,uint16_t port) {
    if(!(s->extensions&SPECTRUM_TURBOSOUND)) s->sound.selected=0;
    uint8_t device;if(spectrum_disk_in(s,port,&device)) return device;
    if(!(port&1)) {
        uint8_t value=0xBF;
        if(s->ear && s->ear(s->ear_context,&s->cpu)) value|=0x40;
        const uint8_t* key=s->keys;
        for(unsigned rows=s->key_rows&~(port>>8);rows;rows>>=1,++key)
            if(rows&1) value&=*key|0xE0;
        return value;
    }
    if((s->extensions&SPECTRUM_ULAPLUS) && port==0xFF3B)
        return (s->ulaplus_select&64)?s->ulaplus_mode:s->ulaplus_palette[s->ulaplus_select&63];
    if(SPECTRUM_HAS_SINCLAIR && (s->extensions&SPECTRUM_TIMEX) && (port&255)==255) return s->timex_mode;
    if((port&0xC002)==0xC000) {
        PSG* ay=s->sound.selected?&s->ay2:&s->ay;
        const uint8_t* regs=s->sound.asynchronous?s->sound.regs[s->sound.selected]:ay->reg;
        return ay->adr==15 || (ay->adr==14 && !(regs[7]&64))?0xFF:regs[ay->adr];
    }
    if((port&0xFF)==0x1F && !s->joystick_mode) return s->joystick;
    return spectrum_is_128(s)?floating_bus_128(s):0xFF;
}
static uint8_t port_in(z80* cpu,uint16_t port) { return spectrum_port_in(cpu->userdata,port); }
/* Within a frame, floor(t/224) is floor((t/32)/7). The reciprocal is
 * exact on this bounded input and needs only a Thumb-1 multiply/shift. */
static unsigned ula_line(unsigned time) { return ((time>>5)*2341u)>>14; }
static unsigned ula_wait(void* raw,uint32_t cycles) {
    const spectrum* s=raw;
    const uint32_t at=cycles-s->frame_origin-ULA_CONTENTION_START;
    const unsigned phase=at&7;
    if(at>=192*224 || phase>=6 || at-ula_line(at)*224>=128) return 0;
    return 6-phase;
}
static unsigned ula_128_wait(void* raw,uint32_t cycles) {
    const spectrum* s=raw;
    const uint32_t at=cycles-s->frame_origin-ULA_128_CONTENTION_START;
    if(at>=192*228) return 0;
    const unsigned column=at-ula_128_line(at)*228,phase=column&7;
    return column<128 && phase<6?6-phase:0;
}

static const uint16_t spectrum_colors[16]={
    0,0x0019,0xc800,0xc819,0x0660,0x0679,0xce60,0xce79,
    0,0x001f,0xf800,0xf81f,0x07e0,0x07ff,0xffe0,0xffff
};
static uint16_t ulaplus_color(unsigned grb) {
    const unsigned r=(grb>>2)&7,g=(grb>>5)&7;
    const unsigned blue=grb&3,b=(blue<<1)|(blue?1:0);
    return (uint16_t)((((r<<2)|(r>>1))<<11)|(((g<<3)|g)<<5)|((b<<2)|(b>>1)));
}
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
enum { RASTER_START=14336-32*224-16, RASTER_COLUMNS=40, RASTER_ROWS=256,
       RASTER_CELLS=SPECTRUM_RASTER_CELLS };

static const uint8_t* ula_screen(const spectrum* s) {
    return s->memory?s->memory->cache:s->ram;
}

/* Store each bitmap, two latched color codes and a ULAplus mode bit.
 * The codes already account for the palette at this point on the beam. */
static void raster_until(spectrum* s,uint32_t cycles) {
    int32_t elapsed=(int32_t)(cycles-s->frame_origin-RASTER_START);
    if(elapsed<=0 || !s->video_bytes) return;
    unsigned end=RASTER_ROWS*RASTER_COLUMNS;
    if((unsigned)elapsed<RASTER_ROWS*224) {
        const unsigned line=ula_line((unsigned)elapsed),through=(unsigned)elapsed-line*224;
        end=line*RASTER_COLUMNS+(through<160?(through+3)/4:RASTER_COLUMNS);
    }
    unsigned cell=s->video_cell;
    if(cell>=end) return;
    unsigned y=cell/RASTER_COLUMNS,x=cell%RASTER_COLUMNS,inside=cell%RASTER_CELLS;
    const bool plus=(s->extensions&SPECTRUM_ULAPLUS) && s->ulaplus_mode;
    const bool flash=!plus && (s->frames&16);
    const unsigned border=plus?s->ulaplus_palette[8+s->border]:s->border;
    const uint8_t* screen=ula_screen(s);
    unsigned bitmap=ula_bitmap(y-32u,0),attributes=ula_attribute(y-32u,0);
    for(;cell<end;++cell) {
        unsigned paper=border,ink=border;
        unsigned pixels=0;
        if((y-32u)<192 && (x-4u)<32) {
            const unsigned column=x-4;
            const unsigned color=screen[attributes+column];
            const unsigned group=plus?(color>>6)*16:(color&64)>>3;
            pixels=screen[bitmap+column];
            ink=group+(color&7);
            paper=group+((color>>3)&7);
            if(plus) {ink=s->ulaplus_palette[ink];paper=s->ulaplus_palette[paper+8];}
            else if(flash && (color&128)) {const unsigned swap=ink;ink=paper;paper=swap;}
        }
        uint8_t* pair=s->video_bytes+RASTER_CELLS+2*inside;
        uint8_t* mode=s->video_bytes+3*RASTER_CELLS+inside/8;
        const unsigned shift=inside&7;
        s->video_bytes[inside]=(uint8_t)pixels;
        pair[0]=(uint8_t)paper;pair[1]=(uint8_t)ink;
        *mode=(uint8_t)((shift?*mode:0)|((unsigned)plus<<shift));
        if(++inside==RASTER_CELLS) {
            if(!s->video_store(s->video_context,y/SPECTRUM_RASTER_STRIP_ROWS,s->video_bytes)) {
                s->video_bytes=NULL;return;
            }
            inside=0;
        }
        if(++x==RASTER_COLUMNS) {
            x=0;++y;
            bitmap=ula_bitmap(y-32u,0);attributes=ula_attribute(y-32u,0);
        }
    }
    s->video_cell=end;
}
static void before_video_store(void* context,uint16_t address,uint32_t cycles) {
    spectrum* s=context;
    if((unsigned)address-0x4000u<6912) raster_until(s,cycles+1);
}
void spectrum_raster_begin(spectrum* s,uint8_t* buffer,void* context,
                           bool (*store)(void*,unsigned,const uint8_t*)) {
    s->video_context=context;s->video_bytes=store?buffer:NULL;s->video_store=store;s->video_cell=0;
    s->cpu.before_store=s->video_bytes?before_video_store:NULL;
}
void spectrum_raster_end(spectrum* s) {
    s->video_bytes=NULL;s->cpu.before_store=NULL;
}
void spectrum_raster_expand(uint8_t* strip) {
    uint8_t modes[RASTER_CELLS/8];
    memcpy(modes,strip+3*RASTER_CELLS,sizeof(modes));
    for(unsigned i=RASTER_CELLS;i--;) {
        const bool plus=(modes[i/8]>>(i&7))&1;
        const uint8_t* codes=strip+RASTER_CELLS+2*i;
        const uint16_t paper=plus?ulaplus_color(codes[0]):spectrum_colors[codes[0]&15];
        const uint16_t ink=plus?ulaplus_color(codes[1]):spectrum_colors[codes[1]&15];
        uint8_t* pair=strip+RASTER_CELLS+4*i;
        pair[0]=(uint8_t)paper;pair[1]=(uint8_t)(paper>>8);
        pair[2]=(uint8_t)ink;pair[3]=(uint8_t)(ink>>8);
    }
}
#else
void spectrum_raster_begin(spectrum* s,uint8_t* b,void* c,bool (*store)(void*,unsigned,const uint8_t*)) {
    (void)s;(void)b;(void)c;(void)store;
}
void spectrum_raster_end(spectrum* s) { (void)s; }
#endif
static void port_out(z80* cpu,uint16_t port,uint8_t value) {
    spectrum* s=cpu->userdata;
    if(!(s->extensions&SPECTRUM_TURBOSOUND)) s->sound.selected=0;
    if(spectrum_disk_out(s,port,value)) return;
    if(port==0xEFF7 && s->memory && spectrum_is_pentagon(s)) { (void)spectrum_memory_control(s->memory,value);spectrum_refresh_map(s); }
    if(!(port&1)) {
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        if(s->video_bytes && s->border!=(value&7)) {
            // OUT FE latches new border color at an 8-pixel boundary.
            raster_until(s,cpu->io_at-3);
        }
#endif
        s->border=value&7;
        if(s->beeper!=((value>>4)&1)) spectrum_sound_write(s,2,0,(value>>4)&1);
        s->beeper=(value>>4)&1;
    }
    if(s->memory && !(port&0x8002) && (spectrum_is_pentagon(s) || spectrum_is_128(s))) {
        (void)spectrum_memory_page(s->memory,value);spectrum_refresh_map(s);
    }
    if(SPECTRUM_HAS_SINCLAIR && (s->extensions&SPECTRUM_TIMEX) && (port&255)==255) s->timex_mode=value;
    if((port&0xC002)==0xC000) {
        if((s->extensions&SPECTRUM_TURBOSOUND) && value>=0xFE) s->sound.selected=value==0xFE;
        else {
            PSG* ay=s->sound.selected?&s->ay2:&s->ay;ay->adr=value&15;
            s->sound.selected_reg[s->sound.selected]=ay->adr;
        }
    }
    if((port&0xC002)==0x8000) {
        const unsigned chip=s->sound.selected,reg=chip?s->ay2.adr:s->ay.adr;
        spectrum_sound_write(s,chip,reg,value);
    }
    if((s->extensions&SPECTRUM_COVOX) && (port&255)==0xFB) spectrum_sound_write(s,3,0,value);
    if((s->extensions&SPECTRUM_SPECDRUM) && (port&255)==0xDF) spectrum_sound_write(s,4,0,value);
    if(s->extensions&SPECTRUM_ULAPLUS) {
        if(port==0xBF3B) s->ulaplus_select=value;
        else if(port==0xFF3B) {
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
            if(s->video_bytes) raster_until(s,cpu->io_at);
#endif
            if((s->ulaplus_select&192)==0) s->ulaplus_palette[s->ulaplus_select&63]=value;
            else if((s->ulaplus_select&192)==64) s->ulaplus_mode=value&1;
        }
    }
}
static void reset_ay(spectrum* s) {
    memset(&s->ay,0,sizeof(s->ay));PSG_setVolumeMode(&s->ay,s->sound_chip==SPECTRUM_YM?1:2);
    s->ay.quality=1;s->ay.rate=s->sample_rate?s->sample_rate:25000;
    PSG_setClock(&s->ay,spectrum_is_128(s)?SPECTRUM_128_AY_HZ:1750000);PSG_reset(&s->ay);
    s->ay2=s->ay;spectrum_sound_reset(s);
    s->sample_phase=0;s->audio_input=s->audio_output=0;
}
void spectrum_reset_cpu(spectrum* s) {
    z80_init(&s->cpu);s->cpu.read_byte=read_byte;s->cpu.write_byte=write_byte;
    s->cpu.port_in=port_in;s->cpu.port_out=port_out;s->cpu.userdata=s;
    spectrum_disk_filter(s);spectrum_refresh_map(s);
    s->frames=s->frame_tstates=s->frame_origin=0;s->border=s->beeper=s->joystick=s->key_rows=0;
    s->video_bytes=NULL;
    memset(s->keys,0x1F,sizeof(s->keys));
    reset_ay(s);
    s->ulaplus_select=s->ulaplus_mode=s->timex_mode=0;
    for(unsigned i=0;i<64;++i) {
        const unsigned c=i&7,n=(i&16)?7:6,b=(i&16)?3:2;
        s->ulaplus_palette[i]=(uint8_t)(((c&4)?n<<5:0)|((c&2)?n<<2:0)|((c&1)?b:0));
    }
}
void spectrum_init(spectrum* s,uint8_t* ram,const uint8_t* rom) {
    memset(s,0,sizeof(*s));s->ram=ram;s->rom=rom;
    s->extensions=SPECTRUM_TURBOSOUND|SPECTRUM_COVOX|SPECTRUM_SPECDRUM|SPECTRUM_ULAPLUS;
    spectrum_reset(s);
}
void spectrum_reset(spectrum* s) {
    spectrum_reset_cpu(s);
    if(s->memory) {
        (void)spectrum_memory_reset(s->memory);
        /* Beta boots the 48K ROM with paging available. Selecting 48 BASIC
         * in the 128K ROM menu would lock 7FFD and break 128K disk loaders. */
        if((spectrum_is_pentagon(s) || spectrum_is_128(s)) && s->disk.mode==SPECTRUM_DISK_BETA) (void)spectrum_memory_page(s->memory,16);
    } else memset(s->ram,0,SPECTRUM_RAM_BYTES);
    spectrum_disk_reset(s);
    spectrum_refresh_map(s);
}
void spectrum_set_audio(spectrum* s,uint32_t rate,void (*sample)(void*,int16_t),void* context) {
    s->sample_rate=rate;s->audio_sample=sample;s->audio_context=context;
    // Preserve registers across pause/resume and only reconfigure the rate.
    PSG_setRate(&s->ay,rate?rate:25000);
}
void spectrum_attach_memory(spectrum* s,spectrum_memory* memory) {
    s->memory=memory;s->pentagon=SPECTRUM_HAS_PENTAGON && memory && !spectrum_is_128(s);spectrum_reset_cpu(s);
}
uint32_t spectrum_frame_cycles(const spectrum* s) {
    return spectrum_is_pentagon(s)?71680:spectrum_is_128(s)?SPECTRUM_128_FRAME_TSTATES:SPECTRUM_FRAME_TSTATES;
}

static void ldir_deadline(spectrum* s,uint32_t phase,uint32_t frame,uint32_t left,bool sinclair128) {
    const unsigned irq=sinclair128?36:32;
    uint32_t limit=phase<irq?irq-phase:frame-phase;
    if(limit>left) limit=left;
    s->cpu.ldir_until=s->sample_rate || s->cpu.before_store || !limit?0:(uint32_t)s->cpu.cyc+limit;
    const unsigned start=sinclair128?ULA_128_CONTENTION_START:ULA_CONTENTION_START;
    if(phase<start+192*(sinclair128?228:224)) {
        // Only batches that touch contended addresses need the shorter budget.
        const uint32_t free_cycles=phase<start?start-phase:0;
        if(limit>free_cycles) limit=free_cycles;
    }
    s->cpu.ldir_contended_until=(uint32_t)s->cpu.cyc+limit;
}

uint32_t spectrum_run(spectrum* s,uint32_t tstates) {
    uint32_t elapsed=0,phase=s->frame_tstates;
    const uint32_t frame=spectrum_frame_cycles(s);
    const bool sinclair128=spectrum_is_128(s);
    const unsigned irq=sinclair128?36:32,clock=sinclair128?SPECTRUM_128_CPU_HZ:3500000;
    spectrum_memory* const memory=s->memory;
    const bool legacy_audio=s->sample_rate && s->audio_sample;
    s->cpu.wait=spectrum_is_pentagon(s)?NULL:sinclair128?ula_128_wait:ula_wait;
    s->frame_origin=(uint32_t)s->cpu.cyc-phase;
    // Keep the frame phase local while the machine's INT level is asserted;
    // neither MMU/port callbacks nor the asynchronous audio consumer use it.
    s->cpu.int_pending=phase<irq;s->cpu.int_data=0xFF;
    ldir_deadline(s,phase,frame,tstates,sinclair128);
    while(elapsed<tstates && !(memory && memory->fault)) {
        const uint32_t old_phase=phase;
        const unsigned long before=s->cpu.cyc;
        if(s->cpu.halted && (!s->cpu.wait || ((s->cpu.pc-1u)&s->cpu.contention_mask)!=0x4000) &&
           !s->cpu.nmi_pending && !s->cpu.iff_delay &&
           !(s->cpu.int_pending && s->cpu.iff1) && !s->sample_rate) {
            /* HALT repeats 4T refresh cycles without memory/port accesses.
             * Stop at the next frame boundary so INT is still sampled on
             * the same cycle; preserve bit 7 and the low-7-bit R wrap. */
            const uint32_t boundary=frame-phase;
            const uint32_t left=tstates-elapsed,limit=left<boundary?left:boundary;
            const uint32_t refresh=(limit+3)/4;
            s->cpu.cyc+=refresh*4;s->cpu.r=(s->cpu.r&128)|((s->cpu.r+refresh)&127);
        } else if(!legacy_audio && phase>=irq) {
            // No external INT edge lies inside this span. Keep per-opcode
            // execution/interrupt handling in the CPU and update machine
            // frame accounting only at the next edge or requested deadline.
            uint32_t limit=frame-phase;
            if(limit>tstates-elapsed) limit=tstates-elapsed;
            (void)z80_run(&s->cpu,limit,memory?&memory->fault:NULL);
        } else z80_step(&s->cpu);
        const uint32_t cycles=(uint32_t)(s->cpu.cyc-before);
        elapsed+=cycles;phase+=cycles;
        if(phase>=frame) {
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
            if(s->video_bytes) {
                raster_until(s,s->frame_origin+frame);
                s->video_cell=0;
            }
#endif
            phase-=frame;++s->frames;
            s->frame_origin+=frame;
            ldir_deadline(s,phase,frame,elapsed<tstates?tstates-elapsed:0,sinclair128);
        }
        if(phase<irq) s->cpu.int_pending=true;
        else if(old_phase<irq) {
            s->cpu.int_pending=false;ldir_deadline(s,phase,frame,elapsed<tstates?tstates-elapsed:0,sinclair128);
        }
        if(legacy_audio) {
            s->frame_tstates=phase;
            s->sample_phase+=cycles*s->sample_rate;
            while(s->sample_phase>=clock) {
                s->sample_phase-=clock;
                const int32_t input=2*PSG_calc(&s->ay)+(s->beeper?8192:0);
                int32_t output=input-s->audio_input+(s->audio_output*255)/256;
                s->audio_input=input;
                if(output>32767) output=32767;else if(output < -32768) output=-32768;
                s->audio_output=output;s->audio_sample(s->audio_context,(int16_t)output);
            }
        }
    }
    s->frame_tstates=phase;s->cpu.ldir_until=s->cpu.ldir_contended_until=0;
    spectrum_sound_publish(s);
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    // Quiet screen regions still have a beam. Capture them a CPU slice
    // at a time so a frame of pixels cannot delay the next audio events.
    if(s->video_bytes) raster_until(s,(uint32_t)s->cpu.cyc);
#endif
    return elapsed;
}
static bool down(const uint8_t* keys,unsigned c) { return (keys[c/8]&(1U<<(c&7)))!=0; }
static void key(spectrum* s,unsigned row,unsigned column) {
    s->keys[row]&=(uint8_t)~(1U<<column);s->key_rows|=(uint8_t)(1U<<row);
}
static void character(spectrum* s,unsigned c) {
    static const char rows[8][6]={" zxcv","asdfg","qwert","12345","09876","poiuy","\rlkjh","  mnb"};
    for(unsigned row=0;row<8;++row) for(unsigned column=0;column<5;++column)
        if((unsigned char)rows[row][column]==c && c!=' ') key(s,row,column);
    if(c==' ') key(s,7,0);
}
void spectrum_keyboard(spectrum* s,const uint8_t wire[32]) {
    memset(s->keys,0x1F,sizeof(s->keys));s->joystick=s->key_rows=0;
    const bool alt=down(wire,0xA1) || down(wire,0xA4);
    if(down(wire,0xA5)) key(s,0,0); // PicoCalc Ctrl -> Caps Shift.
    if(alt) key(s,7,1);
    for(unsigned c=32;c<127;++c) if(down(wire,c)) {
        if(c>='A' && c<='Z') { character(s,c+32);if(!alt) key(s,0,0); }
        else if((c>='a' && c<='z') || (c>='0' && c<='9') || c==' ') character(s,c);
        else {
            static const char symbols[]="!@#$%&'()_\";,. :?/*-+=<>";
            static const char letters[]="1234567890ponm zcvbjklrt";
            for(unsigned i=0;i<sizeof(symbols)-1;++i) if((unsigned char)symbols[i]==c) {
                key(s,7,1);character(s,(unsigned char)letters[i]);break;
            }
        }
    }
    if(down(wire,10) || down(wire,13)) key(s,6,0);
    if(down(wire,8) || down(wire,0x7F) || down(wire,0xD4)) { key(s,0,0);key(s,4,0); }
    if(down(wire,9) || down(wire,0x82)) { key(s,0,0);key(s,7,1); }
    if(down(wire,0xD0)) { key(s,0,0);key(s,7,0); }
    const uint8_t shortcut[]={0x81,0x83,0x84,0x86,0x87,0x88,0x89,0xD6,0xD7};
    const char target[]="158923476";
    for(unsigned i=0;i<sizeof(shortcut);++i) if(down(wire,shortcut[i])) { key(s,0,0);character(s,target[i]); }
    if(down(wire,0xB7)) s->joystick|=1;
    if(down(wire,0xB4)) s->joystick|=2;
    if(down(wire,0xB6)) s->joystick|=4;
    if(down(wire,0xB5)) s->joystick|=8;
    if(down(wire,0x85)) s->joystick|=16;
    if(s->joystick_mode) {
        const char* joystick=s->joystick_mode==1?"67890":"12345";
        const unsigned mask[]={2,1,4,8,16};
        for(unsigned i=0;i<5;++i) if(s->joystick&mask[i]) character(s,(unsigned char)joystick[i]);
    }
}
uint16_t spectrum_color(unsigned index) {
    return spectrum_colors[index&15];
}
static void video_raw(const spectrum* s,uint8_t bitmap[6144],uint8_t tiles[768]) {
    const unsigned base=spectrum_timex_mode(s)==1?8192:0;
    if(s->memory) {
        const unsigned bank=(s->memory->paging&8)?7:5;uint8_t bytes[SPECTRUM_CACHE_PAGE_BYTES];
        for(unsigned offset=0;offset<6144;offset+=sizeof(bytes)) {
            if(!spectrum_bank_read(s->memory,bank,base+offset,bytes,sizeof(bytes))) return;
            for(unsigned part=0;part<sizeof(bytes)/32;++part) {
                const unsigned row=(offset>>5)+part;
                const unsigned y=(row&192)|((row>>3)&7)|((row&7)<<3);
                memcpy(bitmap+y*32,bytes+part*32,32);
            }
        }
        if(!spectrum_bank_read(s->memory,bank,base+6144,tiles,768)) return;
    } else for(unsigned y=0;y<192;++y) {
        const unsigned offset=((y&0xC0)<<5)|((y&7)<<8)|((y&0x38)<<2);
        memcpy(bitmap+y*32,s->ram+base+offset,32);
    }
    if(!s->memory) memcpy(tiles,s->ram+base+6144,768);
}
void spectrum_video(const spectrum* s,uint8_t bitmap[6144],uint8_t tiles[768]) {
    video_raw(s,bitmap,tiles);
    for(unsigned i=0;i<768;++i) {
        const unsigned a=tiles[i],bright=(a&64)>>3;
        unsigned ink=(a&7)|bright,paper=((a>>3)&7)|bright;
        if((a&128) && (s->frames&16)) { unsigned t=ink;ink=paper;paper=t; }
        tiles[i]=(uint8_t)((paper<<4)|ink);
    }
}

void spectrum_video8(const spectrum* s,uint8_t bitmap[6144],uint8_t tiles[1536]) {
    video_raw(s,bitmap,tiles);
    for(int i=767;i>=0;--i) {
        const unsigned a=tiles[i];unsigned ink,paper;
        if((s->extensions&SPECTRUM_ULAPLUS) && s->ulaplus_mode) {
            const unsigned group=(a>>6)*16;ink=group+(a&7);paper=group+8+((a>>3)&7);
        } else {
            const unsigned bright=(a&64)>>3;ink=(a&7)|bright;paper=((a>>3)&7)|bright;
            if((a&128) && (s->frames&16)) { unsigned t=ink;ink=paper;paper=t; }
        }
        tiles[2*i]=(uint8_t)paper;tiles[2*i+1]=(uint8_t)ink;
    }
}
uint16_t spectrum_palette(const spectrum* s,unsigned index) {
    if(!((s->extensions&SPECTRUM_ULAPLUS) && s->ulaplus_mode)) return spectrum_color(index&15);
    return ulaplus_color(s->ulaplus_palette[index&63]);
}
uint16_t spectrum_border(const spectrum* s) {
    return spectrum_palette(s,((s->extensions&SPECTRUM_ULAPLUS) && s->ulaplus_mode)?8+s->border:s->border);
}

typedef struct {
    const spectrum_source* source;
    uint32_t at,end,cache_at,cache_size;
    uint8_t cache[256];
    bool io;
} reader;
static void reader_init(reader* r,const spectrum_source* source,uint32_t at,uint32_t end) {
    memset(r,0,sizeof(*r));r->source=source;r->at=at;r->end=end;r->cache_at=UINT32_MAX;
}
static bool byte_at(reader* r,uint32_t at,uint8_t* value) {
    if(at>=r->end) return false;
    if(r->cache_at==UINT32_MAX || at<r->cache_at || at-r->cache_at>=r->cache_size) {
        r->cache_at=at;r->cache_size=r->end-at<sizeof(r->cache)?r->end-at:sizeof(r->cache);
        if(!r->source->read(r->source->context,at,r->cache,r->cache_size)) { r->io=true;return false; }
    }
    *value=r->cache[at-r->cache_at];return true;
}
static bool get(reader* r,uint8_t* value) { if(!byte_at(r,r->at,value)) return false;++r->at;return true; }
static uint16_t word(const uint8_t* p) { return (uint16_t)(p[0]|((unsigned)p[1]<<8)); }
static void flags(z80* z,uint8_t f) {
    z->sf=(f>>7)&1;z->zf=(f>>6)&1;z->yf=(f>>5)&1;z->hf=(f>>4)&1;
    z->xf=(f>>3)&1;z->pf=(f>>2)&1;z->nf=(f>>1)&1;z->cf=f&1;
}
static bool source_read(const spectrum_source* source,uint32_t at,uint8_t* out,uint32_t n) {
    return source && source->read && at<=source->size && n<=source->size-at &&
           source->read(source->context,at,out,n);
}
static bool store_bytes(spectrum* s,unsigned bank,unsigned offset,const uint8_t* bytes,unsigned count) {
    if(bank!=32) return spectrum_bank_write(s->memory,bank,offset,bytes,count);
    const unsigned banks[]={5,2,0};
    while(count) {
        const unsigned n=count<16384-(offset&16383)?count:16384-(offset&16383);
        if(offset>=49152 || !spectrum_bank_write(s->memory,banks[offset/16384],offset&16383,bytes,n)) return false;
        offset+=n;bytes+=n;count-=n;
    }
    return true;
}
static enum spectrum_error rle_data(reader* r,uint8_t* output,unsigned length,spectrum* banked,unsigned bank) {
    unsigned used=0,pending=0;uint8_t bytes[256];
    while(used<length) {
        uint8_t a,b;unsigned count=1;
        if(!get(r,&a)) return r->io?SPECTRUM_IO:SPECTRUM_FORMAT;
        if(a==0xED && byte_at(r,r->at,&b) && b==0xED) {
            uint8_t n,value;++r->at;
            if(!get(r,&n) || !get(r,&value)) return r->io?SPECTRUM_IO:SPECTRUM_FORMAT;
            count=n;a=value;
            if(!count || count>length-used) return SPECTRUM_FORMAT;
        } else if(r->io) return SPECTRUM_IO;
        if(output) memset(output+used,a,count);
        if(banked) for(unsigned left=count;left;) {
            const unsigned n=left<sizeof(bytes)-pending?left:sizeof(bytes)-pending;
            memset(bytes+pending,a,n);pending+=n;left-=n;
            if(pending==sizeof(bytes)) {
                if(!store_bytes(banked,bank,used+count-left-pending,bytes,pending)) return SPECTRUM_IO;
                pending=0;
            }
        }
        used+=count;
    }
    if(pending && !store_bytes(banked,bank,length-pending,bytes,pending)) return SPECTRUM_IO;
    return SPECTRUM_OK;
}
static enum spectrum_error rle(reader* r,uint8_t* output,unsigned length) { return rle_data(r,output,length,NULL,0); }
static enum spectrum_error raw_page(reader* r,uint8_t* out,unsigned length) {
    if(length>r->end-r->at) return SPECTRUM_FORMAT;
    if(out) for(unsigned used=0;used<length;) {
        const unsigned n=length-used<1024?length-used:1024;
        if(!source_read(r->source,r->at+used,out+used,n)) return SPECTRUM_IO;
        used+=n;
    }
    r->at+=length;return SPECTRUM_OK;
}
static enum spectrum_error load_bank(reader* r,spectrum* s,unsigned bank,bool commit) {
    if(16384U>r->end-r->at) return SPECTRUM_FORMAT;
    if(commit) {
        uint8_t bytes[1024];
        for(unsigned at=0;at<16384;at+=sizeof(bytes))
            if(!source_read(r->source,r->at+at,bytes,sizeof(bytes)) ||
               !spectrum_bank_write(s->memory,bank,at,bytes,sizeof(bytes))) return SPECTRUM_IO;
    }
    r->at+=16384;return SPECTRUM_OK;
}
enum spectrum_error spectrum_load_sna(spectrum* s,const spectrum_source* source) {
    uint8_t h[27];
    if(!source || (source->size!=49179 && source->size!=131103 && source->size!=147487)) return SPECTRUM_UNSUPPORTED;
    const bool banked=source->size!=49179;
    if(banked && (!s->memory || (!spectrum_is_pentagon(s) && !spectrum_is_128(s)))) return SPECTRUM_UNSUPPORTED;
    if(!source_read(source,0,h,sizeof(h))) return SPECTRUM_IO;
    const unsigned sp=word(h+23);
    if(h[25]>2 || h[26]>7 || (!banked && (sp<0x4000 || sp>0xFFFE))) return SPECTRUM_FORMAT;
    uint8_t footer[4]={0};
    if(banked) {
        if(!source_read(source,49179,footer,4)) return SPECTRUM_IO;
        if((footer[3] && s->disk.mode!=SPECTRUM_DISK_BETA) ||
           ((footer[2]&192) && !spectrum_is_128(s))) return SPECTRUM_UNSUPPORTED;
        const unsigned bank=footer[2]&7;
        if(source->size!=((bank==2 || bank==5)?147487U:131103U)) return SPECTRUM_FORMAT;
    }
    if(!spectrum_disk_snapshot(s) || (s->memory && !spectrum_memory_reset(s->memory))) return SPECTRUM_IO;
    if(s->memory && s->memory->extended) s->memory->control=4;
    reader r;reader_init(&r,source,27,source->size);
    enum spectrum_error error=SPECTRUM_OK;
    if(banked) {
        const unsigned banks[]={5,2,footer[2]&7U};
        for(unsigned i=0;i<3 && !error;++i) error=load_bank(&r,s,banks[i],true);
        r.at=49183;
        for(unsigned bank=0;bank<8 && !error;++bank)
            if(bank!=5 && bank!=2 && bank!=banks[2]) error=load_bank(&r,s,bank,true);
    } else if(s->memory) {
        const unsigned banks[]={5,2,0};
        for(unsigned i=0;i<3 && !error;++i) error=load_bank(&r,s,banks[i],true);
    } else error=raw_page(&r,s->ram,SPECTRUM_RAM_BYTES);
    if(error) return error;
    spectrum_reset_cpu(s);z80* z=&s->cpu;
    z->i=h[0];z->l_=h[1];z->h_=h[2];z->e_=h[3];z->d_=h[4];
    z->c_=h[5];z->b_=h[6];z->f_=h[7];z->a_=h[8];
    z->l=h[9];z->h=h[10];z->e=h[11];z->d=h[12];z->c=h[13];z->b=h[14];
    z->iy=word(h+15);z->ix=word(h+17);z->iff1=z->iff2=(h[19]&4)!=0;
    z->r=h[20];flags(z,h[21]);z->a=h[22];z->sp=(uint16_t)(sp+(banked?0:2));
    z->pc=banked?word(footer):(uint16_t)(read_byte(s,(uint16_t)sp)|((unsigned)read_byte(s,(uint16_t)(sp+1))<<8));
    z->interrupt_mode=h[25];s->border=h[26];
    if(s->memory) {
        if(!spectrum_memory_page(s->memory,banked?footer[2]:0x30)) return SPECTRUM_IO;
        if(footer[3]) spectrum_disk_m1(s,0x3D00,true);
    }
    spectrum_refresh_map(s);
    return SPECTRUM_OK;
}
static enum spectrum_error z80_pages(spectrum* s,const spectrum_source* source,const uint8_t* h,
                                     unsigned extra,bool banked,bool commit) {
    reader r;reader_init(&r,source,extra?32+extra:30,source->size);
    if(!extra) {
        enum spectrum_error error;
        if(h[12]&32) error=rle_data(&r,commit && !s->memory?s->ram:NULL,SPECTRUM_RAM_BYTES,commit?s->memory?s:NULL:NULL,32);
        else if(s->memory) {
            const unsigned banks[]={5,2,0};error=SPECTRUM_OK;
            for(unsigned i=0;i<3 && !error;++i) error=load_bank(&r,s,banks[i],commit);
        } else error=raw_page(&r,commit?s->ram:NULL,SPECTRUM_RAM_BYTES);
        if(error) return error;
        if(r.at==r.end) return SPECTRUM_OK;
        uint8_t marker[4];
        if(!(h[12]&32) || r.end-r.at!=4 || !source_read(source,r.at,marker,4)) return SPECTRUM_FORMAT;
        return !memcmp(marker,"\0\xED\xED\0",4)?SPECTRUM_OK:SPECTRUM_FORMAT;
    }
    unsigned pages=0;
    while(r.at<r.end) {
        uint8_t lo,hi,page;
        if(!get(&r,&lo) || !get(&r,&hi) || !get(&r,&page)) return r.io?SPECTRUM_IO:SPECTRUM_FORMAT;
        const unsigned length=lo|((unsigned)hi<<8);
        unsigned offset,bit;
        if(banked) {
            if(page<3 || page>10) return SPECTRUM_UNSUPPORTED;
            offset=page-3;bit=1U<<offset;
        } else if(page==8) { offset=0;bit=1; }
        else if(page==4) { offset=16384;bit=2; }
        else if(page==5) { offset=32768;bit=4; }
        else return SPECTRUM_UNSUPPORTED;
        if(pages&bit) return SPECTRUM_FORMAT;
        pages|=bit;
        const unsigned stored=length==65535?16384:length;
        if(!stored || stored>r.end-r.at) return SPECTRUM_FORMAT;
        const unsigned next=r.at+stored;
        reader block;reader_init(&block,source,r.at,next);
        enum spectrum_error error;
        if(banked) error=length==65535?load_bank(&block,s,offset,commit):rle_data(&block,NULL,16384,commit?s:NULL,offset);
        else if(s->memory) {
            const unsigned bank=offset==0?5:offset==16384?2:0;
            error=length==65535?load_bank(&block,s,bank,commit):rle_data(&block,NULL,16384,commit?s:NULL,bank);
        } else error=length==65535?raw_page(&block,commit?s->ram+offset:NULL,16384):rle(&block,commit?s->ram+offset:NULL,16384);
        if(error) return error;
        if(block.at!=next) return SPECTRUM_FORMAT;
        r.at=next;
    }
    return pages==(banked?255U:7U)?SPECTRUM_OK:SPECTRUM_FORMAT;
}
static unsigned z80_model(unsigned extra,unsigned hardware) {
    if(hardware<=1) return SPECTRUM_48;
    if(hardware==(extra==23?3:4)) return SPECTRUM_128;
    if(hardware==9) return SPECTRUM_P512;
    if(hardware==14) return SPECTRUM_TC2048;
    return UINT32_MAX;
}
enum spectrum_error spectrum_z80_model(const spectrum_source* source,unsigned* model) {
    uint8_t h[11];
    if(source->size<30) return SPECTRUM_FORMAT;
    if(!source_read(source,6,h,2)) return SPECTRUM_IO;
    *model=SPECTRUM_48;
    if(word(h)) return SPECTRUM_OK;
    if(source->size<37) return SPECTRUM_FORMAT;
    if(!source_read(source,30,h,8)) return SPECTRUM_IO;
    const unsigned extra=word(h);
    if((extra!=23 && extra!=54 && extra!=55) || (h[7]&128)) return SPECTRUM_UNSUPPORTED;
    *model=z80_model(extra,h[4]);
    return *model==UINT32_MAX?SPECTRUM_UNSUPPORTED:SPECTRUM_OK;
}
enum spectrum_error spectrum_load_z80(spectrum* s,const spectrum_source* source) {
    uint8_t h[30],extended[55];unsigned extra=0;uint16_t pc;bool banked=false;
    unsigned model=SPECTRUM_48;
    if(!source || source->size<30) return SPECTRUM_FORMAT;
    if(!source_read(source,0,h,sizeof(h))) return SPECTRUM_IO;
    if(h[12]==255) h[12]=1;
    if((h[29]&3)>2) return SPECTRUM_FORMAT;
    pc=word(h+6);
    if(!pc) {
        uint8_t length[2];
        if(source->size<32 || !source_read(source,30,length,2)) return SPECTRUM_FORMAT;
        extra=word(length);
        if(extra!=23 && extra!=54 && extra!=55) return SPECTRUM_UNSUPPORTED;
        if(source->size<32+extra) return SPECTRUM_FORMAT;
        if(!source_read(source,32,extended,extra)) return SPECTRUM_IO;
        model=z80_model(extra,extended[2]);banked=model==SPECTRUM_128 || model==SPECTRUM_P512;
        if(model==UINT32_MAX || (banked && (!s->memory || (!spectrum_is_pentagon(s) && !spectrum_is_128(s)))) ||
           (extended[5]&128) || (model==SPECTRUM_TC2048?(extended[3] || (extended[4]&7)>2):extended[4]) ||
           (banked && (extended[3]&192) && !spectrum_is_128(s)) ||
           (model==SPECTRUM_P512 && !spectrum_is_pentagon(s)) ||
           (model==SPECTRUM_TC2048 && !SPECTRUM_HAS_SINCLAIR)) return SPECTRUM_UNSUPPORTED;
        pc=word(extended);
    }
    enum spectrum_error error=z80_pages(s,source,h,extra,banked,false);
    if(!error && (!spectrum_disk_snapshot(s) || (s->memory && !spectrum_memory_reset(s->memory)))) return SPECTRUM_IO;
    if(!error && s->memory && s->memory->extended) s->memory->control=4;
    if(!error) error=z80_pages(s,source,h,extra,banked,true);
    if(error) return error;
    spectrum_reset_cpu(s);z80* z=&s->cpu;
    z->a=h[0];flags(z,h[1]);z->c=h[2];z->b=h[3];z->l=h[4];z->h=h[5];
    z->pc=pc;z->sp=word(h+8);z->i=h[10];z->r=(h[11]&127)|((h[12]&1)<<7);
    z->e=h[13];z->d=h[14];z->c_=h[15];z->b_=h[16];z->e_=h[17];z->d_=h[18];
    z->l_=h[19];z->h_=h[20];z->a_=h[21];z->f_=h[22];z->iy=word(h+23);z->ix=word(h+25);
    z->iff1=h[27]!=0;z->iff2=h[28]!=0;z->interrupt_mode=h[29]&3;s->border=(h[12]>>1)&7;
    if(extra) {
        for(unsigned i=0;i<16;++i) PSG_writeReg(&s->ay,i,extended[7+i]);
        s->ay.adr=extended[6]&15;
    }
    if(s->memory && !spectrum_memory_page(s->memory,banked?extended[3]:0x30)) return SPECTRUM_IO;
    if(SPECTRUM_HAS_SINCLAIR && model==SPECTRUM_TC2048) { s->extensions|=SPECTRUM_TIMEX;s->timex_mode=extended[4]; }
    spectrum_refresh_map(s);
    return SPECTRUM_OK;
}
