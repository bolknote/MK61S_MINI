#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main spectrum_app_main
#ifndef SPECTRUM_APP_MAIN_SOURCE
#define SPECTRUM_APP_MAIN_SOURCE "../examples/portable-apps/SPECTRUM/main.c"
#endif
#include SPECTRUM_APP_MAIN_SOURCE
#undef main

/* Execute the actual APP UI and core against a bounded resident ABI fixture.
 * Electrical timing, SRAM residency and multicore IRQs require the device. */
static const char* asset_dir;
static char ui[600];
static uint32_t micros_now,frames_shown,session_frames,calls,audio_opens,audio_closes;
static unsigned play_events,pause_events;
static unsigned palette_calls;
static unsigned lcd_clock_requests;
static uint32_t lcd_clock=12000000;
static bool legacy_lcd;
static const char* opened_name;
static bool open_error, save_opened_game;
static bool hicolor_sequence;
static unsigned hicolor_updates,hicolor_marker;
static bool test_flow;
static const char* preferences_phase;
static bool preferences_error;
static unsigned video_calls,video_shows,video_origin,video_psram_ops;
static uint32_t video_submit_us,video_capture_delay_us;
static bool video_test,video_pages,video_scroll,video_fail_once,video_busy_once,video_page_failed;
static mk61_service_color_frame last_strip;
static uint8_t last_attrs[4];
static unsigned open_keys,open_path_calls,selected_reads;
static unsigned snapshots_written;
static unsigned preferences_writes;
static uint8_t canvas[12800],*psram;
static uint8_t* direct_sram[3];
static uint8_t* workspace;
static unsigned psram_bytes,action;
static bool released=true;
static unsigned held_key,held_scans;
static unsigned graphics_ends;
static bool saw_ym,saw_acb;
static bool remote_audio,first_remote_scan;
static unsigned remote_scans;
static uint32_t remote_open_frame;
static mk61_service_audio_synth generator;
typedef struct { const char* screen;unsigned key,frames; } action_item;
static const action_item script[]={
    {"Spectrum",13,0},{NULL,27,80},
    {"Spectrum",'s',0},{"Spectrum",' ',0},
    {"Spectrum",'p',0},{"Options",'j',0},
    {"Options",'c',0},{"Options",'s',0},
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
static const action_item* active_script=script;
static unsigned script_count=sizeof(script)/sizeof(*script);
/* The menu renderer is exercised on the physical RGB panel; this fixture
 * supplies its titles to the scripted input while testing the real APP. */
bool spectrum_ui_begin(spectrum_ui* u,const mk61_app_services* api,const spectrum* s,bool running) {
    (void)s;(void)running;u->api=api;spectrum_display_fast(api);return true;
}
void spectrum_ui_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                        const char* const* labels,unsigned count,unsigned selected) {
    (void)u;(void)x;(void)y;(void)width;assert(selected<=count);
    if(!strcmp(title,"Options")) {
        assert(count==10 || (preferences_phase && SPECTRUM_HAS_RASTER && count==11));
        if(!strcmp(labels[6],"Sound chip: YM2149"))saw_ym=true;
        if(!strcmp(labels[7],"Stereo: ACB"))saw_acb=true;
    }
    if(preferences_phase && !strcmp(title,"Spectrum")) {
        if(count==1 && !strcmp(labels[0],"Cannot save settings")) preferences_error=true;
        if(!strcmp(preferences_phase,"restore") || !strcmp(preferences_phase,"bad") || !strcmp(preferences_phase,"foreign")) {
            const bool restored=!strcmp(preferences_phase,"restore");
            const unsigned model=restored?(SPECTRUM_HAS_PENTAGON?SPECTRUM_P1024:SPECTRUM_48):DEFAULT_MODEL;
            assert(spectrum_model(&machine)==model);
            assert(machine.sound_chip==(restored?SPECTRUM_YM:SPECTRUM_AY));
            assert(machine.sound_layout==(restored?SPECTRUM_ACB:SPECTRUM_ABC));
            assert(machine.joystick_mode==(restored?1:0));
            assert(machine.extensions==(restored?6:15));
            assert(exact_raster==(restored && SPECTRUM_HAS_RASTER));
        }
    }
    snprintf(ui,sizeof(ui),"%s",title);
}
void spectrum_ui_footer(spectrum_ui* u,const char* text) { (void)u;(void)text; }
bool spectrum_ui_present(spectrum_ui* u) { (void)u;return true; }
static void pump(void) {
#if SPECTRUM_HAS_PENTAGON
    assert(!pacing_video_io);
#endif
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
        assert((a==MK61_SERVICE_WORKSPACE && c==WORK_CACHE_BYTES) || (a==MK61_SERVICE_SCRATCH && c==2048));
        if(a==MK61_SERVICE_WORKSPACE) {assert(!workspace);workspace=r->data;}
        return 1;
    }
    if(op==MK61_SERVICE_MEMORY_RELEASE) {
        mk61_service_lease* r=payload;
        if(a==MK61_SERVICE_WORKSPACE) {assert(workspace==r->data);workspace=NULL;}
        free(r->data);*r=(mk61_service_lease){0};return 1;
    }
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
        if(video_test && r->offset>=RASTER_BASE) {
            ++video_psram_ops;
            if(a==MK61_BUFFER_WRITE) {micros_now+=video_capture_delay_us;video_capture_delay_us=0;}
        }
        if(a==MK61_BUFFER_READ) memcpy(r->data,psram+r->offset,r->size);
        else if(a==MK61_BUFFER_WRITE) memcpy(psram+r->offset,r->data,r->size);
        else if(a==MK61_BUFFER_FILL) memset(psram+r->offset,0,r->size);
        else assert(false);
        return 1;
    }
    if(op==MK61_SERVICE_FILE_BYTES) {
        if(a==MK61_FILE_BYTES_WRITE_SOURCE) {
            const mk61_service_write_source* request=payload;
            assert(!b && c==sizeof(*request) && !workspace && !generator.sample);
            for(unsigned i=0;i<WORK_CACHE_BYTES/SPECTRUM_CACHE_PAGE_BYTES;++i)
                assert(!machine.memory->page_data[i] && machine.memory->tag[i]==UINT16_MAX);
            const bool preference=suffix(request->name,".cfg");
            assert(preference?request->size==SPECTRUM_PREFERENCES_BYTES:request->size>512*1024 && suffix(request->name,".szx"));
            if(save_opened_game && !preference) assert(!strcmp(request->name,"/External games/ZX0003.SZX"));
            char filename[1024];path(filename,request->name);
            FILE* f=fopen(filename,"wbx");assert(f);
            for(unsigned at=0;at<request->size;) {
                uint8_t data[1024];
                const unsigned remaining=request->size-at;
                const unsigned n=remaining<sizeof(data)?remaining:sizeof(data);
                assert(request->read(request->context,at,data,n));
                assert(fwrite(data,1,n,f)==n);at+=n;
            }
            assert(!fclose(f));
            if(preference) ++preferences_writes;else ++snapshots_written;
            return 1;
        }
        mk61_service_file_bytes* r=payload;
        if(a==MK61_FILE_BYTES_ID) {
            assert((test_flow || preferences_phase) && !r->data && !r->offset && !r->size);
            if(preferences_phase) {
                assert(!strcmp(r->path,SPECTRUM_APP_PROFILE==2?"SINCLAIR.APP":"SPECTRUM.APP"));return 8;
            }
            assert(!strcmp(r->path,getenv("SPECTRUM_FLOW_TARGET")?getenv("SPECTRUM_FLOW_TARGET"):"SINCLAIR.APP"));return 8;
        }
        if(a==MK61_FILE_BYTES_PATH) {
            assert(opened_name && !r->path && r->offset==42 && r->size==256);++open_path_calls;
            if(open_error && !strcmp(opened_name,"missing"))return 0;
            assert(snprintf(r->data,r->size,"/External games/%s",opened_name)<(int)r->size);return 1;
        }
        char filename[1024];path(filename,r->path);
        if(a==MK61_FILE_BYTES_WRITE && suffix(r->path,".cfg")) {
            assert(!workspace && !generator.sample && r->size==SPECTRUM_PREFERENCES_BYTES);
            ++preferences_writes;
            if(preferences_phase && !strcmp(preferences_phase,"fail")) return 0;
        }
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
    if(op==MK61_SERVICE_FILE_ENTRY) {
        assert(!a && b==7 && !c && preferences_phase && !strcmp(preferences_phase,"short"));
        mk61_service_file* file=payload;memset(file,0,sizeof(*file));file->id=b;file->parent=3;return 1;
    }
    if(op==MK61_SERVICE_FILE_WRITE) {
        const mk61_service_write* request=payload;
        assert(a==3 && b==MK61_SERVICE_INVALID_ID && c==MK61_SERVICE_FILE_MK61_BINARY && !workspace && !generator.sample);
        assert(!strcmp(request->name,preferences_name()) && request->size==SPECTRUM_PREFERENCES_BYTES);
        char filename[1024];path(filename,request->name);
        FILE* f=fopen(filename,"wb");assert(f);
        assert(fwrite(request->data,1,request->size,f)==request->size);assert(!fclose(f));
        ++preferences_writes;return 0; // Physical publication succeeded, text registration rejected the binary CFG.
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
        if(a==MK61_COLOR_END) { lcd_clock=12000000;video_pages=video_scroll=false;return 1; }
        if(video_test) {
            if(a==MK61_COLOR_PAGES_BEGIN_V2) {
                const mk61_service_color_pages* pages=payload;
                assert(c==sizeof(*pages) && pages->top==64 && pages->height==192);
                video_pages=true;video_origin=2;return 1;
            }
            if(a==MK61_COLOR_PAGE_SELECT || a==MK61_COLOR_PAGE_SHOW) {
                const unsigned page=*(unsigned*)payload;
                assert(video_pages && page<2 && page!=video_origin);
                if(video_page_failed) {video_page_failed=false;return 0;}
                if(a==MK61_COLOR_PAGE_SHOW) {video_origin=page;++video_shows;}
                return 1;
            }
            if(a==MK61_COLOR_SCROLL_BEGIN) {
                const mk61_service_color_scroll* scroll=payload;
                assert(c==sizeof(*scroll) && scroll->height==320 && !scroll->offset);
                return video_scroll?1:3;
            }
            if(a==MK61_COLOR_SCROLL_END) {
                if(video_fail_once) {video_fail_once=false;return 0;}
                video_scroll=true;return 1;
            }
            assert(a==MK61_COLOR_PRESENT && c==sizeof(last_strip));
            if(video_busy_once) {video_busy_once=false;return 2;}
            micros_now+=video_submit_us;video_submit_us=0;
            last_strip=*(const mk61_service_color_frame*)payload;
            if(last_strip.tile_bytes==sizeof(last_attrs)) memcpy(last_attrs,last_strip.tiles,sizeof(last_attrs));
            ++video_calls;return 1;
        }
        if(a==MK61_COLOR_PAGES_BEGIN_V2) return 0;
        if(a==MK61_COLOR_SCROLL_BEGIN) return video_scroll?1:3;
        if(a==MK61_COLOR_SCROLL_END) {video_scroll=true;return 1;}
        if(a==MK61_COLOR_PALETTE64) { assert(c==128 && payload);return ++palette_calls%5?1:2; }
        if(a==MK61_COLOR_FORMATS) return preferences_phase?1u<<MK61_COLOR_CELL565:0;
        assert(a==MK61_COLOR_PRESENT);mk61_service_color_frame* f=payload;
        const unsigned format=f->format&~MK61_COLOR_PRESERVE_OUTSIDE;
        if(SPECTRUM_HAS_EXTENDED_VIDEO && (format==MK61_COLOR_INDEX4 || format==MK61_COLOR_CELL565)) {
            assert(f->pixel_bytes<=SPECTRUM_VIDEO_WORK_BYTES && f->width<=320 && f->height<=64);
            if(hicolor_sequence && format==MK61_COLOR_CELL565 && f->width==8 && f->height==1) {
                assert(f->x==32 && f->y==64 && f->pixel_bytes==1);
                assert(!hicolor_updates || f->pixels[0]==hicolor_marker+1);
                hicolor_marker=f->pixels[0];++hicolor_updates;
            }
            ++frames_shown;++session_frames;return 1;
        }
        assert(f->pixel_bytes==6144 && f->tile_bytes==1536 && f->format==MK61_COLOR_TILE8);
        assert(lcd_clock==(legacy_lcd?12000000:24000000));
        assert(f->pixels==canvas && f->tiles==canvas+6144);++frames_shown;++session_frames;
        if(test_flow && !strcmp(opened_name,"OPEN128.Z80")) assert(spectrum_is_128(&machine) && machine.ay.clk==SPECTRUM_128_AY_HZ);
        assert(machine.memory->paged_rom && !machine.rom && !machine.memory->window && machine.memory->page_count==16);
        assert(workspace && machine.memory->page_data[0]==workspace &&
               machine.memory->page_data[8]==page_runs[1] &&
               machine.memory->page_data[10]==page_runs[2] &&
               machine.memory->page_data[14]==canvas+10752);
        assert((machine.keys[6]&1) && (machine.keys[2]&8)); // Menu Enter/R never leak into the guest.
        return frames_shown%3?1:2;
    }
    if(op==MK61_SERVICE_AUDIO_STREAM) {
        if(a==MK61_AUDIO_PSG_CONFIG_OPEN && remote_audio) {
            const mk61_service_audio_psg_config* config=payload;
            assert(c==sizeof(*config) && !*config->psg.running && !generator.sample);
            generator=config->psg.local;++audio_opens;
            remote_open_frame=machine.frames;first_remote_scan=true;
            return 2;
        }
        if(a==MK61_AUDIO_PSG_OPEN || a==MK61_AUDIO_PSG_CONFIG_OPEN)return 0; // Older resident: use SYNTH_OPEN.
        if(a==MK61_AUDIO_SYNTH_OPEN) {
            if(saw_ym && saw_acb)assert(machine.sound_chip==SPECTRUM_YM && machine.sound_layout==SPECTRUM_ACB);
            generator=*(mk61_service_audio_synth*)payload;assert(generator.rate==25000);++audio_opens;
            // Exercise callbacks during a slow native open, before the CPU clock starts.
            for(unsigned i=0;i<500;++i) { assert(!generator.sample(generator.context));micros_now+=40; }
            assert(machine.sound.time==(uint32_t)machine.cpu.cyc && !atomic_load(&machine.sound.starved));return 1;
        }
        assert(a==MK61_AUDIO_CLOSE && !first_remote_scan);
        generator.sample=NULL;++audio_closes;return 1;
    }
    if(op==MK61_SERVICE_KEYBOARD) {
        if(first_remote_scan) {
            assert(machine.frames!=remote_open_frame);
            first_remote_scan=false;++remote_scans;
        }
        assert(a==MK61_SERVICE_KEY_BITMAP && b==32);memset(payload,0,32);pump();
        if(opened_name) {
            unsigned key=0;
            const unsigned limit=hicolor_sequence?48:12;
            if(open_error)key=open_keys++? 'q':' ';
            else if(open_keys++<2)key=13;
            else if(session_frames>=limit || (SPECTRUM_HAS_EXTENDED_VIDEO && spectrum_video_mode(&machine) && machine.frames>=limit)) {
                if(!save_opened_game)key=0x90;
                else if(!ui[0])key=27;
                else if(!snapshots_written)key='s';
                else key=open_keys%2?' ':'q';
            }
            if(key)((uint8_t*)payload)[key/8]|=1U<<(key&7);
            return 1;
        }
        if(!released) {
            if(held_scans) { ((uint8_t*)payload)[held_key/8]|=1U<<(held_key&7);--held_scans; }
            else released=true;
            return 1;
        }
        assert(action<script_count);const action_item step=active_script[action];
        const bool ready=step.screen?!strncmp(ui,step.screen,strlen(step.screen)):!ui[0] && session_frames>=step.frames;
        if(ready) { ((uint8_t*)payload)[step.key/8]|=1U<<(step.key&7);++action;released=false;held_key=step.key;held_scans=2; }
        return 1;
    }
    if(op==MK61_SERVICE_DEBUG_WRITE) {
        assert(!b && !c && payload && a<=128 && !machine.sound.clock_running);
        if(a==sizeof("SP STATE=PLAYING\n")-1 && !memcmp(payload,"SP STATE=PLAYING\n",a)) {
            assert(generator.sample);++play_events;
        } else if(a==sizeof("SP STATE=PAUSED\n")-1 && !memcmp(payload,"SP STATE=PAUSED\n",a)) {
            assert(!generator.sample);++pause_events;
        } else {
            assert(a==sizeof("SP STATE=SAVED\n")-1 && !memcmp(payload,"SP STATE=SAVED\n",a));
            assert(!generator.sample && snapshots_written);
        }
        return 1;
    }
    assert(false);return 0;
}
static const mk61_app_services common={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,call,NULL,format,NULL};
static const void* query(uint32_t id,uint32_t version) { assert(id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION);return &common; }
static const mk61_app_api api={.magic=MK61_APP_API_MAGIC,.version=MK61_APP_API_VERSION,.struct_size=sizeof(mk61_app_api),
    .service=pump,.delay_ms=delay,.display_clear=clear_screen,.graphics_begin=graphics_begin,.graphics_end=graphics_end,.query_service=query};
