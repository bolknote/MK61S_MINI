#include "../examples/portable-apps/SPECTRUM/m3_audio_protocol.h"
#include "spectrum_m3_probe_input.h"
#include "stm3_module.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
uint32_t module_entry(uint32_t,const stm3_api*,stm3_job*);
static const stm3_api api={STM3_ABI,sizeof(stm3_api),NULL,NULL};
static uint32_t crc(uint32_t v,const uint8_t* p,unsigned n) {
    while(n--){v^=*p++;for(unsigned i=0;i<8;++i)v=(v>>1)^(0xedb88320u&(0u-(v&1)));}return v;
}
int main(void) {
    uint8_t configs[3][SPECTRUM_M3_STATE_BYTES],input[512],out[512];uint32_t hashes[3];
    for(unsigned mode=0;mode<3;++mode) {
        PSG chip;memset(&chip,0,sizeof(chip));chip.quality=1;chip.rate=25000;PSG_setVolumeMode(&chip,2);PSG_setClock(&chip,1750000);PSG_reset(&chip);
        const uint8_t regs[14]={0xa2,1,0x4c,1,0x17,1,1,0x38,15,13,10,128,0,10};
        for(unsigned i=0;i<14;++i)PSG_writeReg(&chip,i,regs[i]);
        if(mode==1){PSG_writeReg(&chip,7,0);for(unsigned i=8;i<=10;++i)PSG_writeReg(&chip,i,16);PSG_writeReg(&chip,11,0);}
        if(mode==2)for(unsigned i=8;i<=10;++i)PSG_writeReg(&chip,i,0);
        uint8_t* cfg=configs[mode];memset(cfg,0,SPECTRUM_M3_STATE_BYTES);spectrum_m3_put32(cfg,SPECTRUM_M3_AUDIO_MAGIC);
#if defined(S3_SOUND_PWM8) && S3_SOUND_PWM8
        cfg[5]=1;cfg[6]=(uint8_t)1000;cfg[7]=1000>>8;
#endif
        for(unsigned i=0;i<2;++i)memcpy(cfg+8+i*SPECTRUM_M3_PSG_BYTES,(uint8_t*)&chip+offsetof(PSG,reg),SPECTRUM_M3_PSG_BYTES);
        cfg[SPECTRUM_M3_STATE_BYTES-2]=cfg[SPECTRUM_M3_STATE_BYTES-1]=128;
        stm3_job j={cfg,SPECTRUM_M3_STATE_BYTES,out,512,0,0};assert(module_entry(STM3_INIT,&api,&j)==STM3_DONE);
        uint32_t digest=~0u;
        for(unsigned b=0;b<M3_SOUND_BLOCKS;++b) {
            const unsigned n=m3_sound_probe_packet(mode,b,input);j=(stm3_job){input,n,out,512,0,0};
            uint32_t state=module_entry(STM3_INIT,&api,&j);while(state==STM3_MORE)state=module_entry(STM3_STEP,&api,&j);
            assert(state==STM3_DONE && j.output_bytes==M3_SOUND_OUTPUT_BYTES);digest=crc(digest,out,j.output_bytes);
        }
        hashes[mode]=~digest;
    }
    printf("static const unsigned char sound_configs[3][%u]={\n",(unsigned)SPECTRUM_M3_STATE_BYTES);
    for(unsigned mode=0;mode<3;++mode){putchar('{');for(unsigned i=0;i<SPECTRUM_M3_STATE_BYTES;++i)printf("%u,",configs[mode][i]);puts("},");}puts("};");
    printf("static const unsigned long sound_expected_crc[3]={0x%08lx,0x%08lx,0x%08lx};\n",(unsigned long)hashes[0],(unsigned long)hashes[1],(unsigned long)hashes[2]);
    return 0;
}
