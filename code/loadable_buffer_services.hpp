#ifndef MK61_LOADABLE_BUFFER_SERVICES_HPP
#define MK61_LOADABLE_BUFFER_SERVICES_HPP
#include "loadable_app_services.h"
#include "shared_memory_buffer.hpp"
#include <cstring>
namespace loadable_buffers {
// Never reuse a token, including across APP returns. Exhaustion is a clean
// allocation failure instead of aliasing an old application's handle.
inline u32 token() { static u32 sequence=0;return sequence==UINT32_MAX?0:++sequence; }
class Session {
    struct Slot { shared_memory::Buffer buffer;u32 handle=0; } slots_[4];
    struct Window { shared_memory::BufferWindow window;u32 handle=0; } windows_[2];
    Slot* find(u32 handle) {
        for(auto& s:slots_) if(handle && s.handle==handle) return &s;
        return nullptr;
    }
    Window* window(u32 handle) {
        for(auto& s:windows_) if(handle && s.handle==handle) return &s;
        return nullptr;
    }
public:
    Session()=default;
    Session(const Session&)=delete;
    Session& operator=(const Session&)=delete;
    // Window members are destroyed before slots, so even a misbehaving APP
    // returning with live windows releases its pins and all allocations.
    bool call(u32 operation,mk61_service_buffer& r) {
        using namespace shared_memory;
        if(operation==MK61_BUFFER_ACQUIRE) {
            if(r.handle || !r.size || r.access>MK61_BUFFER_EXTERNAL) return false;
            for(auto& s:slots_) if(!s.handle) {
                const auto id=token();
                if(!id || !s.buffer.acquire(Owner::APPLICATION,r.size,(BufferAccess)r.access)) return false;
                s.handle=id;r.handle=id;r.storage=(u32)s.buffer.storage();r.data=s.buffer.data();return true;
            }
            return false;
        }
        if(operation==MK61_BUFFER_WINDOW_COMMIT || operation==MK61_BUFFER_WINDOW_CLOSE) {
            auto* w=window(r.window);if(!w) return false;
            if(operation==MK61_BUFFER_WINDOW_COMMIT) return w->window.writeback();
            w->window.reset();w->handle=0;r.window=0;r.data=nullptr;return true;
        }
        auto* s=find(r.handle);if(!s) return false;
        if(operation==MK61_BUFFER_RELEASE) {
            if(!s->buffer.reset()) return false;
            s->handle=0;r={};return true;
        }
        if(!s->buffer.ok()) return false;
        if(operation==MK61_BUFFER_INFO) {
            r.size=s->buffer.size();r.storage=(u32)s->buffer.storage();r.data=s->buffer.data();return true;
        }
        if(r.offset>s->buffer.size() || r.size>s->buffer.size()-r.offset || r.size>MK61_BUFFER_IO_BYTES) return false;
        if(operation==MK61_BUFFER_READ) return s->buffer.read(r.offset,r.data,r.size);
        if(operation==MK61_BUFFER_WRITE) return s->buffer.write(r.offset,r.data,r.size);
        if(operation==MK61_BUFFER_FILL) {
            if(r.flags>255) return false;
            u8 bytes[128];std::memset(bytes,(u8)r.flags,sizeof(bytes));
            for(u32 at=0;at<r.size;) {
                const u32 n=r.size-at<sizeof(bytes)?r.size-at:sizeof(bytes);
                if(!s->buffer.write(r.offset+at,bytes,n)) return false;
                at+=n;
            }
            return true;
        }
        if(operation==MK61_BUFFER_WINDOW_OPEN) {
            if(r.window || (r.flags&~MK61_BUFFER_WINDOW_WRITABLE)) return false;
            for(auto& w:windows_) if(!w.handle) {
                const auto id=token();
                if(!id || !w.window.acquire(s->buffer,r.offset,r.size,r.flags&MK61_BUFFER_WINDOW_WRITABLE)) return false;
                w.handle=id;r.window=id;r.data=w.window.data();return true;
            }
        }
        return false;
    }
};
}
#endif
