#include "mk61_app.h"
#include <cstring>

int main() {
    const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_DEBUG_IO);
    if(!services || !mk61_api->graphics_begin()) return 1;
    mk61_service_framebuffer frame{};
    if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(frame),0,&frame) ||
       frame.width!=320 || frame.height!=320 || frame.bytes!=12800 || !frame.pixels) return 2;
    for(unsigned stage=0;stage<8;++stage) {
        std::memset(frame.pixels,0,frame.bytes);
        for(unsigned y=0;y<320;++y) for(unsigned x=0;x<320;++x) {
            bool lit=false;
            if(stage==0 || stage>=6) lit=((x/16+y/16)&1)!=0;
            if(stage>=2 && stage<=4) {
                const unsigned left=stage==2?8:16;
                lit=(x>=left && x<left+24 && y>=40 && y<64) ||
                    (x>=272 && x<296 && y>=256 && y<280);
                if(stage==4) lit|=(!x && !y) || (x==319 && y==319);
            }
            if(stage==5) lit=true;
            if(lit) frame.pixels[y/8*320+x]|=1U<<(y&7);
        }
        if(!mk61_api->graphics_present(frame.pixels,frame.bytes)) return 3;
        char message[]="LCDPROBE STAGE=0 READY\n";message[15]=(char)('0'+stage);
        services->call(MK61_SERVICE_DEBUG_WRITE,std::strlen(message),0,0,message);
        for(;;) {
            const int key=mk61_api->key_wait();
            if(key==MK61_APP_KEY_ESC) { mk61_api->graphics_end();return 0; }
            if(key==MK61_APP_KEY_OK) break;
        }
    }
    mk61_api->graphics_end();return 0;
}
