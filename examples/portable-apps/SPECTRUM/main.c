#include "mk61_app.h"
#include "spectrum.h"
#include "media.h"
#include "ui.h"
#include "preferences.h"
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
#include "szx.h"
#include "tape.h"
#endif
#include <string.h>

static const mk61_app_services* services;
static inline uint32_t pacing_clock_us(void) {
#if defined(MK61_TARGET_PICOCALC) && defined(__ARM_ARCH_6M__)
    // Pico H's native MICROS service reads the same monotonic TIMERAWL.
    // Poll locally in APP SRAM during the final pacing guard, avoiding
    // indirect calls and contention for the resident's XIP cache lines.
    return *(volatile uint32_t*)(uintptr_t)0x40054028u;
#else
    return services->call(MK61_SERVICE_MICROS,0,0,0,NULL);
#endif
}
static spectrum* active_machine;
#define machine (*active_machine)
static uint8_t keys[32],previous_keys[32];
static char *directory,*snapshot_path;
static uint32_t opened_file;
static bool started;
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
static spectrum_tape* tape;
static char* tape_path;
#if SPECTRUM_HAS_TAPE_RECORD
static spectrum_tape_recorder* recording;
#endif
#endif
static uint8_t *guest_blocks[2],*bank_tails[2],*page_runs[4];
enum { WORK_CACHE_BYTES=8192 };
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
enum { TAPE_BASE=SPECTRUM_EXTERNAL_BYTES+SPECTRUM_TRD_BYTES,
       RASTER_BASE=TAPE_BASE+2*SPECTRUM_TAPE_SLOT_BYTES, WIDE_REFERENCE=RASTER_BASE+2*SPECTRUM_BANK_BYTES,
       VIDEO_CAPTURE_END=WIDE_REFERENCE+(SPECTRUM_HAS_PENTAGON_VIDEO?SPECTRUM_WIDE_WIDTH*SPECTRUM_WIDE_HEIGHT/2:
                                         SPECTRUM_HAS_RASTER?SPECTRUM_RASTER_PACKED_BYTES:0),
       VIDEO_INITIAL_GUARD_US=5500, VIDEO_READY_GUARD_US=3000, RASTER_IDLE=255 };
typedef struct {
    uint32_t guard_us;
    uint8_t next,bank,mode;
    bool clear,ready,selected,transaction,valid,repainted;
} raster_output;
#if SPECTRUM_HAS_FAST_VIDEO
#if SPECTRUM_HAS_PENTAGON
enum { WIDE_PACKED_ROWS=24, WIDE_PACKED_BYTES=WIDE_PACKED_ROWS*SPECTRUM_WIDE_WIDTH/2 };
_Static_assert(2*WIDE_PACKED_BYTES<=SPECTRUM_VIDEO_WORK_BYTES,"Wide split windows overlap the disk cache");
#endif
typedef struct {
    uint32_t guard_us;
    uint16_t background,patch_offset;
    uint8_t mode,next,page,valid[2],pending;
    bool active,ready,clear,pages,selected,transaction,repainted,packed;
#if SPECTRUM_HAS_PENTAGON
    uint32_t ready_guard_us;
    bool clipped,compare_wide,gap_right;
    spectrum_wide_gap gaps[SPECTRUM_WIDE_STRIPS];
#endif
    spectrum_video_damage patches[SPECTRUM_HAS_PENTAGON?SPECTRUM_WIDE_STRIPS:3];
    mk61_service_color_frame part;
    spectrum_video_snapshot saved;
} video_output;
#endif
static uint32_t color(uint32_t operation,mk61_service_color_frame* frame);
#endif
#if (SPECTRUM_HAS_PENTAGON || SPECTRUM_RASTER_ENABLED) && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
static bool pacing_video_io;
#endif
static bool banked_buffers;
static spectrum_memory bank_memory;
static mk61_service_buffer external;
typedef struct { char* path;bool scl; } mounted_media;
static mounted_media floppy,sd_card;
static spectrum_ui osd;
static unsigned root_selected;
static mk61_app_flow* app_flow;
static spectrum_preferences preferences;
static bool preferences_dirty;
static bool exact_raster;
enum { DEFAULT_MODEL=SPECTRUM_HAS_TIMEX_2068?SPECTRUM_TS2068:
       (SPECTRUM_APP_PROFILE==3 || SPECTRUM_APP_PROFILE==7)?SPECTRUM_P1024:
       (SPECTRUM_APP_PROFILE==4 || SPECTRUM_APP_PROFILE==8)?SPECTRUM_48:
       SPECTRUM_HAS_PENTAGON?SPECTRUM_P512:SPECTRUM_128 };

static bool model_available(unsigned model) {
    if(spectrum_timex_2068(model)) return SPECTRUM_HAS_TIMEX_2068;
    if(SPECTRUM_HAS_TIMEX_2068) return false;
    if(model==SPECTRUM_TC2048) return SPECTRUM_HAS_TIMEX;
    return model==SPECTRUM_P512 || model==SPECTRUM_P1024?SPECTRUM_HAS_PENTAGON:SPECTRUM_HAS_SINCLAIR;
}
static bool needs_extended_video(void) {
    return !SPECTRUM_HAS_EXTENDED_VIDEO &&
        ((SPECTRUM_HAS_SINCLAIR && (machine.extensions&SPECTRUM_TIMEX)) ||
         (SPECTRUM_HAS_PENTAGON && machine.memory && machine.memory->extended && (machine.memory->control&0x41)));
}

static bool switching_app(void) { return app_flow && app_flow->action==MK61_FLOW_NEXT; }

static void stop_tape(void) {
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    if(tape->playing) spectrum_tape_toggle(tape,(uint32_t)machine.cpu.cyc);
#endif
}

static void reset_machine(void) {
    stop_tape();
    spectrum_reset(&machine);
}

static bool external_transfer(bool write,uint32_t offset,uint8_t* bytes,uint32_t length) {
    spectrum_sound_publish_before_io(&machine);
    while(length) {
        const uint32_t n=length<4096?length:4096;
        const uint32_t ok=write?mk61_app_buffer_write(services,external.handle,offset,bytes,n):
            mk61_app_buffer_read(services,external.handle,offset,bytes,n);
        if(!ok) return false;
        offset+=n;bytes+=n;length-=n;
#if (SPECTRUM_HAS_PENTAGON || SPECTRUM_RASTER_ENABLED) && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        // The pacing loop services input between video steps. Avoid re-running
        // the foreground service for each individual read and write of a strip.
        if(!pacing_video_io
#if SPECTRUM_HAS_BEAM_VIDEO
            && !machine.beam_io
#endif
            )
#endif
            mk61_api->service();
    }
    return true;
}
static bool external_read(void* context,uint32_t at,uint8_t* out,uint32_t n) {
    (void)context;return external_transfer(false,at,out,n);
}
static bool external_write(void* context,uint32_t at,const uint8_t* in,uint32_t n) {
    (void)context;return external_transfer(true,at,(uint8_t*)in,n);
}
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
#if SPECTRUM_RASTER_ENABLED
_Static_assert(SPECTRUM_RASTER_PACKED_BYTES<=2*SPECTRUM_BANK_BYTES,"Raster banks overlap");
_Static_assert(2*SPECTRUM_RASTER_PACKED_STRIP_BYTES<=SPECTRUM_VIDEO_WORK_BYTES,"Raster comparison exceeds the workspace");
_Static_assert(4*SPECTRUM_WIDE_WIDTH*SPECTRUM_BEAM_ROWS<=SPECTRUM_VIDEO_WORK_BYTES,"Beam comparison exceeds the workspace");
static unsigned raster_strip_bytes(const raster_output* output) {
    return SPECTRUM_HAS_BEAM_VIDEO && output->mode?spectrum_beam_row_bytes(output->mode)*SPECTRUM_BEAM_ROWS:
        SPECTRUM_RASTER_PACKED_STRIP_BYTES;
}
static uint32_t raster_address(const raster_output* output,unsigned bank,unsigned strip) {
    if(SPECTRUM_HAS_BEAM_VIDEO && output->mode) {
        // Keep both beam captures in the tail of the unused tape slot.
        const uint32_t base=TAPE_BASE+((uintptr_t)tape->index_context^1u)*SPECTRUM_TAPE_SLOT_BYTES+
            SPECTRUM_TAPE_SLOT_BYTES-2*SPECTRUM_BEAM_FRAME_BYTES;
        return base+bank*SPECTRUM_BEAM_FRAME_BYTES+strip*raster_strip_bytes(output);
    }
    return (bank?WIDE_REFERENCE:RASTER_BASE)+strip*SPECTRUM_RASTER_PACKED_STRIP_BYTES;
}
/* The raster buffer is live during a Z80 bus callback. Keep the transfer
 * bounded and avoid re-entering the guest while the beam is being caught up. */
static bool raster_store(void* context,unsigned strip,const uint8_t* data) {
    const raster_output* output=context;
    const uint32_t at=raster_address(output,output->bank,strip);
    return external_write(NULL,at,data,raster_strip_bytes(output));
}
static bool raster_present(uint8_t* buffer,raster_output* raster) {
    const bool beam=SPECTRUM_HAS_BEAM_VIDEO && raster->mode;
    const unsigned strips=beam?spectrum_beam_height(raster->mode)/SPECTRUM_BEAM_ROWS:SPECTRUM_RASTER_STRIPS;
    if(!raster->selected) {
        mk61_service_color_scroll scroll={0,320,0,0};
        const unsigned status=services->call(MK61_SERVICE_COLOR_DISPLAY,
            MK61_COLOR_SCROLL_BEGIN,0,sizeof(scroll),&scroll);
        if(status==2) return true;
        raster->transaction=status!=0;
        raster->selected=true;
        if(status==3) raster->clear=true;
        if(status!=1) raster->valid=false;
    }
    if(raster->next==strips) {
        if(raster->transaction) {
            const unsigned status=color(MK61_COLOR_SCROLL_END,NULL);
            if(status==2) return true;
            if(!status) {
                if(raster->repainted) return false;
                // A failed end leaves the original mapping open for repaint.
                raster->next=0;raster->valid=false;
                raster->clear=raster->repainted=true;
                return true;
            }
        }
        raster->valid=raster->transaction;
        raster->next=RASTER_IDLE;
        return true;
    }
    if(!raster->ready) {
        const unsigned bytes=raster_strip_bytes(raster);
        if(!external_read(NULL,raster_address(raster,raster->bank,raster->next),buffer,bytes)) return false;
        // Compare against the last accepted raster frame. Keep both captures
        // until the LCD commits, so a failed transfer can repaint every row.
        if(raster->valid) {
            if(!external_read(NULL,raster_address(raster,raster->bank^1u,raster->next),buffer+bytes,bytes)) return false;
            if(!memcmp(buffer,buffer+bytes,bytes)) {++raster->next;return true;}
        }
        if(SPECTRUM_HAS_RASTER && !beam) spectrum_raster_expand(buffer);
#if SPECTRUM_HAS_BEAM_VIDEO && SPECTRUM_HAS_TIMEX
        if(beam) spectrum_timex_beam_expand(buffer);
#endif
        raster->ready=true;
    }
    mk61_service_color_frame part={0};
    part.pixels=buffer;
    if(beam) {
        part.width=spectrum_beam_width(raster->mode);part.x=(320-part.width)/2;
        part.height=SPECTRUM_BEAM_ROWS;
        part.y=(320-spectrum_beam_height(raster->mode))/2+raster->next*SPECTRUM_BEAM_ROWS;
        part.pixel_bytes=SPECTRUM_HAS_PENTAGON?raster_strip_bytes(raster):2*part.width*part.height;
        part.format=SPECTRUM_HAS_PENTAGON?MK61_COLOR_INDEX4:MK61_COLOR_RGB565;
        if(SPECTRUM_HAS_PENTAGON) for(unsigned i=0;i<16;++i) part.palette[i]=spectrum_color(i);
    } else {
        part.width=320;part.height=SPECTRUM_RASTER_STRIP_ROWS;
        part.y=32+raster->next*SPECTRUM_RASTER_STRIP_ROWS;
        part.pixel_bytes=SPECTRUM_RASTER_STRIP_BYTES/5;
        part.tiles=buffer+part.pixel_bytes;part.tile_bytes=part.pixel_bytes*4;
        part.format=MK61_COLOR_CELL565;
    }
    part.background=beam && spectrum_is_pentagon(&machine)?0:spectrum_border(&machine);
    if(!raster->clear) part.format|=MK61_COLOR_PRESERVE_OUTSIDE;
    const unsigned result=color(MK61_COLOR_PRESENT,&part);
    if(result==1) {raster->clear=raster->ready=false;++raster->next;}
    return result!=0;
}
#endif

