#include "wbmp.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include <random>
struct Source {
    std::vector<u8> bytes;
    unsigned fail_at=UINT32_MAX;
    static bool read(void* raw,usize offset,u8* out,usize count) {
        auto& s=*(Source*)raw;
        assert(offset<=s.bytes.size() && count<=s.bytes.size()-offset);
        if(offset<=s.fail_at && count>s.fail_at-offset) return false;
        std::memcpy(out,s.bytes.data()+offset,count);return true;
    }
    wbmp::Reader reader() { return {this,(usize)bytes.size(),read}; }
};
static void varint(std::vector<u8>& out,unsigned n) {
    u8 bytes[5];unsigned used=0;
    do { bytes[used++]=(u8)(n&127);n>>=7; } while(n);
    while(used) { --used;out.push_back(bytes[used]|(used?128:0)); }
}
static void compare(Source& source,bool pixels) {
    wbmp::Info a{},b{};u8 empty=0;
    const auto sa=wbmp::inspect(source.bytes.empty()?&empty:source.bytes.data(),source.bytes.size(),a);
    const auto sb=wbmp::inspect(source.reader(),b);
    assert(sa==sb && !std::memcmp(&a,&b,sizeof(a)));
    if(sa==wbmp::Status::OK && pixels)
        for(unsigned y=0;y<=a.height;++y) for(unsigned x=0;x<=a.width;++x)
            assert(wbmp::dark_pixel(source.bytes.data(),source.bytes.size(),a,x,y)==
                   wbmp::dark_pixel(source.reader(),b,x,y));
    if(sa==wbmp::Status::OK && pixels) {
      for(auto layout:{wbmp::Layout::PAGE_MAJOR_LSB,wbmp::Layout::ROW_MAJOR_MSB})
        for(unsigned x:{0U,1U,7U,8U,a.width-1,a.width})
          for(unsigned y:{0U,1U,a.height-1,a.height}) {
            const unsigned size=wbmp::viewport_bytes(33,17,layout);
            std::vector<u8> direct(size+2,0xA7),indirect(size+2,0xA7);
            assert(wbmp::decode_viewport(source.bytes.data(),source.bytes.size(),a,x,y,33,17,layout,direct.data()+1,size)==wbmp::Status::OK);
            assert(wbmp::decode_viewport(source.reader(),b,x,y,33,17,layout,indirect.data()+1,size)==wbmp::Status::OK);
            assert(direct==indirect && direct.front()==0xA7 && direct.back()==0xA7);
          }
    }
}
int main() {
    std::mt19937 rng(0x57424D50);
    for(unsigned width:{1U,5U,8U,9U,320U,1024U}) for(unsigned height:{1U,2U,10U,320U}) {
        Source source;source.bytes={0,0};varint(source.bytes,width);varint(source.bytes,height);
        const auto header=source.bytes.size();const unsigned stride=(width+7)/8;
        for(unsigned row=0;row<height;++row) {
            for(unsigned i=0;i<stride;++i) source.bytes.push_back((u8)rng());
            if(width%8) source.bytes.back()&=(u8)(255U<<(8-width%8));
        }
        compare(source,true);
        source.bytes.pop_back();compare(source,false);
        source.bytes.push_back(0);source.bytes.push_back(0);compare(source,false);
        source.bytes.resize(header);compare(source,false);
    }
    for(unsigned i=0;i<10000;++i) {
        Source source;source.bytes.resize(rng()%128);
        for(auto& byte:source.bytes) byte=(u8)rng();
        if(i%2 && !source.bytes.empty()) source.bytes[0]=0;
        compare(source,false);
    }
    Source source{{0,0,5,1,0xF8}};wbmp::Info info{};
    assert(wbmp::inspect(source.reader(),info)==wbmp::Status::OK);
    source.fail_at=0;assert(wbmp::inspect(source.reader(),info)==wbmp::Status::IO_ERROR);
    source.fail_at=UINT32_MAX;assert(wbmp::inspect(source.reader(),info)==wbmp::Status::OK);
    source.fail_at=4;assert(!wbmp::dark_pixel(source.reader(),info,0,0));
    u8 viewport[8]{};
    assert(wbmp::decode_viewport(source.reader(),info,0,0,8,8,wbmp::Layout::PAGE_MAJOR_LSB,viewport,sizeof(viewport))==wbmp::Status::IO_ERROR);
    std::puts("WBMP indirect reader: pixel/status parity, malformed corpus, boundaries and I/O failure PASS");
}
