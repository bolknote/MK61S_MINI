/* Optional local snapshot benchmark. No game/ROM data is embedded or fetched. */
#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include "../sdk/coproc/pcm_repeat.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint8_t ram[49152],fixed[32768],pages[2048],window[16384],rom[2][16384],external[SPECTRUM_EXTERNAL_BYTES];
static spectrum machine;
static spectrum_memory memory;
typedef struct {uint8_t* bytes;unsigned size;} source_image;
static bool image_read(void* raw,uint32_t at,uint8_t* out,uint32_t n){source_image* s=raw;if(at>s->size || n>s->size-at)return false;memcpy(out,s->bytes+at,n);return true;}
static bool mem_read(void* unused,uint32_t at,uint8_t* out,uint32_t n){(void)unused;if(at>sizeof(external)||n>sizeof(external)-at)return false;memcpy(out,external+at,n);return true;}
static bool mem_write(void* unused,uint32_t at,const uint8_t* in,uint32_t n){(void)unused;if(at>sizeof(external)||n>sizeof(external)-at)return false;memcpy(external+at,in,n);return true;}
static bool mem_clear(void* unused,uint32_t at,uint32_t n){(void)unused;if(at>sizeof(external)||n>sizeof(external)-at)return false;memset(external+at,0,n);return true;}
static source_image load(const char* path){FILE* f=fopen(path,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0 && n<2000000);rewind(f);source_image s={malloc((size_t)n),(unsigned)n};assert(s.bytes && fread(s.bytes,1,s.size,f)==s.size);assert(!fclose(f));return s;}
static uint32_t crc_byte(uint32_t crc,uint8_t byte){crc^=byte;for(unsigned bit=0;bit<8;++bit)crc=(crc>>1)^((crc&1)?0xedb88320u:0);return crc;}
int main(int argc,char** argv) {
    assert(argc==4 || argc==5);FILE* detail=argc==5?fopen(argv[4],"w"):NULL;if(argc==5)assert(detail);source_image snapshot=load(argv[1]);
    for(unsigned i=0;i<2;++i){source_image r=load(argv[2+i]);assert(r.size==16384);memcpy(rom[i],r.bytes,16384);free(r.bytes);}
    const unsigned chips[]={0,1,0,1},layouts[]={1,2,2,1},frames[]={1500,1500,600,600};
    for(unsigned test=0;test<4;++test) {
        memset(external,0,sizeof(external));memset(&machine,0,sizeof(machine));
        spectrum_init(&machine,ram,rom[0]);spectrum_memory_io io={NULL,mem_read,mem_write,mem_clear};
        assert(spectrum_memory_init_mapped(&memory,fixed,pages,window,rom[0],rom[1],io));
        spectrum_attach_memory(&machine,&memory);machine.pentagon=true;machine.extensions=15;
        spectrum_source input={&snapshot,snapshot.size,image_read};assert(spectrum_load_z80(&machine,&input)==SPECTRUM_OK);
        spectrum_sound_configure(&machine,chips[test],layouts[test]);spectrum_sound_begin(&machine,NULL,NULL);
        uint8_t raw[236],coded[236];unsigned used=0,blocks=0,packed=0,min_bytes=236,max_bytes=0;uint64_t packed_bytes=0;uint32_t crc=~0u;
        while(machine.frames<frames[test]) {
            spectrum_run(&machine,2048);spectrum_sound_publish(&machine);assert(!memory.fault);
            while((int32_t)(atomic_load(&machine.sound.produced)-machine.sound.time)>=140) {
                const uint32_t sample=spectrum_sound_render(&machine);
                raw[2*used]=(uint8_t)(128+(int16_t)sample/512);
                raw[2*used+1]=(uint8_t)(128+(int16_t)(sample>>16)/512);
                if(++used!=118)continue;
                unsigned n=stm3_pcm_repeat_encode(coded,raw,118);assert(n<=236);
                if(n && n<236) {
                    const uint8_t* cursor=coded;stm3_pcm_repeat_state previous={0x8080,0};
                    for(unsigned i=0;i<118;++i){assert(stm3_pcm_repeat_next(&cursor,coded+n,&previous));assert((uint8_t)previous.previous==raw[2*i] && (uint8_t)(previous.previous>>8)==raw[2*i+1]);}
                    assert(cursor==coded+n && !previous.remaining);++packed;
                } else n=236;
                for(unsigned i=0;i<236;++i)crc=crc_byte(crc,raw[i]);
                if(n<min_bytes)min_bytes=n;if(n>max_bytes)max_bytes=n;
                packed_bytes+=34+n;++blocks;if(detail)fprintf(detail,"%u,%u,%u\n",test,blocks,n);used=0;
            }
        }
        assert(!atomic_load(&machine.sound.starved));
        printf("{\"chip\":\"%s\",\"layout\":\"%s\",\"guest_frames\":%u,\"audio_frames\":%u,\"blocks\":%u,\"packed_blocks\":%u,\"raw_stream_wire_bytes\":%llu,\"packed_stream_wire_bytes\":%llu,\"payload_min\":%u,\"payload_max\":%u,\"PCM_CRC32\":\"%08X\",\"physical_hardware\":false}\n",
            chips[test]?"YM":"AY",layouts[test]==1?"ABC":"ACB",frames[test],blocks*118,blocks,packed,
            (unsigned long long)blocks*270,(unsigned long long)packed_bytes,min_bytes,max_bytes,~crc);
        spectrum_sound_end(&machine);
    }
    if(detail)assert(!fclose(detail));
    free(snapshot.bytes);
}