#if SPECTRUM_HAS_FAST_VIDEO
static uint32_t video_page(unsigned operation,unsigned page) {
    return services->call(MK61_SERVICE_COLOR_DISPLAY,operation,0,sizeof(page),&page);
}
static unsigned damage_cells(const spectrum_video_damage* d) {
    return (unsigned)(d->right-d->left)*(unsigned)(d->bottom-d->top);
}
static bool timex_capture(video_output* out,uint8_t* work) {
    spectrum_hicolor_changes* changes=machine.hicolor;
    const bool hires=out->mode==SPECTRUM_VIDEO_HIRES;
    if(out->background!=spectrum_border(&machine)) out->clear=true;
    // A programmable palette can recolor the whole screen without RAM writes.
    out->packed=out->transaction && !out->clear && (hires || (!machine.ulaplus_mode && !out->saved.ulaplus)) &&
        changes && changes->windows && !changes->repaint;
    if(out->packed) {
        if(!hires && ((out->saved.frames^machine.frames)&16)) spectrum_hicolor_flash(&machine,changes);
        unsigned cells=0;
        for(unsigned i=0;i<3;++i) cells+=damage_cells(&changes->strips[i]);
        out->packed=cells<=SPECTRUM_VIDEO_WORK_BYTES/5;
    }
    out->saved.io=external.handle && !out->packed?&bank_memory.io:NULL;
    out->saved.address=RASTER_BASE;
    if(!spectrum_video_capture(&machine,out->mode,work,&out->saved)) return false;
    if(out->packed) {
        // Freeze all dirty rectangles before advancing Z80, even if the
        // LCD has to finish them in the next pacing interval.
        out->patch_offset=0;
        memcpy(out->patches,changes->strips,sizeof(changes->strips));
        for(unsigned i=0;i<3;++i) {
            const unsigned cells=damage_cells(&out->patches[i]);
            if(cells) spectrum_timex_patch(&machine,&out->saved,out->mode,i,&out->patches[i],work);
            work+=5*cells;
        }
    }
    if(changes) {memset(changes->strips,0,sizeof(changes->strips));changes->repaint=false;}
    out->background=out->saved.border;
    return true;
}
#if SPECTRUM_HAS_PENTAGON
static bool pentagon_capture(video_output* out,uint8_t* work) {
    spectrum_pentagon_changes* changes=machine.pentagon_video;
    const unsigned page=out->page,mask=1u<<page,mode=out->mode;
    const unsigned strips=mode==SPECTRUM_VIDEO_WIDE?SPECTRUM_WIDE_STRIPS:3;
    const bool tracked=changes && changes->mode==mode;
    out->clipped=tracked && (out->pages || out->transaction) && !out->clear &&
        out->valid[page] && !(changes->repaint&mask);
    out->compare_wide=mode==SPECTRUM_VIDEO_WIDE && out->transaction && out->valid[0] && !out->clear && !out->clipped;
    out->packed=false;
    out->gap_right=false;
    if(out->clipped) {
        memcpy(out->patches,changes->strips[page],strips*sizeof(*out->patches));
        if(mode==SPECTRUM_VIDEO_WIDE) {
            if((out->saved.frames^machine.frames)&16) {
                if(!spectrum_pentagon_flash(&machine,work,out->patches,out->gaps)) return false;
            } else memset(out->gaps,0,sizeof(out->gaps));
        }
        unsigned rows=0;
        for(unsigned i=0;i<strips;++i) rows+=out->patches[i].bottom-out->patches[i].top;
        // Small updates fit in SRAM with a bounded number of scattered reads.
        // Larger ones use the batched native snapshot and keep their clipping.
        out->packed=rows<=(mode==SPECTRUM_VIDEO_WIDE?WIDE_PACKED_ROWS:16u);
    }
    out->saved.io=external.handle && !out->packed?&bank_memory.io:NULL;
    out->saved.address=RASTER_BASE;
    if(!spectrum_video_capture(&machine,mode,work,&out->saved)) return false;
    if(out->packed) {
        out->patch_offset=0;
        const unsigned unit=mode==SPECTRUM_VIDEO_WIDE?10:4;
        for(unsigned i=0;i<strips;++i) {
            const unsigned cells=damage_cells(&out->patches[i]);
            if(cells && !spectrum_pentagon_patch(&machine,mode,i,&out->patches[i],work)) return false;
            work+=unit*cells;
        }
    }
    if(tracked) {
        memset(changes->strips[page],0,sizeof(changes->strips[page]));
        changes->repaint&=(uint8_t)~mask;
    }
    if(out->pending==mode) out->pending=0; // This capture already includes that guest frame.
    out->background=out->saved.border;
    return true;
}
#endif
static __attribute__((noinline)) void video_begin(video_output* out,unsigned mode) {
    if(mode!=out->mode) {
        if(SPECTRUM_HAS_PENTAGON && (out->pages || mode==SPECTRUM_VIDEO_16C)) {
            color(MK61_COLOR_END,NULL);spectrum_display_fast(services);
            out->pages=false;out->page=0;
            if(mode==SPECTRUM_VIDEO_16C) {
                mk61_service_color_pages pages={64,192};
                out->pages=services->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_PAGES_BEGIN_V2,0,sizeof(pages),&pages)==1;
            }
        }
        out->clear=!SPECTRUM_HAS_PENTAGON || !out->pages;out->mode=mode;
        if(SPECTRUM_HAS_PENTAGON) out->valid[0]=out->valid[1]=0;
    }
    if(!mode) return;
    out->next=0;out->ready=out->selected=out->repainted=false;out->active=true;
}

static __attribute__((noinline)) bool video_present(video_output* out,uint8_t* work) {
    const bool pages=SPECTRUM_HAS_PENTAGON && out->pages;
    const bool timex=SPECTRUM_HAS_SINCLAIR && (!SPECTRUM_HAS_PENTAGON ||
        out->mode==SPECTRUM_VIDEO_HICOLOR || out->mode==SPECTRUM_VIDEO_HIRES);
    if(!out->selected) {
        if(!pages && external.handle && (!SPECTRUM_HAS_PENTAGON || !out->repainted)) {
            // Keep the origin fixed and validate reuse after any LCD error.
            mk61_service_color_scroll scroll={0,320,0,0};
            const unsigned status=services->call(MK61_SERVICE_COLOR_DISPLAY,
                MK61_COLOR_SCROLL_BEGIN,0,sizeof(scroll),&scroll);
            if(status==2) return true;
            out->transaction=status!=0;
            if(status!=1) {
                if(SPECTRUM_HAS_PENTAGON) out->valid[0]=0;
                out->clear=true;
            }
        }
        out->selected=true;
        if(timex) return timex_capture(out,work);
#if SPECTRUM_HAS_PENTAGON
        return pentagon_capture(out,work);
#endif
    }
    const unsigned strips=SPECTRUM_HAS_PENTAGON && out->mode==SPECTRUM_VIDEO_WIDE?SPECTRUM_WIDE_STRIPS:3;
    if(out->next<strips) {
        const spectrum_video_damage* d=&out->patches[out->next];
#if SPECTRUM_HAS_PENTAGON
        const bool clipped=!timex && out->clipped;
        const bool wide=out->mode==SPECTRUM_VIDEO_WIDE && out->transaction;
        const spectrum_wide_gap* gap=&out->gaps[out->next];
        const bool split=wide && out->packed && gap->right;
#else
        const bool clipped=false;
#endif
        if(!out->ready) {
            if((out->packed || clipped) && !d->bottom) goto next_strip;
            if(out->packed) {
                if(timex) spectrum_timex_frame(&out->saved,out->mode,out->next,d,work+out->patch_offset,&out->part);
#if SPECTRUM_HAS_PENTAGON
                else spectrum_pentagon_frame(out->mode,out->next,d,work+out->patch_offset,&out->part);
#endif
            } else {
                if(!spectrum_video_snapshot_strip(&machine,&out->saved,out->mode,out->next,work,&out->part)) return false;
#if SPECTRUM_HAS_PENTAGON
                if(clipped) spectrum_pentagon_clip(out->mode,d,work,&out->part);
#endif
            }
#if SPECTRUM_HAS_PENTAGON
            if(wide) {
                // Write the combined patch to the PSRAM reference once. The
                // LCD skips the gap, whose pixels are identical in both frames.
                if(!out->gap_right) {
                    const int result=spectrum_pentagon_wide_update(&bank_memory.io,WIDE_REFERENCE,work,&out->part,out->compare_wide);
                    if(!result) goto next_strip;
                    if(result<0) return false;
                }
                if(split) spectrum_pentagon_wide_window(&out->part,gap,out->gap_right,work+WIDE_PACKED_BYTES);
            }
#endif
            if(out->clear) {out->part.format&=~MK61_COLOR_PRESERVE_OUTSIDE;out->part.background=out->background;}
            out->ready=true;
        }
        if(pages) {
            // PRESENT can consume a failed DMA write. Check the hidden page
            // before submitting another strip that relies on its contents.
            const uint32_t status=video_page(MK61_COLOR_PAGE_SELECT,out->page);
            if(status==2) return true;
            if(!status) goto fallback;
        }
        const uint32_t status=color(MK61_COLOR_PRESENT,&out->part);
        if(status!=1) return status==2;
#if SPECTRUM_HAS_PENTAGON
        if(split) {
            if(!out->gap_right) {out->gap_right=true;out->ready=false;return true;}
            out->gap_right=false;
            out->patch_offset+=10*damage_cells(d);
        } else
#endif
        if(out->packed) out->patch_offset+=out->part.pixel_bytes+out->part.tile_bytes;
next_strip:
        out->ready=out->clear=false;
        if(++out->next<strips) return true;
    }
    if(pages) {
        const uint32_t status=video_page(MK61_COLOR_PAGE_SHOW,out->page);
        if(status==2) return true;
        if(!status) goto fallback;
        out->valid[out->page]=1;
        out->page^=1;
    } else if(out->transaction) {
        const unsigned status=color(MK61_COLOR_SCROLL_END,NULL);
        if(status==2) return true;
        if(!status) {
            if(out->repainted) return false;
            out->clear=out->repainted=true;out->next=0;
            if(SPECTRUM_HAS_PENTAGON) out->valid[0]=0;
#if SPECTRUM_HAS_PENTAGON
            out->selected=false;
            return true;
#else
            return timex_capture(out,work);
#endif
        }
        if(SPECTRUM_HAS_PENTAGON && !timex) out->valid[0]=1;
    }
    out->active=out->transaction=false;return true;
fallback:
    // A failed page loses its retained contents. Capture afresh and
    // repaint the ordinary display, including the margins.
    color(MK61_COLOR_END,NULL);spectrum_display_fast(services);
    out->pages=out->ready=out->selected=false;out->clear=true;out->page=out->next=0;
    out->valid[0]=out->valid[1]=0;
    return true;
}
#endif
#endif
static bool external_clear(void* context,uint32_t at,uint32_t length) {
    (void)context;
    while(length) {
        mk61_service_buffer r=mk61_app_buffer_request();r.handle=external.handle;r.offset=at;r.size=length<4096?length:4096;
        if(!mk61_app_buffer_call(services,MK61_BUFFER_FILL,&r)) return false;
        at+=r.size;length-=r.size;mk61_api->service();
    }
    return true;
}
static void sound_yield(void* context) { (void)context;mk61_api->service(); }

static uint32_t color(uint32_t operation,mk61_service_color_frame* frame) {
    return services->call(MK61_SERVICE_COLOR_DISPLAY,operation,0,frame?sizeof(*frame):0,frame);
}
static __attribute__((noinline)) void status_event(const char* text) {
    services->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text);
}
static int scan_keys(void) {
    if(!services->call(MK61_SERVICE_KEYBOARD,MK61_SERVICE_KEY_BITMAP,sizeof(keys),0,keys)) return -1;
    int first=-1;
    for(unsigned i=0;i<sizeof(keys);++i) {
        unsigned pressed=keys[i]&~previous_keys[i];
        if(!i) pressed&=~1u;
        if(!pressed) continue;
        unsigned bit=0;while(!(pressed&1)) { pressed>>=1;++bit; }
        first=(int)(i*8+bit);break;
    }
    memcpy(previous_keys,keys,sizeof(keys));return first;
}
static int wait_key(void) { for(;;) { int c=scan_keys();if(c>=0) return c;mk61_api->delay_ms(1); } }
static bool escape(int c) { return c==0x1B || c==0xB1; }
static bool enter(int c) { return c==10 || c==13; }
static void guest_keyboard(uint8_t blocked[32]) {
    uint8_t guest[32];
    for(unsigned i=0;i<32;++i) { blocked[i]&=keys[i];guest[i]=keys[i]&~blocked[i]; }
    spectrum_keyboard(&machine,guest);
}
static int poll_guest(uint8_t blocked[32],uint32_t* deadline,uint32_t now) {
    if((int32_t)(now-*deadline)<0) return -1;
    *deadline=now+20000;
    const int key=scan_keys();guest_keyboard(blocked);return key;
}
enum { ROOT_RESUME, ROOT_DISK_OR_NMI=6 };
#if SPECTRUM_HAS_TIMEX_2068
static const char* const root_items[]={"Start machine","Cartridge...","Eject cartridge","Snapshot...","Machine...",
        "Options...","Tape...","Save snapshot","Reset","Help","Exit"};
