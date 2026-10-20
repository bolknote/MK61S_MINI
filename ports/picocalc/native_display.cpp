#include "native_display.hpp"
#include "canvas.hpp"
#include "script.hpp"
#include "fonts.hpp"
#include "fmk_font.hpp"
#include "mk8_codec.hpp"
#include "ui_font_service.hpp"
#include "m61_platform.hpp"
#include <cstring>
#include <new>
namespace picocalc {
namespace {
bool text_length(const char* text,unsigned maximum,unsigned& size) {
    if(!text) return false;
    size=(unsigned)strnlen(text,maximum);
    return size<maximum && mk8::text_valid((const u8*)text,size);
}
}
NativeDisplay::NativeDisplay(const Settings& settings,bool native):native_(native),surface_(pixels_),settings_(settings) {
    surface_.begin({8,5,8,0},false,32);layout();
}
bool NativeDisplay::load_text_font() {
    font_.reset();font_bytes_.reset();
    unsigned size=0;const u8* data=script::active_font_data(size);
    if(!data || !size) return true;
    auto bytes=std::unique_ptr<u8[]>(new(std::nothrow) u8[prepared_font::MAX_IMAGE_SIZE]);
    if(!bytes) return false;
    prepared_font::Face ready;usize used=0;
    if(ready.open(data,size)) { std::memcpy(bytes.get(),data,size);used=size; }
    else {
        struct Source { const u8* data;unsigned size; } source{data,size};
        const fmk::ReadSource input{&source,size,[](void* raw,usize offset,u8* out,usize n) {
            const auto& s=*(Source*)raw;if(offset>s.size || n>s.size-offset) return false;
            std::memcpy(out,s.data+offset,n);return true;
        }};
        if(!fmk::prepare(input,bytes.get(),prepared_font::MAX_IMAGE_SIZE,used)) return false;
    }
    if(!font_.open(bytes.get(),used)) return false;
    font_bytes_=std::move(bytes);return true;
}
void NativeDisplay::settings(const Settings& settings) {
    const bool changed=settings.ui_font_family!=settings_.ui_font_family ||
        settings.ui_font_size!=settings_.ui_font_size || settings.ui_font_key!=settings_.ui_font_key;
    settings_=settings;
    if(changed && (ui_ || native_)) layout();
}
void NativeDisplay::layout() {
    if(native_) { native_layout();return; }
    surface_.endFullscreenBitmap();bitmap_=false;
    if(ui_) {
        auto info=fonts::info(settings_);
        if(settings_.ui_font_family==4)
            ui_font_service::call(4,16,MK61_UI_FONT_INFO,0,sizeof(info),&info);
        const unsigned pitch=info.height+info.line_gap;
        const u8 rows=(u8)((64U+info.line_gap)/pitch);
        unsigned cols=settings_.ui_font_family==4?16:settings_.ui_font_family==5?47:text_screen::MAX_COLS;
        const auto external=fonts::external_face(settings_);
        if(external && external->metrics().monospaced && external->metrics().default_advance)
            cols=188/external->metrics().default_advance;
        if(cols>text_screen::CELL_CAPACITY/rows) cols=text_screen::CELL_CAPACITY/rows;
        surface_.setFont(external);
        (void)surface_.setUiTextLayout({rows,10,info.height,info.line_gap},(u8)cols);
        surface_.setUiTextStyle(true,settings_.ui_font_family!=0,settings_.ui_font_family==4,
            settings_.ui_font_family==5,ui_font_service::face(1,settings_.ui_font_size));
    } else {
        (void)load_text_font();
        const auto profile=script::text_profile();
        surface_.setFont(font_.valid()?&font_:nullptr);
        surface_.setUiTextStyle(false,false,false,false,ui_font_service::face(1,14));
        const unsigned width=font_.valid()?font_.metrics().default_advance:profile.width+1;
        unsigned cols=width?192/width:1;if(cols>text_screen::MAX_COLS) cols=text_screen::MAX_COLS;
        surface_.setTextLayout({profile.rows,profile.width,profile.height,profile.line_gap},(u8)(cols?cols:1));
    }
    font_revision_=script::font_revision();ui_font_revision_=fonts::revision();++revision_;surface_.clear();flush();
}
void NativeDisplay::flush() {
    if(native_) { native_flush();return; }
    if(!ui_ && font_revision_!=script::font_revision()) { layout();return; }
    if(ui_ && ui_font_revision_!=fonts::revision()) { layout();return; }
    surface_.flush(millis());
    if(published_!=surface_.revision()) { script::show_frame(pixels_);published_=surface_.revision(); }
}
unsigned NativeDisplay::columns() { flush();return native_?ncols_:surface_.cols(); }
unsigned NativeDisplay::rows() { flush();return native_?nrows_:surface_.rows(); }
u32 NativeDisplay::clear() {
    script::clear_text_record();
    if(native_) { std::memset(cells_,0,sizeof(cells_));nx_=ny_=0;gutters_=tails_=0;native_dirty_=true; }
    else surface_.clear();flush();return 1;
}
bool NativeDisplay::put(u16 cp) {
    if(native_) { native_put(cp);return true; }
    if(cp!='\r' && cp!='\n') script::record_codepoint(surface_.cursorX(),surface_.cursorY(),cp);
    surface_.writeCodepoint(cp);return true;
}
u32 NativeDisplay::write(unsigned x,unsigned y,const char* text,unsigned n) {
    if(!text || n>MK61_APP_MAX_TEXT_BYTES || x>=columns() || y>=rows() ||
       !mk8::text_valid((const u8*)text,n)) return 0;
    if(native_) { nx_=x;ny_=y; }else surface_.setCursor((u8)x,(u8)y);
    for(unsigned i=0;i<n;++i) put(mk8::codepoint((u8)text[i]));
    flush();return 1;
}
u32 NativeDisplay::call(u32 op,u32 b,u32 c,void* payload) {
    flush();
    if(native_) return native_call(op,b,c,payload);
    switch(op) {
    case MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT:
    case MK61_SERVICE_DISPLAY_END_UI_TEXT:
        if(ui_!=(op==MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT)) { ui_=!ui_;layout(); }return 1;
    case MK61_SERVICE_DISPLAY_UI_TEXT_ACTIVE:return ui_;
    case MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH:return surface_.uiTextWidth();
    case MK61_SERVICE_DISPLAY_MEASURE_UI_TEXT: {
        unsigned n=0;return text_length((const char*)payload,256,n)?surface_.measureUiText((const char*)payload,(u16)n):0;
    }
    case MK61_SERVICE_DISPLAY_UI_LINE: {
        unsigned n=0;
        if(b>=rows() || !text_length((const char*)payload,256,n)) return 0;
        surface_.printUiLine((u8)b,(const char*)payload,(char)c,(u16)(c>>8));flush();return 1;
    }
    case MK61_SERVICE_DISPLAY_CLEAR:return clear();
    case MK61_SERVICE_DISPLAY_CURSOR:
        if(b>255 || c>255) return 0;
        surface_.setCursor((u8)b,(u8)c);break;
    case MK61_SERVICE_DISPLAY_WRITE:
        if(b>255 || !mk8::valid_byte((u8)b)) return 0;
        put(mk8::codepoint((u8)b));break;
    case MK61_SERVICE_DISPLAY_WRITE_CODEPOINT:put(b>65535?'?':(u16)b);break;
    case MK61_SERVICE_DISPLAY_PRINT: {
        unsigned n=0;if(!text_length((const char*)payload,65536,n)) return 0;
        const auto text=(const u8*)payload;for(unsigned i=0;i<n;++i) put(mk8::codepoint(text[i]));break;
    }
    case MK61_SERVICE_DISPLAY_CURSOR_ON:surface_.cursorOn();break;
    case MK61_SERVICE_DISPLAY_CURSOR_OFF:surface_.cursorOff();surface_.blinkOff();break;
    case MK61_SERVICE_DISPLAY_BLINK_ON:surface_.blinkOn(millis());break;
    case MK61_SERVICE_DISPLAY_SUPPORTS_CURSOR:return 1;
    case MK61_SERVICE_DISPLAY_WIDTH:return 192;
    case MK61_SERVICE_DISPLAY_HEIGHT:return 64;
    case MK61_SERVICE_DISPLAY_GRAPHICS_MODE:
    case MK61_SERVICE_DISPLAY_GRAPHICS:return 1;
    case MK61_SERVICE_DISPLAY_BEGIN_UPDATE:surface_.beginUpdate();break;
    case MK61_SERVICE_DISPLAY_END_UPDATE:surface_.endUpdate();break;
    case MK61_SERVICE_DISPLAY_END_VIEWPORT:
    case MK61_SERVICE_DISPLAY_FLUSH:break;
    case MK61_SERVICE_DISPLAY_FLOW_TEXT: {
        if(!payload) return 0;
        const auto& request=*(const mk61_service_text_flow*)payload;
        if(request.flags&~3U || !request.text || request.length>65535 ||
           request.first_row>=rows() || !request.max_rows ||
           !mk8::text_valid((const u8*)request.text,request.length)) return 0;
        const unsigned limit=request.max_rows<rows()-request.first_row?request.max_rows:rows()-request.first_row;
        const auto next=[&](unsigned at,unsigned& end) {
            end=at;unsigned space=at;u32 width=0;
            while(end<request.length && request.text[end]!='\n') {
                const unsigned advance=ui_?surface_.measureUiText(request.text+end,1):1;
                if(end>at && width+advance>(ui_?surface_.uiTextWidth():columns())) break;
                if(request.text[end]==' ' || request.text[end]=='\t') space=end;
                width+=advance;++end;
            }
            if(end<request.length && request.text[end]=='\n') return end+1;
            if(end<request.length && space>at) { end=space;return space+1; }
            return end;
        };
        unsigned total=0;
        for(unsigned at=0;at<request.length;) { unsigned end;at=next(at,end);++total; }
        if(!request.length && (request.flags&2)) total=1;
        const unsigned skip=(request.flags&1) && total>limit?total-limit:0;unsigned row=0,index=0;
        for(unsigned at=0;at<request.length;) {
            unsigned end;const unsigned after=next(at,end);
            if(index++>=skip && row<limit) {
                const unsigned y=request.first_row+row++;
                surface_.setCursor(0,(u8)y);for(unsigned i=0;i<columns();++i) put(' ');
                surface_.setCursor(0,(u8)y);for(unsigned i=at;i<end;++i) put(mk8::codepoint((u8)request.text[i]));
            }
            at=after;
        }
        if(!request.length && total) { surface_.setCursor(0,(u8)request.first_row);for(unsigned i=0;i<columns();++i) put(' ');row=1; }
        flush();return row;
    }
    default:return 0;
    }
    flush();return 1;
}
bool NativeDisplay::bitmap_begin() { flush();bitmap_=native_?true:surface_.beginFullscreenBitmap();return bitmap_; }
bool NativeDisplay::bitmap_present(const u8* frame,unsigned size) {
    if(native_) {
        if(!bitmap_ || !frame || size!=canvas::BYTES) return false;
        script::show_native_frame(frame);return true;
    }
    if(!bitmap_ || !surface_.showFullscreenBitmap(frame,size)) return false;
    flush();return true;
}
void NativeDisplay::bitmap_end() { if(!native_) surface_.endFullscreenBitmap();bitmap_=false;native_dirty_=true;flush(); }

void NativeDisplay::native_layout() {
    bitmap_=false;update_=0;nx_=ny_=0;gutters_=tails_=0;
    (void)load_text_font();
    const auto info=fonts::info(settings_);
    const bool custom=!ui_ && font_.valid();
    npitch_=custom?font_.metrics().height+font_.metrics().line_gap:info.height+info.line_gap;
    ncell_=custom?font_.metrics().default_advance:fonts::cell_width(settings_);
    if(!npitch_) npitch_=1;if(!ncell_) ncell_=1;
    nrows_=320/npitch_;if(nrows_>20) nrows_=20;if(!nrows_) nrows_=1;
    ncols_=ui_?64:316/ncell_;if(ncols_>64) ncols_=64;if(!ncols_) ncols_=1;
    std::memset(cells_,0,sizeof(cells_));native_dirty_=true;
    font_revision_=script::font_revision();ui_font_revision_=fonts::revision();native_flush();
}
unsigned NativeDisplay::native_advance(u16 cp) const {
    if(!ui_) return ncell_;
    mk61_service_ui_glyph g{};return fonts::glyph(settings_,cp,g)?g.advance:ncell_;
}
unsigned NativeDisplay::native_measure(const char* text,unsigned length) const {
    unsigned width=0;for(unsigned i=0;i<length;++i) width+=native_advance(mk8::codepoint((u8)text[i]));return width;
}
void NativeDisplay::native_put(u16 cp) {
    if(cp=='\r') { nx_=0;return; }
    if(cp=='\n') { nx_=0;ny_=(ny_+1)%nrows_;return; }
    unsigned width=0;
    if(ui_) for(unsigned col=0;col<nx_ && col<ncols_;++col)
        width+=native_advance(cells_[ny_][col]?cells_[ny_][col]:' ');
    if(nx_>=ncols_ || (ui_ && nx_ && width+native_advance(cp)>316)) { nx_=0;ny_=(ny_+1)%nrows_; }
    cells_[ny_][nx_++]=cp;native_dirty_=true;
    script::record_codepoint(nx_-1,ny_,cp);
}
void NativeDisplay::native_flush() {
    if(font_revision_!=script::font_revision() || ui_font_revision_!=fonts::revision()) { native_layout();return; }
    const u32 now=millis();
    if(native_blink_ && (i32)(now-blink_at_)>=0) {
        native_phase_=!native_phase_;blink_at_=now+500;native_dirty_=true;
    }
    if(bitmap_ || update_ || !native_dirty_) return;
    canvas::clear();
    for(unsigned row=0;row<nrows_;++row) {
        unsigned x=2;const unsigned top=row*npitch_;
        for(unsigned col=0;col<ncols_;++col) {
            const u16 cp=cells_[row][col]?cells_[row][col]:' ';
            const unsigned advance=native_advance(cp);
            if(ui_ && (gutters_&(1U<<row)) && col==1) {
                const unsigned marker=native_advance(cells_[row][0]);x=2+(marker>12?marker:12);
            }
            if(ui_ && (tails_&(1U<<row)) && col==ncols_-1) x=318-advance;
            if(x+advance<=320) {
                prepared_font::Glyph g{};u8 bits[prepared_font::MAX_BITMAP_SIZE]{};
                if(!ui_ && font_.valid() && prepared_font::glyphForCodepoint(font_,cp,g) && font_.decode(g,bits,sizeof(bits))) {
                    for(unsigned y=0;y<g.height;++y) for(unsigned dx=0;dx<g.width;++dx)
                        if(fmk::bitmapPixel(bits,g.width,dx,y)) canvas::pixel(canvas::frame(),x+dx,top+y);
                } else {
                    mk61_service_ui_glyph g{};fonts::glyph(settings_,cp,g);
                    canvas::glyph(canvas::frame(),settings_,cp,x+(!ui_?(advance-g.advance)/2:0),top);
                }
                if(row==ny_ && col==nx_ && (native_cursor_ || (native_blink_ && native_phase_)))
                    canvas::rect(canvas::frame(),x,top+(native_blink_&&native_phase_?0:npitch_-2),advance,
                        native_blink_&&native_phase_?npitch_-1:1,true);
            }
            x+=advance;
        }
    }
    script::show_native_frame(canvas::frame());native_dirty_=false;++revision_;
}
u32 NativeDisplay::native_call(u32 op,u32 b,u32 c,void* payload) {
    switch(op) {
    case MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT:
    case MK61_SERVICE_DISPLAY_END_UI_TEXT:
        if(ui_!=(op==MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT)) { ui_=!ui_;native_layout(); }return 1;
    case MK61_SERVICE_DISPLAY_UI_TEXT_ACTIVE:return ui_;
    case MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH:return ui_?316:0;
    case MK61_SERVICE_DISPLAY_MEASURE_UI_TEXT: {
        unsigned n=0;return text_length((const char*)payload,256,n)?native_measure((const char*)payload,n):0;
    }
    case MK61_SERVICE_DISPLAY_UI_LINE: {
        unsigned n=0;if(!ui_ || b>=nrows_ || !text_length((const char*)payload,256,n)) return 0;
        std::memset(cells_[b],0,sizeof(cells_[b]));ny_=b;nx_=0;
        const char marker=(char)c;const u16 tail=c>>8;const unsigned end=tail?ncols_-1:ncols_;
        if(marker) { gutters_|=1U<<b;native_put((u8)marker); }else gutters_&=~(1U<<b);
        if(tail) tails_|=1U<<b;else tails_&=~(1U<<b);
        const unsigned marker_width=marker?native_advance((u8)marker):0;
        unsigned used=0,limit=316-(marker?(marker_width>12?marker_width:12):0)-(tail?native_advance(tail):0),i=0;
        const char* text=(const char*)payload;
        while(i<n && nx_<end && used+native_advance(mk8::codepoint((u8)text[i]))<=limit) {
            const u16 cp=mk8::codepoint((u8)text[i++]);used+=native_advance(cp);native_put(cp);
        }
        if(i<n && nx_>(marker?1U:0U)) cells_[b][nx_-1]=0x2026;
        if(tail) cells_[b][ncols_-1]=tail;
        nx_=0;ny_=b;native_dirty_=true;break;
    }
    case MK61_SERVICE_DISPLAY_CLEAR:return clear();
    case MK61_SERVICE_DISPLAY_CURSOR:if(b>=ncols_ || c>=nrows_) return 0;nx_=b;ny_=c;native_dirty_=true;break;
    case MK61_SERVICE_DISPLAY_WRITE:if(b>255 || !mk8::valid_byte((u8)b)) return 0;native_put(mk8::codepoint((u8)b));break;
    case MK61_SERVICE_DISPLAY_WRITE_CODEPOINT:native_put(b>65535?'?':(u16)b);break;
    case MK61_SERVICE_DISPLAY_PRINT: {
        unsigned n=0;if(!text_length((const char*)payload,65536,n)) return 0;
        for(unsigned i=0;i<n;++i) native_put(mk8::codepoint(((const u8*)payload)[i]));break;
    }
    case MK61_SERVICE_DISPLAY_WIDTH:return 320;
    case MK61_SERVICE_DISPLAY_HEIGHT:return 320;
    case MK61_SERVICE_DISPLAY_SUPPORTS_CURSOR:
    case MK61_SERVICE_DISPLAY_GRAPHICS:
    case MK61_SERVICE_DISPLAY_GRAPHICS_MODE:return 1;
    case MK61_SERVICE_DISPLAY_CURSOR_ON:native_cursor_=true;native_dirty_=true;break;
    case MK61_SERVICE_DISPLAY_CURSOR_OFF:native_cursor_=native_blink_=false;native_dirty_=true;break;
    case MK61_SERVICE_DISPLAY_BLINK_ON:native_blink_=true;native_phase_=true;blink_at_=millis()+500;native_dirty_=true;break;
    case MK61_SERVICE_DISPLAY_BEGIN_UPDATE:++update_;return 1;
    case MK61_SERVICE_DISPLAY_END_UPDATE:if(update_) --update_;break;
    case MK61_SERVICE_DISPLAY_END_VIEWPORT:
    case MK61_SERVICE_DISPLAY_FLUSH:break;
    case MK61_SERVICE_DISPLAY_FRAMEBUFFER:
        if(!bitmap_ || b!=sizeof(mk61_service_framebuffer) || !payload) return 0;
        *(mk61_service_framebuffer*)payload={canvas::frame(),canvas::BYTES,320,320};return 1;
    case MK61_SERVICE_DISPLAY_FLOW_TEXT: {
        if(!payload) return 0;const auto& r=*(const mk61_service_text_flow*)payload;
        if(r.flags&~3U || !r.text || r.length>65535 || r.first_row>=nrows_ || !r.max_rows ||
            !mk8::text_valid((const u8*)r.text,r.length)) return 0;
        const unsigned limit=r.max_rows<nrows_-r.first_row?r.max_rows:nrows_-r.first_row;
        const auto next=[&](unsigned at,unsigned& end) {
            end=at;unsigned space=at,width=0;
            while(end<r.length && r.text[end]!='\n') {
                const unsigned advance=ui_?native_advance(mk8::codepoint((u8)r.text[end])):1;
                if(end>at && width+advance>(ui_?316:ncols_)) break;
                if(r.text[end]==' ' || r.text[end]=='\t') space=end;width+=advance;++end;
            }
            if(end<r.length && r.text[end]=='\n') return end+1;
            if(end<r.length && space>at) { end=space;return space+1; }return end;
        };
        unsigned total=0;for(unsigned at=0;at<r.length;) { unsigned end;at=next(at,end);++total; }
        if(!r.length && (r.flags&2)) total=1;
        const unsigned skip=(r.flags&1) && total>limit?total-limit:0;unsigned row=0,index=0;
        for(unsigned at=0;at<r.length;) {
            unsigned end;const unsigned after=next(at,end);
            if(index++>=skip && row<limit) {
                nx_=0;ny_=r.first_row+row++;std::memset(cells_[ny_],0,sizeof(cells_[ny_]));
                for(unsigned i=at;i<end;++i) native_put(mk8::codepoint((u8)r.text[i]));
            }
            at=after;
        }
        if(!r.length && total) { std::memset(cells_[r.first_row],0,sizeof(cells_[0]));row=1; }
        native_dirty_=true;native_flush();return row;
    }
    default:return 0;
    }
    native_flush();return 1;
}
}
