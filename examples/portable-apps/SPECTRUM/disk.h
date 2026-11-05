#ifndef MK61_SPECTRUM_DISK_H
#define MK61_SPECTRUM_DISK_H
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    void* context;
    uint32_t bytes;
    bool (*read)(void*,uint32_t,uint8_t*,uint32_t);
    bool (*write)(void*,uint32_t,const uint8_t*,uint32_t);
    bool readonly;
    uint8_t tracks,heads;
} spectrum_disk_io;
typedef struct {
    spectrum_disk_io io;
    uint8_t command,status,track,sector,data,system,head,direction;
    uint8_t buffer[256],id[6];
    uint16_t cursor,length,format_cursor,format_bytes,format_crc;
    uint8_t format_state,format_id[4];
    uint32_t due,drq_due;
    bool busy,drq,irq,type1,multiple,writing;
} spectrum_fdc;
void spectrum_fdc_reset(spectrum_fdc*);
uint8_t spectrum_fdc_read(spectrum_fdc*,uint8_t port,uint32_t time);
void spectrum_fdc_write(spectrum_fdc*,uint8_t port,uint8_t value,uint32_t time);

typedef struct {
    spectrum_disk_io io;
    uint8_t command[6],command_size,response[24],response_size,response_at;
    uint8_t block[512],control;
    uint16_t cursor,crc;
    uint32_t lba,erase_first,erase_last;
    uint8_t data_mode,write_mode,write_state,crc_bytes,write_token;
    bool idle,app_command,high_capacity,crc_enabled,selected;
    uint32_t reads,writes;
} spectrum_spi;
void spectrum_spi_reset(spectrum_spi*);
void spectrum_spi_select(spectrum_spi*,uint8_t value);
uint8_t spectrum_spi_transfer(spectrum_spi*,uint8_t value);
uint16_t spectrum_crc16(uint16_t crc,uint8_t byte);
enum { SPECTRUM_DISK_NONE,SPECTRUM_DISK_BETA,SPECTRUM_DISK_DIVMMC };
#define SPECTRUM_DISK_CACHE_BYTES 2048U
typedef struct {
    spectrum_fdc fdc;
    spectrum_spi spi;
    uint8_t mode,control,loaded_control,spi_data;
    bool mapped,automap,dirty;
    uint8_t* cache;
    uint16_t tag[2];
    uint8_t recent;
    bool cache_dirty[2];
    const uint8_t* xip_rom[3];
} spectrum_disk;
struct spectrum;
bool spectrum_disk_mode(struct spectrum*,unsigned mode);
void spectrum_disk_reset(struct spectrum*);
bool spectrum_disk_snapshot(struct spectrum*);
bool spectrum_disk_cache_begin(struct spectrum*,uint8_t cache[SPECTRUM_DISK_CACHE_BYTES]);
bool spectrum_disk_cache_end(struct spectrum*);
uint8_t spectrum_disk_read_memory(struct spectrum*,uint16_t);
void spectrum_disk_m1(void*,uint16_t,bool);
void spectrum_disk_filter(struct spectrum*);
void spectrum_disk_write_memory(struct spectrum*,uint16_t,uint8_t);
bool spectrum_disk_in(struct spectrum*,uint16_t,uint8_t*);
bool spectrum_disk_out(struct spectrum*,uint16_t,uint8_t);
#endif