#else
static const char* const root_items[]={"Start machine","Snapshot...","Beta Disk...","DivMMC...",
        "Machine...","Options...","TR-DOS","Reset","Help",
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        "Tape...","Save snapshot",
#endif
        SPECTRUM_HAS_EXTENDED_VIDEO?"Standard video...":"Video extensions...","Exit"
};
#endif
enum { ROOT_COUNT=sizeof(root_items)/sizeof(*root_items) };
static const char* const root_title=SPECTRUM_HAS_TIMEX_2068?"Timex 2068":"Spectrum";

static void root_labels(const char* labels[ROOT_COUNT]) {
    memcpy(labels,root_items,sizeof(root_items));
    if(started) labels[ROOT_RESUME]="Resume";
    if(!SPECTRUM_HAS_TIMEX_2068 && machine.disk.mode==SPECTRUM_DISK_DIVMMC) labels[ROOT_DISK_OR_NMI]="NMI browser";
}

static bool menu_draw(const char* title,const char* const* labels,unsigned count,unsigned selected,bool nested) {
    if(!spectrum_ui_begin(&osd,services,&machine,started)) return false;
    if(nested) {
        const char* root[ROOT_COUNT];
        root_labels(root);
        spectrum_ui_window(&osd,8,8,224,root_title,root,ROOT_COUNT,root_selected);
    }
    spectrum_ui_window(&osd,nested?40:8,nested?(count>11?24:40):8,nested?208:224,title,labels,count,selected);
    spectrum_ui_footer(&osd,selected<count?"Enter: select    Esc: back":"Press any key");
    return spectrum_ui_present(&osd);
}
static int menu_pick(const char* title,const char* const* labels,unsigned count,unsigned* selected,bool nested,const char* hotkeys) {
    for(;;) {
        if(!menu_draw(title,labels,count,*selected,nested)) return -1;
        const int key=wait_key();
        if(escape(key)) return -1;
        if(enter(key)) return (int)*selected;
        if((key==0xB4 || key==0xB5) && *selected) --*selected;
        else if((key==0xB6 || key==0xB7) && *selected+1<count) ++*selected;
        else if(hotkeys) for(unsigned i=0;hotkeys[i];++i) if((key|32)==hotkeys[i] && hotkeys[i]!=' ') {
            if(i<count) *selected=i;
            return (int)i;
        }
    }
}
static void message(const char* value) {
    char copy[12][27];const char* lines[12];unsigned count=0,at=0;
    while(value[at] && count<12) {
        unsigned end=at,space=at;
        while(value[end] && value[end]!='\n' && end-at<26) { if(value[end]==' ') space=end;++end; }
        if(value[end] && value[end]!='\n' && space>at) end=space;
        memcpy(copy[count],value+at,end-at);copy[count][end-at]=0;lines[count]=copy[count];++count;
        at=end;if(value[at]==' ' || value[at]=='\n') ++at;
    }
    if(!count) { copy[0][0]=0;lines[0]=copy[0];count=1; }
    if(!menu_draw(root_title,lines,count,count,false)) {
        // A missing ROM/font must still produce a readable startup error.
        if(machine.memory) { (void)spectrum_memory_flush_pages(machine.memory);spectrum_refresh_map(&machine); }
        mk61_api->graphics_end();mk61_api->display_clear();
        for(unsigned i=0;i<count && i<10;++i) {
            const unsigned length=(unsigned)strlen(lines[i]);
            mk61_api->display_write_m8(0,i,lines[i],length<20?length:20);
        }
        if(count<10) mk61_api->display_write_m8(0,count,"Press any key",13);
    }
    wait_key();
}
static __attribute__((noinline)) uint32_t file_call(unsigned op,const char* path,void* out,uint32_t offset,uint32_t bytes) {
    mk61_service_file_bytes r={path,out,offset,bytes};
    return services->call(MK61_SERVICE_FILE_BYTES,op,0,sizeof(r),&r);
}
static bool switch_to_app(const char* name,unsigned model,uint32_t file_id,const char* path) {
#if SPECTRUM_HAS_TAPE_RECORD && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    if(recording && recording->write) {message("Save or discard the TAP\nrecording first");return false;}
#endif
    if(!app_flow) return false;
    uint32_t partner=file_call(MK61_FILE_BYTES_ID,name,NULL,0,0);
    if(!partner) {
        // Existing residents can resolve the sibling APP by its name and
        // parent ID. Physical document paths use FILE_BYTES_ID when available.
        mk61_service_file current,target;
        if(!services->call(MK61_SERVICE_FILE_ENTRY,0,app_flow->current.file_id,0,&current) ||
           services->call(MK61_SERVICE_FILE_RESOLVE,current.parent,MK61_SERVICE_FILE_APP,
                           (uint32_t)(uintptr_t)name,&target)) return false;
        partner=target.id+1;
    }
    if(path && file_id==MK61_SERVICE_INVALID_ID) {
        const uint32_t id=file_call(MK61_FILE_BYTES_ID,path,NULL,0,0);
        if(!id) return false;
        file_id=id-1;
    }
    uint32_t* context=app_flow->context;
    context[0]=file_id;context[1]=(model==SPECTRUM_TC2048?SPECTRUM_48:model)+1;
    mk61_app_flow_next(app_flow,mk61_app_flow_to(MK61_APP_KIND_APPLICATION,(uint16_t)(partner-1),
        file_id==MK61_SERVICE_INVALID_ID?0:MK61_APP_FLOW_FILE_PHASE));
    return true;
}
static bool switch_app(unsigned model,uint32_t file_id,const char* path) {
    const char* name=spectrum_timex_2068(model)?"TX2068.APP":model==SPECTRUM_TC2048?"TIMEX.APP":
        model==SPECTRUM_P512 || model==SPECTRUM_P1024?
            (SPECTRUM_HAS_EXTENDED_VIDEO?"ZXVIDEO.APP":"SPECTRUM.APP"):
            (SPECTRUM_HAS_EXTENDED_VIDEO && !SPECTRUM_HAS_TIMEX_2068?"TIMEX.APP":"SINCLAIR.APP");
    return switch_to_app(name,model,file_id,path);
}
static __attribute__((noinline)) bool file_size(const char* path,uint32_t* size) {
    mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,path,&info,0,sizeof(info)) || info.directory) return false;
    *size=info.size;return true;
}
static bool read_source(void* path,uint32_t at,uint8_t* out,uint32_t bytes) {
    spectrum_sound_publish_before_io(&machine);
    const bool ok=file_call(MK61_FILE_BYTES_READ,path,out,at,bytes)!=0;
    mk61_api->service();return ok;
}
static const char* preferences_name(void) {
    return SPECTRUM_APP_PROFILE==2?"SINCLAIR.CFG":"SPECTRUM.CFG";
}
static void load_preferences(void) {
    preferences=(spectrum_preferences){DEFAULT_MODEL,SPECTRUM_HAS_TIMEX_2068?0:15,0,SPECTRUM_AY,SPECTRUM_ABC,0,3};
    preferences_dirty=false;
    if(!SPECTRUM_HAS_PREFERENCES) return;
    uint8_t bytes[SPECTRUM_PREFERENCES_BYTES];uint32_t size;
    spectrum_preferences saved;
    if(file_size(preferences_name(),&size) && size>=sizeof(bytes) &&
       file_call(MK61_FILE_BYTES_READ,preferences_name(),bytes,0,sizeof(bytes)) &&
       spectrum_preferences_decode(&saved,bytes) && model_available(saved.model)) preferences=saved;
}
static bool suffix(const char* name,const char* extension) {
    const unsigned n=(unsigned)strlen(name),k=(unsigned)strlen(extension);
    if(n<k) return false;
    for(unsigned i=0;i<k;++i) if((name[n-k+i]|32)!=(extension[i]|32)) return false;
    return true;
}
static bool join_path(char* out,const char* base,const char* leaf) {
    const unsigned n=(unsigned)strlen(base),k=(unsigned)strlen(leaf);
    const unsigned slash=n && base[n-1]!='/';
    if(n+slash+k+1>256) return false;
    memcpy(out,base,n);if(slash)out[n]='/';memcpy(out+n+slash,leaf,k+1);return true;
}
static void parent_directory(void) {
    char* slash=NULL;
    for(char* p=directory;*p;++p) if(*p=='/') slash=p;
    if(slash==directory) directory[1]=0;
    else if(slash) *slash=0;else { directory[0]='/';directory[1]=0; }
}
enum { FILE_SNAPSHOT, FILE_BETA, FILE_DIV, FILE_TAPE, FILE_CARTRIDGE };
static bool is_snapshot(const char* path) {
    return suffix(path,".sna") || suffix(path,".z80")
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        || suffix(path,".szx")
#endif
        ;
}
static bool is_tape(const char* path) { return suffix(path,".tap") || suffix(path,".tzx"); }
#if SPECTRUM_HAS_TIMEX_2068
static bool is_cartridge(const char* path) { return suffix(path,".dck"); }
#endif
static bool entry(unsigned selected,mk61_service_file_info* out,unsigned type) {
    unsigned matched=0;
    for(unsigned i=0;i<4096;++i) {
        mk61_service_file_info f;
        if(!file_call(MK61_FILE_BYTES_CHILD,directory,&f,i,sizeof(f))) return false;
        mk61_api->service();
        const bool match=type==FILE_SNAPSHOT?is_snapshot(f.name):
            type==FILE_BETA?(suffix(f.name,".trd") || suffix(f.name,".scl")):
#if SPECTRUM_HAS_TIMEX_2068
            type==FILE_CARTRIDGE?is_cartridge(f.name):
#endif
            type==FILE_DIV?suffix(f.name,".img"):is_tape(f.name);
        if(f.name[0]=='.' || !(f.directory || match)) continue;
        if(matched++==selected) { *out=f;return true; }
    }
    return false;
}
static bool choose_file(unsigned type) {
    unsigned selected=0;
    for(;;) {
        mk61_service_file_info f;
        const bool found=entry(selected,&f,type);
        const char* names[10];char labels[10][30];const unsigned top=selected>=10?selected-9:0;unsigned count=0;
        for(unsigned i=top;i<top+10;++i) {
            mk61_service_file_info file;if(!entry(i,&file,type)) break;
            mk61_app_snprintf(services,labels[count],sizeof(labels[count]),"%.23s%s",file.name,file.directory?"/":"");
            names[count]=labels[count];++count;
        }
        if(!count) { names[0]="No matching files";count=1; }
        static const char* const titles[]={"Snapshot","Beta Disk","DivMMC","Tape"
#if SPECTRUM_HAS_TIMEX_2068
            ,"Cartridge"
#endif
        };
        if(!menu_draw(titles[type],names,count,found?selected-top:count,false)) return false;
        const int c=wait_key();
        if(escape(c)) return false;
        if(c==8 || c==0xD4) {
            parent_directory();
            selected=0;
        } else if(c==0xB5 || c==0xB4) { if(selected) --selected; }
        else if(c==0xB6 || c==0xB7) { mk61_service_file_info next;if(entry(selected+1,&next,type)) ++selected; }
        else if(enter(c) && found) {
            if(!join_path(snapshot_path,directory,f.name)) { message("Path too long");continue; }
            if(f.directory) { strcpy(directory,snapshot_path);selected=0; }
            else return true;
        }
    }
}
static bool load_rom(uint8_t* rom) {
    uint32_t size;
    if(!file_size("48.rom",&size) || size!=SPECTRUM_ROM_BYTES) return false;
    for(unsigned at=0;at<SPECTRUM_ROM_BYTES;at+=4096)
        if(!read_source("48.rom",at,rom+at,4096)) return false;
    return true;
}
/* Chunk storage is only live during each read, before any machine reset. */
static __attribute__((noinline)) bool load_banked_roms(bool pentagon) {
    uint8_t bytes[512];
    for(unsigned bank=0;bank<2;++bank) {
        const char* name=SPECTRUM_HAS_TIMEX_2068?(bank?"tc2068-1.rom":"tc2068-0.rom"):
            pentagon?(bank?"128-1.rom":"128-0.rom"):"48.rom";
        uint32_t size;
        if(!file_size(name,&size) || size!=(SPECTRUM_HAS_TIMEX_2068 && bank?8192:SPECTRUM_ROM_BYTES)) return false;
        for(unsigned at=0;at<size;at+=sizeof(bytes)) {
            if(!read_source((void*)name,at,bytes,sizeof(bytes)) ||
               !external_write(NULL,SPECTRUM_ROM_BASE+bank*SPECTRUM_ROM_BYTES+at,bytes,sizeof(bytes))) return false;
        }
    }
    return true;
}
static bool select_model(unsigned model) {
    if(!model_available(model)) return false;
#if SPECTRUM_HAS_TIMEX_2068
    machine.timex_ntsc=model==SPECTRUM_TS2068;
    if(machine.memory) {
        reset_machine();started=false;return !machine.memory->fault;
    }
#endif
    if(!banked_buffers) {
        if(model!=SPECTRUM_48) return false;
        reset_machine();started=false;return true;
    }
    const unsigned external_bytes=
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        VIDEO_CAPTURE_END;
#else
        SPECTRUM_EXTERNAL_BYTES+SPECTRUM_TRD_BYTES;
#endif
    if(!external.handle && !mk61_app_buffer_acquire(services,external_bytes,MK61_BUFFER_EXTERNAL,&external)) {
        message("PSRAM required");return false;
    }
    const spectrum_memory_io io={NULL,external_read,external_write,external_clear};
    if(!load_banked_roms(model!=SPECTRUM_48) ||
       !spectrum_memory_init_fragmented(&bank_memory,guest_blocks[0],guest_blocks[1],bank_tails,page_runs,
            model==SPECTRUM_128?8:model==SPECTRUM_P1024?64:32,io)) return false;
    stop_tape();
    spectrum_attach_memory(&machine,&bank_memory);
    if(model==SPECTRUM_48) machine.pentagon=false;
    if(SPECTRUM_HAS_TIMEX && (SPECTRUM_APP_PROFILE==4 || SPECTRUM_APP_PROFILE==8)) machine.extensions|=SPECTRUM_TIMEX;
    spectrum_disk_reset(&machine);started=false;return true;
}
/* SD publication borrows the cache lease while the guest is paused. */
static bool cache_workspace(mk61_service_lease* workspace,bool release) {
    if(!banked_buffers) return true;
    if(release) {
        if(!spectrum_memory_flush_pages(&bank_memory) ||
           !services->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,0,workspace)) return false;
        memset(bank_memory.page_data,0,WORK_CACHE_BYTES/SPECTRUM_CACHE_PAGE_BYTES*sizeof(bank_memory.page_data[0]));
    } else {
        if(!services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,WORK_CACHE_BYTES,workspace)) {
            started=false;return false;
        }
        page_runs[0]=workspace->data;
        for(unsigned i=0;i<WORK_CACHE_BYTES/SPECTRUM_CACHE_PAGE_BYTES;++i)
            bank_memory.page_data[i]=page_runs[0]+i*SPECTRUM_CACHE_PAGE_BYTES;
    }
    spectrum_refresh_map(&machine);return true;
}
static int preferences_read(void* context,uint32_t offset,uint8_t* output,uint32_t size) {
    if(offset>SPECTRUM_PREFERENCES_BYTES || size>SPECTRUM_PREFERENCES_BYTES-offset) return 0;
    memcpy(output,(const uint8_t*)context+offset,size);return 1;
}
static bool replace_preferences(const uint8_t* bytes) {
    uint32_t id;
    if(app_flow) id=app_flow->current.file_id;
    else {
        id=file_call(MK61_FILE_BYTES_ID,SPECTRUM_APP_PROFILE==2?"SINCLAIR.APP":"SPECTRUM.APP",NULL,0,0);
        if(!id) return false;
        --id;
    }
    mk61_service_file file;
    if(!services->call(MK61_SERVICE_FILE_ENTRY,0,id,0,&file)) return false;
    mk61_service_write request={preferences_name(),bytes,SPECTRUM_PREFERENCES_BYTES,0};
    (void)services->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&request);
    // Publication precedes registry refresh, which classifies CFG as text.
    // Verify the raw file even if that later registration rejected its bytes.
    uint8_t saved[SPECTRUM_PREFERENCES_BYTES];uint32_t size;
    return file_size(preferences_name(),&size) && size==sizeof(saved) &&
        file_call(MK61_FILE_BYTES_READ,preferences_name(),saved,0,sizeof(saved)) && !memcmp(saved,bytes,sizeof(saved));
}
static bool save_preferences(mk61_service_lease* workspace) {
    if(!SPECTRUM_HAS_PREFERENCES || !preferences_dirty) return true;
    uint8_t bytes[SPECTRUM_PREFERENCES_BYTES];
    spectrum_preferences_encode(&preferences,bytes);
    if(!cache_workspace(workspace,true)) { message("Cannot save settings");return true; }
    uint32_t size;
    bool saved;
    if(file_size(preferences_name(),&size))
        saved=size>=sizeof(bytes)?file_call(MK61_FILE_BYTES_WRITE,preferences_name(),bytes,0,sizeof(bytes))!=0:
            replace_preferences(bytes);
    else {
        mk61_service_write_source source={preferences_name(),bytes,preferences_read,sizeof(bytes),0};
        saved=services->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_WRITE_SOURCE,0,sizeof(source),&source)!=0;
    }
    if(!cache_workspace(workspace,false)) { message("Cannot restore cache");return false; }
    if(saved) preferences_dirty=false;
    else message("Cannot save settings");
    return true;
}
#ifdef SPECTRUM_HIL_SNAPSHOT_ONLY
/* A fixed-checkpoint timing probe needs no image mounting or SCL unpacker.
 * Its CPU, renderer and audio paths remain the ordinary APP paths. */
