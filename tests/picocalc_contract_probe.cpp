#include "mk61_app.h"
#include "mk8_literal.hpp"
#include <stdint.h>
#include <string.h>
#ifndef PICO_CONTRACT_ROOT
#define PICO_CONTRACT_ROOT "/MK61S-CONTRACT"
#endif
static const mk61_app_services* s;
static void log(const char* text) { s->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text); }
#define CHECK(test) do { if(!(test)) { char line[80];mk61_app_snprintf(s,line,sizeof(line),"CONTRACT FAIL %u\n",(unsigned)__LINE__);log(line);return __LINE__; } } while(0)
static uint32_t display(uint32_t op,uint32_t b=0,uint32_t c=0,void* p=nullptr) { return s->call(MK61_SERVICE_DISPLAY,op,b,c,p); }
static uint32_t key(uint32_t op,uint32_t value=0) { return s->call(MK61_SERVICE_KEYBOARD,op,value,0,nullptr); }
static uint32_t hook(uint32_t op,mk61_service_edit_hook*) { return op==MK61_EDIT_INSERT?(uint32_t)(uintptr_t)M8("КЛЮЧ"):0; }
int main() {
    s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_SETUP|MK61_SERVICE_CAP_RESOURCES);
    if(!s) return 1;
    mk61_service_lease pressure[2]{};
    // Heap shape depends on preceding APP/font use. Keep a measured lease
    // alive, then force a request larger than the entire linked heap.
    uint32_t pressure_bytes=32768,allocated0=0;
    while(pressure_bytes>=8192 && !(allocated0=s->call(MK61_SERVICE_MEMORY_ACQUIRE,0,0,pressure_bytes,&pressure[0]))) pressure_bytes/=2;
    CHECK(allocated0 && pressure_bytes>=8192);
    const uint32_t allocated1=s->call(MK61_SERVICE_MEMORY_ACQUIRE,1,0,65535,&pressure[1]);
    CHECK(!allocated1);
    { char line[64];mk61_app_snprintf(s,line,sizeof(line),"CONTRACT PRESSURE_BYTES=%u\n",pressure_bytes);log(line); }
    mk61_service_file large{};uint8_t last[3]{};
    CHECK(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_TEXT,
        (uint32_t)(uintptr_t)(PICO_CONTRACT_ROOT "/large.txt"),&large)==0);
    CHECK(large.size==65534 && mk61_api->file_size(large.id)==65534);
    CHECK(mk61_api->file_read(large.id,65532,last,3)==2 && last[0]==0xC6 && last[1]==0xC6);
    CHECK(mk61_api->file_read(large.id,511,last,3)==3 && last[0]==0xC6 && last[2]==0xC6);
    if(allocated0) CHECK(s->call(MK61_SERVICE_MEMORY_RELEASE,0,0,0,&pressure[0]));
    if(allocated1) CHECK(s->call(MK61_SERVICE_MEMORY_RELEASE,1,0,0,&pressure[1]));
    CHECK(s->call(MK61_SERVICE_MEMORY_ACQUIRE,0,0,64,&pressure[0]));
    CHECK(s->call(MK61_SERVICE_MEMORY_RELEASE,0,0,0,&pressure[0]));
    log("CONTRACT LARGE TEXT/EXHAUSTED MEMORY RECOVERY PASS\n");
    // Read-only oracle from RP2040 PWM CH5 CC/TOP (Pico SDK register map).
    volatile const uint32_t* const cc=(volatile const uint32_t*)0x40050070;
    volatile const uint32_t* const top=(volatile const uint32_t*)0x40050074;
    const uint32_t volume=s->call(MK61_SERVICE_SETTINGS,MK61_SERVICE_VOLUME,0,0,nullptr);
    CHECK(mk61_api->beep(2000,100,100));
    const uint32_t loud=*cc&65535,wrap=*top+1;
    CHECK(loud==(wrap*volume*100+2000)/4000);
    CHECK(mk61_api->beep(2000,80,25));
    CHECK((*cc&65535)==(volume?(wrap*volume*25+2000)/4000:0));
    CHECK(!mk61_api->beep(2000,0,100) && !mk61_api->beep(65536,100,100));
    mk61_api->delay_ms(120);CHECK(!*cc);
    CHECK(mk61_api->beep(440,100,0) && !*cc);
    mk61_api->sound_stop();log("CONTRACT PWM MASTER/PERCENT/DURATION PASS\n");
    const uint32_t started=s->call(MK61_SERVICE_MICROS,0,0,0,nullptr);
    CHECK(mk61_api->led_blink(1,300,0));
    CHECK(s->call(MK61_SERVICE_MICROS,0,0,0,nullptr)-started<100000);
    CHECK(*(volatile const uint32_t*)0xD0000010&(1u<<25));
    mk61_api->delay_ms(350);CHECK(!(*(volatile const uint32_t*)0xD0000010&(1u<<25)));
    CHECK(!mk61_api->led_blink(0,1,1));log("CONTRACT ASYNC LED PASS\n");
    const uint32_t original=s->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_CURRENT,0,0,nullptr);
    mk61_service_file source{};
    CHECK(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_TEXT,
        (uint32_t)(uintptr_t)(PICO_CONTRACT_ROOT "/input.txt"),&source)==0);
    const char* text=M8("Привет, ёж!\n");uint8_t data[64]{};
    CHECK(source.size==strlen(text) && mk61_api->file_size(source.id)==strlen(text));
    CHECK(mk61_api->file_read(source.id,0,data,sizeof(data))==strlen(text) && !memcmp(data,text,strlen(text)));
    CHECK(mk61_api->file_size(UINT32_MAX)==UINT32_MAX && mk61_api->file_read(UINT32_MAX,0,data,1)==UINT32_MAX);
    CHECK(mk61_api->file_read(source.id,0,nullptr,0)==0 && mk61_api->file_read(source.id,0,nullptr,1)==UINT32_MAX);
    mk61_service_write output{"output",(const uint8_t*)text,(uint32_t)strlen(text),MK61_SERVICE_INVALID_ID};
    CHECK(s->call(MK61_SERVICE_FILE_WRITE,source.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&output));
    uint32_t stamp=0;
    CHECK(s->call(MK61_SERVICE_RESOURCE_READ,6,output.id,0,&stamp));
    mk61_service_resource read{stamp,(uint16_t)output.id,2,data,4,2};
    CHECK(s->call(MK61_SERVICE_RESOURCE_READ,5,0,0,&read) && !memcmp(data,text+2,4));
    char edited[32]{};mk61_service_edit_key edit{};
    edit.source=edited;edit.capacity=sizeof(edited);edit.options=16;edit.key=s->keyboard_mapping->digit[9];edit.hook_mask=1;edit.hook=hook;
    CHECK(s->call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit)==1 && edit.length==4 && !strcmp(edited,M8("КЛЮЧ")));
    edit.key=s->keyboard_mapping->esc;
    CHECK(s->call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit)==2);
    char literal[32]{};mk61_service_edit_key qwerty{};
    qwerty.source=literal;qwerty.capacity=sizeof(literal);qwerty.options=1;
    for(const char* ch="hello fkl";*ch;++ch) {
        qwerty.key=MK61_APP_KEY_RAW_BASE+*ch;
        CHECK(s->call(MK61_SERVICE_EDITOR_KEY,0,0,0,&qwerty)==1);
    }
    CHECK(!strcmp(literal,"hello fkl") && qwerty.length==9);
    log("CONTRACT QWERTY EDITOR PASS\n");
    CHECK(s->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_APPLY_ITEM,16,0,nullptr));
    CHECK(display(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT));
    CHECK(mk61_api->display_rows()==3 && display(MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH)==188);
    CHECK(mk61_api->display_clear() && display(MK61_SERVICE_DISPLAY_UI_LINE,0,0,(void*)"A"));
    log("CONTRACT UI16 READY\n");
    const int entered=mk61_api->key_wait();
    { char line[80];mk61_app_snprintf(s,line,sizeof(line),"CONTRACT ENTER=%u EXPECT=%u\n",(unsigned)entered,(unsigned)MK61_APP_KEY_OK);log(line); }
    CHECK(entered==MK61_APP_KEY_OK);
    CHECK(display(MK61_SERVICE_DISPLAY_CURSOR,1,0) && display(MK61_SERVICE_DISPLAY_CURSOR_ON));
    key(MK61_SERVICE_KEY_CLEAR_IMMEDIATE);log("CONTRACT KEYS READY\n");
    const uint32_t seven=s->keyboard_mapping->digit[7],two=s->keyboard_mapping->digit[2];
    uint32_t event=UINT32_MAX;
    while(event==UINT32_MAX) event=key(MK61_SERVICE_KEY_POLL);
    CHECK(event==seven && key(MK61_SERVICE_KEY_PRESSED,seven));
    CHECK(key(MK61_SERVICE_KEY_IMMEDIATE,seven)==1 && key(MK61_SERVICE_KEY_IMMEDIATE,seven)==0);
    CHECK(key(MK61_SERVICE_KEY_HANDOFF,seven) && key(MK61_SERVICE_KEY_HANDOFF_PENDING));
    log("CONTRACT KEY HELD\n");
    do { event=key(MK61_SERVICE_KEY_GET,0); } while(event==UINT32_MAX);
    CHECK(event==two);log("CONTRACT OTHER KEY PRESERVED\n");
    while(key(MK61_SERVICE_KEY_HANDOFF_PENDING)) mk61_api->service();
    do { event=key(MK61_SERVICE_KEY_GET,0x40); } while(event==UINT32_MAX);
    CHECK(event==(two|0x40));
    CHECK(display(MK61_SERVICE_DISPLAY_CURSOR_OFF));
    CHECK(s->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_APPLY_ITEM,0,0,nullptr));
    CHECK(display(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT) && mk61_api->display_rows()==8);
    CHECK(mk61_api->display_clear() && display(MK61_SERVICE_DISPLAY_UI_LINE,0,0,(void*)"A"));
    log("CONTRACT UI5X8 READY\n");CHECK(mk61_api->key_wait()==MK61_APP_KEY_OK);
    CHECK(s->call(MK61_SERVICE_SETUP,MK61_SETUP_UI_FONT_APPLY_ITEM,original,0,nullptr));
    CHECK(display(MK61_SERVICE_DISPLAY_END_UI_TEXT));
    char filename[32];memcpy(filename,M8("ёж"),3);mk61_service_save_target target{filename,MK61_SERVICE_ROOT_ID};
    log("CONTRACT FILENAME READY\n");
    CHECK(s->call(MK61_SERVICE_FILE_SAVE_TARGET,MK61_SERVICE_FILE_TEXT,0,sizeof(filename),&target));
    CHECK(!strcmp(filename,M8("Привет.txt")));
    CHECK(mk61_api->key_poll()==MK61_APP_KEY_NONE);
    log("CONTRACT API PASS\n");return 0;
}
