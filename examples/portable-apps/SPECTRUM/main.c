#include "mk61_app.h"
#include "spectrum.h"
#include "media.h"
#include "ui.h"
#include "rom_cache.h"
#include <string.h>

static const mk61_app_services* services;
static spectrum* active_machine;
#define machine (*active_machine)
static uint8_t keys[32],previous_keys[32];
static char *directory,*snapshot_path;
static bool started;
static uint8_t* page_cache;
static uint8_t* bank_window;
static uint8_t *guest_blocks[2],*bank_tails[3];
static bool banked_buffers,mapped_roms;
static const uint8_t* mapped_rom[3];
static spectrum_memory bank_memory;
static mk61_service_buffer external;
typedef struct { char* path;bool scl; } mounted_media;
static mounted_media floppy,sd_card;
static spectrum_ui osd;
static unsigned root_selected;

static bool external_transfer(bool write,uint32_t offset,uint8_t* bytes,uint32_t length) {
    while(length) {
        const uint32_t n=length<4096?length:4096;
        const uint32_t ok=write?mk61_app_buffer_write(services,external.handle,offset,bytes,n):
            mk61_app_buffer_read(services,external.handle,offset,bytes,n);
        if(!ok) return false;
        offset+=n;bytes+=n;length-=n;mk61_api->service();
    }
    return true;
}
static bool external_read(void* context,uint32_t at,uint8_t* out,uint32_t n) {
    (void)context;return external_transfer(false,at,out,n);
}
static bool external_write(void* context,uint32_t at,const uint8_t* in,uint32_t n) {
    (void)context;return external_transfer(true,at,(uint8_t*)in,n);
}
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
static int scan_keys(void) {
    if(!services->call(MK61_SERVICE_KEYBOARD,MK61_SERVICE_KEY_BITMAP,sizeof(keys),0,keys)) return -1;
    int first=-1;
    for(unsigned c=1;c<256;++c) if((keys[c/8]&(1U<<(c&7))) &&
        !(previous_keys[c/8]&(1U<<(c&7))) && first<0) first=(int)c;
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
static void root_window(void) {
    const char* labels[]={started?"Resume":"Start machine","Snapshot...","Beta Disk...","DivMMC...",
        "Machine...","Options...",machine.disk.mode==SPECTRUM_DISK_DIVMMC?"NMI browser":"TR-DOS","Reset","Help","Exit"};
    spectrum_ui_window(&osd,8,8,224,"Spectrum",labels,10,root_selected);
}
static bool menu_draw(const char* title,const char* const* labels,unsigned count,unsigned selected,bool nested) {
    if(!spectrum_ui_begin(&osd,services,&machine,started)) return false;
    if(nested) root_window();
    spectrum_ui_window(&osd,nested?40:8,nested?40:8,nested?208:224,title,labels,count,selected);
    spectrum_ui_footer(&osd,"Enter: select    Esc: back");
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
    if(!menu_draw("Spectrum",lines,count,count,false)) {
        // A missing ROM/font must still produce a readable startup error.
        if(machine.memory) { (void)spectrum_memory_flush_pages(machine.memory);spectrum_refresh_map(&machine); }
        mk61_api->graphics_end();mk61_api->display_clear();
        for(unsigned i=0;i<count && i<10;++i) {
            const unsigned length=(unsigned)strlen(lines[i]);
            mk61_api->display_write_m8(0,i,lines[i],length<20?length:20);
        }
    }
    wait_key();
}
static uint32_t file_call(unsigned op,const char* path,void* out,uint32_t offset,uint32_t bytes) {
    mk61_service_file_bytes r={path,out,offset,bytes};
    return services->call(MK61_SERVICE_FILE_BYTES,op,0,sizeof(r),&r);
}
static bool read_source(void* path,uint32_t at,uint8_t* out,uint32_t bytes) {
    const bool ok=file_call(MK61_FILE_BYTES_READ,path,out,at,bytes)!=0;
    mk61_api->service();return ok;
}
static bool suffix(const char* name,const char* extension) {
    const unsigned n=(unsigned)strlen(name),k=(unsigned)strlen(extension);
    if(n<k) return false;
    for(unsigned i=0;i<k;++i) if((name[n-k+i]|32)!=(extension[i]|32)) return false;
    return true;
}
static bool join_path(char* out,const char* base,const char* leaf) {
    const unsigned n=(unsigned)strlen(base),k=(unsigned)strlen(leaf);
    if(n+k+2>256) return false;
    memcpy(out,base,n);out[n]='/';memcpy(out+n+1,leaf,k+1);return true;
}
static void parent_directory(void) {
    char* slash=NULL;
    for(char* p=directory;*p;++p) if(*p=='/') slash=p;
    if(slash) *slash=0;else { directory[0]='.';directory[1]=0; }
}
static bool entry(unsigned selected,mk61_service_file_info* out,unsigned type) {
    unsigned matched=0;
    for(unsigned i=0;i<4096;++i) {
        mk61_service_file_info f;
        if(!file_call(MK61_FILE_BYTES_CHILD,directory,&f,i,sizeof(f))) return false;
        mk61_api->service();
        const bool match=type==0?(suffix(f.name,".sna") || suffix(f.name,".z80")):
            type==1?(suffix(f.name,".trd") || suffix(f.name,".scl")):suffix(f.name,".img");
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
        if(!menu_draw(type==0?"Snapshot":type==1?"Beta Disk":"DivMMC",names,count,found?selected-top:count,false)) return false;
        const int c=wait_key();
        if(escape(c)) return false;
        if(c==8 || c==0xD4) {
            parent_directory();
            selected=0;
        } else if(c==0xB5 || c==0xB4) { if(selected) --selected; }
        else if(c==0xB6 || c==0xB7) { mk61_service_file_info next;if(entry(selected+1,&next,type)) ++selected; }
        else if(enter(c) && found) {
            if(!join_path(snapshot_path,directory,f.name)) { message("Path too long\n\nPress any key");continue; }
            if(f.directory) { memcpy(directory,snapshot_path,strlen(snapshot_path)+1);selected=0; }
            else return true;
        }
    }
}
static bool load_rom(uint8_t* rom) {
    mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,"48.rom",&info,0,sizeof(info)) ||
       info.directory || info.size!=SPECTRUM_ROM_BYTES) return false;
    for(unsigned at=0;at<SPECTRUM_ROM_BYTES;at+=4096)
        if(!read_source("48.rom",at,rom+at,4096)) return false;
    return true;
}
static const uint8_t* cached_rom(unsigned id,const char* path) {
    uint32_t expected;const uint8_t* data=spectrum_rom_cache_find(id,&expected);if(!data) return NULL;
    const unsigned size=id==SPECTRUM_ROM_DIV?8192:16384;mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,path,&info,0,sizeof(info)) || info.directory || info.size!=size) return NULL;
    uint8_t bytes[256];uint32_t crc=UINT32_MAX;
    for(unsigned at=0;at<size;at+=sizeof(bytes)) {
        if(!read_source((void*)path,at,bytes,sizeof(bytes))) return NULL;
        crc=spectrum_crc32(crc,bytes,sizeof(bytes));
    }
    return (crc^UINT32_MAX)==expected?data:NULL;
}
static bool select_model(unsigned model) {
    const bool pentagon=model!=0;
    if(!pentagon && !banked_buffers) {
        if(!load_rom((uint8_t*)machine.rom)) return false;
        spectrum_attach_memory(&machine,NULL);spectrum_reset(&machine);started=false;return true;
    }
    if(!external.handle && !mk61_app_buffer_acquire(services,SPECTRUM_EXTERNAL_BYTES+SPECTRUM_TRD_BYTES,MK61_BUFFER_EXTERNAL,&external)) {
        message("Pentagon 512K requires PSRAM\n\nPress any key");return false;
    }
    const spectrum_memory_io io={NULL,external_read,external_write,external_clear};
    if(mapped_roms) {
        if(!spectrum_memory_init_split(&bank_memory,guest_blocks[0],guest_blocks[1],bank_tails,bank_window,
            mapped_rom[pentagon?1:0],mapped_rom[pentagon?2:0],io)) return false;
    } else {
      const char* names[]={pentagon?"128-0.rom":"48.rom",pentagon?"128-1.rom":"48.rom"};
      for(unsigned bank=0;bank<2;++bank) {
        mk61_service_file_info info;
        if(!file_call(MK61_FILE_BYTES_STAT,names[bank],&info,0,sizeof(info)) || info.size!=16384 || info.directory) return false;
        for(unsigned at=0;at<16384;at+=4096) {
            if(!read_source((void*)names[bank],at,(uint8_t*)machine.rom,4096) ||
               !external_write(NULL,SPECTRUM_ROM_BASE+bank*16384+at,machine.rom,4096)) return false;
        }
      }
      if(!spectrum_memory_init_split(&bank_memory,guest_blocks[0],guest_blocks[1],bank_tails,page_cache,machine.rom,NULL,io)) return false;
    }
    bank_memory.extended=model==2;bank_memory.banks=model==2?64:32;
    if(model==2 && !spectrum_memory_reset(&bank_memory)) return false;
    spectrum_attach_memory(&machine,&bank_memory);machine.pentagon=pentagon;spectrum_disk_reset(&machine);started=false;return true;
}
#ifdef SPECTRUM_HIL_SNAPSHOT_ONLY
/* A fixed-checkpoint timing probe needs no image mounting or SCL unpacker.
 * Its CPU, renderer and audio paths remain the ordinary APP paths. */
