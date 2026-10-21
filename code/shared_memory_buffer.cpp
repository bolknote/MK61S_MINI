#include "shared_memory_buffer.hpp"
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <limits>

namespace shared_memory {
namespace {
BufferBackend backend{};
Buffer* internal = nullptr;
Buffer* external = nullptr;
BufferStatistics counters{};
u32 next_generation = 0;
bool transitioning = false;
constexpr usize ALIGNMENT = 32;
bool foreground() {
#if defined(__arm__) || defined(__thumb__)
  u32 ipsr; __asm__ volatile("mrs %0, ipsr" : "=r"(ipsr));
  if(ipsr) return false;
#endif
  return !backend.foreground || backend.foreground();
}
bool available() {
  return backend.capacity && backend.available && backend.available() && backend.read && backend.write;
}
void increment(u32& value) { if(value != UINT32_MAX) ++value; }
bool range(usize capacity, usize offset, const void* bytes, usize count) {
  return offset <= capacity && count <= capacity - offset && (bytes || !count);
}
}
bool configure_buffer_backend(const BufferBackend& value) {
  if(!foreground() || transitioning || internal || external ||
     (value.foreground && !value.foreground()) ||
     value.capacity > UINT32_MAX || (value.capacity && (!value.available || !value.read || !value.write))) return false;
  backend = value;
  return true;
}
u32 Buffer::gap(usize size) {
  usize at = 0;
  for(Buffer* p = external; p; p = p->next_) {
    if(size <= p->address_ - at) return (u32)at;
    at = p->address_ + p->reserved_;
  }
  return at <= backend.capacity && size <= backend.capacity - at ? (u32)at : UINT32_MAX;
}
bool Buffer::reclaim_one() {
  for(Buffer* p = external; p; p = p->next_) {
    if(!p->eviction_ || p->pins_) continue;
    transitioning = true;
    const auto decision = p->eviction_();
    if(decision == EvictionDecision::RELEASE) p->release_impl();
    transitioning = false;
    if(decision == EvictionDecision::RELEASE) { increment(counters.reclaims); return true; }
  }
  return false;
}
bool Buffer::acquire(Owner owner, usize size, BufferAccess access) {
  return acquire_impl(owner, size, access, nullptr);
}
bool Buffer::acquire_cache(Owner owner, usize size, EvictionPrepare prepare) {
  if(!prepare) return false;
  return acquire_impl(owner, size, BufferAccess::EXTERNAL_ONLY, prepare);
}
bool Buffer::acquire_impl(Owner owner, usize size, BufferAccess access, EvictionPrepare prepare) {
  if(!foreground() || transitioning || !size || owner == Owner::NONE || owner >= Owner::COUNT ||
     access > BufferAccess::EXTERNAL_ONLY || size > std::numeric_limits<usize>::max() - (ALIGNMENT - 1)) {
    increment(counters.failures); return false;
  }
  if(storage_ != BufferStorage::NONE)
    return ok() && owner_ == owner && size <= size_ && eviction_ == prepare &&
      (access != BufferAccess::DIRECT || data()) &&
      (access != BufferAccess::EXTERNAL_ONLY || storage_ == BufferStorage::EXTERNAL_DEVICE);
  const usize reserved = (size + ALIGNMENT - 1) & ~(ALIGNMENT - 1);
  u32 at = UINT32_MAX;
  if(access != BufferAccess::DIRECT && available() && reserved <= backend.capacity) {
    at = gap(reserved);
    while(at == UINT32_MAX && !prepare && reclaim_one()) at = gap(reserved);
  }
  if(at != UINT32_MAX) {
    address_ = at; storage_ = BufferStorage::EXTERNAL_DEVICE;
    Buffer** link = &external;
    while(*link && (*link)->address_ < at) link = &(*link)->next_;
    next_ = *link; *link = this;
    counters.external_used += reserved; ++counters.external_active;
    if(counters.external_used > counters.external_high_water) counters.external_high_water = counters.external_used;
  } else {
    if(access == BufferAccess::EXTERNAL_ONLY || prepare || !(memory_ = (u8*)std::malloc(size))) {
      increment(counters.failures); return false;
    }
    storage_ = BufferStorage::INTERNAL; next_ = internal; internal = this;
    counters.internal_used += size;
    if(counters.internal_used > counters.internal_high_water) counters.internal_high_water = counters.internal_used;
  }
  size_ = size; reserved_ = reserved; owner_ = owner; eviction_ = prepare;
  if(!++next_generation) ++next_generation;
  generation_ = next_generation;
  ++counters.active; increment(counters.acquisitions);
  return true;
}
bool Buffer::ok() const {
  return storage_ == BufferStorage::INTERNAL || (storage_ == BufferStorage::EXTERNAL_DEVICE && available());
}
void Buffer::release_impl() {
  if(storage_ == BufferStorage::NONE) return;
  Buffer** link = storage_ == BufferStorage::EXTERNAL_DEVICE ? &external : &internal;
  while(*link && *link != this) link = &(*link)->next_;
  if(*link != this) __builtin_trap();
  *link = next_;
  if(storage_ == BufferStorage::EXTERNAL_DEVICE) {
    counters.external_used -= reserved_; --counters.external_active;
  } else {
    counters.internal_used -= size_; std::free(memory_);
  }
  --counters.active; increment(counters.releases);
  memory_ = nullptr; next_ = nullptr; eviction_ = nullptr;
  size_ = reserved_ = 0; address_ = generation_ = 0; pins_ = 0;
  owner_ = Owner::NONE; storage_ = BufferStorage::NONE;
}
bool Buffer::reset() {
  if(storage_ == BufferStorage::NONE) return true;
  if(!foreground() || transitioning || pins_) return false;
  release_impl(); return true;
}
Buffer::~Buffer() { if(!reset()) __builtin_trap(); }
bool Buffer::read(usize offset, void* bytes, usize count) const {
  if(!foreground() || transitioning || !ok() || !range(size_, offset, bytes, count)) return false;
  if(!count) return true;
  if(data()) { std::memmove(bytes, data() + offset, count); return true; }
  const bool result = backend.read(address_ + (u32)offset, bytes, count);
  if(!result) increment(counters.io_errors);
  return result;
}
bool Buffer::write(usize offset, const void* bytes, usize count) {
  if(!foreground() || transitioning || !ok() || !range(size_, offset, bytes, count)) return false;
  if(!count) return true;
  if(data()) { std::memmove(data() + offset, bytes, count); return true; }
  const bool result = backend.write(address_ + (u32)offset, bytes, count);
  if(!result) increment(counters.io_errors);
  return result;
}
bool Buffer::fill(u8 value) {
  if(!foreground() || transitioning || !ok()) return false;
  if(data()) { std::memset(data(), value, size_); return true; }
  u8 bytes[128]; std::memset(bytes, value, sizeof(bytes));
  for(usize at = 0; at < size_;) {
    const usize n = size_ - at < sizeof(bytes) ? size_ - at : sizeof(bytes);
    if(!write(at, bytes, n)) return false;
    at += n;
  }
  return true;
}
bool BufferWindow::acquire(Buffer& parent, usize offset, usize size, bool writable) {
  if(parent_ || !foreground() || transitioning || !parent.ok() || !size ||
     offset > parent.size_ || size > parent.size_ - offset || parent.pins_ == UINT32_MAX) return false;
  ++parent.pins_; ++counters.pinned;
  if(!staging_.acquire(parent.owner_, size) || !parent.read(offset, staging_.data(), size)) {
    staging_.reset(); --parent.pins_; --counters.pinned; return false;
  } else bytes_ = staging_.data();
  parent_ = &parent; offset_ = offset; size_ = size;
  generation_ = parent.generation_; writable_ = writable;
  return true;
}
bool BufferWindow::writeback() {
  if(!parent_ || !writable_ || generation_ != parent_->generation_) return false;
  return parent_->write(offset_, bytes_, size_);
}
void BufferWindow::reset() {
  if(!parent_) return;
  if(!foreground() || transitioning || parent_->generation_ != generation_ || !parent_->pins_) __builtin_trap();
  --parent_->pins_; --counters.pinned;
  parent_ = nullptr; bytes_ = nullptr; offset_ = size_ = 0; generation_ = 0; writable_ = false;
  if(!staging_.reset()) __builtin_trap();
}
BufferWindow::~BufferWindow() { reset(); }
BufferStatistics buffer_statistics() {
  auto result = counters;
  result.external_capacity = available() ? backend.capacity : 0;
  usize at = 0;
  for(Buffer* p = external; p; p = p->next_) {
    const usize gap = p->address_ - at;
    if(gap > result.external_largest) result.external_largest = gap;
    at = p->address_ + p->reserved_;
  }
  if(at <= backend.capacity && backend.capacity - at > result.external_largest)
    result.external_largest = backend.capacity - at;
  if(!result.external_capacity) result.external_largest = 0;
  return result;
}
bool validate_buffer_invariants() {
  usize internal_used = 0, external_used = 0, at = 0;
  u32 active = 0, external_active = 0, pinned = 0;
  for(Buffer* p = internal; p; p = p->next_) {
    if(++active > counters.active || !p->memory_ || !p->size_ || !p->generation_ ||
       p->storage_ != BufferStorage::INTERNAL || p->owner_ == Owner::NONE || p->owner_ >= Owner::COUNT) return false;
    internal_used += p->size_; pinned += p->pins_;
  }
  for(Buffer* p = external; p; p = p->next_) {
    if(++active > counters.active || p->memory_ || !p->size_ || !p->generation_ ||
       p->storage_ != BufferStorage::EXTERNAL_DEVICE || p->owner_ == Owner::NONE || p->owner_ >= Owner::COUNT ||
       p->address_ < at || (p->address_ & (ALIGNMENT-1)) || p->size_ > p->reserved_ ||
       p->reserved_ > backend.capacity || p->address_ > backend.capacity - p->reserved_) return false;
    at = p->address_ + p->reserved_; external_used += p->reserved_; pinned += p->pins_; ++external_active;
  }
  return internal_used == counters.internal_used && external_used == counters.external_used &&
    active == counters.active && external_active == counters.external_active && pinned == counters.pinned;
}
} // namespace shared_memory
