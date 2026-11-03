#include "loadable_module_format.hpp"
#include "loadable_system_api.h"
#include "shared_memory.hpp"
#include "explorer_view.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <new>
using Kind = loadable_module::Kind;
namespace backend {
alignas(16) u8 bytes[8192];
bool busy = false;
unsigned acquisitions = 0, releases = 0;
shared_memory::Owner last = shared_memory::Owner::NONE;
}
namespace language_workspace {
using Owner = shared_memory::Owner;
class Lease {
  bool held_;
  u32 size_;
 public:
  Lease(Owner value, u32 size) : held_(!backend::busy && size <= sizeof(backend::bytes)), size_(size) {
    backend::last = value;
    if(held_) { backend::busy = true; ++backend::acquisitions; }
  }
  ~Lease() { if(held_) { backend::busy = false; ++backend::releases; } }
  bool ok() const { return held_; }
  void* data() const { return held_ ? backend::bytes : nullptr; }
  u32 size() const { return size_; }
  bool fresh() const { return false; }
};
}
namespace shared_scratch {
enum class Owner { APPLICATION, USB_CACHE, MARKDOWN_VIEWER, IMAGE_VIEWER };
class Lease {
 public:
  Lease(Owner,u32) {}
  bool ok() const { return false; }
  u8* data() const { return nullptr; }
  u32 size() const { return 0; }
};
}
namespace usb_mass_storage { void note_startup_stage(u32) {} }
static_assert(sizeof(language_workspace::Lease) <= MK61_SYSTEM_LEASE_BYTES);
static u32 workspace_image_crc[(u8)Kind::EXPLORER + 1U];
#include "explorer_memory_owner.inc"
#include "explorer_workspace_layout.inc"
u32 service(u32 op,u32 a,u32 b,u32 c,void* payload) {
  switch(op) {
#include "explorer_memory_cases.inc"
    default: return 0;
  }
}
int main() {
  constexpr u32 kind = (u32)Kind::EXPLORER;
  static_assert(sizeof(Workspace) <= shared_memory::WORKSPACE_SIZE);
  mk61_system_lease lease{}; lease.image_crc = 0x12345678;
  if(service(MK61_SYS_MEMORY_ACQUIRE,0,kind,sizeof(Workspace),&lease)!=1) {
    std::fputs("Explorer workspace was rejected by the production dispatcher\n",stderr);
    return 2;
  }
  assert(backend::last==shared_memory::Owner::IMAGE_VIEWER);
  assert(lease.data==backend::bytes && lease.size>=sizeof(Workspace) && lease.fresh==1);
  std::memset(lease.data,0xA5,sizeof(Workspace));
  assert(service(MK61_SYS_MEMORY_RELEASE,0,0,0,&lease)==1);
  assert(!lease.data && lease.size==0 && !backend::busy && backend::releases==1);
  assert(service(MK61_SYS_MEMORY_RELEASE,0,0,0,&lease)==0);
  assert(service(MK61_SYS_MEMORY_ACQUIRE,0,kind,sizeof(Workspace),&lease)==1 && lease.fresh==0);
  assert(service(MK61_SYS_MEMORY_RELEASE,0,0,0,&lease)==1);
  lease.image_crc++;
  assert(service(MK61_SYS_MEMORY_ACQUIRE,0,kind,sizeof(Workspace),&lease)==1 && lease.fresh==1);
  assert(service(MK61_SYS_MEMORY_RELEASE,0,0,0,&lease)==1);
  const auto calls=backend::acquisitions;
  backend::busy=true;
  assert(service(MK61_SYS_MEMORY_ACQUIRE,0,kind,sizeof(Workspace),&lease)==0);
  assert(backend::busy && !lease.data && backend::acquisitions==calls);
  backend::busy=false;
  assert(service(MK61_SYS_MEMORY_ACQUIRE,0,kind,sizeof(backend::bytes)+1,&lease)==0);
  assert(!backend::busy && !lease.data);
  assert(service(MK61_SYS_MEMORY_ACQUIRE,1,kind,100,&lease)==0);
  assert(service(MK61_SYS_MEMORY_ACQUIRE,0,0xFF,100,&lease)==0);
  assert(service(MK61_SYS_MEMORY_ACQUIRE,0,kind,100,nullptr)==0);
  assert(service(MK61_SYS_MEMORY_RELEASE,0,0,0,nullptr)==0);
  std::printf("Explorer production dispatcher: workspace=%zu/8192, owner/acquire/release/fresh/busy/invalid/cleanup PASS\n",sizeof(Workspace));
}
