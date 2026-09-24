#include "crc32.hpp"
#include "mk61emu_core.h"
#include "program_load.hpp"
#include "program_store.hpp"
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
IK1302 m_IK1302 = {};
static std::vector<u8> file;
static unsigned fail_read_at = 10000;
static bool short_read = false;
static unsigned reads = 0;
static program_store::ProgramType file_type = program_store::ProgramType::MK61_BINARY;
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
namespace program_store {
bool entry_by_id(u16 id, Entry& out) {
  if(id != 1) return false;
  out = {}; out.id = id; out.type = file_type;
  out.kind = NodeKind::FILE; out.data_len = file.size(); return true;
}
bool read_range_id(u16 id, u16 offset, u8* out, u16 count, u16* got) {
  ++reads;
  if(id != 1 || offset > file.size() || offset >= fail_read_at) return false;
  const auto n = std::min<usize>(count,file.size()-offset);
  std::copy_n(file.data()+offset,n,out); *got = n - (short_read && n ? 1 : 0);
  return true;
}
}
static std::vector<u8> pack(const std::vector<u8>& source) {
  const u32 crc=mk61_crc32::calculate(source.data(),source.size());
  std::vector<u8> compressed={u8(crc),u8(crc>>8),u8(crc>>16),u8(crc>>24)};
  std::vector<u8> workspace(4*(source.size()+1));
  zx0::EncodeResult result;
  assert(zx0::encode(source.data(),source.size(),workspace.data(),workspace.size(),
      {&compressed,[](void* p,u8 v) {
        static_cast<std::vector<u8>*>(p)->push_back(v); return true;
      }},result));
  return compressed;
}
static void roundtrip(const std::vector<u8>& source, unsigned address=0) {
  memory.fill(0xA5); file=pack(source); reads=0; program_load::reset();
  assert(program_load::load(1,address,10000));
  assert(!program_load::blocked());
  assert(program_load::written()==source.size());
  assert(std::equal(source.begin(),source.end(),memory.begin()+address));
  for(unsigned i=0;i<address;++i) assert(memory[i]==0xA5);
  for(usize i=address+source.size();i<memory.size();++i) assert(memory[i]==0xA5);
  assert(reads==1+(file.size()-4+127)/128);
}

int main() {
  program_load::Request request={};
  using Syntax=program_load::Syntax;
  for(const char* arg:{"", "03", "0000", "3 ", "demo.m61", "2026.m61", "dir/a b.m61",
                      "2026 demo.m61", "1 demo.M61 ", "\"2026 demo.m61\""})
    assert(program_load::parse(arg,request)==Syntax::LEGACY);
  for(const char* arg:{"0 a.bin", "123 a.bin", "10000 a.bin", "99999999999999999999999 a.bin"})
    assert(program_load::parse(arg,request)==Syntax::INVALID);
  assert(program_load::parse(" 0250 dir/a b.bin",request)==Syntax::BINARY);
  assert(request.address==250 && std::string(request.path)=="dir/a b.bin");
  assert(program_load::parse("9999 last.bin",request)==Syntax::BINARY && request.address==9999);

  std::mt19937 rng(0x9100);
  for(unsigned size:{1,2,3,7,16,112,513,3584}) {
    for(unsigned pattern=0;pattern<4;++pattern) {
      std::vector<u8> source(size);
      for(unsigned i=0;i<size;++i) source[i]=pattern==0 ? 0 : pattern==1 ? 255 : pattern==2 ? i%256 : rng();
      roundtrip(source,5);
    }
  }
  for(unsigned trial=0;trial<100;++trial) {
    std::vector<u8> source(1+rng()%1024);
    for(auto& b:source) b=rng()%8;
    roundtrip(source,1000);
  }
  const std::vector<u8> source={1,2,3,4,5,6,1,2,3,4,5,6,0x50};
  const auto packed=pack(source);
  roundtrip(source,110); // Cross a bank and then load a separate range, without clearing.
  file=pack({42});
  assert(program_load::load(1,9999,10000));
  assert(memory[9999]==42 && std::equal(source.begin(),source.end(),memory.begin()+110));
  for(usize length=0;length<packed.size();++length) {
    program_load::reset(); file.assign(packed.begin(),packed.begin()+length);
    assert(!program_load::load(1,0,10000));
    if(length>4) assert(program_load::blocked());
  }
  program_load::reset(); file=packed; file[0]^=1;
  assert(!program_load::load(1,0,10000));
  assert(std::string(program_load::error()).find("CRC32")!=std::string::npos);
  assert(program_load::blocked());
  file=packed; assert(!program_load::load(1,0,10000)); // Explicit reset required.
  program_load::reset(); assert(!program_load::load(1,9990,10000));
  program_load::reset(); assert(!program_load::load(1,100,105));
  program_load::reset(); write_limit=4;
  assert(!program_load::load(1,0,10000)); assert(program_load::written()==4);
  write_limit=10000;
  program_load::reset(); file=packed; file.push_back(0);
  assert(!program_load::load(1,0,10000));
  assert(std::string(program_load::error()).find("after ZX0")!=std::string::npos);
  program_load::reset(); file=packed; fail_read_at=4;
  assert(!program_load::load(1,0,10000) && program_load::blocked());
  fail_read_at=10000; program_load::reset(); short_read=true;
  assert(!program_load::load(1,0,10000)); short_read=false;
  program_load::reset(); m_IK1302.comma=core_61::COMMA_RUN_POSITION; memory.fill(0xA5);
  assert(!program_load::load(1,0,10000)); m_IK1302.comma=0;
  assert(memory[0]==0xA5);
  assert(!program_load::load(0,0,10000));
  assert(!program_load::load(1,10000,10000));
  assert(!program_load::load(1,0,10001));
  file_type=program_store::ProgramType::MK61;
  assert(!program_load::load(1,0,10000)); file_type=program_store::ProgramType::MK61_BINARY;
  file.resize(4097); assert(!program_load::load(1,0,10000));
  // Malformed gamma/back-references must terminate with bounded writes.
  for(unsigned trial=0;trial<2000;++trial) {
    file.resize(5+rng()%190);
    for(auto& b:file) b=rng();
    program_load::reset(); (void)program_load::load(1,0,10000);
    assert(program_load::written()<=10000);
  }
  std::puts("binary load: file I/O, ZX0, CRC, separate ranges, bounds, truncation and malformed streams PASS");
}