static void mount_media(unsigned mode) { (void)mode;message("Snapshot timing probe"); }
static bool mount_selected_media(unsigned mode) { (void)mode;return false; }
#else
static bool media_read(void* raw,uint32_t at,uint8_t* out,uint32_t n) {
    const mounted_media* m=raw;
    return m->scl?external_read(NULL,SPECTRUM_EXTERNAL_BYTES+at,out,n):read_source((void*)m->path,at,out,n);
}
static bool media_write(void* raw,uint32_t at,const uint8_t* in,uint32_t n) {
    const mounted_media* m=raw;
    if(m->scl) return false;
    const bool ok=file_call(MK61_FILE_BYTES_WRITE,m->path,(void*)in,at,n)!=0;
    mk61_api->service();return ok;
}
static bool disk_rom(unsigned mode) {
    const char* path=mode==SPECTRUM_DISK_BETA?"trdos.rom":"esxmmc.rom";
    const uint32_t target=mode==SPECTRUM_DISK_BETA?SPECTRUM_TRDOS_ROM:SPECTRUM_DIV_ROM;
    const unsigned size=mode==SPECTRUM_DISK_BETA?16384:8192;
    mk61_service_file_info info;uint8_t bytes[256];
    if(!file_call(MK61_FILE_BYTES_STAT,path,&info,0,sizeof(info)) || info.directory || info.size!=size) {
        message("Disk ROM missing\nSee README.md");return false;
    }
    for(unsigned at=0;at<size;at+=sizeof(bytes))
        if(!read_source((void*)path,at,bytes,sizeof(bytes)) || !external_write(NULL,target+at,bytes,sizeof(bytes))) return false;
    spectrum_memory_invalidate(&bank_memory,target,size);
    spectrum_refresh_map(&machine);
    return true;
}
static bool mount_selected_media(unsigned mode) {
    if(!machine.memory) { message("PSRAM required");return false; }
    mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,snapshot_path,&info,0,sizeof(info)) || info.directory) return false;
    const bool scl=suffix(snapshot_path,".scl");
    if(mode==SPECTRUM_DISK_DIVMMC && (info.size<1024*1024 || info.size%512)) {
        message("SD image at least 1 MiB\nMultiple of 512 bytes");return false;
    }
    if(mode==SPECTRUM_DISK_BETA && !scl && (info.size<4096 || info.size>SPECTRUM_TRD_BYTES || info.size%256)) {
        message("Invalid TRD size");return false;
    }
    if(!disk_rom(mode)) return false;
    if(scl) {
        const spectrum_source source={snapshot_path,info.size,read_source};
        const spectrum_memory_io io={NULL,external_read,external_write,external_clear};
        if(spectrum_scl_unpack(&source,&io,SPECTRUM_EXTERNAL_BYTES)!=SPECTRUM_OK) {
            message("Invalid SCL or SD error");return false;
        }
    }
    mounted_media* m=mode==SPECTRUM_DISK_BETA?&floppy:&sd_card;
    strcpy(m->path,snapshot_path);m->scl=scl;
    spectrum_disk_io* io=mode==SPECTRUM_DISK_BETA?&machine.disk.fdc.io:&machine.disk.spi.io;
    *io=(spectrum_disk_io){m,scl?SPECTRUM_TRD_BYTES:info.size,media_read,media_write,true,80,2};
    if(!spectrum_disk_mode(&machine,mode)) return false;
    reset_machine();started=false;return true;
}
static void mount_media(unsigned mode) {
    if(!machine.memory) { message("PSRAM required");return; }
    if(choose_file(mode==SPECTRUM_DISK_BETA?1:2) && mount_selected_media(mode)) {
        if(mode==SPECTRUM_DISK_BETA) machine.disk.fdc.io.readonly=floppy.scl || (preferences.write_protect&mode);
        else machine.disk.spi.io.readonly=(preferences.write_protect&mode)!=0;
    }
}

static bool tape_index_read(void* context,uint32_t offset,uint8_t* out,uint32_t n) {
    const uint32_t base=TAPE_BASE+(uintptr_t)context*SPECTRUM_TAPE_SLOT_BYTES;
    return external_read(NULL,base+offset,out,n);
}
static bool tape_index_write(void* context,uint32_t offset,const uint8_t* in,uint32_t n) {
    const uint32_t base=TAPE_BASE+(uintptr_t)context*SPECTRUM_TAPE_SLOT_BYTES;
    return external_write(NULL,base+offset,in,n);
}

static enum spectrum_error read_tape(const spectrum_source* source,bool tzx) {
    mk61_service_framebuffer canvas={0};
    if(!mk61_api->graphics_begin() ||
       !services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(canvas),0,&canvas) ||
       !canvas.pixels || canvas.bytes<sizeof(spectrum_tape)+SPECTRUM_TAPE_DECODE_SCRATCH ||
       (uintptr_t)canvas.pixels%_Alignof(spectrum_tape)) return SPECTRUM_IO;
    spectrum_tape* candidate=(spectrum_tape*)canvas.pixels;
    *candidate=(spectrum_tape){0};
    if(external.handle && tzx) {
        candidate->index_read=tape_index_read;candidate->index_write=tape_index_write;
        candidate->index_context=(void*)((uintptr_t)tape->index_context^1u);
        candidate->decode_scratch=canvas.pixels+sizeof(*candidate);
    }
    const enum spectrum_error error=spectrum_tape_open(candidate,source,tzx);
    if(!error) *tape=*candidate;
    return error;
}
static bool mount_tape(void) {
#if SPECTRUM_HAS_TAPE_RECORD && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    if(recording->write) {message("Save or discard the TAP\nrecording first");return false;}
#endif
    mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,snapshot_path,&info,0,sizeof(info)) || info.directory) return false;
    spectrum_source source={snapshot_path,info.size,read_source};
    const enum spectrum_error result=read_tape(&source,suffix(snapshot_path,".tzx"));
    if(result) {
        message(result==SPECTRUM_UNSUPPORTED?"Unsupported tape block":"Cannot read tape");
        return false;
    }
    strcpy(tape_path,snapshot_path);
    tape->source.context=tape_path;tape->playing=true;
    machine.ear=spectrum_tape_ear;machine.ear_context=tape;
    if(!started) spectrum_reset(&machine);
    started=true;
    return true;
}

static void tape_ready(void) {
    status_event("SP STATE=TAPE_READY\n");
    message("Tape ready\nUse LOAD \"\" in BASIC");
}

