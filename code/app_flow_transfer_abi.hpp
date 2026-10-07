#ifndef MK61_APP_FLOW_TRANSFER_ABI_HPP
#define MK61_APP_FLOW_TRANSFER_ABI_HPP
#include "app_flow.hpp"
namespace app_flow {
// Operations are local to a caller's scoped HOST service, not global syscall
// numbers. APP keeps only this data plan; leases stay in the native binding.
enum TransferOperation : uint32_t { RESERVE_IMAGE = 0x100, COMMIT_IMAGE = 0x101 };
struct ImageTransfer {
  uint32_t size, prefix;
  uint8_t* image;
  uint8_t* workspace;
  uint32_t workspace_size;
  Target next;
};
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(ImageTransfer) == 28, "image transfer ARM layout changed");
#endif
}
#endif
