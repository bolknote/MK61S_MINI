#include "../code/c9_inode_wire.hpp"
#include <array>
#include <cassert>
#include <cstring>
#include <cstdio>
#include <sys/mman.h>
#include <unistd.h>
using namespace c9_inode_wire;
static auto fields(const Inode& v) {
  return std::array<u32,12>{{v.address,v.data_len,v.record_len,v.parent_id,
    v.first_child,v.next_sibling,v.prev_sibling,v.name_hash,v.kind_type,v.flags,
    v.exported_size,v.fat_address}};
}
int main() {
  u32 rng=0xC90026;
  const auto next=[&]() { rng=rng*1664525U+1013904223U; return rng; };
  const unsigned widths[]={4,2,2,2,2,2,2,2,1,1,2,4};
  for(unsigned n=0;n<10000;++n) {
    Inode v;std::memset(&v,0xD3,sizeof(v));
    v.address=next();v.data_len=(u16)next();v.record_len=(u16)next();
    v.parent_id=(u16)next();v.first_child=(u16)next();v.next_sibling=(u16)next();
    v.prev_sibling=(u16)next();v.name_hash=(u16)next();v.kind_type=(u8)next();
    v.flags=(u8)next();v.exported_size=(u16)next();v.fat_address=next();
    std::array<u8,26> expected={};unsigned pos=0;
    const auto values=fields(v);
    for(unsigned i=0;i<values.size();++i)
      for(unsigned byte=0;byte<widths[i];++byte) expected[pos++]=(u8)(values[i]>>(8*byte));
    assert(pos==26);
    for(unsigned align=0;align<8;++align) {
      u8 out[42];std::memset(out,0x59,sizeof(out));encode(v,out+align);
      assert(!std::memcmp(out+align,expected.data(),26));
      for(unsigned i=0;i<align;++i)assert(out[i]==0x59);
      for(unsigned i=align+26;i<sizeof(out);++i)assert(out[i]==0x59);
      assert(fields(decode(out+align))==values);
    }
    if(n==0) {
      const auto page=(usize)sysconf(_SC_PAGESIZE);
      auto* p=(u8*)mmap(nullptr,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
      assert(p!=MAP_FAILED && !mprotect(p+page,page,PROT_NONE));
      auto* end=p+page-26;std::memcpy(end,expected.data(),26);
      assert(fields(decode(end))==values);encode(v,end);
      assert(!std::memcmp(end,expected.data(),26));assert(!munmap(p,page*2));
    }
  }
  puts("C9 inode wire: 10000 independent golden records, 8 alignments, padding/canaries and exact protected-page tails PASS");
}
