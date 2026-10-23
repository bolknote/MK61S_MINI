// Native 320x320 LCD HIL probe; build as LCDMOVE with build_portable_app.py.
//45 frames, forward/backward16-row shifts and an ordinary graphics_end.
#include "mk61_app.h"
#include <cstring>
int main() {
    const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_DEBUG_IO|MK61_SERVICE_CAP_FORMAT);
    if(!services || !mk61_api->graphics_available() || !mk61_api->graphics_begin()) return 1;
    mk61_service_framebuffer frame{};
    if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(frame),0,&frame) ||
       frame.width!=320 || frame.height!=320 || !frame.pixels) { mk61_api->graphics_end();return 2; }
    const char ready[]="LCDMOVE READY 320x320 DELTA16\n";
    services->call(MK61_SERVICE_DEBUG_WRITE,sizeof(ready)-1,0,0,(void*)ready);
    for(unsigned step=0;step<45;++step) {
        const unsigned offset=16*(step<=22?step:44-step);
        std::memset(frame.pixels,0,12800);
        for(unsigned y=0;y<320;++y) {
            const unsigned row=y+offset;
            for(unsigned x=0;x<320;++x) {
                const unsigned pattern=(row*73U)^(row>>3)^((x/8)*19U);
                const bool pixel=x<8 || x>=312 || ((pattern>>(x&7))&1U);
                if(pixel) frame.pixels[(y/8)*320+x]|=(uint8_t)(1U<<(y&7));
            }
        }
        if(!mk61_api->graphics_present(frame.pixels,12800)) { mk61_api->graphics_end();return 3; }
        mk61_api->delay_ms(450);
        char message[64];
        const int count=mk61_app_snprintf(services,message,sizeof(message),"LCDMOVE FRAME=%u OFFSET=%u\n",step,offset);
        if(count>0 && count<(int)sizeof(message)) services->call(MK61_SERVICE_DEBUG_WRITE,(uint32_t)count,0,0,message);
        mk61_api->delay_ms(550);
    }
    mk61_api->graphics_end();
    const char done[]="LCDMOVE PASS\n";
    services->call(MK61_SERVICE_DEBUG_WRITE,sizeof(done)-1,0,0,(void*)done);
    return 0;
}
