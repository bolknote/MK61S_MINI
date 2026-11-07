#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../examples/portable-apps/SPECTRUM/rom_cache.h"
static const uint8_t* app_rom_cache_find(unsigned,uint32_t*);
#define spectrum_rom_cache_find app_rom_cache_find
#define main spectrum_app_main
#ifndef SPECTRUM_APP_MAIN_SOURCE
#define SPECTRUM_APP_MAIN_SOURCE "../examples/portable-apps/SPECTRUM/main.c"
#endif
#include SPECTRUM_APP_MAIN_SOURCE
#undef main
#undef spectrum_rom_cache_find

/* Execute the actual APP UI and core against a bounded resident ABI fixture.
 * Electrical timing, SRAM residency and multicore IRQs require the device. */
static const char* asset_dir;
static uint8_t* cache_image;
static unsigned cache_bytes;
static bool cache_mismatch,expect_mapped;
static uint32_t cache_word(unsigned at) {
    return cache_image[at]|((uint32_t)cache_image[at+1]<<8)|((uint32_t)cache_image[at+2]<<16)|((uint32_t)cache_image[at+3]<<24);
}
static const uint8_t* app_rom_cache_find(unsigned id,uint32_t* crc) {
    if(!cache_image || id>=SPECTRUM_ROM_COUNT) return NULL;
    if(crc) *crc=cache_word(32+id*32+12)^(cache_mismatch && id==SPECTRUM_ROM_128_0);
    return cache_image+cache_word(32+id*32+4);
}
static char ui[600];
static uint32_t micros_now,frames_shown,session_frames,calls,audio_opens,audio_closes;
static unsigned palette_calls;
static unsigned lcd_clock_requests;
static uint32_t lcd_clock=12000000;
static bool legacy_lcd;
static const char* opened_name;
static bool open_error;
static unsigned open_keys,open_path_calls,selected_reads;
static uint8_t canvas[12800],*psram;
static uint8_t* direct_sram[3];
static unsigned psram_bytes,action;
static bool released=true;
static unsigned held_key,held_scans;
static unsigned graphics_ends;
static mk61_service_audio_synth generator;
typedef struct { const char* screen;unsigned key,frames; } action_item;
static const action_item script[]={
    {"Spectrum",13,0},{NULL,27,80},
    {"Spectrum",'p',0},{"Options",'j',0},
    {"Options",'1',0},{"Options",'1',0},
    {"Options",'d',0},{"Beta Disk",13,0},
    {"Options",'w',0},{"Options",27,0},
    {"Spectrum",'r',0},{NULL,27,80},{"Spectrum",'t',0},{NULL,27,60},
    {"Spectrum",'p',0},{"Options",'i',0},{"DivMMC",13,0},
    {"Options",'w',0},{"Options",27,0},
    {"Spectrum",'r',0},{NULL,27,100},{"Spectrum",'n',0},{NULL,27,40},
    {"Spectrum",'o',0},{"Snapshot",13,0},{NULL,27,10},
    {"Spectrum",'m',0},{"Machine",0xB6,0},{"Machine",13,0},
    {"Spectrum",'r',0},{NULL,27,50},
    {"Spectrum",'m',0},{"Machine",0xB5,0},{"Machine",13,0},
    {"Spectrum",'q',0},
};
/* The menu renderer is exercised on the physical RGB panel; this fixture
 * supplies its titles to the scripted input while testing the real APP. */
