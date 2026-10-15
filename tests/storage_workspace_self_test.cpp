#include "../code/storage_workspace.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace storage_workspace;
static void payload(const u8* memory,usize bytes,u8 expected) {
  for(usize i=0;i<bytes;++i)assert(memory[i]==expected);
}
int main() {
  using shared_memory::Arena;
  const usize total=shared_memory::capacity(Arena::OVERLAY);
  const auto start=(uintptr_t)shared_memory::adjust_heap(0);
  unsigned calls=0;
  assert(!with_buffer(Owner::FILE_WRITE,WRITE_BYTES,[&](u8* memory) {
    ++calls;std::memset(memory,0x61,WRITE_BYTES);return false;
  }));
  assert(calls==1 && shared_memory::capacity(Arena::OVERLAY)==total);
  assert(shared_memory::validate_invariants());
  {
    shared_memory::Lease full(Arena::OVERLAY,shared_memory::Owner::USB_SCREEN,total);
    assert(full.ok());std::memset(full.data(),0x39,total);
    for(unsigned cycle=0;cycle<30;++cycle) {
      calls=0;
      assert(with_buffer(Owner::FILE_WRITE,WRITE_BYTES,[&](u8* memory) {
        ++calls;
        assert((uintptr_t)memory<start || (uintptr_t)memory>=start+total);
        std::memset(memory,0x71,WRITE_BYTES);
        unsigned nested=0;
        assert(!with_buffer(Owner::FILE_WRITE,1,[&](u8*){++nested;return true;}));
        assert(nested==0);
        Lease batch(Owner::IMPORT_BATCH,BATCH_BYTES);
        assert(batch.ok() && batch.data()==memory+WRITE_BYTES);
        std::memset(batch.data(),0x82,BATCH_BYTES);
        payload(memory,WRITE_BYTES,0x71);
        return true;
      }));
      assert(calls==1);
      calls=0;
      assert(with_buffer(Owner::IMPORT_BATCH,BATCH_BYTES,[&](u8* memory) {
        ++calls;std::memset(memory,0x82,BATCH_BYTES);
        assert(with_buffer(Owner::FILE_WRITE,WRITE_BYTES,[&](u8* writer) {
          assert(writer+WRITE_BYTES==memory);std::memset(writer,0x71,WRITE_BYTES);return true;
        }));
        payload(memory,BATCH_BYTES,0x82);return true;
      }));
      assert(calls==1);
      calls=0;
      assert(!with_buffer(Owner::SIDECAR_SCAN,SIZE,[&](u8* memory) {
        ++calls;std::memset(memory,0x93,SIZE);
        unsigned nested=0;
        assert(!with_buffer(Owner::FILE_WRITE,1,[&](u8*){++nested;return true;}));
        assert(nested==0);payload(memory,SIZE,0x93);return false;
      }));
      assert(calls==1);
      payload(full.data(),full.size(),0x39);
      assert(shared_memory::validate_invariants());
    }
    calls=0;
    try {
      (void)with_buffer(Owner::FILE_WRITE,WRITE_BYTES,[&](u8*)->bool {
        ++calls;throw 43;
      });
      assert(false);
    } catch(int value) {assert(value==43 && calls==1);}
    assert(with_buffer(Owner::FILE_WRITE,1,[](u8*){return true;}));
    payload(full.data(),full.size(),0x39);
    assert(shared_memory::validate_invariants());
  }
  assert(shared_memory::capacity(Arena::OVERLAY)==total);
  assert(shared_memory::adjust_heap(0)==(void*)start);
  puts("Storage workspace: full pinned pool, contiguous nested partitions, exclusion, no double execution, error/exception cleanup and reuse PASS");
}
