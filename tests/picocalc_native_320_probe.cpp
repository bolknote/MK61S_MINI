#include "mk61_app.h"
#include <cstring>
namespace {
const mk61_app_services* services;
void report(const char* value) {
    services->call(MK61_SERVICE_DEBUG_WRITE,std::strlen(value),0,0,(void*)value);
}
bool wait() {
    for(;;) {
        const auto key=mk61_api->key_wait();
        if(key==MK61_APP_KEY_OK) return true;
        if(key==MK61_APP_KEY_ESC) return false;
    }
}
}
int main() {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_DEBUG_IO);
    if(!services) return 1;
#if defined(MK61_TARGET_PICOCALC)
    if(mk61_api->graphics_width()!=320 || mk61_api->graphics_height()!=320) return 2;
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT,0,0,nullptr);
    if(mk61_api->display_rows()<=12) return 3;
    char message[]="Native 320 x 320";
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_UI_LINE,12,0,message);
    report("NATIVE320 TEXT READY\n");if(!wait()) return 0;
    if(!mk61_api->graphics_begin()) return 4;
    mk61_service_framebuffer frame{};
    if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(frame),0,&frame) ||
        frame.width!=320 || frame.height!=320 || frame.bytes!=12800 || !frame.pixels) return 5;
    std::memset(frame.pixels,0,frame.bytes);
    for(unsigned y=0;y<320;++y) for(unsigned x=0;x<320;++x)
        if((x*3+y*5)%11<5) frame.pixels[y/8*320+x]|=1U<<(y&7);
    if(!mk61_api->graphics_present(frame.pixels,frame.bytes)) return 6;
    report("NATIVE320 BITMAP READY\n");if(!wait()) return 0;
    mk61_api->graphics_end();report("NATIVE320 TEXT RESTORED\n");if(!wait()) return 0;
    report("NATIVE320 PASS\n");
#else
    if(mk61_api->graphics_width()!=192 || mk61_api->graphics_height()!=64) return 7;
    static uint8_t bitmap[1536];
    for(unsigned i=0;i<sizeof(bitmap);++i) bitmap[i]=(uint8_t)(i*37+7);
    if(!mk61_api->graphics_begin() || !mk61_api->graphics_present(bitmap,sizeof(bitmap))) return 8;
    report("LEGACY192 BITMAP READY\n");wait();mk61_api->graphics_end();report("LEGACY192 PASS\n");
#endif
    return 0;
}
