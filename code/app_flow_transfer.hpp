#ifndef MK61_APP_FLOW_TRANSFER_HPP
#define MK61_APP_FLOW_TRANSFER_HPP
#include "config.h"
#include "shared_memory.hpp"
#include "loadable_module_runtime.hpp"
#include "app_flow_transfer_abi.hpp"
#if MK61_SCREEN_BUFFER_LOAN
#include "display_buffer_loan.hpp"
#endif

namespace app_flow {
class Transfer {
 public:
  explicit Transfer(shared_memory::Owner owner) : owner_(owner) {}
  loadable_module::RuntimeStatus reserve(ImageTransfer&);
  loadable_module::RuntimeStatus commit(ImageTransfer&);
  loadable_module::RuntimeStatus commit_paged(ImageTransfer&);
  // The caller separately owns and pins this immutable image (e.g. a cache
  // reservation). Only the runtime workspace is acquired here, no copy.
  // A source/compiler APP must be evicted before its workspace is reused.
  // A data-only cache APP releases its Buffer on return and may stay hot.
  loadable_module::RuntimeStatus retain_image(ImageTransfer&, bool evict = true);
  // A retained-image rollback must release the VM prefix before the compiler
  // reacquires it under its own owner. The caller separately releases image.
  void release_workspace() { workspace_.reset(); }
  // Warm execution borrows this same scoped lease without evicting the hot
  // APP. Do not keep a second workspace lease alive alongside the transfer.
  shared_memory::Lease& workspace_lease() { return workspace_; }
 private:
  shared_memory::Owner owner_;
  uint32_t reserved_size_ = 0;
  shared_memory::Lease workspace_, staging_;
#if MK61_OVERLAY_LANGUAGE_VM && MK61_ENABLE_USB_SCREEN
  shared_memory::OverlayBuffer usb_staging_;
#endif
#if MK61_SCREEN_BUFFER_LOAN
  DisplayBufferLoan screen_;
#endif
};
}
#endif