#if SPECTRUM_HAS_TAPE_RECORD
static void end_tape_record(void) {
    machine.mic=NULL;
    recording->write=NULL;
}
static int read_tape_record(void* context,uint32_t offset,uint8_t* output,uint32_t size) {
    return tape_index_read(context,offset,output,size);
}
static bool record_tape(mk61_service_lease* workspace) {
    if(!recording->write) {
        if(!external.handle || !(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL)&MK61_SERVICE_CAP_FILE_WRITE_SOURCE)) {
            message("TAP recording requires PSRAM\nand file writing");return true;
        }
        stop_tape();
        *recording=(spectrum_tape_recorder){.context=(void*)((uintptr_t)tape->index_context^1u),
            .write=tape_index_write,.capacity=SPECTRUM_TAPE_SLOT_BYTES-
                (SPECTRUM_HAS_BEAM_VIDEO?2*SPECTRUM_BEAM_FRAME_BYTES:0)};
        machine.mic_context=recording;machine.mic=spectrum_tape_mic;
        message("Recording TAP\nUse SAVE in BASIC");
        return true;
    }
    machine.mic=NULL;
    spectrum_tape_record_finish(recording);
    if(!recording->size) {
        message(recording->fault?"TAP recording failed":"No complete tape block");
        end_tape_record();return true;
    }
    for(unsigned i=1;i<=9999;++i) {
        mk61_service_file_info info;
        mk61_app_snprintf(services,snapshot_path,256,"TAPE%04u.TAP",i);
        if(file_call(MK61_FILE_BYTES_STAT,snapshot_path,&info,0,sizeof(info))) continue;
        if(!cache_workspace(workspace,true)) {message("Cannot save TAP");return true;}
        mk61_service_write_source request={snapshot_path,recording->context,read_tape_record,recording->size,0};
        const bool saved=services->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_WRITE_SOURCE,0,sizeof(request),&request)!=0;
        if(saved) end_tape_record();
        if(!cache_workspace(workspace,false)) return false;
        if(saved) status_event("SP STATE=TAP_SAVED\n");
        message(saved?snapshot_path:"Cannot save TAP");
        return true;
    }
    message("No free TAP name");return true;
}
#endif

static bool tape_menu(mk61_service_lease* workspace) {
    (void)workspace;
    unsigned selected=0;
    const char* labels[]={"Open TAP / TZX",tape->playing?"Stop":"Play","Rewind","Eject",
#if SPECTRUM_HAS_TAPE_RECORD
        recording->write?"Save recording":"Record TAP",recording->write?"Discard recording":"Back",
#endif
        "Back"};
    unsigned count=sizeof(labels)/sizeof(*labels);
#if SPECTRUM_HAS_TAPE_RECORD
    if(!recording->write) --count;
#endif
    switch(menu_pick("Tape",labels,count,&selected,true,NULL)) {
    case 0:
        if(choose_file(FILE_TAPE) && mount_tape()) tape_ready();
        break;
    case 1:
        spectrum_tape_toggle(tape,(uint32_t)machine.cpu.cyc);
        break;
    case 2:
        if(tape->source.read) spectrum_tape_rewind(tape);
        break;
    case 3:
        tape->source.read=NULL;tape->playing=false;tape->choices=0;machine.ear=NULL;
        break;
#if SPECTRUM_HAS_TAPE_RECORD
    case 4: return record_tape(workspace);
    case 5: if(recording->write) end_tape_record();break;
#endif
    }
    return true;
}
static bool tape_select(void) {
    const unsigned count=tape->choices<10?tape->choices:10;
    char text[10][25];
    const char* labels[10];
    unsigned selected=0,top=0;
    status_event("SP STATE=TAPE_CHOICE\n");
    for(;;) {
        for(unsigned i=0;i<count;++i) {
            labels[i]=text[i];
            if(!spectrum_tape_choice(tape,top+i,text[i],sizeof(text[i]))) goto invalid;
            if(!text[i][0]) strcpy(text[i],"(unnamed)");
        }
        if(!menu_draw("Tape selection",labels,count,selected-top,true)) return false;
        const int c=wait_key();
        if(enter(c)) {
            if(spectrum_tape_choose(tape,selected,(uint32_t)machine.cpu.cyc)) return true;
            goto invalid;
        }
        if(escape(c) || c==0x90) {
            tape->choices=0;
            if(c==0x90) started=false;
            return false;
        }
        if((c==0xB4 || c==0xB5) && selected) --selected;
        else if((c==0xB6 || c==0xB7) && selected+1<tape->choices) ++selected;
        if(selected<top) top=selected;
        if(selected>=top+count) top=selected-count+1;
    }
invalid:
    tape->choices=0;tape->fault=false;
    message("Invalid tape selection");
    return false;
}
#if defined(__GNUC__) && !defined(__clang__) && __GNUC__ >= 12
__attribute__((optimize("Oz")))
#endif
static __attribute__((noinline)) bool save_snapshot(mk61_service_lease* workspace) {
    if(!started) {message("Start a machine first");return true;}
    char* name=snapshot_path;
    unsigned prefix=0;
    if(opened_file!=MK61_SERVICE_INVALID_ID) {
        if(!file_call(MK61_FILE_BYTES_PATH,NULL,name,opened_file,256)) {
            message("Cannot get game folder");return true;
        }
        for(unsigned i=0;name[i];++i) if(name[i]=='/') prefix=i+1;
        if(prefix>245) {message("Save path too long");return true;}
    }
    for(unsigned n=1;n<=9999;++n) {
        mk61_service_file_info info;
        mk61_app_snprintf(services,name+prefix,256-prefix,"ZX%04u.SZX",n);
        if(file_call(MK61_FILE_BYTES_STAT,name,&info,0,sizeof(info))) continue;
        if(!cache_workspace(workspace,true)) {
            message("Cannot save snapshot");return true;
        }
        spectrum_szx_writer writer;
        mk61_service_write_source request={name,&writer,spectrum_szx_read,spectrum_szx_save(&writer,&machine),0};
        const bool saved=request.size &&
            services->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_WRITE_SOURCE,0,sizeof(request),&request)!=0;
        if(!cache_workspace(workspace,false)) {
            message("Cannot restore cache");return false;
        }
        if(saved) { status_event("SP STATE=SAVED\n");message(name); }
        else message("Cannot save snapshot");
        return true;
    }
    message("No free snapshot name");
    return true;
}

