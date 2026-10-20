#include "mk61_app.h"
#include "mk8_literal.hpp"
#include <cstring>
namespace {
const mk61_app_services* services;
void report(const char* text) { services->call(MK61_SERVICE_DEBUG_WRITE,std::strlen(text),0,0,(void*)text); }
bool next() { return mk61_api->key_wait()==MK61_APP_KEY_OK; }
}
int main() {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_DEBUG_IO);
    if(!services) return 1;
#if !defined(MK61_TARGET_PICOCALC)
    if(mk61_api->graphics_width()!=192 || mk61_api->graphics_height()!=64) return 4;
    mk61_service_ui_font_info info{};mk61_service_ui_glyph glyph{};glyph.family=4;glyph.size=16;
    if(!services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_INFO,0,sizeof(info),&info) ||
       info.family!=4 || info.height!=16 || info.line_gap ||
       !services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_GLYPH,'A',sizeof(glyph),&glyph) ||
       glyph.width!=10 || glyph.height!=16 || glyph.advance!=12) return 5;
    char hex[65]{};const char digits[]="0123456789ABCDEF";
    for(unsigned i=0;i<32;++i) {hex[2*i]=digits[glyph.pixels[i]>>4];hex[2*i+1]=digits[glyph.pixels[i]&15];}
    report("LEGACY GLYPH=");report(hex);report("\n");
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT,0,0,nullptr);
    if(mk61_api->display_columns()!=16 || mk61_api->display_rows()!=4) return 6;
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_UI_LINE,0,0,(void*)"A");
    report("LEGACY TEXT READY\n");if(!next()) return 0;
    report("LEGACY TEXT PASS\n");return 0;
#else
    if(mk61_api->display_columns()!=19) return 1;
    const unsigned angle=services->call(MK61_SERVICE_SETTINGS,MK61_SERVICE_ANGLE,0,0,nullptr);
    if(angle<10 || angle>12) return 3;
    char saved_angle[]="ANGLE=0\n";saved_angle[6]+=(char)(angle-10);report(saved_angle);
    mk61_api->display_clear();mk61_api->display_write_m8(0,0,M8("ЖЩЮ←"),4);
    report("NATIVE TEXT MONO READY\n");if(!next()) return 0;
    char source[40];for(unsigned i=0;i<30;++i) source[i]=M8("Щ")[0];source[30]=0;
    mk61_service_editor editor{source,30,30,0,0};
    if(!services->call(MK61_SERVICE_EDITOR_DRAW,0,0,0,&editor)) return 2;
    report("NATIVE TEXT EDITOR READY\n");if(!next()) return 0;
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_CURSOR_OFF,0,0,nullptr);
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT,0,0,nullptr);
    services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_UI_LINE,12,0,(void*)M8("ЖЩЮ←"));
    report("NATIVE TEXT UI READY\n");if(!next()) return 0;
    report("NATIVE TEXT PASS\n");return 0;
#endif
}