const mk61_app_api* mk61_api=&api;
#if !SPECTRUM_APP_PROFILE
static void guest_store(spectrum* s,uint16_t address,uint8_t value) {
    const uint8_t code[]={0x3e,value,0x32,(uint8_t)address,(uint8_t)(address>>8)};
    assert(spectrum_bank_write(s->memory,2,0,code,sizeof(code)));
    s->cpu.pc=0x8000;
    z80_step(&s->cpu);z80_step(&s->cpu);
}
static void extended_frames(void) {
    static uint8_t fixed[32768],slots[16384],rom[16384];
    spectrum state;active_machine=&state;services=&common;
    const spectrum_memory_io io={NULL,external_read,external_write,external_clear};
    uint8_t* tails[]={fixed+15360,fixed+31744};
    uint8_t* runs[]={slots,slots+8192,slots+10240,slots+14336};
    external.handle=1;psram_bytes=VIDEO_CAPTURE_END;
    psram=calloc(1,psram_bytes);assert(psram);
    memset(&state,0,sizeof(state));state.ram=fixed;state.rom=rom;
    assert(spectrum_memory_init_fragmented(&bank_memory,fixed,fixed+16384,tails,runs,64,io));
    spectrum_attach_memory(&state,&bank_memory);
    spectrum_hicolor_changes changes;
    spectrum_pentagon_changes pentagon;
    if(SPECTRUM_HAS_PENTAGON) spectrum_pentagon_watch(&state,&pentagon);
    state.cpu.port_out(&state.cpu,0xeff7,SPECTRUM_VIDEO_16C|4);
    state.cpu.port_out(&state.cpu,0x7ffd,4);
    video_test=true;video_output out={.guard_us=VIDEO_INITIAL_GUARD_US};
    const unsigned expected[]={3,6,6,7,14,14,21,22,25,25,26,29,30,31,34,37,41};
    for(unsigned turn=0;turn<sizeof(expected)/sizeof(*expected);++turn) {
        const unsigned mode=turn<4 || turn==16?SPECTRUM_VIDEO_16C:
            turn<8?SPECTRUM_VIDEO_WIDE:SPECTRUM_VIDEO_HICOLOR;
        if(turn==3) {
            guest_store(&state,0x4000,0x29);video_busy_once=true;
        }
        if(turn==4) {
            state.cpu.port_out(&state.cpu,0xeff7,SPECTRUM_VIDEO_WIDE|4);
            guest_store(&state,0xd018,0x47);
        }
        if(turn==6) video_fail_once=true;
        if(turn==7) guest_store(&state,0xc018,0xff);
        if(turn==8) {
            if(SPECTRUM_HAS_PENTAGON) spectrum_pentagon_watch(&state,NULL);
            state.memory->banks=8;state.memory->extended=false;state.pentagon=false;
            state.extensions|=SPECTRUM_TIMEX;
            spectrum_hicolor_watch(&state,&changes);
            state.cpu.port_out(&state.cpu,0x7ffd,5);
            state.cpu.port_out(&state.cpu,0xff,2);
            assert(changes.windows==10 && !state.cpu.write_pages[16] && !state.cpu.write_pages[48]);
            assert(state.cpu.read_pages[16]==state.cpu.read_pages[48] && state.cpu.write_pages[22]);
        }
        if(turn==9) guest_store(&state,0x4000,bank_memory.cache[0]);
        if(turn==10) guest_store(&state,0xf011,0x47);
        if(turn==11) state.border=1;
        if(turn==12) guest_store(&state,0x6000,0xc7);
        if(turn==13) state.frames=16;
        if(turn==14) {
            guest_store(&state,0x4000,0x55);guest_store(&state,0x47ff,0x55);
            guest_store(&state,0x4800,0x55);guest_store(&state,0x4fff,0x55);
        }
        if(turn==15) {
            state.cpu.port_out(&state.cpu,0x7ffd,15);
            assert(changes.repaint && !changes.windows && state.cpu.write_pages[16]);
        }
        if(turn==16) {
            spectrum_hicolor_watch(&state,NULL);
            state.memory->banks=64;state.memory->extended=state.pentagon=true;
            if(SPECTRUM_HAS_PENTAGON) spectrum_pentagon_watch(&state,&pentagon);
            state.cpu.port_out(&state.cpu,0xeff7,SPECTRUM_VIDEO_16C|4);
        }
        const unsigned io_before=video_psram_ops;
        if(turn==10) {
            uint8_t blocked[32]={0};
            uint32_t deadline=micros_now+4800-guest_time_us(spectrum_frame_cycles(&machine));
            uint32_t keyboard_deadline=micros_now+100000;
            const char* error=NULL;
            out.pending=mode;
            assert(pace_frame(blocked,&keyboard_deadline,&deadline,&out,canvas,&error) && !error);
            assert(out.pending==mode && !out.active && video_calls==expected[turn-1]);
            deadline=micros_now;video_submit_us=4000;
            assert(pace_frame(blocked,&keyboard_deadline,&deadline,&out,canvas,&error) && !error);
            assert(!out.pending && out.guard_us>=6000);
        } else {
            video_begin(&out,mode);
            if(turn==16) {
                assert(video_present(&out,canvas) && !out.next);
                assert(video_present(&out,canvas) && out.next==1);
                video_page_failed=true;
            }
            for(unsigned budget=20;out.active && budget;--budget) assert(video_present(&out,canvas));
        }
        assert(!out.active && video_calls==expected[turn]);
        if(turn==2 || turn==3 || turn==5 || turn==9 || turn==10 || turn==12 || turn==13)
            assert(video_psram_ops==io_before);
        if(turn==7) assert(video_psram_ops==io_before+1); // Keep the sent Wide row in PSRAM.
        if(turn==3) assert(pentagon.strips[0][0].bottom==1 && !pentagon.strips[1][0].bottom);
        if(turn==14 || turn==15) assert(!out.packed && video_psram_ops>io_before);
        if(turn==13) {
            assert(last_strip.width==8 && last_strip.height==1 && last_strip.x==32 && last_strip.y==64);
            assert(last_attrs[0]==255 && last_attrs[1]==255 && last_attrs[2]==0 && last_attrs[3]==0);
        }
        if(turn==3 || turn==7 || turn==10) {
            const unsigned x=turn==3?32:turn==7?0:32+17*8,y=turn==3?64:turn==7?8:192;
            assert(last_strip.x==x && last_strip.y==y && last_strip.width==(turn==7?20:8) && last_strip.height==1);
            assert(last_strip.format&MK61_COLOR_PRESERVE_OUTSIDE);
            if(turn==10) {
                assert(last_strip.pixel_bytes==1 && last_strip.tile_bytes==4);
                assert(last_attrs[0]==0 && last_attrs[1]==0 && last_attrs[2]==255 && last_attrs[3]==255);
            } else assert(last_strip.pixel_bytes==(turn==7?10:4) && !last_strip.tile_bytes);
        }
    }
    assert(video_shows==4);
#if SPECTRUM_HAS_PENTAGON
    {
        video_output queued={.guard_us=VIDEO_INITIAL_GUARD_US,.ready_guard_us=VIDEO_READY_GUARD_US,.clear=true};
        video_begin(&queued,SPECTRUM_VIDEO_16C);
        assert(video_present(&queued,canvas));
        assert(video_present(&queued,canvas) && queued.next==1);
        queued.pending=SPECTRUM_VIDEO_16C;
        uint8_t blocked[32]={0};
        uint32_t deadline=micros_now,keyboard_deadline=micros_now+100000;
        const char* error=NULL;
        assert(pace_frame(blocked,&keyboard_deadline,&deadline,&queued,canvas,&error) && !error);
        assert(!queued.active && !queued.pending && video_shows==6);
    }
#endif
#if SPECTRUM_HAS_PENTAGON
    for(unsigned i=0;i<2;++i) {
        const unsigned mode=i?SPECTRUM_VIDEO_WIDE:SPECTRUM_VIDEO_16C;
        state.cpu.port_out(&state.cpu,0xeff7,mode|4);
        color(MK61_COLOR_END,NULL);
        video_output restarting={.guard_us=VIDEO_INITIAL_GUARD_US,.pending=mode,.clear=true};
        restarting.ready_guard_us=VIDEO_READY_GUARD_US;
        uint8_t blocked[32]={0};
        uint32_t deadline=micros_now,keyboard_deadline=micros_now+100000;
        const char* error=NULL;
        const unsigned calls=video_calls;
        video_capture_delay_us=i?20080:18813;
        assert(pace_frame(blocked,&keyboard_deadline,&deadline,&restarting,canvas,&error) && !error);
        assert(restarting.active && restarting.selected && !restarting.next && video_calls==calls);
        assert(restarting.guard_us==VIDEO_INITIAL_GUARD_US && !video_capture_delay_us);
        assert(pace_frame(blocked,&keyboard_deadline,&deadline,&restarting,canvas,&error) && !error);
        const unsigned strips=i?SPECTRUM_WIDE_STRIPS:3;
        assert(!restarting.active && video_calls==calls+strips);
        if(!i) {
            restarting.pending=mode;
            assert(pace_frame(blocked,&keyboard_deadline,&deadline,&restarting,canvas,&error) && !error);
            assert(!restarting.active && restarting.valid[0] && restarting.valid[1]);
        }
        assert(restarting.valid[restarting.page]);
        state.cpu.port_out(&state.cpu,0x7ffd,state.memory->paging^8);
        restarting.pending=mode;
        video_capture_delay_us=20080;
        const unsigned prior=video_calls;
        assert(pace_frame(blocked,&keyboard_deadline,&deadline,&restarting,canvas,&error) && !error);
        assert(restarting.active && restarting.selected && !restarting.next && video_calls==prior);
        assert(restarting.guard_us==VIDEO_INITIAL_GUARD_US && !video_capture_delay_us);
        assert(pace_frame(blocked,&keyboard_deadline,&deadline,&restarting,canvas,&error) && !error);
        assert(!restarting.active && (i?video_calls<=prior+strips:video_calls==prior+strips));
    }
    puts("Cold capture and live display-bank change at 20.480 ms guest cadence: PASS");
    color(MK61_COLOR_END,NULL);
    spectrum_reset(&state);
    state.cpu.port_out(&state.cpu,0xeff7,0x44);
    spectrum_pentagon_watch(&state,&pentagon);
    memset(canvas,7,4096);
    for(unsigned bank=4;bank<=7;++bank)
        for(unsigned offset=0;offset<SPECTRUM_BANK_BYTES;offset+=4096)
            assert(spectrum_bank_write(&bank_memory,bank,offset,canvas,4096));
    const unsigned wide_pixel=8192+1; // The second cell of the central image.
    const uint8_t value=255;
    assert(spectrum_bank_write(&bank_memory,7,wide_pixel,&value,1));
    video_output diff={.clear=true};
    const unsigned updates[]={7,1,1,1,0,7,0};
    for(unsigned i=0;i<sizeof(updates)/sizeof(*updates);++i) {
        if(i==3) guest_store(&state,0x4000+wide_pixel,value);
        else state.cpu.port_out(&state.cpu,0x7ffd,(i==1 || i==4 || i==6)?0x18:0x10);
        if(i==5) video_fail_once=true;
        const unsigned before=video_calls;
        video_begin(&diff,SPECTRUM_VIDEO_WIDE);
        for(unsigned budget=24;diff.active && budget;--budget) assert(video_present(&diff,canvas));
        assert(!diff.active && diff.valid[0] && video_calls==before+updates[i]);
        if(updates[i]==1) assert(last_strip.x==60 && last_strip.y==72 && last_strip.width==20 && last_strip.height==1);
    }
    puts("Wide bank changes: one clipped rectangle, no traffic for equal banks, reference recovery after LCD fault PASS");
#endif
    if(SPECTRUM_HAS_PENTAGON) spectrum_pentagon_watch(&state,NULL);
    video_test=false;external.handle=0;active_machine=NULL;free(psram);psram=NULL;
    puts("Actual LCD strip renderer: watched HiColor/16C/Wide writes, per-page damage, FLASH, bank flip and fault recovery PASS");
}