static void mount_media(unsigned mode) { (void)mode;message("Snapshot timing probe\n\nPress any key"); }
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
    machine.disk.xip_rom[mode]=cached_rom(mode==SPECTRUM_DISK_BETA?SPECTRUM_ROM_BETA:SPECTRUM_ROM_DIV,path);
    if(machine.disk.xip_rom[mode]) return true;
    const uint32_t target=mode==SPECTRUM_DISK_BETA?SPECTRUM_TRDOS_ROM:SPECTRUM_DIV_ROM;
    const unsigned size=mode==SPECTRUM_DISK_BETA?16384:8192;
    mk61_service_file_info info;uint8_t bytes[256];
    if(!file_call(MK61_FILE_BYTES_STAT,path,&info,0,sizeof(info)) || info.directory || info.size!=size) {
        message("Disk interface ROM missing\nSee SPECTRUM/README.md\n\nPress any key");return false;
    }
    for(unsigned at=0;at<size;at+=sizeof(bytes))
        if(!read_source((void*)path,at,bytes,sizeof(bytes)) || !external_write(NULL,target+at,bytes,sizeof(bytes))) return false;
    return true;
}
static bool mount_selected_media(unsigned mode) {
    if(!machine.memory) { message("Disk interfaces require PSRAM\n\nPress any key");return false; }
    mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,snapshot_path,&info,0,sizeof(info)) || info.directory) return false;
    const bool scl=suffix(snapshot_path,".scl");
    if(mode==SPECTRUM_DISK_DIVMMC && (info.size<1024*1024 || info.size%512)) {
        message("SD image must be sector aligned\nand at least 1 MiB\n\nPress any key");return false;
    }
    if(mode==SPECTRUM_DISK_BETA && !scl && (info.size<4096 || info.size>SPECTRUM_TRD_BYTES || info.size%256)) {
        message("Invalid TRD size\n\nPress any key");return false;
    }
    if(!disk_rom(mode)) return false;
    if(scl) {
        const spectrum_source source={snapshot_path,info.size,read_source};
        const spectrum_memory_io io={NULL,external_read,external_write,external_clear};
        if(spectrum_scl_unpack(&source,&io,SPECTRUM_EXTERNAL_BYTES)!=SPECTRUM_OK) {
            message("Invalid SCL / checksum / SD error\n\nPress any key");return false;
        }
    }
    mounted_media* m=mode==SPECTRUM_DISK_BETA?&floppy:&sd_card;
    memcpy(m->path,snapshot_path,strlen(snapshot_path)+1);m->scl=scl;
    spectrum_disk_io* io=mode==SPECTRUM_DISK_BETA?&machine.disk.fdc.io:&machine.disk.spi.io;
    *io=(spectrum_disk_io){m,scl?SPECTRUM_TRD_BYTES:info.size,media_read,media_write,true,80,2};
    if(!spectrum_disk_mode(&machine,mode)) return false;
    spectrum_reset(&machine);started=false;return true;
}
static void mount_media(unsigned mode) {
    if(!machine.memory) { message("Disk interfaces require PSRAM\n\nPress any key");return; }
    if(choose_file(mode==SPECTRUM_DISK_BETA?1:2)) (void)mount_selected_media(mode);
}
#endif
static void settings(void) {
    unsigned selected=0;
    for(;;) {
        const char* joysticks[]={"Kempston","Sinclair 1","Sinclair 2"};
        char values[6][28];const char* labels[10];
        const char* devices[]={"TurboSound","Covox","SpecDrum","ULAplus"};
        for(unsigned i=0;i<4;++i) { mk61_app_snprintf(services,values[i],28,"%s: %s",devices[i],machine.extensions&(1U<<i)?"On":"Off");labels[i]=values[i]; }
        mk61_app_snprintf(services,values[4],28,"Joystick: %s",joysticks[machine.joystick_mode]);labels[4]=values[4];
        const bool readonly=machine.disk.mode==1?machine.disk.fdc.io.readonly:machine.disk.spi.io.readonly;
        mk61_app_snprintf(services,values[5],28,"Write protect: %s",readonly?"On":"Off");labels[5]=values[5];
        labels[6]="Eject disk";labels[7]="Back";
        const int choice=menu_pick("Options",labels,8,&selected,true,"1234jwu di");
        if(choice<0 || choice==7) return;
        const char actions[]="1234jwu di";const int c=actions[choice];
        if(c>='1' && c<='4') machine.extensions^=1U<<(c-'1');
        else if(c=='j' || c=='J') machine.joystick_mode=(machine.joystick_mode+1)%3;
        else if(c=='d' || c=='D') mount_media(SPECTRUM_DISK_BETA);
        else if(c=='i' || c=='I') mount_media(SPECTRUM_DISK_DIVMMC);
        else if(c=='u' || c=='U') { (void)spectrum_disk_mode(&machine,0);spectrum_reset(&machine);started=false; }
        else if(c=='w' || c=='W') {
            if(machine.disk.mode==1 && !floppy.scl) machine.disk.fdc.io.readonly=!machine.disk.fdc.io.readonly;
            else if(machine.disk.mode==2) machine.disk.spi.io.readonly=!machine.disk.spi.io.readonly;
        }
    }
}
static bool load_snapshot(void) {
    if(machine.disk.mode==SPECTRUM_DISK_DIVMMC && !machine.disk.spi.reads) {
        message("Start esxDOS before opening\na snapshot with DivMMC enabled\n\nPress any key");return false;
    }
    mk61_service_file_info info;
    if(!file_call(MK61_FILE_BYTES_STAT,snapshot_path,&info,0,sizeof(info)) || info.directory) {
        message("Cannot read snapshot\n\nPress any key");return false;
    }
    const spectrum_source source={snapshot_path,info.size,read_source};
    const enum spectrum_error error=suffix(snapshot_path,".sna")?spectrum_load_sna(&machine,&source):
        spectrum_load_z80(&machine,&source);
    if(error) {
        // A mid-read SD error can leave RAM partially loaded. Never resume
        // that state or the previous CPU over the partially replaced RAM.
        spectrum_reset(&machine);started=false;
        message(error==SPECTRUM_UNSUPPORTED?"Unsupported snapshot/model\nUse Pentagon for 128K files\n\nPress any key":
            error==SPECTRUM_IO?"SD read error\n\nPress any key":"Invalid or truncated snapshot\n\nPress any key");
        return false;
    }
    started=true;return true;
}
static void help(void) {
    message("Ctrl: Caps Shift\nAlt: Symbol Shift\nTab/F2: Extended mode\nF1: Edit  F6: Graphics\nBackspace: Delete\nArrows + F5: joystick\nEsc: pause / menu\nF10: exit\n\nPress any key");
}
static bool pace_frame(uint8_t blocked[32],uint32_t* keyboard_deadline,uint32_t* deadline) {
    *deadline+=spectrum_frame_cycles(&machine)*2/7;
    const uint32_t phase_us=machine.frame_tstates*2/7;
    uint32_t target=*deadline+phase_us;
    uint32_t now=services->call(MK61_SERVICE_MICROS,0,0,0,NULL);
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
        // A full keyboard bitmap is relatively costly. The outer CPU loop
        // will scan it just after this boundary if fewer than 512 us remain.
        const int key=target-now>512?poll_guest(blocked,keyboard_deadline,now):-1;
        if(escape(key) || key==0x90) {
            if(key==0x90) started=false;
            return false;
        }
        // The resident millisecond delay already busy-pumps services.
        // Pump directly so it cannot carry us to the next millisecond.
        if(target-now>512) mk61_api->service();
        now=services->call(MK61_SERVICE_MICROS,0,0,0,NULL);
    }
