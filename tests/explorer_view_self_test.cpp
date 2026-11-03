#include "explorer_view.hpp"
#include "builtin_font.hpp"
#include "ui_font.hpp"
#include "mk8_literal.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {
bool glyph(void*,u8 height,u16 cp,explorer_view::Glyph& out) {
  out={};
  if(height==8) {
    builtin_font::Raster raster{};
    if(!builtin_font::decode(builtin_font::FaceId::FONT_5X8,cp,raster)) return false;
    out.width=raster.width;out.height=raster.height;out.advance=6;out.bearing_y=8;
    std::memcpy(out.pixels,raster.data,8);return true;
  }
  const ui_font::Face face{ui_font::Family::PIXEL,ui_font::Size::PX16};
  const auto g=ui_font::glyph(face,cp);
  out.width=g.width;out.height=g.height;out.advance=g.advance;out.bearing_x=g.bearing_x;
  out.bearing_y=g.bearing_y+height-ui_font::metrics(face).ascent;
  for(u8 y=0;y<g.height;++y) for(u8 x=0;x<g.width;++x)
    if(font_glyph::pixel(g,x,y)) out.pixels[y*((g.width+7)/8)+x/8]|=(u8)(0x80U>>(x&7));
  return true;
}
bool pixel(const u8* bytes,unsigned w,unsigned x,unsigned y,bool pages) {
  return pages?(bytes[(y/8)*w+x]&(1U<<(y&7)))!=0:(bytes[y*(w/8)+x/8]&(0x80U>>(x&7)))!=0;
}
void preview(const char* prefix,const char* suffix,const u8* data,unsigned w,unsigned h,bool pages) {
  if(!prefix) return;
  const std::string path=std::string(prefix)+suffix+".pbm";
  FILE* file=std::fopen(path.c_str(),"wb");assert(file);
  std::fprintf(file,"P4\n%u %u\n",w,h);
  for(unsigned y=0;y<h;++y) for(unsigned x=0;x<w;x+=8) {
    u8 value=0;for(unsigned i=0;i<8;++i) if(pixel(data,w,x+i,y,pages)) value|=(u8)(0x80U>>i);
    assert(std::fwrite(&value,1,1,file)==1);
  }
  std::fclose(file);
}
}
int main(int argc,char** argv) {
  using namespace explorer_view;
  unsigned stock_icons=0;
  const auto artwork=std::filesystem::path(__FILE__).parent_path().parent_path()/"doc/explorer-icons";
  for(const auto& file:std::filesystem::directory_iterator(artwork)) {
    if(file.path().extension()!=".wbmp") continue;
    std::ifstream input(file.path(),std::ios::binary);
    std::vector<u8> bytes((std::istreambuf_iterator<char>(input)),{});
    Icon stock{};assert(decode_icon(bytes.data(),bytes.size(),stock));
    for(const auto geometry:{Geometry{192,64,Mode::ICONS},Geometry{320,320,Mode::ICONS}}) {
      u8 buffer[12802];std::memset(buffer,0xA5,sizeof(buffer));
      const bool pages=geometry.width==192;
      const usize size=(usize)geometry.width*geometry.height/8;
      Canvas target(buffer+1,size,geometry,pages?Packing::PAGE_LSB:Packing::ROW_MSB,glyph);
      target.clear();target.item(0,"Icon",Kind::DIRECTORY,&stock,false);
      const unsigned left=pages?16:44,top=pages?16:52;
      for(unsigned y=0;y<32;++y) for(unsigned x=0;x<32;++x)
        assert(pixel(buffer+1,geometry.width,left+x,top+y,pages)==
            !(bytes[4+y*4+x/8]&(0x80U>>(x&7))));
      assert(buffer[0]==0xA5 && buffer[size+1]==0xA5);
    }
    ++stock_icons;
  }
  assert(stock_icons>0);
  u8 wbmp[141];std::memset(wbmp,0xFF,sizeof(wbmp));
  wbmp[0]=wbmp[1]=0;wbmp[2]=wbmp[3]=32;wbmp[4]=0x7F;
  Icon icon{};assert(decode_icon(wbmp,132,icon));assert(icon.pixels[0]==0x80);
  for(unsigned i=1;i<ICON_BYTES;++i) assert(icon.pixels[i]==0);
  for(unsigned length:{0U,1U,4U,131U,133U,141U}) assert(!decode_icon(wbmp,length,icon));
  wbmp[2]=31;assert(!decode_icon(wbmp,132,icon));wbmp[2]=32;
  wbmp[0]=1;assert(!decode_icon(wbmp,132,icon));wbmp[0]=0;
  assert(!decode_icon(nullptr,132,icon));
  assert(decode_icon(wbmp,132,icon));
  const char* names[]={M8("Шахматы"),"High Noon",M8("Элиза"),M8("Таблицы"),"Runner","CHIP-8",M8("Примеры"),M8("Заметки"),M8("Шрифты")};
  u8 row[1538],page[1538];std::memset(row,0xA5,sizeof(row));std::memset(page,0xA5,sizeof(page));
  const Geometry classic{192,64,Mode::ICONS};
  assert(classic.page_size()==3 && Geometry({192,64,Mode::LIST}).page_size()==5);
  Canvas a(row+1,1536,classic,Packing::ROW_MSB,glyph),b(page+1,1536,classic,Packing::PAGE_LSB,glyph);
  for(auto* canvas:{&a,&b}) {
    assert(canvas->ok());canvas->clear();canvas->header(M8("Программы"),"1/3",M8("Файл"),false);
    for(u8 i=0;i<3;++i) canvas->item(i,names[i],Kind::DIRECTORY,i==0?&icon:nullptr,i==0);
    canvas->pixel(-1,-1);canvas->pixel(192,64);canvas->rectangle(191,63,10,10);
  }
  for(unsigned y=0;y<64;++y) for(unsigned x=0;x<192;++x)
    assert(pixel(row+1,192,x,y,false)==pixel(page+1,192,x,y,true));
  assert(row[0]==0xA5 && row[1537]==0xA5 && page[0]==0xA5 && page[1537]==0xA5);
  assert(pixel(page+1,192,16,16,true)); // exact, unscaled source pixel
  assert(!pixel(page+1,192,17,16,true));
  preview(argc>1?argv[1]:nullptr,"-classic-icons",page+1,192,64,true);
  Canvas list(page+1,1536,{192,64,Mode::LIST},Packing::PAGE_LSB,glyph);
  list.clear();list.header(M8("Программы"),"1/2",M8("Файл"),false);
  for(u8 i=0;i<5;++i) list.item(i,names[i],Kind::DIRECTORY,nullptr,i==0);
  preview(argc>1?argv[1]:nullptr,"-classic-list",page+1,192,64,true);
  u8 pico[12800];Canvas large(pico,sizeof(pico),{320,320,Mode::ICONS},Packing::ROW_MSB,glyph);
  large.clear();large.header(M8("Программы"),"",M8("Файл"),false);
  for(u8 i=0;i<9;++i) large.item(i,names[i],Kind::DIRECTORY,nullptr,i==0);
  preview(argc>1?argv[1]:nullptr,"-pico",pico,320,320,false);
  u8 unsupported[200];std::memset(unsupported,0xA5,sizeof(unsupported));
  Canvas tiny(unsupported,sizeof(unsupported),{80,16,Mode::ICONS},Packing::PAGE_LSB,glyph);
  assert(!tiny.ok());tiny.clear();tiny.pixel(0,0);tiny.item(0,"test",Kind::FILE,nullptr,true);
  for(u8 byte:unsupported) assert(byte==0xA5);
  std::puts("Explorer native raster: WBMP validation, exact 32x32, row/page equivalence, bounds, 3/5/9 layouts PASS");
}
