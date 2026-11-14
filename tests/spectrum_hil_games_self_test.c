#include <stdint.h>
static uint32_t test_clock;
#define SPECTRUM_HIL_CLOCK() test_clock
#define main probe_app_main
#include "spectrum_hil_games.c"
#undef main
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>

static uint8_t test_ram[49152],test_rom[16384],canvas[12800],palette_state[65];
static spectrum test_machine;
static char output[32768],path_buffer[256];
static unsigned used;
static bool display_available,read_fails;
const mk61_app_api* mk61_api;

static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
    if(op==MK61_SERVICE_DISPLAY) {
        if(!display_available) return 0;
        assert(a==MK61_SERVICE_DISPLAY_FRAMEBUFFER);
        mk61_service_framebuffer* out=payload;out->pixels=canvas;out->bytes=sizeof(canvas);return 1;
    }
    if(op==MK61_SERVICE_FILE_BYTES) {
        assert(a==MK61_FILE_BYTES_READ && !b && c==sizeof(mk61_service_file_bytes));
        mk61_service_file_bytes* r=payload;
        assert(!strcmp(r->path,"SPMN.ULP") && r->offset==0 && r->size==65);
        if(read_fails) return 0;
        memcpy(r->data,palette_state,65);return 1;
    }
    assert(op==MK61_SERVICE_DEBUG_WRITE && !b && !c && a<=128 && used+a<sizeof(output));
    memcpy(output+used,payload,a);used+=a;output[used]=0;return a;
}
static int format(char* out,uint32_t n,const char* f,va_list args) { return vsnprintf(out,n,f,args); }
static const mk61_app_services fake={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,call,NULL,format,NULL};
static bool source_read_test(void* context,uint32_t at,uint8_t* out,uint32_t n) { memcpy(out,(uint8_t*)context+at,n);return true; }

static void clock_test(uint32_t clock_start,unsigned long cycle_start) {
    spectrum_init(&machine,test_ram,test_rom);machine.cpu.cyc=cycle_start;
    used=0;test_clock=clock_start;observed_begin(&machine,NULL,NULL);test_clock+=300000;
    const uint32_t first=test_clock;
    for(unsigned frame=1;frame<=301;++frame) {
        test_clock=first+(frame-1)*20480U;
        machine.frames=frame;machine.frame_tstates=100;machine.cpu.cyc=cycle_start+frame*71680UL+100;
        atomic_store(&machine.sound.starved,frame==1?1:21);
        assert(observed_run(&machine,0)==0);test_clock+=500;assert(observed_run(&machine,0)==0);
    }
    test_clock=first+300*20480U+400000;observed_end(&machine);
    assert(strstr(output,"SPSTEADY frames=300 cycles=21504000 wall=6144000 phase=100/100 starved=20\n"));
    assert(strstr(output,"wall=6844000 rom_psram="));
}
static void palette_test(void) {
    static uint8_t snapshot[49182];snapshot[6]=0x00;snapshot[7]=0x80;
    spectrum_source source={snapshot,sizeof(snapshot),source_read_test};
    strcpy(path_buffer,"SPMN.Z80");snapshot_path=path_buffer;
    palette_state[0]=1;for(unsigned i=1;i<65;++i)palette_state[i]=(uint8_t)(i*3);
    assert(observed_load(&machine,&source)==SPECTRUM_OK);
    assert(machine.cpu.pc==0x8000 && machine.ulaplus_mode==1 && !memcmp(machine.ulaplus_palette,palette_state+1,64));
    palette_state[0]=2;assert(observed_load(&machine,&source)==SPECTRUM_FORMAT);
    palette_state[0]=0;read_fails=true;assert(observed_load(&machine,&source)==SPECTRUM_IO);read_fails=false;
    machine.disk.mode=SPECTRUM_DISK_DIVMMC;
    assert(observed_load(&machine,&source)==SPECTRUM_UNSUPPORTED);machine.disk.mode=0;
}
static void framebuffer_test(const char* destination) {
    spectrum_init(&machine,test_ram,test_rom);used=0;display_available=true;
    for(unsigned i=0;i<6912;++i)test_ram[i]=(uint8_t)(i*13+i/97);
    observed_begin(&machine,NULL,NULL);observed_end(&machine);
    unsigned offset=0,lines=0;char* cursor=output;
    while((cursor=strstr(cursor,"SPDATA "))!=NULL) {
        unsigned at;assert(sscanf(cursor+7,"%4X",&at)==1 && at==offset);cursor+=12;
        for(unsigned i=0;i<32;++i) { unsigned byte;assert(sscanf(cursor+2*i,"%2X",&byte)==1 && byte==canvas[offset++]); }
        assert(cursor[64]=='\n');++lines;cursor+=65;
    }
    assert(lines==244 && offset==7808);
    FILE* file=fopen(destination,"wb");assert(file);assert(fwrite(output,1,used,file)==used);assert(!fclose(file));
}
int main(int argc,char** argv) {
    assert(argc==2);services=&fake;active_machine=&test_machine;
    clock_test(1000000,0);clock_test(UINT32_MAX-200000,UINT32_MAX-40000UL);
    palette_test();framebuffer_test(argv[1]);
    puts("Actual game probe: steady timing/wrap, palette restoration/errors, no disk mounts and exact full-frame wire bytes PASS");
}
