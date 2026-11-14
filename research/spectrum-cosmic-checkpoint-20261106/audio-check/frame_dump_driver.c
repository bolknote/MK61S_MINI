#include "spectrum.h"
#include "../host_driver.c"
static void pump(void* raw) {
    spectrum* m=raw;const uint32_t available=atomic_load(&m->sound.produced);
    while((int32_t)(available-(m->sound.time+140))>=0)(void)spectrum_sound_render(m);
}
int main(int argc,char** argv) {
    assert(argc==4);host_init("/private/tmp/mk61-spectrum-20261105/downloads","programs/spectrum/GAMES.img");host_disconnect();
    static uint8_t blocks[2][SPECTRUM_BANK_HEAP_BYTES],tails[2][1024],halves[2][8192];
    uint8_t* split[]={tails[0],tails[1],halves[1]};
    assert(spectrum_memory_init_split(&memory,blocks[0],blocks[1],split,halves[0],roms[0],roms[1],(spectrum_memory_io){external,rd,wr,zero}));
    s.ram=blocks[0];spectrum_attach_memory(&s,&memory);
    FILE* f=fopen(argv[1],"rb");assert(f && !fseek(f,0,SEEK_END));unsigned n=(unsigned)ftell(f);rewind(f);
    uint8_t* bytes=malloc(n);assert(bytes && fread(bytes,1,n,f)==n);fclose(f);uint8_t palette[65];load(argv[2],palette,65);
    assert(!host_load_snapshot(bytes,n,palette));free(bytes);host_disconnect();spectrum_sound_begin(&s,pump,&s);
    f=fopen(argv[3],"wb");assert(f);const uint32_t header[]={0x31504653,3100};assert(fwrite(header,1,sizeof(header),f)==sizeof(header));
    uint8_t frame[7808];
    for(uint32_t index=1;index<=3100;++index) {
        host_keys(0,0);if(index>=100 && index<200)host_keys('p',1);
        const uint32_t before=s.frames;
        while(s.frames==before) {assert(spectrum_run(&s,512)<=556);pump(&s);assert(!memory.fault);}
        host_video(frame);const uint16_t border=spectrum_border(&s);
        assert(fwrite(&index,1,4,f)==4 && fwrite(&border,1,2,f)==2 && fwrite(frame,1,sizeof(frame),f)==sizeof(frame));
    }
    assert(!fclose(f));spectrum_sound_end(&s);puts("3100 complete512T capture frames, fixedP100..199; not exact physical HIL input timeline");return 0;
}