#endif
static void bounded_audio_prefill(void) {
    static uint8_t ram[SPECTRUM_RAM_BYTES],rom[SPECTRUM_ROM_BYTES];
    spectrum state;
    spectrum_tape empty={0};
    active_machine=&state;tape=&empty;
    spectrum_init(&state,ram,rom);
    rom[0]=0x76; // HALT: one quiet guest frame is available immediately.
    state.cpu.cyc=UINT32_MAX-99;
    spectrum_sound_begin(&state,NULL,NULL);spectrum_sound_clock(&state,false);
    prime_audio();
    assert((uint32_t)(state.cpu.cyc-(UINT32_MAX-99U))==SPECTRUM_FRAME_TSTATES);
    assert(atomic_load(&state.sound.produced)==(uint32_t)state.cpu.cyc);
    assert(!atomic_load(&state.sound.clock_running) && !atomic_load(&state.sound.write));

    const uint8_t loop[]={0x3e,0x10,0xd3,0xfe,0xee,0x10,0x18,0xfa};
    memcpy(rom,loop,sizeof(loop));spectrum_reset(&state);
    spectrum_sound_begin(&state,NULL,NULL);spectrum_sound_clock(&state,false);
    prime_audio();
    const unsigned events=atomic_load(&state.sound.write);
    assert(events>SPECTRUM_SOUND_QUEUE_EVENTS/2 && events<SPECTRUM_SOUND_QUEUE_EVENTS);
    assert(state.cpu.cyc<SPECTRUM_FRAME_TSTATES && !atomic_load(&state.sound.clock_running));
#if SPECTRUM_HAS_SINCLAIR
    spectrum_memory banks;
    const spectrum_memory_io io={NULL,external_read,external_write,external_clear};
    uint8_t* tails[]={ram+15360,ram+31744};
    uint8_t* runs[]={ram+32768,ram+40960,ram+43008,ram+47104};
    external.handle=1;psram_bytes=SPECTRUM_ROM_BASE+2*SPECTRUM_ROM_BYTES;
    psram=calloc(1,psram_bytes);assert(psram);
    psram[SPECTRUM_ROM_BASE]=0x76;
    assert(spectrum_memory_init_fragmented(&banks,ram,ram+16384,tails,runs,8,io));
    spectrum_attach_memory(&state,&banks);
    for(unsigned expected=4;expected<=5;++expected) {
        spectrum_sound_begin(&state,NULL,NULL);spectrum_sound_clock(&state,false);
        prime_audio();
        assert(state.frames==expected && state.cpu.cyc==expected*SPECTRUM_128_FRAME_TSTATES);
        assert(!banks.fault && !atomic_load(&state.sound.clock_running));
    }
    external.handle=0;free(psram);psram=NULL;
    puts("Sinclair 128K M3 prefill: four cold guest frames, one on resume PASS");
#endif
    active_machine=NULL;tape=NULL;
    puts("48K M3 prefill: real guest frame, clock wrap and bounded dense event queue PASS");
}
static void preferences_scenario(const char* filename) {
    const action_item save_script[]={
        {"Spectrum",'m',0},{"Machine",SPECTRUM_HAS_PENTAGON?0xB6:0xB5,0},{"Machine",13,0},
        {"Spectrum",'p',0},{"Options",'j',0},{"Options",'c',0},{"Options",'s',0},
        {"Options",'1',0},{"Options",'4',0},
#if SPECTRUM_HAS_RASTER
        {"Options",'r',0},
#endif
        {"Options",27,0},{"Spectrum",'q',0}
    };
    const action_item failed_script[]={
        {"Spectrum",'p',0},{"Options",'j',0},{"Options",27,0},
        {"Spectrum",' ',0},{"Spectrum",'q',0}
    };
    const action_item exit_script[]={{"Spectrum",'q',0}};
    uint8_t before[SPECTRUM_PREFERENCES_BYTES]={0};
    const bool save=!strcmp(preferences_phase,"save"),fail=!strcmp(preferences_phase,"fail");
    const bool short_file=!strcmp(preferences_phase,"short"),handoff=!strcmp(preferences_phase,"handoff");
    if(save || handoff) remove(filename);
    else {
        FILE* f=fopen(filename,"rb");assert(f);
        assert(fread(before,1,sizeof(before),f)==sizeof(before));assert(!fclose(f));
        if(!strcmp(preferences_phase,"bad") || !strcmp(preferences_phase,"foreign") || short_file) {
            if(!strcmp(preferences_phase,"foreign")) {
                spectrum_preferences other={SPECTRUM_HAS_PENTAGON?SPECTRUM_128:SPECTRUM_P512,15,0,0,1,0,3};
                spectrum_preferences_encode(&other,before);
            } else before[7]^=1;
            f=fopen(filename,"wb");assert(f);
            assert(fwrite(before,1,short_file?3:sizeof(before),f)==(short_file?3:sizeof(before)));
            assert(!fclose(f));
        }
    }
    active_script=save?save_script:fail || short_file?failed_script:exit_script;
    script_count=save?sizeof(save_script)/sizeof(*save_script):fail || short_file?
        sizeof(failed_script)/sizeof(*failed_script):sizeof(exit_script)/sizeof(*exit_script);
    if(handoff) assert(!run_app(MK61_SERVICE_INVALID_ID,SPECTRUM_HAS_PENTAGON?SPECTRUM_P1024:SPECTRUM_48));
    else assert(!spectrum_app_main());
    assert(!psram && !workspace && !generator.sample && !audio_opens && !audio_closes);
    for(unsigned i=0;i<3;++i) assert(!direct_sram[i]);
    assert(action==script_count && graphics_ends==1);
    uint8_t after[SPECTRUM_PREFERENCES_BYTES]={0};
    FILE* f=fopen(filename,"rb");assert(f);
    assert(fread(after,1,sizeof(after),f)==sizeof(after));assert(!fclose(f));
    if(handoff) {
        spectrum_preferences restored;
        assert(preferences_writes==1 && spectrum_preferences_decode(&restored,after));
        assert(restored.model==(SPECTRUM_HAS_PENTAGON?SPECTRUM_P1024:SPECTRUM_48));
        assert(restored.chip==SPECTRUM_AY && restored.layout==SPECTRUM_ABC && !restored.joystick);
    } else if(save) {
        spectrum_preferences restored;
        assert(preferences_writes==2 && spectrum_preferences_decode(&restored,after));
        assert(restored.model==(SPECTRUM_HAS_PENTAGON?SPECTRUM_P1024:SPECTRUM_48));
        assert(restored.extensions==6 && restored.joystick==1 && restored.chip==SPECTRUM_YM &&
            restored.layout==SPECTRUM_ACB && restored.raster==SPECTRUM_HAS_RASTER);
        for(unsigned i=0;i<sizeof(after);++i) {
            after[i]^=1;assert(!spectrum_preferences_decode(&restored,after));after[i]^=1;
        }
    } else if(short_file) {
        spectrum_preferences restored;
        assert(spectrum_preferences_decode(&restored,after) && restored.model==DEFAULT_MODEL && restored.joystick==1);
        assert(preferences_writes==1 && !preferences_error);
    } else {
        assert(!memcmp(before,after,sizeof(after)));
        assert(preferences_error==fail && preferences_writes==(unsigned)fail);
    }
    printf("Actual APP preferences %s: model, sound, joystick, extensions, raster, SD and cache ownership PASS\n",preferences_phase);
}
int main(int argc,char** argv) {
    assert(argc==2);asset_dir=argv[1];
    char settings_path[1024];path(settings_path,preferences_name());
    preferences_phase=getenv("SPECTRUM_PREFERENCES_PHASE");
    if(preferences_phase) { preferences_scenario(settings_path);return 0; }
    remove(settings_path);
    legacy_lcd=getenv("SPECTRUM_LEGACY_LCD")!=NULL;
    remote_audio=getenv("SPECTRUM_REMOTE_AUDIO")!=NULL;
    opened_name=getenv("SPECTRUM_OPEN_FILE");open_error=getenv("SPECTRUM_OPEN_ERROR")!=NULL;
    hicolor_sequence=SPECTRUM_APP_PROFILE==4 && opened_name && !strcmp(opened_name,"HICOLOR.SZX");
    save_opened_game=getenv("SPECTRUM_SAVE_OPEN_FILE")!=NULL;
    test_flow=getenv("SPECTRUM_TEST_FLOW")!=NULL;
#if SPECTRUM_APP_PROFILE
    if(test_flow) {
        uint32_t context[2]={42,0};
        mk61_app_flow step={.size=sizeof(step),.version=MK61_APP_FLOW_VERSION,.context=context,
            .context_size=sizeof(context),.current=mk61_app_flow_to(MK61_APP_KIND_APPLICATION,5,MK61_APP_FLOW_FILE_PHASE)};
        if(SPECTRUM_HAS_SINCLAIR) context[1]=SPECTRUM_128+1;
        assert(mk61_app_file_flow()==MK61_APP_FLOW_MAGIC && mk61_app_flow_step(&step));
        assert(!psram && !workspace && !generator.sample && open_path_calls==1 && graphics_ends==1);
        assert(!preferences_writes);
        const char* target=getenv("SPECTRUM_FLOW_TARGET");
        if(target) {
            assert(step.action==MK61_FLOW_NEXT && step.next.file_id==7 && step.next.phase==MK61_APP_FLOW_FILE_PHASE);
            assert(context[0]==42 && context[1]==(unsigned)atoi(getenv("SPECTRUM_FLOW_MODEL"))+1 && !audio_opens);
            printf("Actual APP Flow hands %s to %s and releases all leases PASS\n",opened_name,target);
        } else {
            assert(step.action==MK61_FLOW_RETURN && !step.result && audio_opens==1 && frames_shown);
            if(hicolor_sequence) {
                assert(hicolor_updates>=40);
                puts("HiColor output preserves consecutive guest frame markers: PASS");
            }
            printf("Actual profile %u APP Flow loads and plays %s PASS\n",SPECTRUM_APP_PROFILE,opened_name);
        }
        return 0;
    }
#endif
    assert(mk61_app_open_file(MK61_SERVICE_INVALID_ID)==MK61_APP_INVALID_FILE);
    assert(mk61_app_open_file(UINT32_MAX)==MK61_APP_INVALID_FILE);
    assert(!(opened_name?mk61_app_open_file(42):(uint32_t)spectrum_app_main()));
    assert(!psram && !workspace && !generator.sample);
    assert(play_events==audio_opens && pause_events==audio_closes);
    char picker_path[256]=".";
    directory=picker_path;
    parent_directory();assert(!strcmp(picker_path,"/"));
    parent_directory();assert(!strcmp(picker_path,"/"));
    strcpy(picker_path,"/Programs/Spectrum");
    parent_directory();assert(!strcmp(picker_path,"/Programs"));
    for(unsigned i=0;i<3;++i)assert(!direct_sram[i]);
    if(opened_name) {
        assert(open_path_calls==1+save_opened_game && !action && graphics_ends==1);
        if(save_opened_game) assert(snapshots_written==1);
        if(open_error) assert(!audio_opens && !audio_closes);
        else {
            assert(audio_opens==1 && audio_closes==1 && frames_shown>=12);
            if(is_snapshot(opened_name) || suffix(opened_name,".scl"))assert(selected_reads);
        }
    } else assert(action==sizeof(script)/sizeof(*script) && audio_opens==7 && audio_closes==7 &&
        frames_shown>350 && graphics_ends==1 && saw_ym && saw_acb && snapshots_written==1);
    assert(lcd_clock_requests>=audio_opens && lcd_clock==12000000);
    if(remote_audio) {
        assert(remote_scans==audio_opens);
        puts("Actual M3 APP startup: first frame produced before first keyboard pump, release and exit PASS");
    }
    if(remote_audio && !opened_name) bounded_audio_prefill();
#if !SPECTRUM_APP_PROFILE
    if(!opened_name && !remote_audio && !legacy_lcd) extended_frames();
#endif
    if(opened_name) printf("Actual FILE_OPEN %s: external path, %s, held Enter blocked, readonly media, complete cleanup PASS\n",opened_name,open_error?"error handled":"started and F10 exited");
    else puts("Actual APP menus, SD ROM->PSRAM/shared16KiB cache, Beta/DivMMC, snapshots, key handoff and exit: PASS");
    return 0;
}