static bool load_szx(const spectrum_source* source,uint32_t file_id) {
    unsigned model;
    enum spectrum_error error=spectrum_szx_model(source,&model);
    if(!error) {
        if(!model_available(model) && switch_app(model,file_id,snapshot_path)) return false;
        if(model==SPECTRUM_TC2048) model=SPECTRUM_48;
        if(spectrum_model(&machine)!=model && !select_model(model)) error=SPECTRUM_UNSUPPORTED;
    }
    if(!error) {
        mk61_service_framebuffer canvas={0};
        (void)services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(canvas),0,&canvas);
        uint8_t* low=canvas.bytes>=12288?canvas.pixels:NULL;
        error=spectrum_load_szx(&machine,source,low,page_runs[2]);
    }
    if(error) {
        if(error==SPECTRUM_IO) {reset_machine();started=false;}
        message(error==SPECTRUM_UNSUPPORTED?"Unsupported SZX format":
            error==SPECTRUM_MEDIA?"Mount original DivMMC image\nStart esxDOS for old SZX":"Cannot read snapshot");
        return false;
    }
    if(needs_extended_video()) {
        const char* name=spectrum_is_pentagon(&machine)?"ZXVIDEO.APP":"TIMEX.APP";
        if(!switch_to_app(name,spectrum_model(&machine),file_id,snapshot_path)) {
            started=false;message("Video extension APP missing");
        }
        return false;
    }
    started=true;
    return true;
}
#endif
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
static bool raster_available(void) {
    return SPECTRUM_HAS_RASTER && !spectrum_is_pentagon(&machine) &&
        !(machine.extensions&SPECTRUM_TIMEX) && external.handle;
}
#endif
static bool settings(mk61_service_lease* workspace) {
    unsigned selected=0;
    for(;;) {
        static const char* const layouts[]={"Stereo: Mono","Stereo: ABC","Stereo: ACB"};
        const unsigned enabled=machine.extensions;
#if SPECTRUM_HAS_TIMEX_2068
        static const char* const joysticks[]={"Joystick: Timex 1","Joystick: Timex 2","Joystick: Sinclair 1"};
        const char* labels[]={joysticks[machine.joystick_mode],
            machine.sound_chip==SPECTRUM_YM?"Sound chip: YM2149":"Sound chip: AY-3-8912",
            layouts[machine.sound_layout],enabled&SPECTRUM_ULAPLUS?"ULAplus: On":"ULAplus: Off",
            exact_raster?"Raster: On":"Raster: Off","Back"};
        const unsigned back=(color(MK61_COLOR_FORMATS,NULL)&(1u<<MK61_COLOR_RGB565))?5:4;
        if(back==4) labels[4]="Back";
        const char actions[]="jcs4r ";
#else
        static const char* const joysticks[]={"Joystick: Kempston","Joystick: Sinclair 1","Joystick: Sinclair 2"};
        const bool readonly=machine.disk.mode==1?machine.disk.fdc.io.readonly:machine.disk.spi.io.readonly;
        const char* labels[12]={
            enabled&SPECTRUM_TURBOSOUND?"TurboSound: On":"TurboSound: Off",
            enabled&SPECTRUM_COVOX?"Covox: On":"Covox: Off",
            enabled&SPECTRUM_SPECDRUM?"SpecDrum: On":"SpecDrum: Off",
            enabled&SPECTRUM_ULAPLUS?"ULAplus: On":"ULAplus: Off",
            joysticks[machine.joystick_mode],readonly?"Write protect: On":"Write protect: Off",
            machine.sound_chip==SPECTRUM_YM?"Sound chip: YM2149":"Sound chip: AY-3-8912",
            layouts[machine.sound_layout],"Eject disk"
        };
        unsigned back=9;
        char actions[15]="1234jwcsu";
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        if(color(MK61_COLOR_FORMATS,NULL)&(1u<<MK61_COLOR_CELL565)) {
            if(SPECTRUM_HAS_TIMEX) {
                actions[back]='v';labels[back++]=machine.extensions&SPECTRUM_TIMEX?"Timex video: On":"Timex video: Off";
            }
            if(raster_available()) {
                actions[back]='r';labels[back++]=exact_raster?"Raster: On":"Raster: Off";
            }
        }
#endif
        labels[back]="Back";
        memcpy(actions+back," di",4);
#endif
        const int choice=menu_pick("Options",labels,back+1,&selected,true,actions);
        if(choice<0 || (unsigned)choice==back) {
            if(SPECTRUM_HAS_PREFERENCES) {
                const spectrum_preferences changed={preferences.model,(uint8_t)(machine.extensions&15),
                    machine.joystick_mode,machine.sound_chip,machine.sound_layout,exact_raster,preferences.write_protect};
                preferences_dirty|=memcmp(&preferences,&changed,sizeof(changed))!=0;
                preferences=changed;
            }
            return save_preferences(workspace);
        }
        const int c=actions[choice];
        if(c>='1' && c<='4') machine.extensions^=1U<<(c-'1');
        else if(c=='j' || c=='J') machine.joystick_mode=machine.joystick_mode==2?0:machine.joystick_mode+1;
        else if(c=='c') spectrum_sound_configure(&machine,machine.sound_chip^1,machine.sound_layout);
        else if(c=='s') spectrum_sound_configure(&machine,machine.sound_chip,
            machine.sound_layout==SPECTRUM_ACB?SPECTRUM_MONO:machine.sound_layout+1);
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        else if(SPECTRUM_HAS_TIMEX && c=='v') { machine.extensions^=SPECTRUM_TIMEX;machine.timex_mode=0; }
        else if(c=='r') exact_raster=!exact_raster;
#endif
        else if(!SPECTRUM_HAS_TIMEX_2068 && (c=='d' || c=='D')) mount_media(SPECTRUM_DISK_BETA);
        else if(!SPECTRUM_HAS_TIMEX_2068 && (c=='i' || c=='I')) mount_media(SPECTRUM_DISK_DIVMMC);
        else if(!SPECTRUM_HAS_TIMEX_2068 && (c=='u' || c=='U')) { (void)spectrum_disk_mode(&machine,0);reset_machine();started=false; }
        else if(!SPECTRUM_HAS_TIMEX_2068 && (c=='w' || c=='W')) {
            if(machine.disk.mode==1 && !floppy.scl) machine.disk.fdc.io.readonly=!machine.disk.fdc.io.readonly;
            else if(machine.disk.mode==2) machine.disk.spi.io.readonly=!machine.disk.spi.io.readonly;
            if(SPECTRUM_HAS_PREFERENCES && (machine.disk.mode==2 || (machine.disk.mode==1 && !floppy.scl))) {
                const unsigned mask=machine.disk.mode;
                const bool protect=machine.disk.mode==1?machine.disk.fdc.io.readonly:machine.disk.spi.io.readonly;
                preferences.write_protect=(uint8_t)((preferences.write_protect&~mask)|(protect?mask:0));
                preferences_dirty=true;
            }
        }
    }
}
#if SPECTRUM_HAS_TIMEX_2068
static bool load_cartridge(void) {
    uint32_t size;
    if(!file_size(snapshot_path,&size)) {message("Cannot read cartridge");return false;}
    const spectrum_source source={snapshot_path,size,read_source};
    const enum spectrum_error result=spectrum_load_dck(&machine,&source);
    if(result) {
        if(machine.memory->fault) started=false;
        message(result==SPECTRUM_UNSUPPORTED?"Unsupported DCK bank":
                result==SPECTRUM_FORMAT?"Invalid DCK file":"Cannot read cartridge");
        return false;
    }
    stop_tape();started=true;return true;
}
#endif
static __attribute__((noinline)) bool load_snapshot(uint32_t file_id) {
    uint32_t size;
    if(!file_size(snapshot_path,&size)) {
        message("Cannot read snapshot");return false;
    }
    const spectrum_source source={snapshot_path,size,read_source};
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    if(suffix(snapshot_path,".szx")) {stop_tape();return load_szx(&source,file_id);}
#endif
    if(machine.disk.mode==SPECTRUM_DISK_DIVMMC && !machine.disk.spi.reads) {
        message("Start esxDOS before loading\nDivMMC snapshots");return false;
    }
    stop_tape();
    enum spectrum_error error;
    if(suffix(snapshot_path,".sna")) {
        if(SPECTRUM_HAS_TIMEX_2068) {
            if(switch_app(size==49179?SPECTRUM_48:SPECTRUM_128,file_id,snapshot_path)) return false;
            message("Open SNA in SINCLAIR.APP");return false;
        }
        if(!SPECTRUM_HAS_SINCLAIR && size==49179 && switch_app(SPECTRUM_48,file_id,snapshot_path)) return false;
        const unsigned banked=SPECTRUM_HAS_SINCLAIR?SPECTRUM_128:SPECTRUM_P512;
        if((size==131103 || size==147487) && spectrum_model(&machine)==SPECTRUM_48 && !select_model(banked))
            error=SPECTRUM_UNSUPPORTED;
        else error=spectrum_load_sna(&machine,&source);
    } else {
        unsigned model;
        error=spectrum_z80_model(&source,&model);
        if(!error && !model_available(model)) {
            if(switch_app(model,file_id,snapshot_path)) return false;
            // A legacy install with only SPECTRUM.APP can still play its
            // existing 128K .Z80 library on a Pentagon as before.
            if(SPECTRUM_HAS_PENTAGON && (model==SPECTRUM_128 || model==SPECTRUM_48)) model=SPECTRUM_P512;
            else error=SPECTRUM_UNSUPPORTED;
        }
        if(!error && ((model==SPECTRUM_128 && !spectrum_is_128(&machine)) ||
           (model==SPECTRUM_48 && spectrum_is_128(&machine)) ||
           (model==SPECTRUM_P512 && !spectrum_is_pentagon(&machine)) ||
           (model==SPECTRUM_TC2048 && spectrum_model(&machine)!=SPECTRUM_48) ||
           (SPECTRUM_HAS_TIMEX_2068 && model!=spectrum_model(&machine))) &&
           !select_model(model==SPECTRUM_TC2048?SPECTRUM_48:model)) error=SPECTRUM_UNSUPPORTED;
        if(!error) error=spectrum_load_z80(&machine,&source);
    }
    if(error) {
        // A mid-read SD error can leave RAM partially loaded. Never resume
        // that state or the previous CPU over the partially replaced RAM.
        reset_machine();started=false;
        message(error==SPECTRUM_UNSUPPORTED?"Unsupported snapshot or model":
            error==SPECTRUM_IO?"SD read error":"Invalid or truncated snapshot");
        return false;
    }
    started=true;return true;
}
static void help(void) {
    message("Ctrl: Caps Shift\nAlt: Symbol Shift\nTab/F2: Extended mode\nF1: Edit  F6: Graphics\nBackspace: Delete\nArrows + F5: joystick\nEsc: pause / menu\nF10: exit");
}
static uint32_t guest_time_us(uint32_t cycles) {
    if(spectrum_model(&machine)==SPECTRUM_TS2068) return cycles*125u/441u;
    return spectrum_is_128(&machine)?cycles*10000u/35469u:cycles*2/7;
}
static bool pace_frame(uint8_t blocked[32],uint32_t* keyboard_deadline,uint32_t* deadline
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
#if SPECTRUM_RASTER_ENABLED
                       ,raster_output* raster
#endif
#if SPECTRUM_HAS_FAST_VIDEO
                       ,video_output* video
#endif
#if SPECTRUM_RASTER_ENABLED || SPECTRUM_HAS_FAST_VIDEO
                       ,uint8_t* work,const char** error
#endif
#endif
                       ) {
    *deadline+=guest_time_us(spectrum_frame_cycles(&machine));
    // Carry the fractional microseconds of 70908 T at 3.5469 MHz.
    if(spectrum_is_128(&machine)) {
        const unsigned remainder=(SPECTRUM_128_FRAME_TSTATES*10000u)%35469u;
        *deadline+=((machine.frames%35469u)*remainder)%35469u<remainder;
    }
    if(spectrum_model(&machine)==SPECTRUM_TS2068) {
        const unsigned remainder=(SPECTRUM_TS2068_FRAME_TSTATES*125u)%441u;
        *deadline+=((machine.frames%441u)*remainder)%441u<remainder;
    }
    const uint32_t phase_us=guest_time_us(machine.frame_tstates);
    uint32_t target=*deadline+phase_us;
    uint32_t now=pacing_clock_us();
#ifdef SPECTRUM_HIL_PACED
    const uint32_t ready=now;
    bool resynced=false;
#endif
    // Avoid a long catch-up burst after an SD/LCD stall. Include the
    // already executed part of the following frame in this deadline.
    if((int32_t)(now-target)>100000) {
        *deadline=now-phase_us;target=now;
#ifdef SPECTRUM_HIL_PACED
        resynced=true;
#endif
    }
    while((int32_t)(now-target)<0) {
        // A native keyboard/service turn can take almost 2 ms. Do not
        // begin one inside that guard, and refresh time after keyboard I/O
        // before deciding whether another service turn still fits.
        const int key=target-now>2000?poll_guest(blocked,keyboard_deadline,now):-1;
        if(escape(key) || key==0x90) {
            if(key==0x90) started=false;
            return false;
        }
        // The resident millisecond delay already busy-pumps services.
        // Pump directly so it cannot carry us to the next millisecond.
        now=pacing_clock_us();
#if SPECTRUM_RASTER_ENABLED && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        // Z80 has already published the frame. Spend its remaining wall
        // time on PSRAM, strip expansion and LCD submission.
        if(raster && raster->next<RASTER_IDLE && (int32_t)(target-now)>(int32_t)raster->guard_us) {
            const uint32_t start=now;
            pacing_video_io=true;
            const bool ok=raster_present(work,raster);
            pacing_video_io=false;
            if(!ok) {*error="Raster output failed";return false;}
            now=pacing_clock_us();
            const uint32_t needed=now-start+2000;
            if(needed>raster->guard_us && needed<target-start) raster->guard_us=needed;
        }
#endif
#if SPECTRUM_HAS_FAST_VIDEO && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        // Z80 has produced this frame's sound events. Fit capture and strip
        // work here, using the longest observed step plus the service guard.
        if(video->active || video->pending) {
            const unsigned mode=video->active?0:video->pending;
            uint32_t* guard=&video->guard_us;
#if SPECTRUM_HAS_PENTAGON
            // A full conversion can raise its guard without delaying
            // the submission of strips that are already packed.
            if(machine.pentagon && (mode?mode==video->mode:video->selected && (video->packed || video->ready)))
                guard=&video->ready_guard_us;
#endif
            if((int32_t)(target-now)>(int32_t)*guard) {
                const uint32_t start=now;
                const bool cold=SPECTRUM_HAS_PENTAGON && machine.pentagon &&
                    (mode?mode!=video->mode:!video->selected && !video->valid[video->page]);
                if(mode) {video->pending=0;video_begin(video,mode);}
                else {
#if SPECTRUM_HAS_PENTAGON
                    pacing_video_io=machine.pentagon;
#endif
                    const bool ok=video_present(video,work);
#if SPECTRUM_HAS_PENTAGON
                    pacing_video_io=false;
#endif
                    if(!ok) {*error="Color output failed";return false;}
                }
                now=pacing_clock_us();
                const uint32_t duration=now-start+2000;
                // Learn from steps that fit their slot. A long overrun must
                // leave the already captured strips a chance to reach the LCD.
                const bool fits=!SPECTRUM_HAS_PENTAGON || !machine.pentagon || duration<target-start;
                if(!cold && fits && duration>*guard) *guard=duration;
            }
        }
#endif
        if((int32_t)(target-now)>2000) {
            mk61_api->service();
            now=pacing_clock_us();
        }
    }
#ifdef SPECTRUM_HIL_PACED
    SPECTRUM_HIL_PACED(&machine,target,now,ready,resynced);
#endif
    return true;
}
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
static __attribute__((noinline)) void prime_audio(bool beam) {
    // Generate real guest events before PWM. Wide needs time for its
    // initial video snapshot. The original 128K and 2068 ROMs need more
    // lead across the RAM test, paging, and the first complete screen.
    // Each 512T slice fits in the free half of the queue even with two
    // events per OUT, so it never waits on gated audio.
    spectrum_sound* sound=&machine.sound;
    const bool sinclair128=spectrum_is_128(&machine);
    const uint32_t frame=SPECTRUM_HAS_TIMEX_2068?spectrum_frame_cycles(&machine):
        sinclair128?SPECTRUM_128_FRAME_TSTATES:SPECTRUM_FRAME_TSTATES;
    const bool cold128=sinclair128 && !machine.cpu.cyc && !machine.cpu.pc;
    const bool wide=SPECTRUM_HAS_PENTAGON && spectrum_video_mode(&machine)==SPECTRUM_VIDEO_WIDE;
    const bool cold2068=SPECTRUM_HAS_TIMEX_2068 && !machine.cpu.cyc && !machine.cpu.pc;
    const uint32_t ahead=cold128 || cold2068?4*frame:
        SPECTRUM_HAS_BEAM_VIDEO && beam?3*spectrum_frame_cycles(&machine):
        wide?2*spectrum_frame_cycles(&machine):frame;
    const uint32_t end=(uint32_t)machine.cpu.cyc+ahead;
    int32_t left;
    while((left=(int32_t)(end-(uint32_t)machine.cpu.cyc))>0 &&
          !(machine.memory && machine.memory->fault) && !tape->fault && !tape->choices) {
        if(atomic_load_explicit(&sound->write,memory_order_relaxed)-
           atomic_load_explicit(&sound->read,memory_order_relaxed)>SPECTRUM_SOUND_QUEUE_EVENTS/2) break;
        (void)spectrum_run(&machine,left<512?(uint32_t)left:512u);
    }
}
#endif
/* Keep display/audio locals out of the menu and SD paths. The timing
 * probe uses this same frame even when LTO strips the unused menus. */