bool spectrum_ui_begin(spectrum_ui* u,const mk61_app_services* api,const spectrum* s,bool running) {
    (void)s;(void)running;u->api=api;spectrum_display_fast(api);return true;
}
void spectrum_ui_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                        const char* const* labels,unsigned count,unsigned selected) {
    (void)u;(void)x;(void)y;(void)width;(void)labels;assert(selected<=count);
    snprintf(ui,sizeof(ui),"%s",title);
}
void spectrum_ui_footer(spectrum_ui* u,const char* text) { (void)u;(void)text; }
bool spectrum_ui_present(spectrum_ui* u) { (void)u;return true; }
static void pump(void) {
    if(generator.sample) for(unsigned i=0;i<64 && (int32_t)(atomic_load(&machine.sound.produced)-(machine.sound.time+140))>=0;++i)
        (void)generator.sample(generator.context);
}
static void delay(uint32_t n) { micros_now+=n*1000;pump(); }
static uint32_t clear_screen(void) { return 1; }
static uint32_t graphics_begin(void) { ui[0]=0;session_frames=0;return 1; }
static void graphics_end(void) { assert(!generator.sample);++graphics_ends;memset(canvas,0,sizeof(canvas)); }
static int format(char* out,uint32_t n,const char* f,va_list args) { return vsnprintf(out,n,f,args); }
static void path(char out[1024],const char* name) {
    while(name[0]=='.' && name[1]=='/') name+=2;
    const char* prefix="/External games/";
    if(!strncmp(name,prefix,strlen(prefix))) name+=strlen(prefix);
    assert(snprintf(out,1024,"%s/%s",asset_dir,name)<1024);
}
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
    if(++calls>2000000) { fprintf(stderr,"APP stalled action=%u screen=%s\n",action,ui);abort(); }
    if(op==MK61_SERVICE_CAPABILITIES) return MK61_SERVICE_CAP_MEMORY|MK61_SERVICE_CAP_COLOR_DISPLAY|
        MK61_SERVICE_CAP_FILE_BYTES|MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_AUDIO_STREAM|
        MK61_SERVICE_CAP_BUFFERS|MK61_SERVICE_CAP_EXTERNAL_BUFFERS;
    if(op==MK61_SERVICE_MICROS) { micros_now+=100;return micros_now; }
    if(op==MK61_SERVICE_MEMORY_ACQUIRE) {
        mk61_service_lease* r=payload;r->data=calloc(1,c);assert(r->data);r->size=c;r->fresh=1;
        assert((expect_mapped && a<=1 && c==8192) || (!expect_mapped && a==1 && c==16384));return 1;
    }
    if(op==MK61_SERVICE_MEMORY_RELEASE) { mk61_service_lease* r=payload;free(r->data);r->data=NULL;return 1; }
    if(op==MK61_SERVICE_BUFFER) {
        mk61_service_buffer* r=payload;
        if(a==MK61_BUFFER_ACQUIRE) {
            if(r->access==MK61_BUFFER_DIRECT) {
                assert(r->size==15360); // No 32K allocation may be required for guest SRAM.
                for(unsigned i=0;i<3;++i)if(!direct_sram[i]) {
                    r->data=direct_sram[i]=malloc(r->size);assert(r->data);r->handle=2+i;r->storage=MK61_BUFFER_SRAM;return 1;
                }
                assert(false);
            }
            assert(!psram);psram_bytes=r->size;psram=calloc(1,r->size);assert(psram);r->handle=1;return 1;
        }
        if(r->handle>=2 && r->handle<=4) {
            assert(a==MK61_BUFFER_RELEASE && !generator.sample);
            free(direct_sram[r->handle-2]);direct_sram[r->handle-2]=NULL;return 1;
        }
        assert(r->handle==1 && psram);
        if(a==MK61_BUFFER_RELEASE) { free(psram);psram=NULL;return 1; }
        assert(r->offset<=psram_bytes && r->size<=psram_bytes-r->offset);
        if(a==MK61_BUFFER_READ) memcpy(r->data,psram+r->offset,r->size);
        else if(a==MK61_BUFFER_WRITE) memcpy(psram+r->offset,r->data,r->size);
        else if(a==MK61_BUFFER_FILL) memset(psram+r->offset,0,r->size);
        else assert(false);
        return 1;
    }
    if(op==MK61_SERVICE_FILE_BYTES) {
        mk61_service_file_bytes* r=payload;
        if(a==MK61_FILE_BYTES_PATH) {
            assert(opened_name && !r->path && r->offset==42 && r->size==256);++open_path_calls;
            if(open_error && !strcmp(opened_name,"missing"))return 0;
            assert(snprintf(r->data,r->size,"/External games/%s",opened_name)<(int)r->size);return 1;
        }
        char filename[1024];path(filename,r->path);
        if(a==MK61_FILE_BYTES_CHILD) {
            const char* names[]={"DEMO128.sna","BLANK.trd","ESXDOS.img"};
            if(r->offset>=3) return 0;
            mk61_service_file_info* info=r->data;memset(info,0,sizeof(*info));strcpy(info->name,names[r->offset]);return 1;
        }
        FILE* f=fopen(filename,a==MK61_FILE_BYTES_WRITE?"r+b":"rb");if(!f) return 0;
        if(opened_name && !strncmp(r->path,"/External games/",16)) {
            assert(a!=MK61_FILE_BYTES_WRITE);if(a==MK61_FILE_BYTES_READ)++selected_reads;
        }
        fseek(f,0,SEEK_END);const long length=ftell(f);bool ok=true;
        if(a==MK61_FILE_BYTES_STAT) { mk61_service_file_info* info=r->data;memset(info,0,sizeof(*info));info->size=(uint32_t)length; }
        else {
            assert(r->size<=4096);ok=r->offset<=(unsigned)length && r->size<=(unsigned)length-r->offset;
            if(ok) { assert(!fseek(f,r->offset,SEEK_SET));ok=(a==MK61_FILE_BYTES_WRITE?fwrite(r->data,1,r->size,f):fread(r->data,1,r->size,f))==r->size; }
        }
        fclose(f);return ok;
    }
    if(op==MK61_SERVICE_DISPLAY) {
        if(a==MK61_SERVICE_DISPLAY_PRINT) { assert(!generator.sample);snprintf(ui,sizeof(ui),"%s",(char*)payload);return 1; }
        if(a==MK61_SERVICE_DISPLAY_FRAMEBUFFER) {
            mk61_service_framebuffer* f=payload;f->pixels=canvas;f->bytes=sizeof(canvas);f->width=f->height=320;return 1;
        }
        assert(false);
    }
    if(op==MK61_SERVICE_COLOR_DISPLAY) {
        if(a==MK61_COLOR_SPI_HZ) {
            assert(!b && c==sizeof(uint32_t) && payload && *(uint32_t*)payload==24000000);
            ++lcd_clock_requests;if(legacy_lcd) return 0;
            return lcd_clock=24000000;
        }
        if(a==MK61_COLOR_END) { lcd_clock=12000000;return 1; }
        if(a==MK61_COLOR_PALETTE64) { assert(c==128 && payload);return ++palette_calls%5?1:2; }
        assert(a==MK61_COLOR_PRESENT);mk61_service_color_frame* f=payload;
        assert(f->pixel_bytes==6144 && f->tile_bytes==1536 && f->format==MK61_COLOR_TILE8);
        assert(lcd_clock==(legacy_lcd?12000000:24000000));
        assert(f->pixels==canvas && f->tiles==canvas+6144);++frames_shown;++session_frames;
        assert(mapped_roms==expect_mapped);
        assert(!machine.memory->window && machine.memory->page_count==(expect_mapped?16:2));
        if(expect_mapped) {
            assert(machine.memory->pages==bank_window && machine.memory->pages_tail==bank_tails[2]);
            assert(machine.rom>=cache_image && machine.rom<cache_image+cache_bytes);
        }
        assert((machine.keys[6]&1) && (machine.keys[2]&8)); // Menu Enter/R never leak into the guest.
        return frames_shown%3?1:2;
    }
    if(op==MK61_SERVICE_AUDIO_STREAM) {
        if(a==MK61_AUDIO_SYNTH_OPEN) {
            generator=*(mk61_service_audio_synth*)payload;assert(generator.rate==25000);++audio_opens;
            // Exercise callbacks during a slow native open, before the CPU clock starts.
            for(unsigned i=0;i<500;++i) { assert(!generator.sample(generator.context));micros_now+=40; }
            assert(machine.sound.time==(uint32_t)machine.cpu.cyc && !atomic_load(&machine.sound.starved));return 1;
        }
        assert(a==MK61_AUDIO_CLOSE);generator.sample=NULL;++audio_closes;return 1;
    }
    if(op==MK61_SERVICE_KEYBOARD) {
        assert(a==MK61_SERVICE_KEY_BITMAP && b==32);memset(payload,0,32);pump();
        if(opened_name) {
            unsigned key=0;
            if(open_error)key=open_keys++? 'q':' ';
            else if(open_keys++<2)key=13;
            else if(session_frames>=12)key=0x90;
            if(key)((uint8_t*)payload)[key/8]|=1U<<(key&7);
            return 1;
        }
        if(!released) {
            if(held_scans) { ((uint8_t*)payload)[held_key/8]|=1U<<(held_key&7);--held_scans; }
            else released=true;
            return 1;
        }
        assert(action<sizeof(script)/sizeof(*script));const action_item step=script[action];
        const bool ready=step.screen?!strncmp(ui,step.screen,strlen(step.screen)):!ui[0] && session_frames>=step.frames;
        if(ready) { ((uint8_t*)payload)[step.key/8]|=1U<<(step.key&7);++action;released=false;held_key=step.key;held_scans=2; }
        return 1;
    }
    assert(false);return 0;
}
static const mk61_app_services common={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,call,NULL,format,NULL};
static const void* query(uint32_t id,uint32_t version) { assert(id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION);return &common; }
static const mk61_app_api api={.magic=MK61_APP_API_MAGIC,.version=MK61_APP_API_VERSION,.struct_size=sizeof(mk61_app_api),
    .service=pump,.delay_ms=delay,.display_clear=clear_screen,.graphics_begin=graphics_begin,.graphics_end=graphics_end,.query_service=query};