#ifdef SPECTRUM_HIL_PACED
    SPECTRUM_HIL_PACED(&machine,target,now,ready,resynced);
#endif
    return true;
}
static void emulate(void) {
    uint8_t blocked[32];memcpy(blocked,keys,sizeof(blocked));
    uint32_t keyboard_deadline=services->call(MK61_SERVICE_MICROS,0,0,0,NULL);guest_keyboard(blocked);
    if(!mk61_api->graphics_begin()) return;
    mk61_service_framebuffer scratch={0};
    if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(scratch),0,&scratch) ||
       !scratch.pixels || scratch.bytes<10240+SPECTRUM_DISK_CACHE_BYTES) {
        message("Native framebuffer unavailable\n\nPress any key");return;
    }
    if(!spectrum_disk_cache_begin(&machine,scratch.pixels+7680)) {
        message("PSRAM I/O error\n\nPress any key");return;
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
    psg.extensions=machine.extensions;psg.events=(const uint8_t*)sound->events;psg.event_capacity=SPECTRUM_SOUND_QUEUE_EVENTS;
    psg.read=(volatile uint32_t*)&sound->read;psg.write=(const volatile uint32_t*)&sound->write;
    psg.produced=(const volatile uint32_t*)&sound->produced;psg.time=&sound->time;
    psg.running=(const volatile uint8_t*)&sound->clock_running;psg.dac=&sound->beeper;
    psg.dc_input=&sound->input;psg.dc_output=&sound->output;psg.recover=spectrum_sound_recover;
    uint32_t audio_mode=services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_PSG_OPEN,0,sizeof(psg),&psg);
    if(!audio_mode)audio_mode=services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_SYNTH_OPEN,0,sizeof(audio),&audio);
    if(!audio_mode) {
        spectrum_sound_end(&machine);(void)spectrum_disk_cache_end(&machine);
        message("Audio stream unavailable\n\nPress any key");return;
    }
    /* A resumed frame may already be partly executed. Account for that
     * time instead of adding a full frame's wait to its remaining work. */
    uint32_t deadline=services->call(MK61_SERVICE_MICROS,0,0,0,NULL)-machine.frame_tstates*2/7,last_frame=machine.frames;
    // The audio device may wait for LCD/I2C while opening. Both virtual
    // clocks start here, after that wait, rather than during its callbacks.
    spectrum_sound_clock(&machine,true);
    const char* error=NULL;
    for(;;) {
        const int c=poll_guest(blocked,&keyboard_deadline,services->call(MK61_SERVICE_MICROS,0,0,0,NULL));
        if(escape(c) || c==0x90) {
            if(c==0x90) started=false;
            break;
        }
        spectrum_run(&machine,2048);
        if(machine.memory && machine.memory->fault) goto memory_error;
        if(machine.frames==last_frame) continue;
        last_frame=machine.frames;
        // Submit the completed frame before its pacing wait, leaving the
        // next frame's first CPU/audio slice free of display conversion.
        {
            uint16_t palette[64];for(unsigned i=0;i<64;++i) palette[i]=spectrum_palette(&machine,i);
            const uint32_t ready=services->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_PALETTE64,0,sizeof(palette),palette);
            if(ready==2) goto paced;
            if(!ready) { error="Update color display service\n\nPress any key";break; }
            spectrum_video8(&machine,scratch.pixels,scratch.pixels+SPECTRUM_BITMAP_BYTES);
            if(machine.memory && machine.memory->fault) goto memory_error;
            frame.background=spectrum_border(&machine);
            const uint32_t result=color(MK61_COLOR_PRESENT,&frame);
            if(!result) { error="Color output failed\n\nPress any key";break; }
        }
