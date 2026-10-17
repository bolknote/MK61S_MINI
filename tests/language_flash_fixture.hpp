#pragma once
#include "language_flash.hpp"
#include <array>
#include <map>
#include <algorithm>
#include <cassert>
using namespace language_vm::flash;
struct Disk {
  std::array<std::map<uint32_t,std::array<uint8_t,WRITE_BYTES>>,4> pages;
  unsigned maximum_read=0,writes=0,polls=0;
  int fail=-1;
  static bool read(void* raw,Space space,uint32_t at,uint8_t* out,uint16_t n) {
    auto& d=*(Disk*)raw;d.maximum_read=std::max(d.maximum_read,unsigned(n));
    while(n) {
      auto p=d.pages[space].find(at/WRITE_BYTES);
      if(p==d.pages[space].end())return false;
      const unsigned inside=at%WRITE_BYTES,count=std::min<unsigned>(n,WRITE_BYTES-inside);
      memcpy(out,p->second.data()+inside,count);at+=count;out+=count;n=uint16_t(n-count);
    }
    return true;
  }
  static bool write(void* raw,Space space,uint32_t at,const uint8_t* in,uint16_t n) {
    auto& d=*(Disk*)raw;assert(at%WRITE_BYTES==0 && n==WRITE_BYTES);
    if(d.fail>=0 && int(d.writes)==d.fail)return false;
    ++d.writes;memcpy(d.pages[space][at/WRITE_BYTES].data(),in,n);return true;
  }
  static bool truncate(void* raw,Space space,uint32_t n) {assert(!n);((Disk*)raw)->pages[space].clear();return true;}
  static bool poll(void* raw) {++((Disk*)raw)->polls;return true;}
  IO io() {return {this,read,write,truncate,poll};}
};
