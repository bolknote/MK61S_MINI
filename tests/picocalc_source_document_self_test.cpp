#include "source_document.hpp"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

namespace {
std::vector<u8> memory(512*1024);
int writes_before_failure=-1;
int reads_before_failure=-1;
bool fail_read=false;
bool available() { return true; }
bool read(u32 at,void* bytes,usize n) {
    if(fail_read || reads_before_failure==0 || at>memory.size() || n>memory.size()-at) return false;
    if(reads_before_failure>0) --reads_before_failure;
    std::memcpy(bytes,memory.data()+at,n);return true;
}
bool write(u32 at,const void* bytes,usize n) {
    if(writes_before_failure==0 || at>memory.size() || n>memory.size()-at) return false;
    if(writes_before_failure>0) --writes_before_failure;
    std::memcpy(memory.data()+at,bytes,n);return true;
}
bool input(void* raw,u16 at,u8* out,u16 n) {
    std::memcpy(out,((std::string*)raw)->data()+at,n);return true;
}
void equal(const picocalc::SourceDocument& document,const std::string& expected) {
    assert(document.size()==expected.size());
    std::vector<u8> actual(expected.size());
    assert(document.read(0,actual.data(),(u16)actual.size()));
    assert(!std::memcmp(actual.data(),expected.data(),actual.size()));
}
}
// Only the external bus is mocked; exercise the real shared Buffer owner and
// the same source::Document used by STM32, including failed bank publication.
namespace picocalc::buffers { bool init() { return true; } }
int main() {
    using namespace shared_memory;
    assert(configure_buffer_backend({(usize)memory.size(),available,read,write,nullptr}));
    {
        picocalc::SourceDocument document;
        std::string expected(64000,'A');
        for(unsigned i=0;i<expected.size();++i) expected[i]=(char)('A'+i%26);
        for(unsigned i=70;i<expected.size();i+=71) expected[i]='\n';
        assert(document.load({&expected,input,(u16)expected.size()}));
        u16 cursor=511;
        assert(document.replace(cursor,cursor,"FIRST",cursor));expected.insert(511,"FIRST");
        equal(document,expected);
        // A write failing partway through the first full draft must not
        // publish that partial bank or lose the current, unsaved SRAM edit.
        writes_before_failure=5;cursor=50000;
        assert(!document.replace(cursor,cursor,"LATE",cursor));
        writes_before_failure=-1;equal(document,expected);
        assert(document.replace(cursor,cursor,"LATE",cursor));expected.insert(50000,"LATE");
        equal(document,expected);
        // Repeat after a bank map has already been committed.
        writes_before_failure=3;cursor=10;
        assert(!document.replace(cursor,cursor,"EARLY",cursor));
        writes_before_failure=-1;equal(document,expected);
        assert(document.replace(cursor,cursor,"EARLY",cursor));expected.insert(10,"EARLY");
        equal(document,expected);
        fail_read=true;
        assert(!document.park());
        fail_read=false;equal(document,expected);
        // Input failure, independently of output writes, preserves the owner.
        assert(!document.load({nullptr,[](void*,u16 at,u8* out,u16 n) {
            if(at>=512) return false;std::memset(out,'Z',n);return true;
        },1024}));
        equal(document,expected);
        assert(document.park());equal(document,expected);
        assert(document.statistics().window_bytes==0 && document.statistics().sram_bytes<1024);
        // Seeking reads a line prefix and then the next edit window. A read
        // failing after either has started must retain the previous window.
        cursor=4000;const char same[]={expected[cursor],0};
        assert(document.replace(cursor,(u16)(cursor+1),same,cursor));
        reads_before_failure=2;cursor=50000;
        assert(!document.replace(cursor,cursor,"SEEK",cursor));
        reads_before_failure=-1;equal(document,expected);
        assert(document.replace(cursor,cursor,"SEEK",cursor));expected.insert(50000,"SEEK");
        equal(document,expected);
        assert(buffer_statistics().internal_used==0);
        assert(validate_buffer_invariants());
    }
    assert(!buffer_statistics().active && !buffer_statistics().external_used);
    std::puts("Pico source fault recovery: partial bank writes/seek reads, retained unsaved edits, failed replacement, bounded SRAM and owner cleanup PASS");
}
