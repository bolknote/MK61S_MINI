#include "app_flow_transfer.hpp"
#include "workspace_swap.hpp"
#include <string.h>

namespace app_flow {
using loadable_module::RuntimeStatus;
RuntimeStatus Transfer::reserve(ImageTransfer& p) {
  if(!p.size || p.image || reserved_size_ || p.size > shared_memory::WORKSPACE_SIZE)
    return RuntimeStatus::CORRUPT_MODULE;
#if MK61_SCREEN_BUFFER_LOAN
  if(screen_.acquire(p.size)) p.image = screen_.data();
#endif
#if MK61_OVERLAY_LANGUAGE_VM && MK61_ENABLE_USB_SCREEN
  if(!p.image && shared_memory::active_owner(shared_memory::Arena::OVERLAY) ==
                 shared_memory::Owner::USB_SCREEN) {
    if(!usb_staging_.acquire(shared_memory::Owner::LOADABLE_MODULE, p.size))
      return RuntimeStatus::BUSY;
    p.image = usb_staging_.data();
  }
#endif
  if(!p.image) {
    // The previous APP/source must not be evicted during output reservation.
    if(((p.size + 7U) & ~7U) > shared_memory::capacity(shared_memory::Arena::OVERLAY) ||
       !staging_.acquire(shared_memory::Arena::OVERLAY,
                         shared_memory::Owner::LOADABLE_MODULE, p.size)) return RuntimeStatus::BUSY;
    p.image = staging_.data();
  }
  reserved_size_ = p.size;
  return RuntimeStatus::OK;
}
RuntimeStatus Transfer::commit(ImageTransfer& p) {
  bool owned = staging_.ok() && p.image == staging_.data() && p.size <= staging_.size();
#if MK61_OVERLAY_LANGUAGE_VM && MK61_ENABLE_USB_SCREEN
  owned = owned || (usb_staging_.ok() && p.image == usb_staging_.data() && p.size <= usb_staging_.size());
#endif
#if MK61_SCREEN_BUFFER_LOAN
  owned = owned || (screen_.ok() && p.image == screen_.data());
#endif
  if(!owned || !p.size || p.size != reserved_size_ ||
     p.prefix >= shared_memory::capacity(shared_memory::Arena::WORKSPACE))
    return RuntimeStatus::CORRUPT_MODULE;
  const auto evicted = loadable_module::evict_cached();
  if(evicted != RuntimeStatus::OK) return evicted;
  if(!workspace_swap::acquire(owner_, shared_memory::capacity(shared_memory::Arena::WORKSPACE),
      workspace_swap::AcquireMode::REQUIRED, workspace_)) return RuntimeStatus::BUSY;
  p.workspace = workspace_.data(); p.workspace_size = workspace_.size();
  if(p.size <= p.workspace_size - p.prefix) {
    u8* destination = p.workspace + p.prefix;
    memcpy(destination, p.image, p.size); p.image = destination;
    staging_.reset();
#if MK61_OVERLAY_LANGUAGE_VM && MK61_ENABLE_USB_SCREEN
    usb_staging_.reset();
#endif
#if MK61_SCREEN_BUFFER_LOAN
    screen_.reset();
#endif
  } else {
#if MK61_SCREEN_BUFFER_LOAN
    if(screen_.ok()) return RuntimeStatus::BUSY; // Never retain a framebuffer into UI/RUN.
#endif
    if(staging_.ok() && !staging_.shrink_to(p.size)) return RuntimeStatus::BUSY;
  }
  return RuntimeStatus::OK;
}
}
