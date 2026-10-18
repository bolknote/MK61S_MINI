/* Physical RP2040 contract checks through the ordinary public APP ABI. */
#include "mk61_app.h"
#include "fmk_font.hpp"
#include "prepared_font.hpp"
#include <stdint.h>
#include <string.h>
#ifndef PICO_SOFTWARE_ROOT
#define PICO_SOFTWARE_ROOT "/MK61S-SOFTWARE"
#endif
#ifndef PICO_SOFTWARE_FONT_ITEM
#define PICO_SOFTWARE_FONT_ITEM "DejaVu-12"
#endif
static uint8_t prepared[prepared_font::MAX_IMAGE_SIZE];
static const mk61_app_services* services;
static void log(const char* value) {
    services->call(MK61_SERVICE_DEBUG_WRITE,(uint32_t)strlen(value),0,0,(void*)value);
}
static bool resolve(const char* path,uint32_t type,mk61_service_file& file) {
    return services->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,type,
        (uint32_t)(uintptr_t)path,&file)==0;
}
int main() {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_RESOURCES|MK61_SERVICE_CAP_UI_FONT|MK61_SERVICE_CAP_SETUP);
    if(!services) return 1;
    mk61_service_file source{};
    if(!resolve(PICO_SOFTWARE_ROOT "/stamp.txt",MK61_SERVICE_FILE_TEXT,source)) return 2;
    uint32_t stamp=0;
    if(!services->call(MK61_SERVICE_RESOURCE_READ,6,source.id,0,&stamp)) return 3;
    uint8_t bytes[6]{};
    mk61_service_resource request{stamp,(uint16_t)source.id,0,bytes,6,2};
    if(!services->call(MK61_SERVICE_RESOURCE_READ,5,0,0,&request) || memcmp(bytes,"abcdef",6)) return 4;
    const uint32_t revision=services->call(MK61_SERVICE_RESOURCE_READ,4,0,0,0);
    mk61_service_write unrelated{"unrelated",bytes,6,MK61_SERVICE_INVALID_ID};
    if(!services->call(MK61_SERVICE_FILE_WRITE,source.parent,MK61_SERVICE_INVALID_ID,
        MK61_SERVICE_FILE_TEXT,&unrelated)) return 5;
    uint32_t next=0;
    if(!services->call(MK61_SERVICE_RESOURCE_READ,6,source.id,0,&next) || next!=stamp ||
       !services->call(MK61_SERVICE_RESOURCE_READ,5,0,0,&request)) return 6;
    request.reserved=1;request.revision=revision;
    if(services->call(MK61_SERVICE_RESOURCE_READ,5,0,0,&request)) return 7;
    const uint8_t changed[]="ABCDEF";
    mk61_service_write replacement{"stamp",changed,6,source.id};
    if(!services->call(MK61_SERVICE_FILE_WRITE,source.parent,source.id,
        MK61_SERVICE_FILE_TEXT,&replacement)) return 8;
    request.reserved=2;request.revision=stamp;
    if(services->call(MK61_SERVICE_RESOURCE_READ,5,0,0,&request) ||
       !services->call(MK61_SERVICE_RESOURCE_READ,6,source.id,0,&next) || next==stamp) return 9;
    if(!services->call(MK61_SERVICE_FILE_REMOVE,unrelated.id,0,0,nullptr)) return 10;
    log("PICO SOFTWARE RESOURCE STAMPS PASS\n");
    const uint32_t original=services->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_CURRENT,0,0,nullptr);
    const uint32_t count=services->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_COUNT,0,0,nullptr);
    mk61_setup_ui_font_item selected{};bool found=false;
    for(uint32_t i=0;i<count;++i) {
        mk61_setup_ui_font_item item{};
        if(!services->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_ITEM,i,0,&item)) return 11;
        if(!strcmp(item.name,PICO_SOFTWARE_FONT_ITEM)) { selected=item;found=true; }
    }
    if(!found || !services->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_APPLY_ITEM,selected.key,0,nullptr)) return 12;
    mk61_service_ui_font_info info{};
    if(!services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_INFO,0,sizeof(info),&info) ||
       info.family!=3 || info.size!=12) return 13;
    mk61_service_ui_glyph glyph{};glyph.family=info.family;glyph.size=info.size;
    if(!services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_GLYPH,0x416,sizeof(glyph),&glyph) || !glyph.width) return 14;
    mk61_setup_ui_font_source font{};
    if(!services->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_SOURCE,selected.key,0,&font)) return 15;
    const fmk::ReadSource reader{&font,mk61_api->file_size(font.id),
        [](void* raw,usize offset,uint8_t* out,usize count) {
            return mk61_api->file_read(((mk61_setup_ui_font_source*)raw)->id,offset,out,count)==count;
        }};
    usize size=0;
    if(!fmk::prepare(reader,prepared,sizeof(prepared),size)) return 16;
    mk61_setup_prepared_font install{prepared,(uint32_t)size,font.id,selected.key,
        MK61_PREPARED_FONT_UI,12,MK61_PREPARED_FONT_PERSIST|MK61_PREPARED_FONT_SELECT_UI,0};
    if((int32_t)services->call(MK61_SERVICE_SETUP,MK61_SETUP_PREPARED_FONT_INSTALL,0,0,&install)!=MK61_TEXT_FONT_OK) return 17;
    const uint8_t gap=prepared[8];prepared[8]=5;
    uint16_t crc=prepared_font::checksum(prepared,size);prepared[18]=(uint8_t)crc;prepared[19]=(uint8_t)(crc>>8);
    if((int32_t)services->call(MK61_SERVICE_SETUP,MK61_SETUP_PREPARED_FONT_INSTALL,0,0,&install)!=MK61_TEXT_FONT_INVALID) return 21;
    prepared[8]=gap;crc=prepared_font::checksum(prepared,size);prepared[18]=(uint8_t)crc;prepared[19]=(uint8_t)(crc>>8);
    prepared[size-1]^=1;
    if((int32_t)services->call(MK61_SERVICE_SETUP,MK61_SETUP_PREPARED_FONT_INSTALL,0,0,&install)!=MK61_TEXT_FONT_INVALID) return 18;
    if(!services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_INFO,0,sizeof(info),&info) || info.family!=3) return 19;
    if(!services->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_APPLY_ITEM,original,0,nullptr)) return 20;
    log("PICO SOFTWARE UI FONT CATALOG/GLYPHS/PREPARED/CRC/RESTORE PASS\n");
    log("PICO SOFTWARE APP PASS\n");return 0;
}
