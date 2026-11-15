#include "loadable_buffer_services.hpp"
#include <cassert>
#include <cstring>
#include <new>

namespace {
constexpr usize CAPACITY=2U*1024U*1024U;
u8 external[CAPACITY];
alignas(loadable_buffers::Session) u8 storage[sizeof(loadable_buffers::Session)];
loadable_buffers::Session* session=nullptr;
}
extern "C" void aw_test_buffers_begin() {
    assert(!session);
    assert(shared_memory::configure_buffer_backend({CAPACITY,[] { return true; },
        [](u32 at,void* out,usize n) { if(at>CAPACITY || n>CAPACITY-at) return false;std::memcpy(out,external+at,n);return true; },
        [](u32 at,const void* in,usize n) { if(at>CAPACITY || n>CAPACITY-at) return false;std::memcpy(external+at,in,n);return true; },
        nullptr}));
    session=new(storage) loadable_buffers::Session;
}
extern "C" unsigned aw_test_buffers_call(unsigned op,mk61_service_buffer* request) {
    return session && request && session->call(op,*request);
}
extern "C" void aw_test_buffers_end() {
    assert(session);
    const auto stats=session->statistics();
    assert(!stats.count && !stats.bytes && !stats.external_bytes && !stats.windows && !stats.arena_bytes);
    session->~Session();session=nullptr;
    const auto total=shared_memory::buffer_statistics();
    assert(!total.active && !total.internal_used && !total.external_used && !total.pinned &&
           shared_memory::validate_buffer_invariants());
    assert(shared_memory::configure_buffer_backend({}));
}
