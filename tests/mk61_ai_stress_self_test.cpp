#include "mk61_ai_stress.hpp"
#include "ai_psram_read_clock.hpp"
#include <array>
#include <cassert>
#include <cstdio>
using namespace mk61ai::diagnostic;
struct Memory {
  std::array<unsigned char,65536> bytes{};
  unsigned fault=0,writes=0,reads=0;
  bool write(unsigned offset,const void *data,unsigned n) {
    assert(n==256 && offset+n<=bytes.size());++writes;
    if(fault==1)return false;
    std::memcpy(bytes.data()+offset,data,fault==2?13:n);
    if(fault==2)return false;
    if(fault==3)bytes[offset+17]^=64;
    return true;
  }
  bool read(unsigned offset,void *data,unsigned n) {
    assert(n==256 && offset+n<=bytes.size());++reads;
    if(fault==4)return false;
    std::memcpy(data,bytes.data()+offset,fault==5?13:n);
    if(fault==5)return false;
    if(fault==6)static_cast<unsigned char*>(data)[17]^=64;
    return true;
  }
};
int main() {
  const auto div=picocalc::ai_psram_read_clock::divider256(270000000,692);
  Memory memory;StressDiagnostics r;unsigned char want[256]{},got[256]{};
  r.busy_entered=true;
  for(unsigned i=0;i<2048;++i) {
    assert(r.memory(memory,i,want,got));
    assert(r.iteration==i && r.address==((i*4093U)&(65536-256)));
    assert(r.write==1 && r.read==1 && r.crc_match && r.busy_entered);
  }
  for(unsigned fault=1;fault<=6;++fault) {
    memory.fault=fault;memory.writes=memory.reads=0;r={};
    assert(!r.memory(memory,123,want,got));
    assert(r.iteration==123 && r.address==((123*4093U)&(65536-256)) && memory.writes==1);
    if(fault<=2)assert(r.failure==StressFailure::WRITE && r.write==2 && r.read==0 && !memory.reads);
    else if(fault==4||fault==5)assert(r.failure==StressFailure::READ && r.write==1 && r.read==2);
    else {
      assert(r.failure==StressFailure::MEMORY_BYTES && r.write==1 && r.read==1);
      assert(r.first_bad==17 && r.expected==want[17] && r.actual==(want[17]^64) && !r.crc_match);
      // A stable re-read without a rewrite distinguishes read corruption.
      memory.fault=0;assert(memory.read(r.address,got,256));
      const bool stable=StressDiagnostics::crc(got,256)==r.expected_crc;
      assert(stable==(fault==6));
    }
  }
  const float reference[]={1,2,3,4};float output[]={1,2,3,4};r={};
  assert(r.math(0,0,true,reference,output,sizeof(output)));
  assert(!r.math(3,0,true,reference,output,sizeof(output)) && r.failure==StressFailure::LOCAL_MATH);
  r={};assert(!r.math(0,3,true,reference,output,sizeof(output)) && r.failure==StressFailure::REMOTE_MATH);
  r={};reinterpret_cast<unsigned char*>(output)[5]^=1;
  assert(!r.math(0,0,false,reference,output,sizeof(output)) && r.failure==StressFailure::MATH_BYTES);
  assert(r.math_byte==5 && r.address==~0U && !r.write && !r.read);
  const unsigned char standard[]="123456789";
  assert(StressDiagnostics::crc(standard,9)==0xcbf43926U);
  std::printf("HOST private-stress logic at read-divider%u:2048 blocks, write/read/partial/byte/CRC/math fault injection and stable reread discrimination PASS; no hardware inference claimed\n",div);
}
