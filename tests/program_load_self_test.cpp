#include "base91.hpp"
#include "crc32.hpp"
#include "mk61emu_core.h"
#include "program_load.hpp"
#include "zx0.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <random>
#include <string>
#include <vector>

static std::array<u8,10000> memory;
static unsigned write_limit = 10000;
namespace core_61 {
bool read_absolute_program(u16 address, u8& value) {
  if(address >= memory.size()) return false;
  value = memory[address]; return true;
}
bool write_absolute_program(u16 address, u8 value) {
  if(address >= write_limit) return false;
  memory[address] = value; return true;
}
}

static std::string b91(const u8* data, usize size) {
  std::string result;
  assert(base91::encode(data,size,{&result,[](void* p,char v) {
    static_cast<std::string*>(p)->push_back(v); return true;
  }}));
  return result;
}
static std::vector<u8> pack(const std::vector<u8>& source) {
  std::vector<u8> compressed, workspace(4*(source.size()+1));
  zx0::EncodeResult result;
  assert(zx0::encode(source.data(),source.size(),workspace.data(),workspace.size(),
      {&compressed,[](void* p,u8 v) {
        static_cast<std::vector<u8>*>(p)->push_back(v); return true;
      }},result));
  return compressed;
}
static void start(const std::vector<u8>& source, unsigned address=0, unsigned limit=10000, bool corrupt=false) {
  program_load::reset();
  const auto crc=mk61_crc32::finish(mk61_crc32::extend(
      mk61_crc32::INITIAL_STATE,source.data(),source.size()));
  char header[40]; std::snprintf(header,sizeof(header),"%04u %08X",address,crc^unsigned(corrupt));
  assert(program_load::start(header,limit));
  assert(program_load::blocked());
}
static bool send(const std::vector<u8>& packed, usize chunk, usize count) {
  for(usize i=0;i<count;i+=chunk) {
    const auto line=b91(packed.data()+i,std::min(chunk,count-i));
    if(!program_load::data(line.c_str())) return false;
  }
  return true;
}
static void roundtrip(const std::vector<u8>& source, usize chunk, unsigned address=0) {
  memory.fill(0xA5);
  const auto packed=pack(source);
  start(source,address);
  assert(send(packed,chunk,packed.size()));
  assert(!program_load::blocked());
  assert(program_load::written()==source.size());
  assert(std::equal(source.begin(),source.end(),memory.begin()+address));
  for(unsigned i=0;i<address;++i) assert(memory[i]==0xA5);
  for(usize i=address+source.size();i<memory.size();++i) assert(memory[i]==0xA5);
}

int main() {
  std::mt19937 rng(0x9100);
  // Canonical base91 covers both 13- and 14-bit pairs, odd tails, all bytes.
  for(unsigned size=1;size<=205;++size) {
    std::vector<u8> raw(size), check(size);
    for(auto& b:raw) b=rng();
    const auto text=b91(raw.data(),raw.size());
    usize got;
    assert(base91::decode(text.data(),text.size(),check.data(),check.size(),got));
    assert(got==raw.size() && raw==check);
    assert(!base91::decode(text.data(),text.size(),check.data(),size-1,got));
  }
  for(const auto* invalid:{"", "A", "A'", "A-", "A\\", "AA ", "~\""}) {
    u8 raw[8]; usize got;
    assert(!base91::decode(invalid,std::string(invalid).size(),raw,sizeof(raw),got));
  }
  assert(b91(reinterpret_cast<const u8*>("test"),4)=="fPNKd");
  for(unsigned size:{1,2,3,7,16,112,513,3584}) {
    for(unsigned pattern=0;pattern<4;++pattern) {
      std::vector<u8> source(size);
      for(unsigned i=0;i<size;++i) source[i]=pattern==0 ? 0 : pattern==1 ? 255 : pattern==2 ? i%251 : rng();
      for(usize chunk:{1,2,3,7,176,190}) roundtrip(source,chunk,5);
    }
  }
  for(unsigned trial=0;trial<100;++trial) {
    std::vector<u8> source(1+rng()%1024);
    for(auto& b:source) b=rng()%8;
    roundtrip(source,1+rng()%190,1000);
  }
  const std::vector<u8> source={1,2,3,4,5,6,1,2,3,4,5,6,0x50};
  const auto packed=pack(source);
  // Every truncated byte prefix is unfinished, including a valid line tail.
  for(usize length=0;length<packed.size();++length) {
    start(source);
    assert(send(packed,3,length));
    assert(program_load::blocked());
    program_load::cancel();
    assert(program_load::blocked());
  }
  start(source,0,10000,true);
  assert(!send(packed,3,packed.size()));
  assert(std::string(program_load::error()).find("CRC32")!=std::string::npos);
  assert(program_load::blocked());
  start(source,9990);
  assert(!send(packed,3,packed.size()));
  start(source,100,105);
  assert(!send(packed,3,packed.size()));
  start(source);
  write_limit=4;
  assert(!send(packed,3,packed.size()));
  write_limit=10000;
  auto extra=packed; extra.push_back(0);
  start(source);
  assert(!send(extra,190,extra.size()));
  start(source);
  assert(send(packed,190,packed.size()));
  assert(!program_load::data("AA"));
  program_load::reset();
  assert(!program_load::data("AA"));
  for(const char* bad:{"", "0 12345678", "00000 12345678", "0000 1234567", "0000 123456789", "0000 1234567G", "0000 12345678 junk"}) {
    program_load::reset();
    assert(!program_load::start(bad,10000));
  }
  // Malformed gamma/back-reference streams must terminate with bounded writes.
  for(unsigned trial=0;trial<2000;++trial) {
    std::vector<u8> noise(1+rng()%190);
    for(auto& b:noise) b=rng();
    start(source);
    (void)send(noise,190,noise.size());
    assert(program_load::written()<=10000);
  }
  std::puts("program load: Base91, fragmented ZX0, CRC, bounds, truncation and malformed streams PASS");
}
