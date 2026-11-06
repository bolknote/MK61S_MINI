#ifndef MK61_SPECTRUM_MEMORY_H
#define MK61_SPECTRUM_MEMORY_H
#include <stdbool.h>
#include <stdint.h>
#define SPECTRUM_BANK_BYTES 16384U
#define SPECTRUM_FIXED_BYTES 32768U
#define SPECTRUM_CACHE_PAGE_BYTES 1024U
#define SPECTRUM_BANK_HEAP_BYTES (16384U-SPECTRUM_CACHE_PAGE_BYTES)
#define SPECTRUM_CACHE_BYTES (32768U+2*SPECTRUM_CACHE_PAGE_BYTES)
#define SPECTRUM_ROM_BASE (1024U*1024U)
#define SPECTRUM_TRDOS_ROM (SPECTRUM_ROM_BASE+32768U)
#define SPECTRUM_DIV_ROM (SPECTRUM_TRDOS_ROM+16384U)
#define SPECTRUM_DIV_RAM (SPECTRUM_DIV_ROM+8192U)
#define SPECTRUM_EXTERNAL_BYTES (SPECTRUM_DIV_RAM+128U*1024U)
typedef struct {
    void* context;
    bool (*read)(void*,uint32_t,uint8_t*,uint32_t);
    bool (*write)(void*,uint32_t,const uint8_t*,uint32_t);
    bool (*clear)(void*,uint32_t,uint32_t);
} spectrum_memory_io;
typedef struct {
    uint8_t *cache,*fixed2,*fixed_tail[2],*pages,*pages_tail,*window;
    const uint8_t *rom,*rom_banks[2];
    spectrum_memory_io io;
    uint16_t tag[16];
    uint8_t recent,victim,page_count,paging,dummy,banks,control;
    bool dirty[16],fault,overlay,overlay_cached,extended,locked;
    uint32_t loads,writebacks;
} spectrum_memory;
bool spectrum_memory_init(spectrum_memory*,uint8_t cache[SPECTRUM_CACHE_BYTES],uint8_t rom[16384],spectrum_memory_io);
uint8_t* spectrum_memory_byte(spectrum_memory*,uint16_t address,bool writing);
bool spectrum_memory_init_pages(spectrum_memory*,uint8_t fixed[SPECTRUM_FIXED_BYTES],uint8_t pages[2*SPECTRUM_CACHE_PAGE_BYTES],uint8_t rom[16384],spectrum_memory_io);
bool spectrum_memory_init_mapped(spectrum_memory*,uint8_t fixed[SPECTRUM_FIXED_BYTES],uint8_t pages[2*SPECTRUM_CACHE_PAGE_BYTES],uint8_t window[16384],const uint8_t* rom0,const uint8_t* rom1,spectrum_memory_io);
/* Fixed banks keep their final 1K in tails[0..1]. The cache consists of
 * two 8K halves, pages and tails[2], without requiring contiguous SRAM.
 * rom1==NULL selects the two-page cache and writable SD-loaded ROM path. */
bool spectrum_memory_init_split(spectrum_memory*,uint8_t* fixed5,uint8_t* fixed2,uint8_t* tails[3],uint8_t* pages,const uint8_t* rom0,const uint8_t* rom1,spectrum_memory_io);
uint8_t* spectrum_memory_fixed(spectrum_memory*,unsigned bank);
uint8_t* spectrum_memory_mapped(spectrum_memory*,bool writing);
void spectrum_memory_map_pages(spectrum_memory*,const uint8_t* read[64],uint8_t* write[64]);
bool spectrum_memory_flush_pages(spectrum_memory*);
bool spectrum_memory_reset(spectrum_memory*);
bool spectrum_memory_page(spectrum_memory*,uint8_t value);
bool spectrum_memory_control(spectrum_memory*,uint8_t value);
bool spectrum_bank_read(spectrum_memory*,unsigned bank,unsigned offset,uint8_t*,unsigned bytes);
bool spectrum_bank_write(spectrum_memory*,unsigned bank,unsigned offset,const uint8_t*,unsigned bytes);
#endif
