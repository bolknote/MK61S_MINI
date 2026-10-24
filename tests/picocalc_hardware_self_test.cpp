#include "psram.hpp"
#include "external_cache.hpp"
#include "lcd_update.hpp"
#include "dma_support.hpp"
#include "buffers.hpp"
#include "source_document.hpp"
#include <string>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include <array>
#include <algorithm>
namespace picocalc::diagnostics { void feed_watchdog() {} u64 timestamp() { static u64 tick=0;return ++tick; } }
int main() {
    using namespace picocalc;
    assert(!psram::ready() && !external_cache::init());
    std::vector<u8> ram(psram::CAPACITY,0xA5);
    psram::test_memory(ram.data(),ram.size()-1);assert(!psram::init());
    psram::test_memory(ram.data(),ram.size());assert(psram::init());
    std::array<u8,2051> input{},output{};
    for(unsigned i=0;i<input.size();++i) input[i]=(u8)(i*17+41);
    for(u32 offset : {0U,1U,1023U,1024U,0x3FFFFFU,psram::CAPACITY-(u32)input.size()}) {
        assert(psram::write(offset,input.data(),input.size()));
        assert(psram::read(offset,output.data(),output.size()) && output==input);
    }
    assert(psram::read(psram::CAPACITY,nullptr,0));
    assert(psram::write(psram::CAPACITY,nullptr,0));
    assert(!psram::read(psram::CAPACITY,output.data(),1));
    assert(!psram::write(0xFFFFFFFF,input.data(),2));
    assert(!psram::write(0,nullptr,1));
    assert(external_cache::init());
    std::array<u8,512> sector{},read{};
    for(unsigned i=0;i<sector.size();++i) sector[i]=(u8)(i^0x69);
    for(u32 lba : {0U,1U,4095U,65536U,0xFFFFFFFEU}) {
        external_cache::store_sector(lba,sector.data());
        assert(external_cache::sector(lba,read.data()) && read==sector);
        external_cache::invalidate_sector(lba);
        assert(!external_cache::sector(lba,read.data()));
    }
    external_cache::store_sector(17,sector.data());
    external_cache::store_sector(17+external_cache::SECTOR_SLOTS,input.data());
    assert(!external_cache::sector(17,read.data()));
    assert(external_cache::sector(17+external_cache::SECTOR_SLOTS,read.data()) &&
        !std::memcmp(read.data(),input.data(),read.size()));
    external_cache::invalidate_sectors();
    assert(!external_cache::sector(17+external_cache::SECTOR_SLOTS,read.data()));
    unsigned used=0;
    std::vector<u8> image(9728),decoded(image.size());
    for(unsigned i=0;i<image.size();++i) image[i]=(u8)(i*23+19);
    for(u64 key : {1ULL,0xFFFFFFFFULL,0x123456789ABCDEF0ULL}) {
        external_cache::store_module(key,image.data(),image.size());
        assert(external_cache::module(key,decoded.data(),decoded.size(),used) &&
            used==image.size() && decoded==image);
        assert(!external_cache::module(key,decoded.data(),image.size()-1,used));
    }
    // Corrupt all payloads in the emulated external chip; CRC protection must
    // reject them without publishing a partial validated module.
    unsigned corrupted=0;
    for(auto at=ram.begin();at!=ram.end();) {
        at=std::search(at,ram.end(),image.begin(),image.end());
        if(at==ram.end()) break;
        at[17]^=1;++corrupted;at+=image.size();
    }
    assert(corrupted>=3);
    const auto rejected=external_cache::statistics().rejected;
    assert(!external_cache::module(0x123456789ABCDEF0ULL,decoded.data(),decoded.size(),used));
    assert(external_cache::statistics().rejected>rejected);
    external_cache::store_module(19,image.data(),image.size());
    external_cache::store_module(27,image.data(),image.size(),"/owned/first.bas");
    assert(external_cache::module(27,decoded.data(),decoded.size(),used,"/owned/first.bas"));
    assert(!external_cache::module(27,decoded.data(),decoded.size(),used,"/owned/other.bas"));
    assert(!external_cache::module(27,decoded.data(),decoded.size(),used));
    external_cache::store_module(27,image.data(),image.size(),"/owned/other.bas");
    assert(external_cache::module(27,decoded.data(),decoded.size(),used,"/owned/first.bas"));
    assert(external_cache::module(27,decoded.data(),decoded.size(),used,"/owned/other.bas"));
    external_cache::invalidate_modules();
    assert(!external_cache::module(19,decoded.data(),decoded.size(),used));
    // Every slot is usable even when home buckets collide. A bounded table
    // must not evict a VM merely because its hash shares an occupied bucket.
    for(unsigned i=0;i<external_cache::MODULE_SLOTS;++i)
        external_cache::store_module(0x10000+i,sector.data(),sector.size());
    for(unsigned i=0;i<external_cache::MODULE_SLOTS;++i) {
        assert(external_cache::module(0x10000+i,decoded.data(),decoded.size(),used));
        assert(used==sector.size() && !std::memcmp(decoded.data(),sector.data(),used));
    }
    external_cache::store_module(0x20000,sector.data(),sector.size());
    assert(external_cache::module(0x20000,decoded.data(),decoded.size(),used));
    external_cache::invalidate_modules();
    // Short modules consume their real record size, rather than one 16-KiB
    // slot. These 1000 distinct programs must coexist in the original 4 MiB.
    for(unsigned i=0;i<1000;++i) external_cache::store_module(0x30000+i,sector.data(),sector.size(),"/short.bas");
    auto packed=external_cache::statistics();
    assert(packed.module_entries==1000 && packed.module_payload==512000 && packed.module_used==556000);
    for(unsigned i=0;i<1000;++i) {
        assert(external_cache::module(0x30000+i,decoded.data(),decoded.size(),used,"/short.bas"));
        assert(used==512 && !std::memcmp(decoded.data(),sector.data(),512));
    }
    assert(packed.sector_slots==external_cache::SECTOR_SLOTS && packed.sector_slots>7800);
    // Repeatedly wrap the packed FIFO, including non-word owner lengths.
    for(unsigned i=0;i<2200;++i) external_cache::store_module(0x40000+i,image.data(),image.size(),"/wrapping/program.bas");
    for(unsigned i=2200-256;i<2200;++i)
        assert(external_cache::module(0x40000+i,decoded.data(),decoded.size(),used,"/wrapping/program.bas") && decoded==image);
    assert(!external_cache::module(0x40000,decoded.data(),decoded.size(),used,"/wrapping/program.bas"));
    external_cache::store_module(19,image.data(),image.size());
    // The full external chip belongs to one allocator. A required 6 MiB
    // user buffer reclaims caches; rebuilding them cannot touch its bytes.
    {
        shared_memory::Buffer large;
        assert(large.acquire(shared_memory::Owner::APPLICATION,6U*1024*1024,
                             shared_memory::BufferAccess::EXTERNAL_ONLY));
        assert(large.fill(0x79));
        external_cache::store_module(777,image.data(),image.size());
        external_cache::store_sector(77,sector.data());
        assert(external_cache::module(777,decoded.data(),decoded.size(),used) && decoded==image);
        assert(external_cache::sector(77,read.data()) && read==sector);
        assert(external_cache::statistics().evictions>=2);
        std::array<u8,513> verify{};
        for(unsigned at:{0U,1023U,4095U,6U*1024*1024-513}) {
            assert(large.read(at,verify.data(),verify.size()));
            for(u8 b:verify) assert(b==0x79);
        }
        assert(shared_memory::validate_buffer_invariants());
    }
    // Editor originals/drafts and an unsaved parent snapshot share the same
    // PSRAM owner with both packed caches and a large native APP allocation.
    {
        std::string expected(65000,'A');
        for(unsigned i=0;i<expected.size();++i) expected[i]=(char)('A'+i%26);
        for(unsigned i=70;i<expected.size();i+=71) expected[i]='\n';
        SourceDocument document;
        assert(document.load({&expected,[](void* raw,u16 at,u8* out,u16 n) {
            std::memcpy(out,((std::string*)raw)->data()+at,n);return true;
        },(u16)expected.size()}));
        u16 cursor=15000;
        assert(document.replace(cursor,cursor,"FIRST",cursor));expected.insert(15000,"FIRST");
        cursor=58000;assert(document.replace(cursor,cursor,"LATE",cursor));expected.insert(58000,"LATE");
        shared_memory::Buffer snapshot,native;
        assert(snapshot.acquire(shared_memory::Owner::STORAGE_WORKSPACE,expected.size(),shared_memory::BufferAccess::BLOCK));
        assert(!snapshot.data() && snapshot.write(0,expected.data(),expected.size()));
        assert(native.acquire(shared_memory::Owner::APPLICATION,6U*1024*1024,shared_memory::BufferAccess::EXTERNAL_ONLY));
        assert(native.fill(0xC7));
        for(unsigned i=0;i<600;++i) {
            external_cache::store_module(0x50000+i,sector.data(),sector.size(),"/coexisting.bas");
            external_cache::store_sector(1000+i,sector.data());
        }
        assert(external_cache::module(0x50000+599,decoded.data(),decoded.size(),used,"/coexisting.bas") && used==512);
        assert(external_cache::sector(1599,read.data()) && read==sector);
        std::vector<u8> source(expected.size()),saved(expected.size());
        assert(document.read(0,source.data(),(u16)source.size()) && snapshot.read(0,saved.data(),saved.size()));
        assert(!std::memcmp(source.data(),expected.data(),source.size()) && source==saved);
        for(unsigned at:{0U,1021U,6U*1024*1024-512}) {
            assert(native.read(at,read.data(),read.size()));for(u8 byte:read) assert(byte==0xC7);
        }
        assert(document.park() && document.statistics().window_bytes==0);
        assert(document.read(0,source.data(),(u16)source.size()) && source==saved);
        assert(shared_memory::validate_buffer_invariants());
    }
    external_cache::invalidate_modules();external_cache::invalidate_sectors();
    external_cache::store_module(778,image.data(),image.size());external_cache::store_sector(78,sector.data());
    assert(external_cache::statistics().module_bytes==4U*1024*1024);
    assert(external_cache::statistics().sector_bytes==4U*1024*1024);
    assert(external_cache::module(778,decoded.data(),decoded.size(),used) && decoded==image);
    assert(external_cache::sector(78,read.data()) && read==sector);
    assert(buffers::self_test().passed);
    assert(external_cache::init()); // MCU reset with retained powered PSRAM.
    assert(!external_cache::module(19,decoded.data(),decoded.size(),used));
    assert(dma_support::crc32((const u8*)"123456789",9)==0xCBF43926U);
    psram::test_memory(nullptr,0);assert(!psram::init());
    assert(!external_cache::sector(0,read.data()));
    assert(!external_cache::statistics().ready);
    std::puts("PicoCalc PSRAM: boundaries, page crossings, partitions, collisions, CRC rejection, invalidation, warm reset and missing-chip fallback PASS");
}