static __attribute__((noinline)) void emulate_session(void) {
    uint8_t blocked[32];memcpy(blocked,keys,sizeof(blocked));
    uint32_t keyboard_deadline=services->call(MK61_SERVICE_MICROS,0,0,0,NULL);guest_keyboard(blocked);
    if(!mk61_api->graphics_begin()) return;
    mk61_service_framebuffer scratch={0};
    if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(scratch),0,&scratch) ||
       !scratch.pixels || scratch.bytes<SPECTRUM_VIDEO_WORK_BYTES+SPECTRUM_DISK_CACHE_BYTES) {
        message("No framebuffer");return;
    }
    if(!spectrum_disk_cache_begin(&machine,scratch.pixels+SPECTRUM_VIDEO_WORK_BYTES)) {
        message("PSRAM I/O error");return;
    }
    // Resolve the first instruction/stack pages before starting real-time
    // audio. These ordinary memory reads leave guest time and CPU registers
    // untouched, and avoid a cold PSRAM page load in the first sound block.
    if(machine.memory) {
        (void)machine.cpu.read_byte(&machine,machine.cpu.pc);
        (void)machine.cpu.read_byte(&machine,(uint16_t)(machine.cpu.pc+1));
        (void)machine.cpu.read_byte(&machine,machine.cpu.sp);
        (void)machine.cpu.read_byte(&machine,(uint16_t)(machine.cpu.sp-2));
        if(machine.memory->fault) {
            started=false;(void)spectrum_disk_cache_end(&machine);
            message("PSRAM I/O error");return;
        }
    }
    spectrum_display_fast(services);
    mk61_service_color_frame frame={0};
    frame.pixels=scratch.pixels;frame.tiles=scratch.pixels+SPECTRUM_BITMAP_BYTES;
    frame.pixel_bytes=SPECTRUM_BITMAP_BYTES;frame.tile_bytes=SPECTRUM_ATTRIBUTE_BYTES*2;
    frame.x=32;frame.y=64;frame.width=256;frame.height=192;frame.format=MK61_COLOR_TILE8;
    for(unsigned i=0;i<16;++i) frame.palette[i]=spectrum_color(i);
    mk61_service_audio_synth audio={spectrum_sound_render,&machine,25000,100};
    spectrum_sound_begin(&machine,sound_yield,NULL);
    spectrum_sound_clock(&machine,false);
    spectrum_sound* sound=&machine.sound;
    mk61_service_audio_psg psg={0};psg.local=audio;psg.module_path="AY.S3M";
    psg.psg[0]=(uint8_t*)&machine.ay.reg;psg.psg[1]=(uint8_t*)&machine.ay2.reg;psg.psg_bytes=132;
    psg.extensions=machine.extensions&15u;psg.events=(const uint8_t*)sound->events;psg.event_capacity=SPECTRUM_SOUND_QUEUE_EVENTS;
    psg.read=(volatile uint32_t*)&sound->read;psg.write=(const volatile uint32_t*)&sound->write;
    psg.produced=(const volatile uint32_t*)&sound->produced;psg.time=&sound->time;
    psg.running=(const volatile uint8_t*)&sound->clock_running;psg.dac=&sound->beeper;
    psg.dc_input=&sound->input;psg.dc_output=&sound->output;psg.recover=spectrum_sound_recover;
    mk61_service_audio_psg_config config={0};config.psg=psg;
    config.layout=machine.sound_layout;config.chip=machine.sound_chip;config.stereo=sound->stereo;
    uint32_t audio_mode=services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_PSG_CONFIG_OPEN,0,sizeof(config),&config);
    if(!audio_mode && !machine.sound_layout && !machine.sound_chip)
        audio_mode=services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_PSG_OPEN,0,sizeof(psg),&psg);
    if(!audio_mode)audio_mode=services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_SYNTH_OPEN,0,sizeof(audio),&audio);
    if(!audio_mode) {
        spectrum_sound_end(&machine);(void)spectrum_disk_cache_end(&machine);
        message("No audio stream");return;
    }
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    const bool raster=(SPECTRUM_HAS_BEAM_VIDEO?external.handle && (!SPECTRUM_HAS_FAST_VIDEO || exact_raster):
                       exact_raster && raster_available()) &&
        (color(MK61_COLOR_FORMATS,NULL)&(1u<<(SPECTRUM_HAS_BEAM_VIDEO?
             (SPECTRUM_HAS_PENTAGON?MK61_COLOR_INDEX4:MK61_COLOR_RGB565):MK61_COLOR_CELL565)));
    if(audio_mode==2 && (SPECTRUM_HAS_TIMEX_2068 || spectrum_is_128(&machine) || spectrum_video_mode(&machine) ||
       (!machine.pentagon && (raster || tape->playing)))) prime_audio(raster);
    spectrum_hicolor_changes changes;
    if(SPECTRUM_HAS_FAST_VIDEO && SPECTRUM_HAS_TIMEX && !raster && (machine.extensions&SPECTRUM_TIMEX))
        spectrum_hicolor_watch(&machine,&changes);
#if SPECTRUM_HAS_PENTAGON && SPECTRUM_HAS_FAST_VIDEO
    spectrum_pentagon_changes pentagon_changes;
    if(SPECTRUM_HAS_PENTAGON_VIDEO && spectrum_is_pentagon(&machine) && machine.memory && machine.memory->extended)
        spectrum_pentagon_watch(&machine,&pentagon_changes);
#endif
#endif
    status_event("SP STATE=PLAYING\n");
    /* A resumed frame may already be partly executed. Account for that
     * time instead of adding a full frame's wait to its remaining work. */
    uint32_t deadline=services->call(MK61_SERVICE_MICROS,0,0,0,NULL)-guest_time_us(machine.frame_tstates),last_frame=machine.frames;
    // The audio device may wait for LCD/I2C while opening. Both virtual
    // clocks start here, after that wait, rather than during its callbacks.
    spectrum_sound_clock(&machine,true);
    const char* error=NULL;
    // The keys from the menu or FILE_OPEN are already latched. Produce the
    // first frame's sound events before pumping keyboard/LCD/USB from a key
    // scan. The first pacing wait can poll input while M3 renders the queue.
    bool first_remote_frame=audio_mode==2;
    bool after_pace=false;
#if SPECTRUM_HAS_TIMEX
    const uint32_t video_frame=!machine.pentagon &&
        (machine.extensions&SPECTRUM_TIMEX)?spectrum_frame_cycles(&machine):0;
#endif
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
#if SPECTRUM_HAS_FAST_VIDEO
    video_output video={.guard_us=VIDEO_INITIAL_GUARD_US,.clear=true};
#if SPECTRUM_HAS_PENTAGON
    video.ready_guard_us=VIDEO_READY_GUARD_US;
#endif
#endif
#if SPECTRUM_RASTER_ENABLED
    raster_output output={.next=RASTER_IDLE,
        .guard_us=SPECTRUM_HAS_BEAM_VIDEO?VIDEO_READY_GUARD_US:VIDEO_INITIAL_GUARD_US,.clear=true};
#endif
#endif
    for(;;) {
        // The pacing guard already polled input. Produce the next CPU/audio
        // slice before starting another potentially millisecond-long scan.
        const int c=first_remote_frame || after_pace?-1:
            poll_guest(blocked,&keyboard_deadline,services->call(MK61_SERVICE_MICROS,0,0,0,NULL));
        after_pace=false;
        if(escape(c) || c==0x90) {
            if(c==0x90) started=false;
            break;
        }
#if SPECTRUM_HAS_TIMEX
        // Latch completed Timex frames before the next interrupt can change
        // their pixels. A fixed 2048T slice has a different overshoot each frame.
        uint32_t slice=2048;
        if(video_frame) {
            const uint32_t left=video_frame-machine.frame_tstates;
            if(left<slice) slice=left;
        }
        spectrum_run(&machine,slice);
#else
        spectrum_run(&machine,2048);
#endif
        if(machine.memory && machine.memory->fault) goto memory_error;
        if(needs_extended_video()) {error="Open this game in\nZXVIDEO.APP";break;}
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        if(SPECTRUM_HAS_BEAM_VIDEO && !SPECTRUM_HAS_FAST_VIDEO && !raster && spectrum_video_mode(&machine)) {
            error="Raster video requires\nupdated firmware";break;
        }
        if(tape && tape->fault) {tape->fault=false;error="Tape read failed";break;}
        if(tape->choices) break;
        if(raster && machine.cpu.before_store && !machine.video_bytes) goto memory_error;
#endif
        if(machine.frames==last_frame) continue;
        last_frame=machine.frames;
        first_remote_frame=false;
        // Submit the completed frame before its pacing wait, leaving the
        // next frame's first CPU/audio slice free of display conversion.
        {
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
#if SPECTRUM_RASTER_ENABLED
            if(raster) {
                if(machine.video_bytes) {
                    spectrum_raster_end(&machine);
#if SPECTRUM_HAS_BEAM_VIDEO
                    if(machine.beam_geometry_changed) {
                        output.valid=false;output.clear=true;
                        goto paced;
                    }
#endif
                    output.next=0;
                    output.selected=output.repainted=false;
                    goto paced;
                }
                // Capture again only when the previous frame is committed.
                if(output.next!=RASTER_IDLE) goto paced;
#if SPECTRUM_HAS_BEAM_VIDEO
                const unsigned mode=SPECTRUM_HAS_PENTAGON?spectrum_pentagon_video_mode(&machine):SPECTRUM_VIDEO_HICOLOR;
                if(mode) {
                    if(output.mode!=mode) {output.valid=false;output.clear=true;}
                    output.mode=(uint8_t)mode;
                    output.bank^=1u;
                    spectrum_beam_begin(&machine,mode,scratch.pixels,&output,raster_store);
                    goto paced;
                }
                output.valid=false;output.clear=true;
#else
                    output.bank^=1u;
                    spectrum_raster_begin(&machine,scratch.pixels,&output,raster_store);
                    goto paced;
#endif
            }
#endif
#if SPECTRUM_HAS_FAST_VIDEO
            if(!SPECTRUM_HAS_PENTAGON && video.active) goto paced;
            video.pending=spectrum_video_mode(&machine);
            if(video.active || video.pending) goto paced;
            if(SPECTRUM_HAS_PENTAGON && video.pages) video_begin(&video,0);
            video.mode=0;
            if(!SPECTRUM_HAS_PENTAGON) video.clear=true;
#endif
#endif
            uint16_t palette[64];for(unsigned i=0;i<64;++i) palette[i]=spectrum_palette(&machine,i);
            const uint32_t ready=services->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_PALETTE64,0,sizeof(palette),palette);
            if(ready==2) goto paced;
            if(!ready) { error="Color output failed";break; }
            spectrum_video8(&machine,scratch.pixels,scratch.pixels+SPECTRUM_BITMAP_BYTES);
            if(machine.memory && machine.memory->fault) goto memory_error;
            frame.background=spectrum_border(&machine);
            const uint32_t result=color(MK61_COLOR_PRESENT,&frame);
            if(!result) { error="Color output failed";break; }
        }
paced:
        if(!pace_frame(blocked,&keyboard_deadline,&deadline
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
#if SPECTRUM_RASTER_ENABLED
                       ,raster?&output:NULL
#endif
#if SPECTRUM_HAS_FAST_VIDEO
                       ,&video
#endif
#if SPECTRUM_RASTER_ENABLED || SPECTRUM_HAS_FAST_VIDEO
                       ,scratch.pixels,&error
#endif
#endif
                       )) goto done;
        after_pace=true;
    }
    goto done;
memory_error:
    started=false;error="PSRAM I/O error";
done:
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    if(SPECTRUM_HAS_TIMEX) spectrum_hicolor_watch(&machine,NULL);
#if SPECTRUM_HAS_PENTAGON_VIDEO
    spectrum_pentagon_watch(&machine,NULL);
#endif
    spectrum_raster_end(&machine);
#endif
    spectrum_sound_clock(&machine,false);
    services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_CLOSE,0,0,NULL);
    spectrum_sound_end(&machine);
    if(!spectrum_disk_cache_end(&machine)) { started=false;error="PSRAM I/O error"; }
    /* Keep the borrowed canvas owned across the OSD: graphics_end would
     * redraw resident text over the RAM pages stored in its unused tail. */
    color(MK61_COLOR_END,NULL);
    status_event("SP STATE=PAUSED\n");
    if(error) message(error);
}
static void emulate(void) {
    do {
        emulate_session();
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    } while(tape->choices && tape_select());
#else
    } while(0);
#endif
}
/* The Z80 state and cache are in run_app's frame. Keep OSD/SD locals here
 * so their callees can reuse stack slots after their own return. */
