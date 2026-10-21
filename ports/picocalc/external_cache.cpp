#include "external_cache.hpp"
#include "psram.hpp"
#include "buffers.hpp"
#include "dma_support.hpp"
#include "diagnostics.hpp"
#include <cstring>
namespace picocalc::external_cache {
namespace {
using shared_memory::Buffer;
using shared_memory::Owner;
using shared_memory::EvictionDecision;
constexpr u32 MAGIC=0x50434332,MODULE_STRIDE=16384,SECTOR_STRIDE=1024;
constexpr unsigned OWNER_LIMIT=384;
struct Header { u32 magic,generation;u64 key;u32 count,crc; };
static_assert(sizeof(Header)==24);
Buffer modules,sectors;
Statistics state{};
u32 module_generation=1,sector_generation=1,module_victim=0;
unsigned module_slots=0,sector_slots=0;
bool enabled=false,module_busy=false,sector_busy=false;
EvictionDecision evict_modules() {
    if(module_busy) return EvictionDecision::KEEP;
    module_slots=0;module_victim=0;++state.evictions;return EvictionDecision::RELEASE;
}
EvictionDecision evict_sectors() {
    if(sector_busy) return EvictionDecision::KEEP;
    sector_slots=0;++state.evictions;return EvictionDecision::RELEASE;
}
struct Busy { bool& flag; explicit Busy(bool& f):flag(f){flag=true;} ~Busy(){flag=false;} };
bool clear(Buffer& buffer,unsigned slots,unsigned stride) {
    const u32 invalid=0;
    for(unsigned i=0;i<slots;++i) {
        if(!buffer.write(i*stride,&invalid,sizeof(invalid))) return false;
        if(!(i&63)) diagnostics::feed_watchdog();
    }
    return true;
}
bool ensure(bool module) {
    if(!enabled || !psram::ready()) return false;
    Buffer& buffer=module?modules:sectors;
    unsigned& slots=module?module_slots:sector_slots;
    if(buffer.ok()) return slots!=0;
    const unsigned stride=module?MODULE_STRIDE:SECTOR_STRIDE;
    const auto free=shared_memory::buffer_statistics().external_largest;
    const bool other_live=module?sectors.ok():modules.ok();
    const unsigned limit=!other_live && free>=32768?free/2:free;
    // Caches never evict another lease to fill themselves. A required user
    // buffer can revoke a whole cache, which later returns at a smaller size.
    for(unsigned bytes=4U*1024*1024;bytes>=16384;bytes/=2) {
        if(bytes>limit) continue;
        if(buffer.acquire_cache(module?Owner::LOADABLE_MODULE:Owner::USB_CACHE,
                bytes,module?evict_modules:evict_sectors)) {
            slots=bytes/stride;
            if(clear(buffer,slots,stride)) return true;
            buffer.reset();slots=0;return false;
        }
    }
    return false;
}
unsigned module_slot(u64 key) {
    key^=key>>33;key*=0xff51afd7ed558ccdULL;key^=key>>33;
    return (unsigned)key%module_slots;
}
unsigned owner_bytes(const char* owner) {
    if(!owner) return 0;
    unsigned n=0;while(n<OWNER_LIMIT && owner[n]) ++n;
    return n<OWNER_LIMIT?n+1:OWNER_LIMIT+1;
}
bool same_owner(Buffer& buffer,u32 address,const char* owner,unsigned size) {
    if(!owner) return true;
    char stored[OWNER_LIMIT];
    return buffer.read(address+sizeof(Header),stored,size) && !std::memcmp(stored,owner,size);
}
u32 module_address(u64 key,const char* owner,bool writing) {
    const unsigned start=module_slot(key),size=owner_bytes(owner);
    for(unsigned probe=0;probe<module_slots;++probe) {
        const u32 address=((start+probe)%module_slots)*MODULE_STRIDE;
        Header header{};
        if(!modules.read(address,&header,sizeof(header))) return UINT32_MAX;
        if((header.magic!=MAGIC && header.magic!=MAGIC+1) || header.generation!=module_generation)
            return writing?address:UINT32_MAX;
        if(header.magic==MAGIC+(owner?1U:0U) && header.key==key && same_owner(modules,address,owner,size)) return address;
    }
    return writing?(module_victim++%module_slots)*MODULE_STRIDE:UINT32_MAX;
}
bool fetch(Buffer& buffer,u32 address,u32 generation,u64 key,void* bytes,unsigned capacity,unsigned& count,const char* owner=nullptr) {
    Header header{};count=0;
    const unsigned owner_size=owner_bytes(owner);
    if(!buffer.read(address,&header,sizeof(header)) || owner_size>OWNER_LIMIT ||
       header.magic!=MAGIC+(owner?1U:0U) || header.generation!=generation || header.key!=key ||
       !header.count || header.count>capacity || !same_owner(buffer,address,owner,owner_size)) return false;
    if(!buffer.read(address+sizeof(Header)+owner_size,bytes,header.count) ||
       dma_support::crc32((const u8*)bytes,header.count)!=header.crc) { ++state.rejected;return false; }
    count=header.count;return true;
}
void store(Buffer& buffer,u32 address,u32 generation,u64 key,const void* bytes,unsigned count,const char* owner=nullptr) {
    if(!count) return;
    const unsigned owner_size=owner_bytes(owner);if(owner_size>OWNER_LIMIT) return;
    const u32 invalid=0;
    const Header header{MAGIC+(owner?1U:0U),generation,key,count,dma_support::crc32((const u8*)bytes,count)};
    if(buffer.write(address,&invalid,sizeof(invalid)) &&
       (!owner || buffer.write(address+sizeof(Header),owner,owner_size)) &&
       buffer.write(address+sizeof(Header)+owner_size,bytes,count) &&
       buffer.write(address,&header,sizeof(header))) ++state.stores;
}
}
bool init() {
    suspend();state={};module_generation=sector_generation=1;module_victim=0;
    enabled=buffers::init() && psram::ready();
    // Never trust retained PSRAM headers after a CPU reset. Every allocation
    // clears only its own headers, preserving other live shared buffers.
    const bool module=ensure(true),sector=ensure(false);
    state.ready=enabled && (module || sector);return state.ready;
}
void suspend() {
    enabled=false;
    if(!modules.reset() || !sectors.reset()) __builtin_trap();
    module_slots=sector_slots=0;state.ready=false;
}
void invalidate_modules() {
    if(++module_generation==0) {
        if(modules.ok() && !clear(modules,module_slots,MODULE_STRIDE)) modules.reset();
        module_generation=1;
    }
}
void invalidate_sectors() {
    if(++sector_generation==0) {
        if(sectors.ok() && !clear(sectors,sector_slots,SECTOR_STRIDE)) sectors.reset();
        sector_generation=1;
    }
}
bool module(u64 key,void* bytes,unsigned capacity,unsigned& count,const char* owner) {
    count=0;const unsigned owner_size=owner_bytes(owner);
    if(owner_size>OWNER_LIMIT || !ensure(true)) return false;
    Busy busy(module_busy);
    const unsigned maximum=MODULE_STRIDE-sizeof(Header)-owner_size;
    const u32 address=module_address(key,owner,false);
    const bool found=address!=UINT32_MAX && fetch(modules,address,module_generation,key,bytes,
        capacity<maximum?capacity:maximum,count,owner);
    if(!found) count=0;
    if(found) ++state.module_hits;else ++state.module_misses;return found;
}
void store_module(u64 key,const void* bytes,unsigned count,const char* owner) {
    const unsigned owner_size=owner_bytes(owner);
    if(owner_size<=OWNER_LIMIT && count<=MODULE_STRIDE-sizeof(Header)-owner_size && ensure(true)) {
        Busy busy(module_busy);
        const u32 address=module_address(key,owner,true);
        if(address!=UINT32_MAX) store(modules,address,module_generation,key,bytes,count,owner);
    }
}
bool sector(u32 lba,u8 bytes[512]) {
    if(!ensure(false)) return false;
    Busy busy(sector_busy);unsigned count=0;
    const bool found=fetch(sectors,(lba%sector_slots)*SECTOR_STRIDE,sector_generation,lba,bytes,512,count) && count==512;
    if(found) ++state.sector_hits;else ++state.sector_misses;return found;
}
void store_sector(u32 lba,const u8 bytes[512]) {
    if(!ensure(false)) return;
    Busy busy(sector_busy);
    store(sectors,(lba%sector_slots)*SECTOR_STRIDE,sector_generation,lba,bytes,512);
}
void invalidate_sector(u32 lba) {
    if(!enabled || !sectors.ok() || !sector_slots) return;
    Busy busy(sector_busy);const u32 invalid=0;
    (void)sectors.write((lba%sector_slots)*SECTOR_STRIDE,&invalid,sizeof(invalid));
}
Statistics statistics() {
    auto result=state;result.ready=enabled && psram::ready();
    result.module_bytes=modules.size();result.sector_bytes=sectors.size();return result;
}
}
