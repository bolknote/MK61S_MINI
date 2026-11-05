#include "../examples/portable-apps/SPECTRUM/rom_cache.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void put32(uint8_t* p,uint32_t value) { for(unsigned i=0;i<4;++i) p[i]=(uint8_t)(value>>(i*8)); }
static void header_crc(uint8_t* p) { put32(p+24,0);put32(p+24,spectrum_crc32(UINT32_MAX,p,256)^UINT32_MAX); }
int main(int argc,char** argv) {
    assert(argc==2);FILE* f=fopen(argv[1],"rb");assert(f);
    uint8_t* original=malloc(SPECTRUM_ROM_CACHE_CAPACITY),*bad=malloc(SPECTRUM_ROM_CACHE_CAPACITY);assert(original && bad);
    memset(original,255,SPECTRUM_ROM_CACHE_CAPACITY);const unsigned used=(unsigned)fread(original,1,SPECTRUM_ROM_CACHE_CAPACITY,f);fclose(f);
    assert(used>70000 && spectrum_rom_cache_valid(original,used));
    assert((spectrum_crc32(UINT32_MAX,(const uint8_t*)"123456789",9)^UINT32_MAX)==0xCBF43926U);
    for(unsigned at=0;at<used;at+=251) {
        memcpy(bad,original,used);bad[at]^=128;
        // Padding beyond the declared pack is deliberately ignored.
        const unsigned size=original[12]|((unsigned)original[13]<<8)|((unsigned)original[14]<<16);
        if(at<size) assert(!spectrum_rom_cache_valid(bad,used));
    }
    const unsigned fields[]={12,32,36,40,44};
    for(unsigned i=0;i<sizeof(fields)/sizeof(*fields);++i) {
        memcpy(bad,original,used);put32(bad+fields[i],UINT32_MAX);header_crc(bad);
        assert(!spectrum_rom_cache_valid(bad,used));
    }
    assert(!spectrum_rom_cache_valid(original,255) && !spectrum_rom_cache_valid(NULL,used));
    memset(bad,255,used);assert(!spectrum_rom_cache_valid(bad,used));
    free(bad);free(original);puts("XIP ROM cache CRC, sizes, offsets, corruption and missing-cache fallback: PASS");return 0;
}
