#include "external_cache.hpp"
#include "psram.hpp"
#include "buffers.hpp"
#include "dma_support.hpp"
#include "diagnostics.hpp"
#include <cstddef>
#include <cstring>
namespace picocalc::external_cache {
namespace {
using shared_memory::Buffer;
using shared_memory::Owner;
using shared_memory::EvictionDecision;
constexpr u32 MAGIC=0x50434332,WRAP=0x50435752;
constexpr unsigned OWNER_LIMIT=384,MAX_MODULE_BYTES=16360;
struct Header { u32 magic,generation;u64 key;u32 count,crc; };
static_assert(sizeof(Header)==24);
struct Record { Header header;u32 next;u16 owner_size,reserved; };
static_assert(sizeof(Record)==32);
constexpr unsigned SECTOR_STRIDE=sizeof(Header)+512;
constexpr unsigned INDEX_BYTES=MODULE_SLOTS*sizeof(u32);
Buffer modules,sectors;
Statistics state{};
u32 module_generation=1,sector_generation=1;
u32 module_head=INDEX_BYTES,module_tail=INDEX_BYTES,module_used=0;
u32 module_entries=0,module_payload=0;
unsigned sector_slots=0;
bool enabled=false,module_busy=false,sector_busy=false;
void empty_modules() {
    module_head=module_tail=INDEX_BYTES;module_used=module_entries=module_payload=0;
}
EvictionDecision evict_modules() {
    if(module_busy) return EvictionDecision::KEEP;
    empty_modules();++state.evictions;return EvictionDecision::RELEASE;
}
EvictionDecision evict_sectors() {
    if(sector_busy) return EvictionDecision::KEEP;
    sector_slots=0;++state.evictions;return EvictionDecision::RELEASE;
}
struct Busy { bool& flag; explicit Busy(bool& f):flag(f){flag=true;} ~Busy(){flag=false;} };
bool clear_sectors() {
    const u32 invalid=0;
    for(unsigned i=0;i<sector_slots;++i) {
        if(!sectors.write(i*SECTOR_STRIDE,&invalid,sizeof(invalid))) return false;
        if(!(i&63)) diagnostics::feed_watchdog();
    }
    return true;
}
bool clear_modules() {
    u32 heads[MODULE_SLOTS]{};empty_modules();
    return modules.write(0,heads,sizeof(heads));
}
void abandon_modules() {
    ++state.rejected;empty_modules();
    if(!modules.reset()) __builtin_trap();
}
bool ensure(bool module) {
    if(!enabled || !psram::ready()) return false;
    Buffer& buffer=module?modules:sectors;
    if(buffer.ok()) return module || sector_slots!=0;
    const auto free=shared_memory::buffer_statistics().external_largest;
    const bool other_live=module?sectors.ok():modules.ok();
    const unsigned limit=!other_live && free>=32768?free/2:free;
    for(unsigned bytes=4U*1024*1024;bytes>=16384;bytes/=2) {
        if(bytes>limit) continue;
        if(buffer.acquire_cache(module?Owner::LOADABLE_MODULE:Owner::USB_CACHE,
                bytes,module?evict_modules:evict_sectors)) {
            if(!module) sector_slots=bytes/SECTOR_STRIDE;
            if(module?clear_modules():clear_sectors()) return true;
            buffer.reset();if(!module) sector_slots=0;return false;
        }
    }
    return false;
}
unsigned bucket(u64 key) {
    key^=key>>33;key*=0xff51afd7ed558ccdULL;key^=key>>33;
    return (unsigned)key%MODULE_SLOTS;
}
unsigned owner_bytes(const char* owner) {
    if(!owner) return 0;
    unsigned n=0;while(n<OWNER_LIMIT && owner[n]) ++n;
    return n<OWNER_LIMIT?n+1:OWNER_LIMIT+1;
}
u32 span(const Record& record) { return (sizeof(Record)+record.owner_size+record.header.count+3)&~3U; }
bool record_at(u32 address,Record& record) {
    if(address<INDEX_BYTES || (address&3) || address>modules.size()-sizeof(record) ||
       !modules.read(address,&record,sizeof(record))) return false;
    const auto& h=record.header;
    return (h.magic==MAGIC || h.magic==MAGIC+1) && h.generation==module_generation &&
        h.count && h.count<=MAX_MODULE_BYTES && record.owner_size<=OWNER_LIMIT &&
        (h.magic==MAGIC)==(record.owner_size==0) && !record.reserved &&
        span(record)<=modules.size()-address &&
        (!record.next || (record.next>=INDEX_BYTES && !(record.next&3) && record.next<=modules.size()-sizeof(record)));
}
bool same_owner(u32 address,const Record& record,const char* owner,unsigned size) {
    if(record.owner_size!=size) return false;
    if(!size) return true;
    char stored[OWNER_LIMIT];
    return modules.read(address+sizeof(record),stored,size) && !std::memcmp(stored,owner,size);
}
bool pop_module() {
    if(!module_used) return false;
    u32 marker=0;
    const unsigned rest=modules.size()-module_tail;
    if(rest<sizeof(Record) || (modules.read(module_tail,&marker,sizeof(marker)) && marker==WRAP)) {
        if(rest>module_used) return false;
        module_used-=rest;module_tail=INDEX_BYTES;
    }
    if(!module_used || !module_entries) return false;
    Record oldest{};
    if(!record_at(module_tail,oldest) || span(oldest)>module_used || oldest.header.count>module_payload) return false;
    const unsigned index=bucket(oldest.header.key)*sizeof(u32);
    u32 address=0,previous=0;
    if(!modules.read(index,&address,sizeof(address))) return false;
    unsigned traversed=0;
    while(address && address!=module_tail) {
        Record record{};
        if(++traversed>module_entries || !record_at(address,record)) return false;
        previous=address;address=record.next;
    }
    if(address!=module_tail || !modules.write(previous?previous+offsetof(Record,next):index,&oldest.next,sizeof(oldest.next))) return false;
    module_tail+=span(oldest);module_used-=span(oldest);
    if(module_tail==modules.size()) module_tail=INDEX_BYTES;
    --module_entries;module_payload-=oldest.header.count;
    if(!module_used) empty_modules();
    return true;
}
bool reserve_module(unsigned bytes) {
    const unsigned capacity=modules.size()-INDEX_BYTES;
    if(bytes>capacity) return false;
    for(;;) {
        const unsigned remaining=modules.size()-module_head;
        const unsigned need=bytes+(remaining<bytes?remaining:0);
        if(need<=capacity-module_used) break;
        if(!pop_module()) { abandon_modules();return false; }
    }
    const unsigned remaining=modules.size()-module_head;
    if(remaining<bytes) {
        if(remaining && !modules.write(module_head,&WRAP,sizeof(WRAP))) { abandon_modules();return false; }
        module_used+=remaining;module_head=INDEX_BYTES;
    }
    return true;
}
}
bool init() {
    suspend();state={};module_generation=sector_generation=1;
    enabled=buffers::init() && psram::ready();
    const bool module=ensure(true),sector=ensure(false);
    state.ready=enabled && (module || sector);return state.ready;
}
void suspend() {
    enabled=false;
    if(!modules.reset() || !sectors.reset()) __builtin_trap();
    empty_modules();sector_slots=0;state.ready=false;
}
void invalidate_modules() {
    if(++module_generation==0) module_generation=1;
    if(modules.ok() && !clear_modules()) modules.reset();
    if(!module_busy && modules.ok() && modules.size()<4U*1024*1024 &&
       shared_memory::buffer_statistics().external_largest>=modules.size()) modules.reset();
    empty_modules();
}
void invalidate_sectors() {
    if(++sector_generation==0) {
        if(sectors.ok() && !clear_sectors()) sectors.reset();
        sector_generation=1;
    }
    if(!sector_busy && sectors.ok() && sectors.size()<4U*1024*1024 &&
       shared_memory::buffer_statistics().external_largest>=sectors.size()) {
        sectors.reset();sector_slots=0;
    }
}
bool module(u64 key,void* bytes,unsigned capacity,unsigned& count,const char* owner) {
    count=0;const unsigned owner_size=owner_bytes(owner);
    if(!bytes || owner_size>OWNER_LIMIT || !ensure(true)) return false;
    Busy busy(module_busy);u32 address=0;
    if(!modules.read(bucket(key)*sizeof(u32),&address,sizeof(address))) { abandon_modules();return false; }
    unsigned traversed=0;
    while(address) {
        Record record{};
        if(++traversed>module_entries || !record_at(address,record)) { abandon_modules();++state.module_misses;return false; }
        const auto& h=record.header;
        if(h.key==key && same_owner(address,record,owner,owner_size)) {
            if(h.count<=capacity && modules.read(address+sizeof(record)+owner_size,bytes,h.count) &&
               dma_support::crc32((const u8*)bytes,h.count)==h.crc) {
                count=h.count;++state.module_hits;return true;
            }
            if(h.count<=capacity) ++state.rejected;
            break;
        }
        address=record.next;
    }
    ++state.module_misses;return false;
}
void store_module(u64 key,const void* bytes,unsigned count,const char* owner) {
    const unsigned owner_size=owner_bytes(owner);
    if(!bytes || !count || count>MAX_MODULE_BYTES || owner_size>OWNER_LIMIT || !ensure(true)) return;
    Busy busy(module_busy);
    Record record{{MAGIC+(owner?1U:0U),module_generation,key,count,dma_support::crc32((const u8*)bytes,count)},0,(u16)owner_size,0};
    if(!reserve_module(span(record))) return;
    const unsigned index=bucket(key)*sizeof(u32);const u32 invalid=0;
    if(!modules.read(index,&record.next,sizeof(record.next)) ||
       !modules.write(module_head,&invalid,sizeof(invalid)) ||
       (owner_size && !modules.write(module_head+sizeof(record),owner,owner_size)) ||
       !modules.write(module_head+sizeof(record)+owner_size,bytes,count) ||
       !modules.write(module_head,&record,sizeof(record)) ||
       !modules.write(index,&module_head,sizeof(module_head))) { abandon_modules();return; }
    module_used+=span(record);module_head+=span(record);++module_entries;module_payload+=count;++state.stores;
}
bool sector(u32 lba,u8 bytes[512]) {
    if(!bytes || !ensure(false)) return false;
    Busy busy(sector_busy);Header header{};
    const u32 address=(lba%sector_slots)*SECTOR_STRIDE;
    bool found=sectors.read(address,&header,sizeof(header)) && header.magic==MAGIC &&
        header.generation==sector_generation && header.key==lba && header.count==512;
    if(found && (!sectors.read(address+sizeof(header),bytes,512) || dma_support::crc32(bytes,512)!=header.crc)) {
        ++state.rejected;found=false;
    }
    if(found) ++state.sector_hits;else ++state.sector_misses;return found;
}
void store_sector(u32 lba,const u8 bytes[512]) {
    if(!bytes || !ensure(false)) return;
    Busy busy(sector_busy);const u32 address=(lba%sector_slots)*SECTOR_STRIDE,invalid=0;
    const Header header{MAGIC,sector_generation,lba,512,dma_support::crc32(bytes,512)};
    if(sectors.write(address,&invalid,sizeof(invalid)) &&
       sectors.write(address+sizeof(header),bytes,512) && sectors.write(address,&header,sizeof(header))) ++state.stores;
}
void invalidate_sector(u32 lba) {
    if(!enabled || !sectors.ok() || !sector_slots) return;
    Busy busy(sector_busy);const u32 invalid=0;
    (void)sectors.write((lba%sector_slots)*SECTOR_STRIDE,&invalid,sizeof(invalid));
}
Statistics statistics() {
    auto result=state;result.ready=enabled && psram::ready();
    result.module_bytes=modules.size();result.sector_bytes=sectors.size();
    result.module_entries=module_entries;result.module_payload=module_payload;result.module_used=module_used;
    result.sector_slots=sector_slots;return result;
}
}
