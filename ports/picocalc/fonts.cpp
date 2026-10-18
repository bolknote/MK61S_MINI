#include "fonts.hpp"
#include "storage.hpp"
#include "ui_font_catalog.hpp"
#include "ui_font_service.hpp"
#include "mk8_codec.hpp"
#include <cstdio>
#include <cstring>
#include <memory>
#include <new>

namespace picocalc { namespace fonts {
namespace {
std::unique_ptr<u8[]> bytes;
prepared_font::Face face;
u32 active_key = 0;
u32 generation = 1;
constexpr Item builtins[] = {{12,1,12,"Ark Pixel 12"}, {14,1,14,"Ark Pixel 14"},
    {16,1,16,"Ark Pixel 16"}, {0x10010,4,16,"Classic 10x16"},
    {0x10005,5,5,"Compact 3x5"}, {0,0,14,"5x8"}};
constexpr unsigned builtin_count = sizeof(builtins)/sizeof(builtins[0]);
bool external(const files::Entry& entry, Item& out, char* path) {
    if(entry.directory) return false;
    const unsigned length = std::strlen(entry.name);
    if(length < 5 || !ui_font_catalog::name_equal(entry.name+length-4,".fmk")) return false;
    if(std::snprintf(path, files::PATH_SIZE,"/Fonts/%s",entry.name) >= (int)files::PATH_SIZE) return false;
    u8 header[fmk::HEADER_SIZE]; unsigned used=0;u8 height=0;
    if(entry.size > fmk::MAX_FILE_SIZE ||
       !files::read_range(path,0,header,sizeof(header),used) || used!=sizeof(header) ||
       !ui_font_catalog::inspect_header(header,sizeof(header),(u16)entry.size,height)) return false;
    out = {};out.key = ui_font_catalog::name_key(entry.name);out.family=3;out.size=height;
    usize n=0;
    if(!mk8::from_utf8((const u8*)entry.name,length-4,(u8*)out.name,sizeof(out.name)-1,n)) {
        std::snprintf(out.name,sizeof(out.name),"Font %08lX",(unsigned long)out.key);
    } else out.name[n]=0;
    return true;
}
template<class Visitor> void visit(Visitor visitor) {
    files::Entry entries[4];bool more=true;unsigned skip=0;
    while(more) {
        unsigned used=0;
        if(!files::list("/Fonts",skip,entries,4,used,more)) break;
        skip+=used;
        for(unsigned i=0;i<used;++i) {
            Item entry{};char path[files::PATH_SIZE];
            if(external(entries[i],entry,path) && !visitor(entry,path)) return;
        }
    }
}
}
u32 key(const Settings& s) {
    if(s.ui_font_family==0) return 0;
    return s.ui_font_family==3 ? s.ui_font_key : s.ui_font_family==4 ? 0x10010 :
        s.ui_font_family==5 ? 0x10005 : s.ui_font_size;
}
unsigned count() {
    unsigned result=builtin_count;
    visit([&](const Item&,const char*) { ++result;return true; });
    return result;
}
bool item(unsigned index, Item& out) {
    if(index<builtin_count) { out=builtins[index];return true; }
    index-=builtin_count;bool found=false;
    visit([&](const Item& value,const char*) { if(index--) return true;out=value;found=true;return false; });
    return found;
}
bool describe(u32 choice, Item& out) {
    for(const auto& value:builtins) if(value.key==choice) { out=value;return true; }
    unsigned found=0;
    visit([&](const Item& value,const char*) { if(value.key==choice) { out=value;++found; }return true; });
    return found==1;
}
bool step(u32 choice,int direction,Item& out) {
    if(direction!=1 && direction!=-1) return false;
    const unsigned total=count();unsigned at=0;
    Item entry{};
    for(unsigned i=0;i<total;++i) if(item(i,entry) && entry.key==choice) { at=i;break; }
    return item((at+total+(direction<0?-1:1))%total,out);
}
bool install(const u8* data,unsigned size,u32 choice,unsigned expected_height) {
    prepared_font::Face candidate;
    if(!data || size>prepared_font::MAX_IMAGE_SIZE || !candidate.open(data,size) ||
       !ui_font_catalog::supported_height(candidate.metrics().height) ||
       !ui_font_service::valid_external(&candidate,candidate.metrics().height) ||
       (expected_height && expected_height!=candidate.metrics().height) || !choice) return false;
    auto copy=std::unique_ptr<u8[]>(new(std::nothrow) u8[size]);
    if(!copy) return false;
    std::memcpy(copy.get(),data,size);
    if(!candidate.open(copy.get(),size)) return false;
    bytes=std::move(copy);face=candidate;active_key=choice;++generation;return true;
}
bool select(const Settings& s) {
    if(!valid_settings(s)) return false;
    if(s.ui_font_family!=3) { if(face.valid() || bytes) ++generation;face.reset();bytes.reset();active_key=0;return true; }
    if(active_key==s.ui_font_key && face.valid() && face.metrics().height==s.ui_font_size) return true;
    char path[files::PATH_SIZE]{};unsigned matches=0;
    visit([&](const Item& item,const char* file) {
        if(item.key==s.ui_font_key && item.size==s.ui_font_size) {
            std::snprintf(path,sizeof(path),"%s",file);++matches;
        }return true;
    });
    if(matches!=1) return false;
    files::Entry entry{};
    if(!files::stat(path,entry)) return false;
    auto candidate=std::unique_ptr<u8[]>(new(std::nothrow) u8[prepared_font::MAX_IMAGE_SIZE]);
    if(!candidate) return false;
    const u32 revision=files::revision();usize size=0;
    const fmk::ReadSource source{path,entry.size,
        [](void* raw,usize offset,u8* out,usize n) {
            unsigned used=0;
            return files::read_range((const char*)raw,offset,out,n,used) && used==n;
        }};
    if(!fmk::prepare(source,candidate.get(),prepared_font::MAX_IMAGE_SIZE,size) ||
       revision!=files::revision()) return false;
    prepared_font::Face decoded;
    if(!decoded.open(candidate.get(),size) || decoded.metrics().height!=s.ui_font_size ||
       !ui_font_service::valid_external(&decoded,s.ui_font_size)) return false;
    bytes=std::move(candidate);face=decoded;active_key=s.ui_font_key;++generation;return true;
}
u32 service(const Settings& s,u32 op,u32 cp,u32 size,void* out) {
    const bool loaded=s.ui_font_family==3 && active_key==s.ui_font_key && face.valid();
    const u8 family=s.ui_font_family==3 && !loaded ? 1 : s.ui_font_family;
    return ui_font_service::call(family,s.ui_font_size,op,cp,size,out,loaded?&face:nullptr);
}
bool glyph(const Settings& s,u32 cp,mk61_service_ui_glyph& out) {
    if(s.ui_font_family==0) {
        builtin_font::Raster raster{};
        const bool fallback=cp>0xFFFF || !builtin_font::decode(builtin_font::FaceId::FONT_5X8,(u16)cp,raster);
        if(fallback && !builtin_font::decode(builtin_font::FaceId::FONT_5X8,'?',raster)) return false;
        out={};out.size=8;out.width=raster.width;out.height=raster.height;
        out.bearing_y=8;out.advance=6;out.fallback=fallback;std::memcpy(out.pixels,raster.data,sizeof(out.pixels));return true;
    }
    const auto current=info(s);out={};out.family=current.family;out.size=current.size;
    if(service(s,MK61_UI_FONT_GLYPH,cp,sizeof(out),&out)) return true;
    // A subset FMK must not make menu labels disappear. The public glyph
    // service keeps its wire result; local UI rendering has a builtin fallback.
    out={};out.family=1;out.size=s.ui_font_size;
    return ui_font_service::call(1,s.ui_font_size,MK61_UI_FONT_GLYPH,cp,sizeof(out),&out)!=0;
}
mk61_service_ui_font_info info(const Settings& s) {
    if(s.ui_font_family==0) return {0,8,8,0,0,8};
    mk61_service_ui_font_info out{};service(s,MK61_UI_FONT_INFO,0,sizeof(out),&out);return out;
}
const prepared_font::Face* external_face(const Settings& s) {
    return s.ui_font_family==3 && active_key==s.ui_font_key && face.valid()?&face:nullptr;
}
u32 revision() { return generation; }
} }
