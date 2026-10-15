#include "storage_workspace.hpp"
#if MK61_STORAGE_SHARED_TEMP
namespace storage_workspace {
namespace {
#if MK61_SCOPED_RESIDENT_BUFFERS
static shared_memory::LifetimeBuffer bytes;
static u8* stack_storage;
#if defined(ARDUINO_ARCH_STM32)
static_assert(SIZE == 1536, "update scoped filesystem ELF reserve");
__asm__(".global mk61_storage_workspace_bytes\n.set mk61_storage_workspace_bytes, 1536");
#endif
#else
alignas(8) u8 bytes[SIZE];
#endif
u8 active_owners;
bool interrupt_context() {
#if defined(__arm__) || defined(__thumb__)
  u32 ipsr;
  __asm__ volatile ("mrs %0, ipsr" : "=r" (ipsr));
  return ipsr != 0;
#else
  return false;
#endif
}
}
#if MK61_SCOPED_RESIDENT_BUFFERS
namespace {
struct BufferRequest {
  Owner owner;
  usize size;
  BufferOperation operation;
  const void* context;
  mutable bool acquired;
};
static bool invoke_buffer(const void* opaque) {
  const auto& request = *static_cast<const BufferRequest*>(opaque);
  Lease memory(request.owner, request.size);
  request.acquired = memory.ok();
  return request.acquired && request.operation(request.context, memory.data());
}
__attribute__((noinline))
static bool run_with_stack(const BufferRequest& request) {
  alignas(8) u8 storage[SIZE];
  struct Clear {
    ~Clear() {
      if(active_owners) __builtin_trap();
      stack_storage = nullptr;
    }
  } clear;
  stack_storage = storage;
  return invoke_buffer(&request);
}
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline, noclone))
#endif
bool with_buffer(Owner owner, usize required, BufferOperation operation,
                 const void* context) {
  if(!operation || !required || required > SIZE || interrupt_context()) return false;
  const BufferRequest request = {owner, required, operation, context, false};
  const bool result = invoke_buffer(&request);
  // A failed operation must never run twice: retry only a failed lease.
  if(request.acquired) return result;
  if(active_owners || stack_storage || bytes.ok()) return false;
  return run_with_stack(request);
}
#endif

Lease::Lease(Owner owner, usize required) : owner_(Owner::NONE) {
  usize capacity = SIZE;
  u8 conflicts = 7;
  switch(owner) {
    case Owner::FILE_WRITE: capacity = WRITE_BYTES; conflicts = 3; break;
    case Owner::IMPORT_BATCH: capacity = BATCH_BYTES; conflicts = 6; break;
    case Owner::SIDECAR_SCAN: break;
    default: return;
  }
  if(!required || required > capacity || (active_owners & conflicts) ||
     interrupt_context()) return;
#if MK61_SCOPED_RESIDENT_BUFFERS
  if(!active_owners && !stack_storage &&
     !bytes.acquire(shared_memory::Owner::STORAGE_WORKSPACE, SIZE)) return;
#endif
  active_owners |= static_cast<u8>(owner);
  owner_ = owner;
}
Lease::~Lease() {
  if(owner_ == Owner::NONE) return;
  const u8 bit = static_cast<u8>(owner_);
  if(!(active_owners & bit)) __builtin_trap();
  active_owners &= static_cast<u8>(~bit);
#if MK61_SCOPED_RESIDENT_BUFFERS
  if(!active_owners) bytes.reset();
#endif
}
u8* Lease::data() const {
  if(owner_ == Owner::NONE || !(active_owners & static_cast<u8>(owner_))) return nullptr;
#if MK61_SCOPED_RESIDENT_BUFFERS
  u8* const memory = stack_storage ? stack_storage : bytes.data();
#else
  u8* const memory = bytes;
#endif
  return memory + (owner_ == Owner::IMPORT_BATCH ? WRITE_BYTES : 0);
}
}
#endif
