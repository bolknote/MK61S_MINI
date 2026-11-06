/* Actual APP scheduler with real Z80/AY and fixed timestamped guest input.
 * Wall clock/native costs are simulated; no physical latency claim. */
#include "candidate/examples/portable-apps/SPECTRUM/spectrum.h"
#define external host_external
#include "../host_driver.c"
#undef external
static uint32_t timed_run(spectrum*,uint32_t);
static void capture_video(const spectrum*,uint8_t*,uint8_t*);
static void prefetch_begin(spectrum*);
#define SPECTRUM_HIL_FRAME_READY prefetch_begin
#define spectrum_run timed_run
#define spectrum_video8 capture_video
#define main unused_app_main
#ifndef ORACLE_SOURCE
#define ORACLE_SOURCE "candidate/examples/portable-apps/SPECTRUM/main.c"
#endif
#include ORACLE_SOURCE
#undef main
#undef spectrum_run
#undef spectrum_video8
static uint32_t clock_us,origin_cycles,limit=3100,seen;
static uint32_t epoch,frame_base,frozen_cycles,frozen_target,max_wall_ahead;
static unsigned captures,event_index,script_changes,closes,prefetch_reads,delay_edges;
static uint64_t events=14695981039346656037ULL,wave=14695981039346656037ULL,inputs=14695981039346656037ULL;
static uint64_t samples,event_count,in_count;
static uint8_t canvas[12800],flatram[49152],flatrom[16384];
static bool opened,need_epoch,prefetching;
static uint8_t (*real_in)(z80*,uint16_t);
static uint64_t hash(uint64_t h,const void* data,unsigned n) {
    const uint8_t* p=data;while(n--)h=(h^*p++)*1099511628211ULL;return h;
}
static void pump_sound(spectrum* m) {
    spectrum_sound* q=&m->sound;uint32_t w=atomic_load(&q->write),available=atomic_load(&q->produced);
    assert(w-seen<=SPECTRUM_SOUND_QUEUE_EVENTS);
    while(seen!=w) {const spectrum_sound_event* e=&q->events[seen++&(SPECTRUM_SOUND_QUEUE_EVENTS-1)];events=hash(events,e,sizeof(*e));++event_count;}
    while((int32_t)(available-(q->time+140))>=0) {
        const uint32_t before=q->time,value=spectrum_sound_render(m);
        if(q->time!=before) {wave=hash(wave,&value,sizeof(value));++samples;}
    }
}
static void queue_pump(void* p) {pump_sound(p);}
static uint8_t timestamped_in(z80* z,uint16_t port) {
    if(prefetching) {
        const int32_t lead=(int32_t)(frozen_target-clock_us)+(int32_t)((uint32_t)z->cyc-frozen_cycles)*2/7;
        assert(lead<=4000);if(lead>0 && (uint32_t)lead>max_wall_ahead)max_wall_ahead=(uint32_t)lead;
    }
    static const int offsets[]={-1,1,1800,13999,14001,35600};
    const uint32_t elapsed=(uint32_t)z->cyc-origin_cycles;
    while(event_index<6*(limit+1)) {
        const uint32_t edge=(event_index/6+1)*71680+offsets[event_index%6]+delay_edges;
        if((int32_t)(elapsed-edge)<0)break;
        ++event_index;++script_changes;
    }
    uint8_t bitmap[32]={0};
    if(event_index&1)bitmap['p'/8]|=1U<<('p'&7);
    if(event_index&2)bitmap[' '/8]|=1U<<(' '&7);
    spectrum_keyboard(&s,bitmap);
    const uint8_t value=real_in(z,port);uint32_t record[]={elapsed,port,value};
    inputs=hash(inputs,record,sizeof(record));++in_count;
    if(captures && s.frames==captures && s.frame_tstates<14000)++prefetch_reads;
    return value;
}
static void prefetch_begin(spectrum* m) {
    frozen_cycles=(uint32_t)m->cpu.cyc;frozen_target=epoch+(m->frames-frame_base)*20480+m->frame_tstates*2/7;prefetching=true;
}
static uint32_t timed_run(spectrum* m,uint32_t quantum) {
    assert(quantum==512);const uint32_t used=spectrum_run(m,quantum);assert(used<=556);
    assert(!m->memory || !m->memory->fault);
    clock_us+=used/5+1;pump_sound(m);return used;
}
static void capture_video(const spectrum* m,uint8_t* pixels,uint8_t* tiles) {
    spectrum_video8(m,pixels,tiles);++captures;
    if(captures>limit)return;
    const z80* z=&m->cpu;
    const uint32_t fields[]={ (uint32_t)z->cyc,z->pc,z->sp,z->ix,z->iy,z->mem_ptr,z->a,z->f,z->bc,z->de,z->hl,z->a_,z->f_,z->bc_,z->de_,z->hl_,z->i,z->r,
        z->iff_delay,z->interrupt_mode,z->int_data,z->iff1,z->iff2,z->halted,z->int_pending,z->nmi_pending,z->ldir_until,
        m->frames,m->frame_tstates,m->sample_phase,z->m1_start,z->m1_limit};
    uint64_t cpu=hash(14695981039346656037ULL,fields,sizeof(fields)),ramhash=14695981039346656037ULL;
    if(m->memory) {uint8_t bank[16384];for(unsigned i=0;i<8;++i) {assert(spectrum_bank_read(m->memory,i,0,bank,sizeof(bank)));ramhash=hash(ramhash,bank,sizeof(bank));}}
    else ramhash=hash(ramhash,flatram,sizeof(flatram));
    uint64_t video=hash(14695981039346656037ULL,pixels,6144);video=hash(video,tiles,1536);
    for(unsigned i=0;i<64;++i) {uint16_t value=spectrum_palette(m,i);video=hash(video,&value,sizeof(value));}
    uint8_t border=spectrum_border(m);video=hash(video,&border,1);
    PSG chips[]={m->ay,m->ay2};chips[0].voltbl=chips[1].voltbl=NULL;
    printf("%u %016llx %016llx %016llx %llu/%016llx %llu/%016llx %016llx %u/%llu/%016llx\n",captures,
        (unsigned long long)cpu,(unsigned long long)ramhash,(unsigned long long)video,
        (unsigned long long)event_count,(unsigned long long)events,(unsigned long long)samples,(unsigned long long)wave,
        (unsigned long long)hash(14695981039346656037ULL,chips,sizeof(chips)),script_changes,
        (unsigned long long)in_count,(unsigned long long)inputs);
}
static void service(void) {clock_us+=7;}
static uint32_t graphics_begin(void) {return 1;}
static void delay(uint32_t n) {(void)n;assert(!"No millisecond delay in scheduler");}
static const mk61_app_api api={.service=service,.graphics_begin=graphics_begin,.delay_ms=delay};
const mk61_app_api* mk61_api=&api;
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* data) {
    (void)b;(void)c;
    if(op==MK61_SERVICE_MICROS) {if(need_epoch) {epoch=clock_us-s.frame_tstates*2/7;need_epoch=false;}return clock_us++;}
    if(op==MK61_SERVICE_DISPLAY) {mk61_service_framebuffer* f=data;assert(a==MK61_SERVICE_DISPLAY_FRAMEBUFFER);f->pixels=canvas;f->bytes=sizeof(canvas);return 1;}
    if(op==MK61_SERVICE_KEYBOARD) {memset(data,0,32);if(captures>=limit)((uint8_t*)data)[27/8]|=1U<<(27&7);clock_us+=37;return 1;}
    if(op==MK61_SERVICE_AUDIO_STREAM) {if(a==MK61_AUDIO_SYNTH_OPEN) {opened=need_epoch=true;return 1;}assert(a==MK61_AUDIO_CLOSE);opened=false;++closes;return 1;}
    assert(op==MK61_SERVICE_COLOR_DISPLAY);
    if(a==MK61_COLOR_PRESENT) {clock_us+=1500;prefetching=false;}else if(a==MK61_COLOR_PALETTE64)clock_us+=20;else assert(a==MK61_COLOR_END);
    return 1;
}
static const mk61_app_services fake={.magic=MK61_APP_SERVICES_MAGIC,.version=MK61_APP_SERVICES_VERSION,.struct_size=sizeof(mk61_app_services),.call=call};
int main(int argc,char** argv) {
    (void)prefetch_begin;
    assert(argc>=2);delay_edges=argc==4?(unsigned)strtoul(argv[3],NULL,10):0;
    if(!strcmp(argv[1],"INPUT")) {
        limit=80;spectrum_init(&s,flatram,flatrom);s.pentagon=true;
        const uint8_t code[]={0x3e,0xdf,0xdb,0xfe,0x32,0,0x40,0xe6,1,7,7,7,7,0xd3,0xfe,
            1,0xfd,0xff,0x3e,8,0xed,0x79,1,0xfd,0xbf,0x3a,0,0x40,0xe6,15,0xed,0x79,0xc3,0,0x80};
        memcpy(flatram+0x4000,code,sizeof(code));s.cpu.pc=0x8000;s.cpu.sp=0xfffe;
    } else {
        assert(argc==3);host_init("/private/tmp/mk61-spectrum-20261105/downloads","programs/spectrum/GAMES.img");host_disconnect();
        static uint8_t blocks[2][SPECTRUM_BANK_HEAP_BYTES],tails[2][1024],halves[2][8192];
        uint8_t* split[]={tails[0],tails[1],halves[1]};
        assert(spectrum_memory_init_split(&memory,blocks[0],blocks[1],split,halves[0],roms[0],roms[1],(spectrum_memory_io){host_external,rd,wr,zero}));
        s.ram=blocks[0];spectrum_attach_memory(&s,&memory);
        FILE* f=fopen(argv[1],"rb");assert(f && !fseek(f,0,SEEK_END));unsigned n=(unsigned)ftell(f);rewind(f);
        uint8_t* bytes=malloc(n);assert(bytes && fread(bytes,1,n,f)==n);fclose(f);uint8_t palette[65];load(argv[2],palette,65);
        assert(!host_load_snapshot(bytes,n,palette));free(bytes);host_disconnect();
    }
    origin_cycles=(uint32_t)s.cpu.cyc-s.frame_tstates;real_in=s.cpu.port_in;s.cpu.port_in=timestamped_in;
    active_machine=&s;services=&fake;started=true;clock_us=UINT32_MAX-100000;frame_base=s.frames;
    // The APP owns asynchronous lifetime. Our yield wrapper is only for a
    // full-queue assertion; each real512T call is consumed by pump_sound.
    (void)queue_pump;emulate();assert(!opened && closes==1 && captures>=limit && script_changes>100 && in_count>100);
    fprintf(stderr,"Actual scheduler oracle: captures=%u timestamped_changes=%u IN=%llu audio=%llu events=%llu max_prefetch_IN_wall_ahead_us=%u close=1 wall-wrap PASS\n",captures,script_changes,(unsigned long long)in_count,(unsigned long long)samples,(unsigned long long)event_count,max_wall_ahead);
}