paced:
        if(!pace_frame(blocked,&keyboard_deadline,&deadline)) goto done;
    }
    goto done;
memory_error:
    started=false;error="PSRAM I/O error\n\nPress any key";
done:
    spectrum_sound_clock(&machine,false);
    services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_CLOSE,0,0,NULL);
    spectrum_sound_end(&machine);
    if(!spectrum_disk_cache_end(&machine)) { started=false;error="PSRAM I/O error\n\nPress any key"; }
    /* Keep the borrowed canvas owned across the OSD: graphics_end would
     * redraw resident text over the RAM pages stored in its unused tail. */
    color(MK61_COLOR_END,NULL);
    if(error) message(error);
}
static int app_run(uint32_t file_id) {
    /* These paths live for the complete foreground APP session. Keep them
     * in the resident stack reservation instead of enlarging the heap image
     * alongside the 32K/16K guest-memory leases. No I/O outlives main(). */
    char paths[4][256];
    directory=paths[0];snapshot_path=paths[1];floppy.path=paths[2];sd_card.path=paths[3];
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
    mapped_roms=banked_buffers && (mapped_rom[0]=cached_rom(SPECTRUM_ROM_48,"48.rom")) &&
        (mapped_rom[1]=cached_rom(SPECTRUM_ROM_128_0,"128-0.rom")) && (mapped_rom[2]=cached_rom(SPECTRUM_ROM_128_1,"128-1.rom"));
    if(banked_buffers) {
        mk61_service_framebuffer canvas={0};
        if(!mk61_api->graphics_begin() ||
           !services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(canvas),0,&canvas) ||
           !canvas.pixels || canvas.bytes<10240+2*SPECTRUM_CACHE_PAGE_BYTES) {
            message("Native framebuffer unavailable\n\nPress any key");return 0;
        }
        /* UI: 0..9215; running video: 0..7679; disk cache: 7680..9727.
         * RAM pages at 10240 remain valid across both display modes. */
        page_cache=canvas.pixels+10240;
        /* Fixed banks use 15K heap chunks and 1K stack tails. The complete
         * sixteen-page cache uses two further 8K leases. */
        for(unsigned i=0;i<2;++i) {
            if(!mk61_app_buffer_acquire(services,SPECTRUM_BANK_HEAP_BYTES,MK61_BUFFER_DIRECT,&sram[i]) ||
               sram[i].storage!=MK61_BUFFER_SRAM || !sram[i].data) {
                message("Not enough SRAM for Spectrum\n\nPress any key");return 0;
            }
            guest_blocks[i]=sram[i].data;
        }
    }
    if((!banked_buffers && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,SPECTRUM_RAM_BYTES,&ram)) ||
       (mapped_roms && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_WORKSPACE,MK61_SERVICE_OWNER_APP,8192,&ram)) ||
       (mapped_roms && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,8192,&rom)) ||
       (!mapped_roms && !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,SPECTRUM_ROM_BYTES,&rom))) {
        message("Not enough SRAM for Spectrum\n\nPress any key");return 0;
    }
    if(!mapped_roms && !load_rom(rom.data)) {
        message("48.rom (16384 bytes) is required\nnext to SPECTRUM.APP\n\nPress any key");return 0;
    }
    bank_window=mapped_roms?ram.data:NULL;bank_tails[2]=mapped_roms?rom.data:NULL;
    if(!banked_buffers) spectrum_init(&machine,ram.data,rom.data);
    else { memset(&machine,0,sizeof(machine));machine.ram=guest_blocks[0];machine.rom=mapped_roms?mapped_rom[0]:rom.data;
        machine.extensions=SPECTRUM_TURBOSOUND|SPECTRUM_COVOX|SPECTRUM_SPECDRUM|SPECTRUM_ULAPLUS; }
    if(!select_model(true)) {
        if(!select_model(false)) return 0;
    }
    if(file_id!=MK61_SERVICE_INVALID_ID) {
        mk61_service_file_bytes request={NULL,snapshot_path,file_id,256};
        if(!services->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_PATH,0,sizeof(request),&request)) {
            message("Cannot get selected file path\nUpdate PicoCalc firmware\n\nPress any key");
        } else {
            memcpy(directory,snapshot_path,strlen(snapshot_path)+1);parent_directory();
            const bool snapshot=suffix(snapshot_path,".z80") || suffix(snapshot_path,".sna");
            const bool disk=suffix(snapshot_path,".trd") || suffix(snapshot_path,".scl");
            if((snapshot && load_snapshot()) || (disk && mount_selected_media(SPECTRUM_DISK_BETA))) {
                // The Explorer's opening Enter/F-key may still be held.
                // Seed the normal guest-key blocker before starting the CPU.
                const int key=scan_keys();
                if(escape(key) || key==0x90) goto done;
                started=true;emulate();
                if(!started) goto done;
            } else if(!snapshot && !disk) message("Unsupported Spectrum file\n\nPress any key");
        }
    }
