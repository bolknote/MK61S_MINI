/* Finite Classic/M4 diagnostic. The embedded kernel is the exact M3 binary;
 * no UART, audio output, Flash, CPU clock or calculator-state writes. */
#include "mk61_app.h"
#include "stm3_module.h"
#include "module_image.h"
#include "sound_vectors.h"
#include "spectrum_m3_probe_input.h"
#include <string.h>

static const mk61_app_services* services;
static uint8_t input[512],output[512];
static stm3_entry kernel;
static char result_text[1536];
static unsigned result_used;
#define REG32(p) (*(volatile uint32_t*)(uintptr_t)(p))
#define DEMCR REG32(0xe000edfcu)
#define DWT_CTRL REG32(0xe0001000u)
#define DWT_CYCLES REG32(0xe0001004u)
static void line(const char* p) {
    unsigned length=(unsigned)strlen(p);
    if(length<=sizeof(result_text)-result_used){memcpy(result_text+result_used,p,length);result_used+=length;}
    if(!(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL)&MK61_SERVICE_CAP_DEBUG_IO))return;
    while(*p){unsigned n=(unsigned)strlen(p);if(n>128)n=128;services->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void*)p);p+=n;}
}
static int read_result(void* unused,uint32_t offset,uint8_t* out,uint32_t n) {
    (void)unused;if(offset>result_used || n>result_used-offset)return 0;
    memcpy(out,result_text+offset,n);return 1;
}
static uint32_t crc(uint32_t value,const uint8_t* bytes,unsigned n) {
    while(n--){value^=*bytes++;for(unsigned i=0;i<8;++i)value=(value>>1)^(0xedb88320u&(0u-(value&1)));}return value;
}
static int relocate(void) {
    const uint32_t base=(uint32_t)(uintptr_t)sound_module_image;
    for(unsigned i=0;i<SOUND_RELOCATIONS;++i) {
        unsigned at=sound_module_relocations[i];uint32_t value;
        if((at&3) || at>SOUND_IMAGE_BYTES-4)return 0;
        memcpy(&value,sound_module_image+at,4);
        if(value<0x20000000u || value-0x20000000u>SOUND_MEMORY_BYTES)return 0;
    }
    for(unsigned i=0;i<SOUND_RELOCATIONS;++i) {
        unsigned at=sound_module_relocations[i];uint32_t value;memcpy(&value,sound_module_image+at,4);
        value=base+(value-0x20000000u);memcpy(sound_module_image+at,&value,4);
    }
    kernel=(stm3_entry)(uintptr_t)(base+SOUND_ENTRY_OFFSET);
    __asm volatile("dsb\nisb":::"memory");return 1;
}
static int run(void) {
    static const char*const names[]={"TONE3","TURBO_ENV_NOISE","DAC_DENSE"};
    /* No timer callback: DWT surrounds the complete render job externally.
     * Only integer/pointer arguments cross the M4-hard/M3-soft ABI boundary. */
    const stm3_api api={STM3_ABI,sizeof(stm3_api),NULL,NULL};
    for(unsigned mode=0;mode<3;++mode) {
        stm3_job job={sound_configs[mode],sizeof(sound_configs[mode]),output,sizeof(output),0,0};
        if(kernel(STM3_INIT,&api,&job)!=STM3_DONE)return -1;
        uint64_t cycles=0;uint32_t maximum=0,digest=~0u;
        const uint32_t begin_ms=mk61_api->millis_ms();
        for(unsigned block=0;block<M3_SOUND_BLOCKS;++block) {
            const unsigned n=m3_sound_probe_packet(mode,block,input);
            job=(stm3_job){input,n,output,sizeof(output),0,0};
            const uint32_t begin=DWT_CYCLES;
            uint32_t result=kernel(STM3_INIT,&api,&job);
            for(unsigned turns=0;result==STM3_MORE && turns<8;++turns)result=kernel(STM3_STEP,&api,&job);
            const uint32_t elapsed=DWT_CYCLES-begin;
            if(result!=STM3_DONE || job.output_bytes!=M3_SOUND_OUTPUT_BYTES)return -2;
            cycles+=elapsed;if(elapsed>maximum)maximum=elapsed;
            digest=crc(digest,output,job.output_bytes);
            if(mk61_api->key_poll()==MK61_APP_KEY_ESC)return -3;
            mk61_api->service();
        }
        const uint32_t wall=mk61_api->millis_ms()-begin_ms;
        if((~digest)!=sound_expected_crc[mode])return -4;
        char text[224];mk61_app_snprintf(services,text,sizeof(text),
            "S3BENCH mode=%s samples=%u cycles_lo=%lu cycles_hi=%lu max_block_cycles=%lu wall_ms=%lu pcm_crc=%08lX\n",
            names[mode],M3_SOUND_BLOCKS*M3_SOUND_FRAMES,(unsigned long)cycles,(unsigned long)(cycles>>32),
            (unsigned long)maximum,(unsigned long)wall,(unsigned long)(~digest));line(text);
    }
    stm3_job job={input,0,output,sizeof(output),0,0};return kernel(STM3_FINI,&api,&job)==STM3_DONE?0:-5;
}
static int benchmark(void) {
    if(((REG32(0xe000ed00u)>>4)&0xfffu)!=0xc24u || !relocate()) {
        line("S3BENCH FAIL target_or_relocation\n");return -7;
    }
    const uint32_t saved_demcr=DEMCR,saved_control=DWT_CTRL;
    DEMCR|=1u<<24;DWT_CTRL|=1;
    __asm volatile("dsb\nisb":::"memory");
    const uint32_t first=DWT_CYCLES;for(volatile unsigned i=0;i<32;++i)__asm volatile("nop");
    int result=-6;
    if(DWT_CYCLES!=first) {
        line("S3BENCH BEGIN host=M4 kernel_isa=M3 physical_uart=0 clock_change=0 timer_callback=0\n");
        line("S3BENCH module_sha256=" SOUND_MODULE_SHA256 "\n");
        char clock[128];mk61_app_snprintf(services,clock,sizeof(clock),
            "S3BENCH RCC cr=%08lX pll=%08lX cfgr=%08lX\n",(unsigned long)REG32(0x40023800u),
            (unsigned long)REG32(0x40023804u),(unsigned long)REG32(0x40023808u));line(clock);
        result=run();
        mk61_app_snprintf(services,clock,sizeof(clock),
            "S3BENCH RCC_END cr=%08lX pll=%08lX cfgr=%08lX\n",(unsigned long)REG32(0x40023800u),
            (unsigned long)REG32(0x40023804u),(unsigned long)REG32(0x40023808u));line(clock);
    }
    if(!(saved_control&1u))DWT_CTRL&=~1u;
    if(!(saved_demcr&(1u<<24)))DEMCR&=~(1u<<24);
    return result;
}
int main(void) {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_FILE_WRITE_SOURCE);
    if(!services)return MK61_APP_RUNTIME_ERROR;
    const int result=benchmark();
    char text[80];mk61_app_snprintf(services,text,sizeof(text),"S3BENCH END result=%d\n",result);line(text);
    mk61_service_write_source file={SOUND_RESULT_NAME,NULL,read_result,result_used,MK61_SERVICE_INVALID_ID};
    const int saved=mk61_app_file_write_source(services,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)!=0;
    mk61_api->display_clear();
    const char* label=result || !saved?"M3 benchmark FAIL":"M3 benchmark PASS";
    mk61_api->display_write_m8(0,0,label,(uint32_t)strlen(label));
    return MK61_APP_OK;
}
