#ifndef MK61_PICOCALC_LANGUAGE_CACHE_HPP
#define MK61_PICOCALC_LANGUAGE_CACHE_HPP
#include "language_bytecode.hpp"
#include "rust_types.h"

namespace picocalc::language_cache {
struct Prepared {
    language_vm::View view{};
    u32 generation=0;
    u16 slot=0xFFFF;
    explicit operator bool() const { return generation && slot!=0xFFFF; }
};
struct Statistics {
    u32 ram_hits=0,ram_misses=0,disk_hits=0,disk_misses=0;
    u32 compiles=0,stores=0,rejected=0,evictions=0;
    u32 packs=0,thaws=0;
    u32 psram_hits=0,psram_misses=0;
    unsigned allocated=0,used=0,packed=0;
};
Prepared find(const char* path,language_vm::Language,bool rf_available,
              u8* scratch=nullptr,unsigned scratch_size=0);
void bind(void* owner,void* bytes,unsigned capacity);
void revoke(void* owner);
void detach(void* owner);
void release(Prepared&);
bool load(const char* path,language_vm::Language,bool rf_available,
          const char* source,u16 length,u8* image,language_vm::View&);
void remember(const char* path,bool rf_available,u32 revision,
              const char* source,u16 length,const language_vm::View&,bool persist=true);
void compilation();
// The owner lends unused source-buffer space. A running image stays pinned
// until its VM call (including INPUT) has returned.
void discard();
Statistics statistics();
}
#endif
