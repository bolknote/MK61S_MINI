#include "rom_cache.h"
#include <string.h>
static uint32_t word(const uint8_t* p) { return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
uint32_t spectrum_crc32(uint32_t crc,const uint8_t* p,unsigned bytes) {
    while(bytes--) {
        crc^=*p++;
        for(unsigned bit=0;bit<8;++bit) crc=(crc>>1)^((crc&1)?0xEDB88320U:0);
    }
    return crc;
}
bool spectrum_rom_cache_valid(const uint8_t* p,unsigned capacity) {
    if(!p || capacity<256 || memcmp(p,"MK61ROM1",8) || word(p+8)!=1 || word(p+16)!=SPECTRUM_ROM_COUNT) return false;
    const uint32_t size=word(p+12);
    if(size<256 || size>capacity) return false;
    uint8_t header[256];memcpy(header,p,256);memset(header+24,0,4);
    if((spectrum_crc32(UINT32_MAX,header,256)^UINT32_MAX)!=word(p+24) ||
       (spectrum_crc32(UINT32_MAX,p+256,size-256)^UINT32_MAX)!=word(p+20)) return false;
    uint32_t expected=256;
    for(unsigned i=0;i<SPECTRUM_ROM_COUNT;++i) {
        const uint8_t* entry=p+32+i*32;
        const unsigned bytes=i==SPECTRUM_ROM_DIV?8192:16384;
        if(word(entry)!=i || word(entry+4)!=expected || word(entry+8)!=bytes || bytes>size-expected) return false;
        if((spectrum_crc32(UINT32_MAX,p+expected,bytes)^UINT32_MAX)!=word(entry+12)) return false;
        expected+=bytes;
    }
    return expected==size;
}
const uint8_t* spectrum_rom_cache_find(unsigned id,uint32_t* crc) {
#if defined(MK61_TARGET_PICOCALC)
    static uint8_t checked;
    const uint8_t* p=(const uint8_t*)SPECTRUM_ROM_CACHE_ADDRESS;
    if(!checked) checked=spectrum_rom_cache_valid(p,SPECTRUM_ROM_CACHE_CAPACITY)?1:2;
    if(checked!=1 || id>=SPECTRUM_ROM_COUNT) return NULL;
    const uint8_t* entry=p+32+id*32;if(crc) *crc=word(entry+12);return p+word(entry+4);
#else
    (void)id;(void)crc;return NULL;
#endif
}