const mk61_app_api* mk61_api=&api;
int main(int argc,char** argv) {
    assert(argc==2 || argc==3);asset_dir=argv[1];
    legacy_lcd=getenv("SPECTRUM_LEGACY_LCD")!=NULL;
    opened_name=getenv("SPECTRUM_OPEN_FILE");open_error=getenv("SPECTRUM_OPEN_ERROR")!=NULL;
    if(argc==3) {
        cache_mismatch=!strcmp(argv[2],"mismatch");expect_mapped=!cache_mismatch;
        char filename[1024];path(filename,"ROMCACHE.bin");FILE* f=fopen(filename,"rb");assert(f);
        assert(!fseek(f,0,SEEK_END));cache_bytes=(unsigned)ftell(f);rewind(f);
        cache_image=malloc(cache_bytes);assert(cache_image);
        assert(fread(cache_image,1,cache_bytes,f)==cache_bytes);fclose(f);
        assert(spectrum_rom_cache_valid(cache_image,cache_bytes));
    }
    assert(mk61_app_open_file(MK61_SERVICE_INVALID_ID)==MK61_APP_INVALID_FILE);
    assert(mk61_app_open_file(UINT32_MAX)==MK61_APP_INVALID_FILE);
    assert(!(opened_name?mk61_app_open_file(42):(uint32_t)spectrum_app_main()));
    assert(!psram && !generator.sample);
    for(unsigned i=0;i<3;++i)assert(!direct_sram[i]);
    if(opened_name) {
        assert(open_path_calls==1 && !action && graphics_ends==1);
        if(open_error) assert(!audio_opens && !audio_closes);
        else {
            assert(audio_opens==1 && audio_closes==1 && frames_shown>=12);
            if(suffix(opened_name,".sna") || suffix(opened_name,".z80") || suffix(opened_name,".scl"))assert(selected_reads);
        }
    } else assert(action==sizeof(script)/sizeof(*script) && audio_opens==7 && audio_closes==7 && frames_shown>350 && graphics_ends==1);
    assert(lcd_clock_requests>=audio_opens && lcd_clock==12000000);
    if(cache_image) { assert(spectrum_rom_cache_valid(cache_image,cache_bytes));free(cache_image); }
    if(opened_name) printf("Actual FILE_OPEN %s: external path, %s, held Enter blocked, readonly media, complete cleanup PASS\n",opened_name,open_error?"error handled":"started and F10 exited");
    else printf("Actual APP menus, PSRAM bounds, Beta/DivMMC, snapshots, key handoff and exit (%s): PASS\n",
        expect_mapped?"Flash ROM / retained RAM pages":cache_mismatch?"custom ROM fallback":"SD ROM / small pages");
    return 0;
}