#ifdef SPECTRUM_HIL_AFTER_FILE
    SPECTRUM_HIL_AFTER_FILE();
#endif
    for(;;) {
        const char* labels[]={started?"Resume":"Start machine","Snapshot...","Beta Disk...","DivMMC...",
            "Machine...","Options...",machine.disk.mode==SPECTRUM_DISK_DIVMMC?"NMI browser":"TR-DOS","Reset","Help","Exit"};
        const char* hotkeys=machine.disk.mode==SPECTRUM_DISK_DIVMMC?"rodimpnbhqt":"rodimptbhqn";
        const char actions[]={13,'o','d','i','m','p',machine.disk.mode==SPECTRUM_DISK_DIVMMC?'n':'t','b','h','q',machine.disk.mode==SPECTRUM_DISK_DIVMMC?'t':'n'};
        const int choice=menu_pick("Spectrum",labels,10,&root_selected,false,hotkeys);
        const int c=choice<0?'q':actions[choice];
        if(escape(c) || c=='q' || c=='Q' || c==0x90) break;
        if(c=='h' || c=='H') { help();continue; }
        if(c=='p' || c=='P') { settings();continue; }
        if(c=='d' || c=='D') { mount_media(SPECTRUM_DISK_BETA);continue; }
        if(c=='i' || c=='I') { mount_media(SPECTRUM_DISK_DIVMMC);continue; }
        if(c=='m' || c=='M') {
            const char* models[]={"Spectrum 48K","Pentagon 512K","Pentagon 1024K"};unsigned model=machine.pentagon?machine.memory->extended?2:1:0;
            const int picked=menu_pick("Machine",models,3,&model,true,NULL);
            if(picked<0) continue;
            if(!select_model((unsigned)picked)) {
                message("Cannot initialize ROM / PSRAM\n\nPress any key");(void)select_model(false);
            }
            continue;
        }
        if(c=='o' || c=='O') { if(!choose_file(0) || !load_snapshot()) continue; }
        else if((c=='t' || c=='T') && machine.disk.mode==SPECTRUM_DISK_BETA && started) {
            if(machine.pentagon) (void)spectrum_memory_page(machine.memory,machine.memory->paging|16);
            spectrum_refresh_map(&machine);
            machine.cpu.sp-=2;
            machine.cpu.write_byte(&machine,machine.cpu.sp,(uint8_t)machine.cpu.pc);
            machine.cpu.write_byte(&machine,(uint16_t)(machine.cpu.sp+1),(uint8_t)(machine.cpu.pc>>8));
            machine.cpu.pc=15616;machine.cpu.halted=false;
        } else if((c=='n' || c=='N') && machine.disk.mode==SPECTRUM_DISK_DIVMMC && started) z80_gen_nmi(&machine.cpu);
        else if(c=='b' || c=='B' || enter(c)) {
            if(c=='b' || c=='B' || !started) spectrum_reset(&machine);
            started=true;
        } else continue;
        emulate();
        if(!started) break;
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
static int run_app(uint32_t file_id) {
    /* The complete machine lives until audio and display have stopped. Keep
     * it in the resident 32K stack instead of splitting the APP/guest heap. */
    spectrum state={0};uint8_t tails[2][SPECTRUM_CACHE_PAGE_BYTES];active_machine=&state;
    for(unsigned i=0;i<2;++i)bank_tails[i]=tails[i];
    const int result=app_run(file_id);active_machine=NULL;return result;
}
int main(void) { return run_app(MK61_SERVICE_INVALID_ID); }
uint32_t mk61_app_open_file(uint32_t file_id) {
    return file_id>=MK61_SERVICE_INVALID_ID?MK61_APP_INVALID_FILE:(uint32_t)run_app(file_id);
}
