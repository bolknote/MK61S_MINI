#include "external_cache.hpp"
#include "psram.hpp"
#include "dma_support.hpp"
#include "diagnostics.hpp"
#include <cstring>
namespace picocalc::external_cache {
namespace {
constexpr u32 MAGIC=0x50434332,MODULE_STRIDE=16384,SECTOR_BASE=4U*1024*1024,SECTOR_STRIDE=1024;
constexpr unsigned OWNER_LIMIT=384;
struct Header { u32 magic,generation;u64 key;u32 count,crc; };
static_assert(sizeof(Header)==24);
static_assert(MODULE_SLOTS*MODULE_STRIDE==SECTOR_BASE);
static_assert(SECTOR_BASE+SECTOR_SLOTS*SECTOR_STRIDE==psram::CAPACITY);
Statistics state{};
u32 module_generation=1,sector_generation=1,module_victim=0;
unsigned module_slot(u64 key) {
    key^=key>>33;key*=0xff51afd7ed558ccdULL;key^=key>>33;
    return (unsigned)key%MODULE_SLOTS;
}
unsigned owner_bytes(const char* owner) {
    if(!owner) return 0;
    unsigned n=0;while(n<OWNER_LIMIT && owner[n]) ++n;
    return n<OWNER_LIMIT?n+1:OWNER_LIMIT+1;
}
bool same_owner(u32 address,const char* owner,unsigned size) {
    if(!owner) return true;
    char stored[OWNER_LIMIT];
    return psram::read(address+sizeof(Header),stored,size) && !std::memcmp(stored,owner,size);
}
u32 module_address(u64 key,const char* owner,bool writing) {
    if(!state.ready) return psram::CAPACITY;
    const unsigned start=module_slot(key),size=owner_bytes(owner);
    for(unsigned probe=0;probe<MODULE_SLOTS;++probe) {
        const u32 address=((start+probe)%MODULE_SLOTS)*MODULE_STRIDE;
        Header header{};
        if(!psram::read(address,&header,sizeof(header))) return psram::CAPACITY;
        if((header.magic!=MAGIC && header.magic!=MAGIC+1) || header.generation!=module_generation)
            return writing?address:psram::CAPACITY;
        if(header.magic==MAGIC+(owner?1U:0U) && header.key==key && same_owner(address,owner,size)) return address;
    }
    // Only a genuinely full partition evicts an image. Hash collisions
    // probe unused slots rather than wasting most of the 4 MiB partition.
    return writing?(module_victim++%MODULE_SLOTS)*MODULE_STRIDE:psram::CAPACITY;
}
bool fetch(u32 address,u32 generation,u64 key,void* bytes,unsigned capacity,unsigned& count,const char* owner=nullptr) {
    Header header{};count=0;
    const unsigned owner_size=owner_bytes(owner);
    if(!state.ready || !psram::read(address,&header,sizeof(header)) ||
       owner_size>OWNER_LIMIT || header.magic!=MAGIC+(owner?1U:0U) || header.generation!=generation || header.key!=key ||
       !header.count || header.count>capacity) return false;
    if(!same_owner(address,owner,owner_size)) return false;
    if(!psram::read(address+sizeof(Header)+owner_size,bytes,header.count) ||
       dma_support::crc32((const u8*)bytes,header.count)!=header.crc) { ++state.rejected;return false; }
    count=header.count;return true;
}
void store(u32 address,u32 generation,u64 key,const void* bytes,unsigned count,const char* owner=nullptr) {
    if(!state.ready || !count) return;
    const unsigned owner_size=owner_bytes(owner);if(owner_size>OWNER_LIMIT) return;
    const u32 invalid=0;
    const Header header{MAGIC+(owner?1U:0U),generation,key,count,dma_support::crc32((const u8*)bytes,count)};
    // Publish the header only after all payload bytes have arrived. This
    // protects optional caches against an interrupted/failed bus transfer.
    if(psram::write(address,&invalid,sizeof(invalid)) &&
       (!owner || psram::write(address+sizeof(Header),owner,owner_size)) &&
       psram::write(address+sizeof(Header)+owner_size,bytes,count) &&
       psram::write(address,&header,sizeof(header))) ++state.stores;
}
bool clear(u32 base,unsigned slots,unsigned stride) {
    const u32 invalid=0;
    for(unsigned i=0;i<slots;++i) {
        if(!psram::write(base+i*stride,&invalid,sizeof(invalid))) return false;
        if(!(i&63)) diagnostics::feed_watchdog();
    }
    return true;
}
}
bool init() {
    state={};module_generation=sector_generation=1;module_victim=0;
    // A processor reset can leave the external chip powered. Explicitly
    // discard every header rather than trusting power-on contents or a
    // probabilistic boot nonce.
    state.ready=psram::ready() && clear(0,MODULE_SLOTS,MODULE_STRIDE) &&
        clear(SECTOR_BASE,SECTOR_SLOTS,SECTOR_STRIDE);
    return state.ready;
}
void suspend() { state.ready=false; }
void invalidate_modules() {
    if(++module_generation==0) { state.ready=clear(0,MODULE_SLOTS,MODULE_STRIDE);module_generation=1; }
}
void invalidate_sectors() {
    if(++sector_generation==0) { state.ready=clear(SECTOR_BASE,SECTOR_SLOTS,SECTOR_STRIDE);sector_generation=1; }
}
bool module(u64 key,void* bytes,unsigned capacity,unsigned& count,const char* owner) {
    const unsigned owner_size=owner_bytes(owner);
    if(owner_size>OWNER_LIMIT) { count=0;return false; }
    const unsigned maximum=MODULE_STRIDE-sizeof(Header)-owner_size;
    const u32 address=module_address(key,owner,false);
    const bool found=address!=psram::CAPACITY && fetch(address,module_generation,key,bytes,
        capacity<maximum?capacity:maximum,count,owner);
    if(!found) count=0;
    if(found) ++state.module_hits;else ++state.module_misses;return found;
}
void store_module(u64 key,const void* bytes,unsigned count,const char* owner) {
    const unsigned owner_size=owner_bytes(owner);
    if(owner_size<=OWNER_LIMIT && count<=MODULE_STRIDE-sizeof(Header)-owner_size) {
        const u32 address=module_address(key,owner,true);
        if(address!=psram::CAPACITY) store(address,module_generation,key,bytes,count,owner);
    }
}
bool sector(u32 lba,u8 bytes[512]) {
    unsigned count=0;
    const bool found=fetch(SECTOR_BASE+(lba%SECTOR_SLOTS)*SECTOR_STRIDE,sector_generation,lba,bytes,512,count) && count==512;
    if(found) ++state.sector_hits;else ++state.sector_misses;return found;
}
void store_sector(u32 lba,const u8 bytes[512]) {
    store(SECTOR_BASE+(lba%SECTOR_SLOTS)*SECTOR_STRIDE,sector_generation,lba,bytes,512);
}
void invalidate_sector(u32 lba) {
    if(!state.ready) return;
    const u32 invalid=0;
    (void)psram::write(SECTOR_BASE+(lba%SECTOR_SLOTS)*SECTOR_STRIDE,&invalid,sizeof(invalid));
}
Statistics statistics() { auto result=state;result.ready=result.ready && psram::ready();return result; }
}