#if defined(__GNUC__) && !defined(__clang__) && __GNUC__ >= 12
__attribute__((optimize("Oz")))
#endif
static __attribute__((noinline)) int app_run(uint32_t file_id,unsigned initial_model) {
    /* These paths live for the complete foreground APP session. Keep them
     * in the resident stack reservation instead of enlarging the heap image
     * alongside the 32K/16K guest-memory leases. No I/O outlives main(). */
    char paths[4][256];
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    char mounted_path[256];
    spectrum_tape mounted_tape={0};
    tape_path=mounted_path;tape=&mounted_tape;
#if SPECTRUM_HAS_TAPE_RECORD
    spectrum_tape_recorder recorder={0};
    recording=&recorder;
#endif
#endif
    directory=paths[0];snapshot_path=paths[1];floppy.path=paths[2];sd_card.path=paths[3];
    opened_file=file_id;
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
    exact_raster=false;
#endif
    directory[0]='.';directory[1]=snapshot_path[0]=floppy.path[0]=sd_card.path[0]=0;
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_MEMORY|MK61_SERVICE_CAP_COLOR_DISPLAY|
        MK61_SERVICE_CAP_FILE_BYTES|MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_AUDIO_STREAM);
    if(!services) {
        mk61_api->display_clear();
        mk61_api->display_write_m8(0,0,"Update PicoCalc firmware",24);
        mk61_api->key_wait();return 0;
    }
    mk61_service_lease ram={0},rom={0};
    mk61_service_buffer sram[2]={{0}};
    banked_buffers=(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL)&MK61_SERVICE_CAP_EXTERNAL_BUFFERS)!=0;
    if(SPECTRUM_HAS_TIMEX_2068 && !banked_buffers) {message("Timex requires PSRAM");return 0;}
    if(!SPECTRUM_HAS_SINCLAIR && !banked_buffers) {
        if(!switch_app(SPECTRUM_48,file_id,NULL)) message("Pentagon requires PSRAM\nUse SINCLAIR.APP for 48K");
        return 0;
    }
    if(banked_buffers) {
        mk61_service_framebuffer canvas={0};
        if(!mk61_api->graphics_begin() ||
           !services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(canvas),0,&canvas) ||
           !canvas.pixels || canvas.bytes<12800) {
            message("No framebuffer");return 0;
        }
        /* The OSD uses up to byte 9983. Reserve the final two 1K pages
         * across gameplay and menus. The other slots use heap and stack. */
        page_runs[3]=canvas.pixels+10752;
        for(unsigned i=0;i<2;++i) {
            if(!mk61_app_buffer_acquire(services,SPECTRUM_BANK_HEAP_BYTES,MK61_BUFFER_DIRECT,&sram[i]) ||
               sram[i].storage!=MK61_BUFFER_SRAM || !sram[i].data) {
                message("Not enough SRAM for Spectrum");return 0;
            }
            guest_blocks[i]=sram[i].data;
        }
    }
    if((!banked_buffers && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,SPECTRUM_RAM_BYTES,&ram)) ||
       (banked_buffers && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,WORK_CACHE_BYTES,&ram)) ||
       (banked_buffers && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,2048,&rom)) ||
       (!banked_buffers && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,SPECTRUM_ROM_BYTES,&rom))) {
        message("Not enough SRAM for Spectrum");return 0;
    }
    uint32_t rom_size;
    if(!SPECTRUM_HAS_TIMEX_2068 && ((!banked_buffers && !load_rom(rom.data)) || (banked_buffers &&
       (!file_size("48.rom",&rom_size) || rom_size!=SPECTRUM_ROM_BYTES)))) {
        message("Put 16 KiB 48.rom\nnext to SPECTRUM.APP");return 0;
    }
    page_runs[0]=ram.data;page_runs[1]=rom.data;
    if(!banked_buffers) spectrum_init(&machine,ram.data,rom.data);
    else { memset(&machine,0,sizeof(machine));machine.ram=guest_blocks[0];machine.rom=NULL;
        machine.extensions=SPECTRUM_TURBOSOUND|SPECTRUM_COVOX|SPECTRUM_SPECDRUM|SPECTRUM_ULAPLUS; }
    load_preferences();
    machine.extensions=preferences.extensions;
    machine.joystick_mode=preferences.joystick;
    exact_raster=preferences.raster;
    spectrum_sound_configure(&machine,preferences.chip,preferences.layout);
    const bool remember_model=SPECTRUM_HAS_PREFERENCES && initial_model!=UINT32_MAX && file_id==MK61_SERVICE_INVALID_ID;
    if(initial_model==UINT32_MAX || (SPECTRUM_HAS_TIMEX_2068 && !model_available(initial_model)))
        initial_model=preferences.model;
    if(!select_model(banked_buffers?initial_model:SPECTRUM_48)) {
        if(SPECTRUM_HAS_TIMEX_2068) {
            message("Check tc2068-0.rom and\ntc2068-1.rom next to APP");
            goto done;
        }
        if(!select_model(SPECTRUM_48)) return 0;
    }
    if(remember_model && preferences.model!=spectrum_model(&machine)) {
        preferences.model=(uint8_t)spectrum_model(&machine);preferences_dirty=true;
        if(!save_preferences(&ram)) goto done;
    }
    if(file_id!=MK61_SERVICE_INVALID_ID) {
        if(!file_call(MK61_FILE_BYTES_PATH,NULL,snapshot_path,file_id,256)) {
            message("Update firmware for file launch");
        } else {
            strcpy(directory,snapshot_path);parent_directory();
            bool play=false;
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
            if(is_tape(snapshot_path)) {
                if(!SPECTRUM_HAS_SINCLAIR) {
                    if(switch_app(SPECTRUM_48,file_id,snapshot_path)) goto done;
                    message("Open this tape in SINCLAIR.APP");
                } else if((SPECTRUM_HAS_TIMEX_2068 || select_model(SPECTRUM_48)) && mount_tape()) tape_ready();
            } else
#endif
#if SPECTRUM_HAS_TIMEX_2068
            if(is_cartridge(snapshot_path)) play=load_cartridge();
            else if(is_snapshot(snapshot_path)) play=load_snapshot(file_id);
            else message("Unsupported Timex file");
#else
            play=is_snapshot(snapshot_path)?load_snapshot(file_id):
                mount_selected_media(suffix(snapshot_path,".img")?SPECTRUM_DISK_DIVMMC:SPECTRUM_DISK_BETA);
#endif
            if(play) {
                // The Explorer's opening Enter/F-key may still be held.
                // Seed the normal guest-key blocker before starting the CPU.
                const int key=scan_keys();
                if(escape(key) || key==0x90) goto done;
                started=true;emulate();
                if(!started) goto done;
            }
            if(switching_app()) goto done;
        }
    }
#ifdef SPECTRUM_HIL_AFTER_FILE
    SPECTRUM_HIL_AFTER_FILE();
#endif
    for(;;) {
        const char* labels[ROOT_COUNT];
        root_labels(labels);
#if SPECTRUM_HAS_TIMEX_2068
        const char hotkeys[]="rkeomplsbhq";
#else
        char hotkeys[]="rodimptbh"
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
            "ls"
#endif
            "vq";
        if(machine.disk.mode==SPECTRUM_DISK_DIVMMC) hotkeys[ROOT_DISK_OR_NMI]='n';
#endif
        const int choice=menu_pick(root_title,labels,ROOT_COUNT,&root_selected,false,hotkeys);
        const int c=choice<0?'q':choice==0?13:hotkeys[choice];
        if(escape(c) || c=='q' || c=='Q' || c==0x90) {
#if SPECTRUM_HAS_TAPE_RECORD && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
            if(recording->write) {message("Save or discard the TAP\nrecording first");continue;}
#endif
            break;
        }
        if(c=='h' || c=='H') { help();continue; }
        if(!SPECTRUM_HAS_TIMEX_2068 && c=='v') {
            const bool pentagon=spectrum_is_pentagon(&machine);
            const char* name=SPECTRUM_HAS_EXTENDED_VIDEO?(pentagon?"SPECTRUM.APP":"SINCLAIR.APP"):
                pentagon?"ZXVIDEO.APP":"TIMEX.APP";
            if(switch_to_app(name,spectrum_model(&machine),MK61_SERVICE_INVALID_ID,NULL)) goto done;
            message("Companion APP missing");continue;
        }
        if(c=='p' || c=='P') { if(!settings(&ram)) break;continue; }
#if !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
        if(c=='l') { if(!tape_menu(&ram)) break;continue; }
        if(c=='s') { if(!save_snapshot(&ram)) break;continue; }
#endif
        if(!SPECTRUM_HAS_TIMEX_2068 && (c=='d' || c=='D')) { mount_media(SPECTRUM_DISK_BETA);continue; }
        if(!SPECTRUM_HAS_TIMEX_2068 && (c=='i' || c=='I')) { mount_media(SPECTRUM_DISK_DIVMMC);continue; }
        if(c=='m' || c=='M') {
#if SPECTRUM_HAS_TIMEX_2068
            const char* models[]={"TS2068 (NTSC)","TC2068 (PAL)"};
            unsigned model=!machine.timex_ntsc;
            const int picked=menu_pick("Machine",models,2,&model,true,NULL);
            if(picked>=0 && !select_model(picked?SPECTRUM_TC2068:SPECTRUM_TS2068)) message("PSRAM I/O error");
#else
            const char* models[]={"Spectrum 48K","Pentagon 512K","Pentagon 1024K","Sinclair 128K"};
            unsigned model=spectrum_model(&machine);
            int picked;
            if(SPECTRUM_HAS_PENTAGON) picked=menu_pick("Machine",models,4,&model,true,NULL);
            else {
                const char* originals[]={models[SPECTRUM_48],models[SPECTRUM_128]};
                model=model==SPECTRUM_128;
                picked=menu_pick("Machine",originals,2,&model,true,NULL);
                if(picked==1) picked=SPECTRUM_128;
            }
            if(picked<0) continue;
            if(!model_available((unsigned)picked)) {
                if(switch_app((unsigned)picked,MK61_SERVICE_INVALID_ID,NULL)) goto done;
                message(SPECTRUM_HAS_PENTAGON?"Open SINCLAIR.APP for 128K":"Open SPECTRUM.APP for Pentagon");
                continue;
            }
            if(!select_model((unsigned)picked)) {
                message("ROM or PSRAM not ready");(void)select_model(false);
            } else if(SPECTRUM_HAS_PREFERENCES && preferences.model!=(unsigned)picked) {
                preferences.model=(uint8_t)picked;preferences_dirty=true;
                if(!save_preferences(&ram)) goto done;
            }
#endif
            continue;
        }
#if SPECTRUM_HAS_TIMEX_2068
        if(c=='e') {
            machine.cartridge=(spectrum_cartridge){0};
            reset_machine();started=false;continue;
        }
        if(c=='k') {
            if(!choose_file(FILE_CARTRIDGE) || !load_cartridge()) continue;
        } else
#endif
        if(c=='o' || c=='O') {
            if(!choose_file(FILE_SNAPSHOT) || !load_snapshot(MK61_SERVICE_INVALID_ID)) {
                if(switching_app()) goto done;
                continue;
            }
        }
        else if(!SPECTRUM_HAS_TIMEX_2068 && (c=='t' || c=='T') && machine.disk.mode==SPECTRUM_DISK_BETA && started) {
            if(spectrum_model(&machine)!=SPECTRUM_48) (void)spectrum_memory_page(machine.memory,machine.memory->paging|16);
            spectrum_refresh_map(&machine);
            machine.cpu.sp-=2;
            machine.cpu.write_byte(&machine,machine.cpu.sp,(uint8_t)machine.cpu.pc);
            machine.cpu.write_byte(&machine,(uint16_t)(machine.cpu.sp+1),(uint8_t)(machine.cpu.pc>>8));
            machine.cpu.pc=15616;machine.cpu.halted=false;
        } else if(!SPECTRUM_HAS_TIMEX_2068 && (c=='n' || c=='N') && machine.disk.mode==SPECTRUM_DISK_DIVMMC && started) z80_gen_nmi(&machine.cpu);
        else if(c=='b' || c=='B' || enter(c)) {
            if(c=='b' || c=='B' || !started) reset_machine();
            started=true;
        } else continue;
        emulate();
        if(!started) {
#if SPECTRUM_HAS_TAPE_RECORD && !defined(SPECTRUM_HIL_SNAPSHOT_ONLY)
            if(recording->write) {message("Save or discard the TAP\nrecording first");continue;}
#endif
            break;
        }
    }
done:
    color(MK61_COLOR_END,NULL);mk61_api->graphics_end();
    if(rom.data) services->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,0,&rom);
    if(banked_buffers) {
        for(unsigned i=0;i<2;++i) if(sram[i].handle) mk61_app_buffer_release(services,sram[i].handle);
    }
    if(ram.data) services->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,0,&ram);
    if(external.handle) mk61_app_buffer_release(services,external.handle);
    return 0;
}
static int run_app(uint32_t file_id,unsigned initial_model) {
    /* The complete machine lives until audio and display have stopped. Keep
     * it in the resident 32K stack instead of splitting the APP/guest heap. */
    spectrum state={0};uint8_t tails[2][SPECTRUM_CACHE_PAGE_BYTES],pages[4096];active_machine=&state;
    page_runs[2]=pages;
    for(unsigned i=0;i<2;++i)bank_tails[i]=tails[i];
    const int result=app_run(file_id,initial_model);active_machine=NULL;return result;
}
int main(void) { return run_app(MK61_SERVICE_INVALID_ID,UINT32_MAX); }
uint32_t mk61_app_open_file(uint32_t file_id) {
    return file_id>=MK61_SERVICE_INVALID_ID?MK61_APP_INVALID_FILE:(uint32_t)run_app(file_id,UINT32_MAX);
}
#if SPECTRUM_APP_PROFILE
uint32_t mk61_app_file_flow(void) { return MK61_APP_FLOW_MAGIC; }
uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
    if(!mk61_app_flow_compatible(flow) || flow->context_size<2*sizeof(uint32_t)) return 0;
    const uint32_t* context=flow->context;
    const uint32_t file=flow->current.phase==MK61_APP_FLOW_FILE_PHASE?context[0]:MK61_SERVICE_INVALID_ID;
    const unsigned model=context[1] && context[1]<=SPECTRUM_TS2068+1?context[1]-1:UINT32_MAX;
    app_flow=flow;
    const int result=run_app(file,model);
    if(!switching_app()) mk61_app_flow_return(flow,(uint32_t)result,MK61_FLOW_OK);
    app_flow=NULL;return 1;
}
#endif
