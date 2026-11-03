#include "firmware_optimization.hpp"
#include "explorer_view.hpp"
#include "wbmp.hpp"
#include "mk8_codec.hpp"
#include <string.h>

namespace explorer_view {
bool decode_icon(const u8* data,usize size,Icon& out) {
  if(!data || size > MAX_ICON_FILE_BYTES) return false;
  wbmp::Info info{};
  if(wbmp::inspect(data,size,info) != wbmp::Status::OK ||
     info.width != ICON_WIDTH || info.height != ICON_HEIGHT ||
     info.pixel_bytes != ICON_BYTES) return false;
  // WBMP 0 is dark; the display buffer uses 1 for foreground ink.
  for(usize i=0;i<ICON_BYTES;++i) out.pixels[i]=(u8)~data[info.pixel_offset+i];
  return true;
}

Canvas::Canvas(u8* data,usize bytes,Geometry geometry,Packing packing,
               GlyphProvider provider,void* context)
    : data_(data),bytes_(bytes),geometry_(geometry),packing_(packing),
      provider_(provider),context_(context),
      valid_(data && geometry.supported() && bytes >=
          (usize)geometry.width*geometry.height/8U) {}
void Canvas::clear() { if(valid_) memset(data_,0,bytes_); }
void Canvas::pixel(i16 x,i16 y,bool ink) {
  if(!valid_ || x<0 || y<0 || x>=geometry_.width || y>=geometry_.height) return;
  const usize index=packing_==Packing::PAGE_LSB
      ? (usize)(y/8)*geometry_.width+x
      : (usize)y*(geometry_.width/8)+x/8;
  const u8 mask=packing_==Packing::PAGE_LSB ? (u8)(1U<<(y&7)) : (u8)(0x80U>>(x&7));
  if(ink) data_[index]|=mask; else data_[index]&=(u8)~mask;
}
void Canvas::rectangle(i16 x,i16 y,u16 w,u16 h,bool ink) {
  for(u16 dy=0;dy<h;++dy) for(u16 dx=0;dx<w;++dx) pixel(x+dx,y+dy,ink);
}
bool Canvas::glyph(u8 height,u8 m8,Glyph& out) const {
  out={};
  if(!provider_ || !provider_(context_,height,(u16)mk8::codepoint(m8),out) ||
     out.width>16 || out.height>16 || !out.advance || out.advance>16 ||
     ((out.width+7U)/8U)*out.height>sizeof(out.pixels)) return false;
  return true;
}
u16 Canvas::measure(const char* m8,u8 height) const {
  u16 width=0;
  for(;m8 && *m8;++m8) {
    Glyph g{};
    const u16 advance=glyph(height,(u8)*m8,g) ? g.advance : height==8 ? 6 : 8;
    if(width>0xFFFFU-advance) return 0xFFFFU;
    width+=advance;
  }
  return width;
}
void Canvas::text(i16 x,i16 y,const char* m8,u8 height,u16 maximum,bool ink) {
  if(!valid_ || !m8) return;
  u16 used=0;
  for(;*m8;++m8) {
    Glyph g{};
    if(!glyph(height,(u8)*m8,g)) continue;
    if(g.advance>maximum-used) break;
    for(u8 dy=0;dy<g.height;++dy) for(u8 dx=0;dx<g.width;++dx) {
      const i16 px=x+used+g.bearing_x+dx;
      if(px>=x+maximum) continue;
      if(g.pixels[dy*((g.width+7)/8)+dx/8]&(0x80U>>(dx&7)))
        pixel(px,y+height-g.bearing_y+dy,ink);
    }
    used+=g.advance;
  }
}
void Canvas::header(const char* title,const char* progress,const char* file,bool parent) {
  const bool small=geometry_.classic();
  const u8 h=geometry_.font_height();
  if(parent) text(small?2:10,small?1:8,"<",h,12);
  text(parent?(small?14:29):(small?2:10),small?1:8,title,h,small?100:190);
  text(small?120:230,small?1:8,progress,h,small?40:40);
  text(small?166:276,small?1:8,file,h,small?26:36);
  rectangle(0,small?11:31,geometry_.width,1);
}
void Canvas::item(u8 slot,const char* name,Kind kind,const Icon* icon,bool selected,u8 offset) {
  if(!valid_ || slot>=geometry_.page_size() || !name) return;
  const bool small=geometry_.classic(), icons=geometry_.mode==Mode::ICONS;
  const u8 height=geometry_.font_height();
  const u16 maximum=geometry_.label_width();
  char label[64];
  usize n=0;
  const usize length=strlen(name);
  if(offset>length) offset=(u8)length;
  const char* source=name+offset;
  for(;source[n] && n<sizeof(label)-1;++n) label[n]=source[n];
  label[n]=0;
  if(measure(label,height)>maximum) {
    while(n && measure(label,height)+measure("...",height)>maximum) label[--n]=0;
    if(n+3<sizeof(label)) { memcpy(label+n,"...",4); }
  }
  const u16 label_width=measure(label,height);
  const i16 cell_x=small ? (slot%3)*64 : 10+(slot%3)*100;
  const i16 cell_y=small ? 13 : 43+(slot/3)*86;
  const i16 label_x=icons ? cell_x+((small?64:100)-label_width)/2 : small?4:16;
  const i16 label_y=icons ? (small?52:cell_y+49) : (small?14+slot*10:49+slot*29);
  if(icons) {
    const i16 left=cell_x+(small?16:34),top=small?16:cell_y+9;
    if(icon) {
      for(u8 y=0;y<32;++y) for(u8 x=0;x<32;++x)
        if(icon->pixels[y*4+x/8]&(0x80U>>(x&7))) pixel(left+x,top+y);
    } else if(kind==Kind::DIRECTORY) {
      rectangle(left+3,top+5,10,1);rectangle(left+3,top+5,1,22);
      rectangle(left+13,top+6,1,1);rectangle(left+14,top+7,1,1);
      rectangle(left+15,top+8,14,1);rectangle(left+28,top+8,1,19);
      rectangle(left+3,top+10,26,1);rectangle(left+3,top+26,26,1);
    } else {
      rectangle(left+6,top+2,15,1);rectangle(left+6,top+2,1,28);
      rectangle(left+6,top+29,21,1);rectangle(left+26,top+8,1,22);
      for(u8 i=0;i<7;++i) pixel(left+20+i,top+2+i);
      rectangle(left+20,top+2,1,7);rectangle(left+20,top+8,7,1);
      for(u8 y=13;y<=21;y+=4) rectangle(left+10,top+y,y==21?8:12,1);
    }
  }
  if(selected) rectangle(label_x-2,label_y-1,label_width+4,height+2);
  text(label_x,label_y,label,height,maximum,!selected);
}
void Canvas::empty(const char* value) {
  text(geometry_.classic()?4:10,geometry_.classic()?22:61,value,
       geometry_.font_height(),geometry_.width-12);
}
} // namespace explorer_view
